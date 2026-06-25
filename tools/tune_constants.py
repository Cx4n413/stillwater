"""Autonomous search-constant tuner for the post-campaign engine (mask 0xBFF).

Coordinate-ascent (Gauss-Seidel) pattern search over 8 runtime tunables,
scored on the Strategic Test Suite (graded c8/c9 points). In-process: one
oracle + one RustEngine reused across every evaluation (no per-config engine
spawn). Checkpoints the best vector every eval; on the wall-clock budget it
runs a final validation (full STS + WAC) of best-vs-baseline and writes a
report. Designed to run unattended for hours.

  python tools/tune_constants.py [budget_seconds]
"""

from __future__ import annotations

import json
import os
import sys
import time

import chess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

STS = os.path.join(REPO, "games", "sts.epd")
WAC = os.path.join(REPO, "games", "wac.epd")
LOG = os.path.join(REPO, "games", "tune_log.txt")
BEST = os.path.join(REPO, "games", "tune_best.json")
REPORT = os.path.join(REPO, "games", "tune_report.txt")

NODES = 600
STRIDE = 7          # ~214 themed positions for the tuning fitness
BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 else 21600   # 6h tuning

# name, index, value, lo, hi, step
PARAMS = [
    ["lcb_k",        0, 0.30, 0.00, 0.80, 0.10],
    ["fpu_red",      1, 0.20, 0.00, 0.60, 0.08],
    ["ml_thresh",    2, 0.80, 0.40, 0.95, 0.10],
    ["cpuct_init",   3, 1.745, 0.80, 3.50, 0.30],
    ["cpuct_factor", 4, 3.894, 0.00, 8.00, 0.80],
    ["c_var",        5, 0.35, 0.00, 1.20, 0.15],
    ["vloss_w",      6, 0.85, 0.20, 2.00, 0.20],
    ["pick_k",       7, 0.50, 0.00, 1.50, 0.20],   # python-side robust pick
]
BASE = [p[2] for p in PARAMS]


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_sts(path: str, stride: int = 1):
    out = []
    for i, line in enumerate(open(path, encoding="utf-8")):
        if stride > 1 and i % stride != 0:
            continue
        line = line.strip()
        if not line:
            continue
        board = chess.Board()
        try:
            ops = board.set_epd(line)
        except Exception:
            continue
        # c9 = space-separated UCI moves; c8 = matching points
        c9 = ops.get("c9", ""); c8 = ops.get("c8", "")
        if c9 and c8:
            mv = c9.split()
            pts = [int(x) for x in c8.split()]
            pmap = {m: p for m, p in zip(mv, pts)}
        else:
            bm = ops.get("bm")
            bm = bm if isinstance(bm, list) else [bm]
            pmap = {m.uci(): 10 for m in bm if m}
        if pmap:
            out.append((board, pmap))
    return out


def load_wac(path: str, limit: int):
    out = []
    for line in open(path, encoding="utf-8"):
        b = chess.Board()
        try:
            ops = b.set_epd(line.strip())
        except Exception:
            continue
        bm = ops.get("bm")
        if not bm:
            continue
        bm = bm if isinstance(bm, list) else [bm]
        out.append((b, {m.uci() for m in bm}))
        if len(out) >= limit:
            break
    return out


def make_engine():
    from stillwater.oracle import LeelaOracle
    from stillwater.engine_rs import RustEngine
    orc = LeelaOracle()
    orc.warmup()
    eng = RustEngine(oracle=orc, batch=128, harvest_on=False, ledger_on=False)
    eng.refine_mask = 0xBFF
    eng.core.set_refine(0xBFF & 0xDFF)
    return eng


def apply(eng, v):
    eng.core.set_tunables(v[0], v[1], v[2], v[3], v[4], v[5], v[6])
    eng.pick_k = v[7]


def sts_score(eng, suite, v):
    """Graded STS points as a percentage of the achievable maximum."""
    apply(eng, v)
    got = mx = 0
    for board, pmap in suite:
        mx += max(pmap.values())
        try:
            eng.new_game()
            r = eng.think(board, node_budget=NODES)
            mv = r[0] if isinstance(r, tuple) else r
            if mv is not None:
                got += pmap.get(mv.uci(), 0)
        except Exception as ex:
            log(f"  eval error: {repr(ex)[:120]}")
    return 100.0 * got / max(1, mx)


def wac_score(eng, suite, v):
    apply(eng, v)
    n = 0
    for board, bms in suite:
        try:
            eng.new_game()
            r = eng.think(board, node_budget=NODES)
            mv = r[0] if isinstance(r, tuple) else r
            if mv is not None and mv.uci() in bms:
                n += 1
        except Exception:
            pass
    return 100.0 * n / max(1, len(suite))


def checkpoint(v, score, rounds):
    tmp = BEST + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"vector": v, "names": [p[0] for p in PARAMS],
                   "sts_subset": score, "rounds": rounds}, f, indent=1)
    os.replace(tmp, BEST)


def main() -> int:
    open(LOG, "w").close()
    log(f"tuner start: budget {BUDGET}s, nodes {NODES}")
    fit = load_sts(STS, STRIDE)
    log(f"fitness suite: {len(fit)} STS positions (stride {STRIDE})")
    try:
        eng = make_engine()
    except Exception as ex:
        log(f"FATAL engine build: {repr(ex)[:200]}")
        return 1

    t0 = time.time()
    cur = list(BASE)
    best_s = sts_score(eng, fit, cur)
    log(f"baseline STS-subset = {best_s:.2f}%")
    checkpoint(cur, best_s, 0)

    steps = {p[0]: p[5] for p in PARAMS}
    rounds = 0
    while time.time() - t0 < BUDGET:
        rounds += 1
        improved = False
        for name, idx, _v, lo, hi, _st in PARAMS:
            if time.time() - t0 >= BUDGET:
                break
            step = steps[name]
            for direction in (+1, -1):
                cand = list(cur)
                nv = cand[idx] + direction * step
                if nv < lo or nv > hi or abs(nv - cur[idx]) < 1e-9:
                    continue
                cand[idx] = round(nv, 4)
                s = sts_score(eng, fit, cand)
                if s > best_s + 1e-6:
                    log(f"  r{rounds} {name} {cur[idx]:.3f}->{cand[idx]:.3f}: "
                        f"{best_s:.2f}->{s:.2f}%  (accept)")
                    cur, best_s, improved = cand, s, True
                    checkpoint(cur, best_s, rounds)
                    break   # Gauss-Seidel: take first improving dir, next param
        if not improved:
            for k in steps:
                steps[k] *= 0.5
            log(f"  r{rounds}: no improvement, steps halved -> "
                f"{ {k: round(v,3) for k,v in steps.items()} }")
            if all(steps[p[0]] < p[5] * 0.2 for p in PARAMS):
                log("  steps below 20% of initial: converged")
                break
        log(f"round {rounds} done: best {best_s:.2f}%, "
            f"{(time.time()-t0)/60:.0f} min elapsed")

    # ---- final validation: full STS + WAC, best vs baseline (held-out signal)
    log("=== VALIDATION (full STS-1500 + WAC-300) ===")
    full = load_sts(STS, 1)
    wac = load_wac(WAC, 300)
    b_sts = sts_score(eng, full, BASE)
    n_sts = sts_score(eng, full, cur)
    b_wac = wac_score(eng, wac, BASE)
    n_wac = wac_score(eng, wac, cur)
    ship = (n_sts >= b_sts + 0.4) and (n_wac >= b_wac - 0.7)
    rep = [
        "STILLWATER constant tuning report",
        f"rounds: {rounds}, tuning fitness STS-subset best: {best_s:.2f}%",
        "",
        f"{'param':14} {'baseline':>10} {'tuned':>10}",
    ]
    for p in PARAMS:
        rep.append(f"{p[0]:14} {BASE[p[1]]:>10.4f} {cur[p[1]]:>10.4f}")
    rep += [
        "",
        f"full STS-1500:  baseline {b_sts:.2f}%  tuned {n_sts:.2f}%  "
        f"(delta {n_sts-b_sts:+.2f})",
        f"WAC-300:        baseline {b_wac:.2f}%  tuned {n_wac:.2f}%  "
        f"(delta {n_wac-b_wac:+.2f})",
        "",
        f"DECISION: {'SHIP tuned' if ship else 'KEEP baseline'}",
    ]
    text = "\n".join(rep)
    with open(REPORT, "w") as f:
        f.write(text + "\n")
    json.dump({"vector": cur, "baseline": BASE,
               "names": [p[0] for p in PARAMS],
               "full_sts": [b_sts, n_sts], "wac": [b_wac, n_wac],
               "ship": ship}, open(BEST, "w"), indent=1)
    log(text)
    log("TUNE DONE ship=" + str(ship))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as ex:
        log(f"TUNE CRASH: {repr(ex)[:300]}")
        raise
