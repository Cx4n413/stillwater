"""Refined loss anatomy for the ceiling match: for each SW loss, find the COLLAPSE
move (first SW move where SW's own eval crosses from >= -0.35 to <= -0.90 within
two SW moves, evals capped to +/-3 to ignore mate-scale artifacts) and report how
much TIME the court allocated to exactly that move vs SW's average. If SW blitzed
its blunders (court cut early on a settled-but-wrong belief), that is a concrete
time-management pathology: the engine loses games on moves it chose to think
LESS about.
"""
import re
import statistics as st
import sys

PGN = sys.argv[1] if len(sys.argv) > 1 else "games/lc0_ceiling.pgn"
text = open(PGN, encoding="utf-8", errors="ignore").read()
games = [g for g in re.split(r"(?=\[Event )", text) if g.startswith("[Event")]
MOVE_RE = re.compile(
    r"([a-hRNBQKO][\w=+#-]*|O-O(?:-O)?)\s*\{([+-]?[\d.]+|book|[+-]?M\d+)"
    r"(?:/(\d+))?\s*(?:([\d.]+)s)?")


def cap(e):
    return max(-3.0, min(3.0, e))


rows = []
all_sw_times = []
for g in games:
    hdrs = dict(re.findall(r'\[(\w+) "([^"]*)"\]', g))
    sw = "w" if "SW" in hdrs.get("White", "") else (
        "b" if "SW" in hdrs.get("Black", "") else None)
    if sw is None:
        continue
    res = hdrs.get("Result", "*")
    sw_lost = (res == "1-0" and sw == "b") or (res == "0-1" and sw == "w")
    body = g.split("\n\n", 1)[1] if "\n\n" in g else ""
    seq = MOVE_RE.findall(body)
    sw_moves = []   # (san, eval, time)
    for i, (mv, ev, dep, tm) in enumerate(seq):
        is_sw = ((i % 2 == 0) and sw == "w") or ((i % 2 == 1) and sw == "b")
        if not is_sw or ev == "book":
            continue
        try:
            e = cap(float(ev))
        except ValueError:
            e = 3.0 if ev.startswith("+M") else -3.0
        t = float(tm) if tm else 0.0
        sw_moves.append((mv, e, t))
        all_sw_times.append(t)
    if not sw_lost or len(sw_moves) < 6:
        continue
    # collapse = first j where eval[j] <= -0.9 and eval[j-2] >= -0.35
    col = None
    for j in range(2, len(sw_moves)):
        if sw_moves[j][1] <= -0.9 and sw_moves[j - 2][1] >= -0.35:
            col = j
            break
    if col is None:
        rows.append((hdrs.get("Round", "?"), "gradual", None, None, None))
        continue
    # the decision that did it: the SW move where eval was still ok (j-2 or j-1)
    dec = col - 2 if sw_moves[col - 1][1] <= -0.9 else col - 1
    san, e, t = sw_moves[dec]
    rows.append((hdrs.get("Round", "?"), "sharp", san, t, e))

avg_t = st.mean(all_sw_times)
print(f"SW mean time/move overall: {avg_t:.2f}s\n")
print("=== the move that lost each game (SW's last ok-eval decision) ===")
sharp = [r for r in rows if r[1] == "sharp"]
for rnd, kind, san, t, e in rows:
    if kind == "sharp":
        flag = "FAST" if t < avg_t else ("SLOW" if t > 2 * avg_t else "avg ")
        print(f"  R{rnd:>4}: {san:8} spent {t:5.2f}s ({flag})  eval-before {e:+.2f}")
    else:
        print(f"  R{rnd:>4}: gradual slide (no 2-move collapse)")
print(f"\nsharp collapses: {len(sharp)}/{len(rows)}")
if sharp:
    ts = [t for _, _, _, t, _ in sharp]
    fast = sum(1 for t in ts if t < avg_t)
    print(f"time spent on the LOSING decision: mean {st.mean(ts):.2f}s vs "
          f"overall {avg_t:.2f}s | blitzed (<avg) {fast}/{len(ts)}")
