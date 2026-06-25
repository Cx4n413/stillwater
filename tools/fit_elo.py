"""Maximum-likelihood Elo fit over all match PGNs -- CCRL 40/15 placement.

Goal: place STILLWATER (SW) on the CCRL 40/15 (1-CPU) scale.

ANCHORS are FIXED to CCRL 40/15 ratings:
  - Caissa 1.23  and  Starzix 6.0   (real engines, downloaded; CCRL list rows)
  - the SF18 node rung that is pinned to N0 (== SF18's own CCRL rating)
SW is FREE. Intermediate SF18 node rungs are LEFT FREE and are identified by
the inline SF18-vs-SF18 self-play bridge games plus the fixed anchors -- per
the placement plan, only the N0 rung is hard-pinned; the lower rungs are
"loosely pinned" and so float, anchored through the bridge slope.

Draws count as half a point (Bernoulli mean-matching gradient MLE).
Exact-duplicate games collapse (a deterministic node-limited tier replaying
the same game N times carries one game of information, not N).

CONFIDENCE INTERVAL: bootstrap over games, but when games arrive as
color-reversed PAIRS from the SAME opening line (cutechess -repeat), resample
by PAIR and score the pair as a PENTANOMIAL outcome in {0,0.5,1,1.5,2}. This
removes the within-pair (opening-line) variance and shrinks SW's CI relative
to naive per-game resampling. Unpaired games are resampled individually.

The ANCHORS keys MUST match the EXACT cutechess `-engine name=` strings the
harness writes into the PGN [White]/[Black] tags. A startup assertion fails
loudly if a declared anchor never appears in the parsed games (otherwise it
would silently free-float at the 3200 init and corrupt the scale).

Run:
  python tools/fit_elo.py games/placement_preflight.pgn \
      games/placement_scout.pgn games/placement_concentrate.pgn \
      games/calibrate_slope.pgn games/calibrate_pin.pgn
"""

import math
import random
import re
import sys

# ---------------------------------------------------------------------------
# FIXED anchors on the CCRL 40/15 (1-CPU) scale. Keys = exact cutechess
# `-engine name=` strings. SW is intentionally NOT here (it is the free
# parameter we are solving for). Lower SF18 node rungs are intentionally NOT
# here either -- they float and are pinned through the bridge slope + these
# fixed anchors (the plan calls them only "loosely pinned").
#
# SF18-N0 is the node rung empirically solved so SF18@N0 == its CCRL rating;
# the harness names that engine "SF18-N0".
#
# >>> SCALE FRAME (RESOLVED 2026-06-13 from the ACTUAL CCRL 40/15 list rows):
# Report SW on the CCRL 40/15 STANDARD **1-CPU** frame. The list has separate
# 1-CPU and 4CPU rows; we run Threads=1, so we pin to the 1-CPU rows:
#   Stockfish 18 64-bit        = 3627   (1-CPU)   <-- OUR PIN
#   Stockfish 18 64-bit 4CPU   = 3651   (do NOT use; 4-core, +24 over 1-CPU)
#   SF17.1 1CPU 3623 / SF17 1CPU 3619 / SF14 1CPU 3573 / SF13 1CPU 3572
#   Stockfish 10 64-bit        = 3445   (1-CPU; CCRL's TC-normalization engine)
# The SF-version 1-CPU ladder above is a same-frame cross-check and is
# POOL-calibrated (vs many engines) -> sound to anchor to (NOT self-test
# inflation). The ~4000+ numbers were the CCRL 40/15 FRC/Chess960 list, NOT this.
# ---------------------------------------------------------------------------
ANCHORS = {
    # --- SAME-LEVEL DIRECT ANCHORING (CCRL 40/15 STANDARD 1-CPU frame) ---
    # Keys MUST match the cutechess `-engine name=` strings in
    # tools/ccrl_samelevel.cmd EXACTLY. These are classical / pre-NNUE Stockfish
    # versions whose PUBLISHED CCRL 40/15 1-CPU ratings BRACKET SW's ~3350. They
    # are normalized by ONE clock factor S (from the SF10 bench) -- exactly CCRL's
    # own SF10-based per-machine normalization -- so anchoring SW directly to them
    # is fully self-consistent. The old NNUE SF18-N0 pin and the ~3600 Caissa /
    # Starzix ladder cross-checks are DROPPED: mixing the NNUE-vs-classical profile
    # gap (and the failed-ladder slope) back in would re-introduce ~+/-20-40 Elo
    # of systematic error (adversarial guard a2).
    "SF-DD": 3210.0,   # Stockfish DD (4.5) 64-bit -- below SW
    "SF7":   3303.0,   # Stockfish 7 64-bit         -- below SW
    "SF8":   3362.0,   # Stockfish 8 64-bit         -- tight lower straddle
    "SF9":   3425.0,   # Stockfish 9 64-bit         -- tight upper straddle
    "SF10":  3447.0,   # Stockfish 10 64-bit        -- above SW (CCRL's TC-norm engine)
}

# Anchors that are expected only in some runs; absence is tolerated (warn,
# don't hard-fail) because not every PGN bundle contains the pin/cross-check
# games. The hard requirement is that NO anchor silently free-floats: an
# anchor present in ANCHORS that never appears in ANY parsed game is fatal.
SW_NAME_HINTS = ("STILLWATER", "SW")  # how SW may be named across runs

LN10_400 = math.log(10) / 400.0


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def _split_games(txt):
    """Yield (header_text, body_text) for each game in a PGN file."""
    # Split on the [Event tag that begins every game record.
    for chunk in txt.split("[Event ")[1:]:
        chunk = "[Event " + chunk
        parts = chunk.split("\n\n", 1)
        head = parts[0]
        body = parts[1] if len(parts) > 1 else ""
        yield head, body


def _tag(head, name):
    m = re.search(r'\[' + name + r' "([^"]*)"\]', head)
    return m.group(1) if m else None


def parse(paths):
    """Parse games into records. Each record:
        {file, idx, white, black, score, round, opening, fen, sig}
    score is from White's perspective (1.0/0.5/0.0).

    Exact duplicates (same players, same result, same first 40 plies) collapse
    to one. Duplicate detection is global across files.
    """
    records = []
    seen = set()
    dupes = 0
    missing = []
    for p in paths:
        try:
            txt = open(p, encoding="utf-8", errors="replace").read()
        except FileNotFoundError:
            missing.append(p)
            continue
        for i, (head, body) in enumerate(_split_games(txt)):
            w = _tag(head, "White")
            b = _tag(head, "Black")
            r = _tag(head, "Result")
            if not (w and b and r) or r not in ("1-0", "0-1", "1/2-1/2"):
                continue
            moves = re.sub(r"\{[^}]*\}", "", body)
            moves = re.sub(r"\([^)]*\)", "", moves)  # strip variations
            first_plies = " ".join(moves.split()[:40])
            sig = (w, b, r, first_plies)
            if sig in seen:
                dupes += 1
                continue
            seen.add(sig)
            score = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}[r]
            records.append({
                "file": p,
                "idx": i,
                "white": w,
                "black": b,
                "score": score,
                "round": _tag(head, "Round"),
                "opening": _tag(head, "Opening"),
                "fen": _tag(head, "FEN"),
                "moves": first_plies,
            })
    if missing:
        for p in missing:
            print(f"  (skipping missing {p})")
    if dupes:
        print(f"  ({dupes} exact-duplicate games collapsed)")
    return records


# ---------------------------------------------------------------------------
# Pentanomial pairing
# ---------------------------------------------------------------------------
def build_units(records):
    """Group records into resampling UNITS.

    A PAIR unit = two games, same source file, same opening line (same Round +
    same Opening + same starting FEN when present), with the SAME two engines
    on OPPOSITE colors (color-reversed repeat). The pair's pentanomial score is
    the total points scored by a chosen reference engine across both games,
    in {0, 0.5, 1, 1.5, 2}.

    Anything not matched into a pair becomes a SINGLE unit (one game).

    Returns a list of units. Each unit is a dict:
        {"games": [rec, ...],                  # 1 or 2 game records
         "players": (engineA, engineB)}        # unordered pair of names
    Pairing is done greedily within (file, line-key, engine-set) buckets so
    that two games on the same line with swapped colors fuse; a 2nd identical
    repeat (rare) falls through to a new pair or a single.
    """
    # Bucket key that identifies one opening line for one engine matchup,
    # scoped to a single source file so Round numbers don't collide across
    # different matches/files.
    buckets = {}
    order = []
    for rec in records:
        line_key = (rec["round"], rec["opening"], rec["fen"])
        engine_set = frozenset((rec["white"], rec["black"]))
        key = (rec["file"], line_key, engine_set)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(rec)

    units = []
    for key in order:
        bucket = buckets[key]
        # Within a bucket, fuse games into color-reversed pairs.
        # We want one game with engineX as White and the other with engineX as
        # Black. Walk the bucket and pair the first available opposite-color
        # game; leftovers become singles.
        used = [False] * len(bucket)
        for i in range(len(bucket)):
            if used[i]:
                continue
            ri = bucket[i]
            partner = None
            for j in range(i + 1, len(bucket)):
                if used[j]:
                    continue
                rj = bucket[j]
                # opposite colors for the same matchup
                if ri["white"] == rj["black"] and ri["black"] == rj["white"]:
                    partner = j
                    break
            if partner is not None:
                used[i] = True
                used[partner] = True
                units.append({
                    "games": [ri, bucket[partner]],
                    "players": tuple(sorted({ri["white"], ri["black"]})),
                })
            else:
                used[i] = True
                units.append({
                    "games": [ri],
                    "players": tuple(sorted({ri["white"], ri["black"]})),
                })
    return units


def units_to_games(units):
    """Flatten units back to per-game (white, black, score) tuples for the
    point-estimate MLE fit (which uses every game directly)."""
    out = []
    for u in units:
        for g in u["games"]:
            out.append((g["white"], g["black"], g["score"]))
    return out


def resample_units(units):
    """Bootstrap resample by UNIT (pentanomial for pairs). Returns a flat list
    of per-game (white, black, score) tuples for one bootstrap replicate.

    Resampling whole pairs preserves the {0,0.5,1,1.5,2} pentanomial outcome
    distribution and removes within-pair opening-line variance, shrinking the
    CI versus per-game resampling."""
    n = len(units)
    out = []
    for _ in range(n):
        u = units[random.randrange(n)]
        for g in u["games"]:
            out.append((g["white"], g["black"], g["score"]))
    return out


def pentanomial_summary(units):
    """For each engine matchup that has pairs, tabulate the pentanomial
    outcome counts (from the FIRST-listed player's perspective within the
    sorted pair). Diagnostic only."""
    table = {}
    for u in units:
        if len(u["games"]) != 2:
            continue
        ref = u["players"][0]  # sorted reference engine
        total = 0.0
        for g in u["games"]:
            s = g["score"] if g["white"] == ref else (1.0 - g["score"])
            total += s
        # total in {0,0.5,1,1.5,2}
        bucket = int(round(total * 2))  # 0..4
        key = u["players"]
        if key not in table:
            table[key] = [0, 0, 0, 0, 0]
        table[key][bucket] += 1
    return table


# ---------------------------------------------------------------------------
# MLE fit
# ---------------------------------------------------------------------------
def fit(games, iters=4000, lr=8.0):
    players = sorted({p for g in games for p in g[:2]})
    rating = {p: ANCHORS.get(p, 3200.0) for p in players}
    for _ in range(iters):
        grad = {p: 0.0 for p in players}
        for w, b, s in games:
            e = 1.0 / (1.0 + 10 ** (-(rating[w] - rating[b]) / 400.0))
            g = (s - e) * LN10_400
            grad[w] += g
            grad[b] -= g
        for p in players:
            if p not in ANCHORS:
                rating[p] += lr * grad[p]
    return rating


def find_sw_name(players):
    """Identify SW's player name among the parsed players. Accepts exact
    'STILLWATER' or any 'SW*' / '*SW*' label the harness used."""
    for p in players:
        if p == "STILLWATER":
            return p
    for p in players:
        up = p.upper()
        if up == "SW" or up.startswith("SW-") or up.startswith("SW_"):
            return p
    for p in players:
        if "STILLWATER" in p.upper():
            return p
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    paths = sys.argv[1:] or [
        "games/placement_preflight.pgn",
        "games/placement_scout.pgn",
        "games/placement_concentrate.pgn",
        "games/calibrate_slope.pgn",
        "games/calibrate_pin.pgn",
    ]
    records = parse(paths)
    if not records:
        print("No games parsed; nothing to fit.")
        return
    print(f"{len(records)} games parsed")

    all_players = sorted({r["white"] for r in records}
                         | {r["black"] for r in records})

    # ---- HARD assertion: no anchor may silently free-float ----------------
    present_anchors = [a for a in ANCHORS if a in all_players]
    absent_anchors = [a for a in ANCHORS if a not in all_players]
    if not present_anchors:
        raise SystemExit(
            "FATAL: none of the fixed ANCHORS "
            f"{sorted(ANCHORS)} appear in the parsed PGN player names "
            f"{all_players}. The scale would be unidentified. Fix the harness "
            "engine name= strings or the ANCHORS dict before fitting.")
    if absent_anchors:
        # An anchor declared but absent does NOT free-float (it's only used as
        # a fixed point WHEN present), but warn loudly so a typo'd name or a
        # missing cross-check file is caught.
        print(f"  WARNING: declared anchors not present in these PGNs "
              f"(not used as fixed points here): {absent_anchors}")

    sw = find_sw_name(all_players)
    if sw is None:
        print(f"  WARNING: no STILLWATER/SW player found among {all_players}; "
              "reporting all fitted ratings without an SW CI.")

    units = build_units(records)
    n_pairs = sum(1 for u in units if len(u["games"]) == 2)
    n_single = sum(1 for u in units if len(u["games"]) == 1)
    print(f"  {len(units)} resampling units "
          f"({n_pairs} color-reversed PAIRS, {n_single} singles)")

    games = units_to_games(units)
    rating = fit(games)

    # ---- pentanomial diagnostic table -------------------------------------
    pent = pentanomial_summary(units)
    if pent:
        print("\nPentanomial pair outcomes (ref = first engine, "
              "counts over {0, 0.5, 1, 1.5, 2}):")
        for (a, bname), counts in sorted(pent.items()):
            print(f"  {a} vs {bname}: {counts}")

    # ---- bootstrap CI for SW via PAIR (pentanomial) resampling ------------
    lo = hi = float("nan")
    if sw is not None:
        boots = []
        for _ in range(1000):
            sample = resample_units(units)
            r = fit(sample, iters=1500).get(sw, float("nan"))
            if not math.isnan(r):
                boots.append(r)
        if boots:
            boots.sort()
            n = len(boots)
            lo = boots[max(0, int(0.025 * n))]
            hi = boots[min(n - 1, int(0.975 * n))]

    # ---- report -----------------------------------------------------------
    print(f"\n{'player':<16} {'rating':>7}  {'games':>5}  {'score':>6}  anchor")
    by = {}
    for w, b, s in games:
        for p, sc in ((w, s), (b, 1 - s)):
            cnt, t = by.get(p, (0, 0.0))
            by[p] = (cnt + 1, t + sc)
    for p in sorted(rating, key=rating.get):
        cnt, t = by[p]
        tag = "fixed" if p in ANCHORS else ("SW" if p == sw else "fitted")
        print(f"{p:<16} {rating[p]:>7.0f}  {cnt:>5}  {100*t/cnt:>5.1f}%  {tag}")

    if sw is not None:
        half = (hi - lo) / 2.0 if not math.isnan(lo) else float("nan")
        print(f"\n{sw} maximum-likelihood CCRL 40/15 rating: "
              f"{rating[sw]:.0f}  (95% CI {lo:.0f} - {hi:.0f}, "
              f"half-width {half:.0f})")
        print("Scale: CCRL 40/15 (1-CPU), pinned via fixed anchors "
              f"{present_anchors}.")
        print("Pentanomial pair resampling used for the CI "
              f"({n_pairs} pairs, {n_single} singles).")
        if not math.isnan(half) and half > 12:
            print("  NOTE: CI half-width > 12 Elo; per the stopping rule, run "
                  "more concentrate games before declaring placement.")
    else:
        print("\n(No SW player; ratings above are the fitted scale only.)")


if __name__ == "__main__":
    main()
