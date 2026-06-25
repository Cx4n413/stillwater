"""SMAB PREMISE GATE -- no mechanism build, pure value-geometry off the live lattice.

SMAB's entire re-rank claim: on the drift (depth_unstable) positions, the SF-best
move M sits atop a MORE SINGULAR principal variation than the move that overtakes
it. pv_margin(edge) = min_d LAMBDA^d * (best_q - 2nd_q) along that root edge's PV
(the depth-discounted weakest link of the line). If pv_margin_M is NOT
systematically larger than pv_margin_overtaker, the value-geometry asymmetry the
design rests on is ABSENT and SMAB cannot re-rank -> KILL before any build.

PASS:  >=60% of drifted positions have pv_margin_M >= pv_margin_overtaker + 0.05.
KILL:  the gap is <0.05 (tie+loss) on >=40% -> asymmetry absent.
"""
import json
import math
import os
import statistics as st
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import chess

NODES = int(sys.argv[1]) if len(sys.argv) > 1 else 16000
LAMBDA = float(sys.argv[2]) if len(sys.argv) > 2 else 0.8
DEPTH = 14
THRESH = 0.05
GAMMA, MLH_W, MLH_SCALE = 0.997, 0.12, 80.0


def effv(v, mlh):
    return v * (1.0 + MLH_W * max(0.0, 1.0 - mlh / MLH_SCALE))


def pv_margin(gaps, lam):
    # gaps: per-ply (best_q, second_q, n_expanded); skip plies with <2 children
    vals = [(lam ** dd) * (bq - sq)
            for dd, (bq, sq, n) in enumerate(gaps)
            if n >= 2 and not math.isnan(sq)]
    return min(vals) if vals else None


d = json.load(open(os.path.join(REPO, "games", "gap_depth_eval.json"),
                   encoding="utf-8"))
du = [r for r in d["records"] if r["bucket"] == "depth_unstable"]
print(f"{len(du)} depth_unstable positions | nodes {NODES} | lambda {LAMBDA} "
      f"| depth {DEPTH}", flush=True)

from stillwater.oracle import LeelaOracle
from stillwater.engine_rs import RustEngine
oracle = LeelaOracle()
print("provider:", oracle._sess.get_providers()[0], flush=True)
eng = RustEngine(oracle=oracle, batch=128, refine=True, harvest_on=False,
                 ledger_on=False)
core = eng.core

rows = []
skip_noM = skip_nodrift = skip_nomargin = 0
for i, r in enumerate(du):
    board = chess.Board(r["fen"])
    eng.new_game()
    eng.think(board, node_budget=NODES)
    rc = core.root_children()
    if not rc:
        continue
    pick = min(rc, key=lambda c: effv(c[1], c[7]))[0]   # raw value-argmax
    M = r["M"]
    if pick == M:
        skip_nodrift += 1
        continue
    if M not in {c[0] for c in rc}:
        skip_noM += 1
        continue
    pmM = pv_margin(core.pv_child_gaps(M, DEPTH), LAMBDA)
    pmO = pv_margin(core.pv_child_gaps(pick, DEPTH), LAMBDA)
    if pmM is None or pmO is None:
        skip_nomargin += 1
        continue
    rows.append((pmM, pmO, M, pick))
    if (i + 1) % 10 == 0:
        print(f"  {i+1}/{len(du)} (drifted {len(rows)})", flush=True)

eng.shutdown()

n = len(rows)
print(f"\ndrifted & analyzable: {n}  (skipped: {skip_nodrift} no-drift, "
      f"{skip_noM} M-unexpanded, {skip_nomargin} no-margin)")
if n == 0:
    print("no analyzable drift positions -- inconclusive (try another rung).")
    sys.exit()
wins = sum(1 for pmM, pmO, *_ in rows if pmM >= pmO + THRESH)
ties = sum(1 for pmM, pmO, *_ in rows if abs(pmM - pmO) < THRESH)
loss = sum(1 for pmM, pmO, *_ in rows if pmO > pmM + THRESH)
print(f"  pv_margin_M >= overtaker + {THRESH}:  {wins}/{n} = {100*wins/n:.0f}%"
      f"   <- PASS needs >=60%")
print(f"  within {THRESH} (tie):                {ties}/{n} = {100*ties/n:.0f}%")
print(f"  overtaker MORE singular:           {loss}/{n} = {100*loss/n:.0f}%")
print(f"  median pv_margin: M={st.median([x[0] for x in rows]):.3f}  "
      f"overtaker={st.median([x[1] for x in rows]):.3f}")
print(f"  median (M - overtaker) gap: {st.median([x[0]-x[1] for x in rows]):+.3f}")
if wins / n >= 0.60:
    verdict = "PASS -> build R_SMAB"
elif (ties + loss) / n >= 0.40:
    verdict = "KILL -> SMAB dead (singularity asymmetry absent)"
else:
    verdict = "WEAK -> borderline, inspect before building"
print(f"\nVERDICT: {verdict}")
