"""HYBRID FEASIBILITY GATE: can the lattice cheaply FLAG the positions it should
route to a (selective) tree search?

The measured gap lives on ~9% lattice-vs-lc0 DISAGREEMENT positions. A hybrid
(no-tree by default, small tree on hard positions) only works if a cheap lattice
feature predicts those positions WITHOUT a tree. Test the natural feature: the
top-2 root value MARGIN (how close the best and 2nd-best root moves are) and root
WDL-variance. If routing the lowest-margin K% catches most disagreements at small
K, the hybrid is efficient; if disagreements look like everything else, it isn't.
"""
import json
import os
import sys

import chess
import chess.engine

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
LC0 = r"C:\Users\nonna\Downloads\lc0\cuda12\lc0.exe"
BT4 = os.path.join(REPO, "nets",
                   "BT4-1024x15x32h-swa-6147500-policytune-332.pb.gz")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 120
NODES = int(sys.argv[2]) if len(sys.argv) > 2 else 16000
MLH_W, MLH_SCALE = 0.12, 80.0


def effv(v, mlh):
    return v * (1.0 + MLH_W * max(0.0, 1.0 - mlh / MLH_SCALE))


d = json.load(open(os.path.join(REPO, "games", "gap_depth_eval.json"),
                   encoding="utf-8"))
recs = [r for r in d["records"] if r.get("fen") and r.get("M")][:N]
print(f"{len(recs)} positions | nodes {NODES} | hybrid-detectability gate", flush=True)

from stillwater.oracle import LeelaOracle
from stillwater.engine_rs import RustEngine
oracle = LeelaOracle()
print("SW provider:", oracle._sess.get_providers()[0], flush=True)
eng = RustEngine(oracle=oracle, batch=128, refine=True, harvest_on=False,
                 ledger_on=False)
core = eng.core
lc0 = chess.engine.SimpleEngine.popen_uci([LC0], timeout=180)
lc0.configure({"WeightsFile": BT4})

rows = []   # (margin, variance, disagree, decisive, lc0_better)
for i, r in enumerate(recs):
    board = chess.Board(r["fen"])
    M = r["M"]
    eng.new_game()
    eng.think(board, node_budget=NODES)
    rc = core.root_children()
    if not rc or len(rc) < 2:
        continue
    qs = sorted((effv(c[1], c[7]) for c in rc))  # lower effv = better for us
    margin = qs[1] - qs[0]                        # gap best vs 2nd-best (>=0)
    var = core.root_info()[0][4]
    sw = min(rc, key=lambda c: effv(c[1], c[7]))[0]
    try:
        mv = lc0.play(board, chess.engine.Limit(nodes=NODES)).move
        lp = mv.uci() if mv else None
    except Exception:
        lp = None
    disagree = (sw != lp)
    lc0_better = disagree and lp == M and sw != M
    rows.append((margin, var, disagree, r.get("decisive", False), lc0_better))
    if (i + 1) % 20 == 0:
        dd = sum(1 for x in rows if x[2])
        print(f"  {i+1}/{len(recs)} (disagree {dd})", flush=True)

eng.shutdown()
lc0.quit()

import statistics as st
dis = [x for x in rows if x[2]]
agr = [x for x in rows if not x[2]]
n = len(rows)
print(f"\nanalyzed {n} | disagree {len(dis)} | agree {len(agr)}")
if dis and agr:
    print(f"  median top-2 MARGIN:  disagree {st.median([x[0] for x in dis]):.3f}  "
          f"agree {st.median([x[0] for x in agr]):.3f}   (smaller margin = more uncertain)")
    print(f"  median root VARIANCE: disagree {st.median([x[1] for x in dis]):.3f}  "
          f"agree {st.median([x[1] for x in agr]):.3f}")
    # routing efficiency: sort by margin asc (most uncertain first); how many
    # disagreements (and lc0-better ones) are caught by routing the lowest-margin K%?
    order = sorted(range(n), key=lambda j: rows[j][0])
    nd = len(dis)
    nlb = sum(1 for x in rows if x[4])
    print("\n  routing the lowest-MARGIN K% to a tree catches:")
    for K in (0.10, 0.20, 0.30, 0.50):
        cut = max(1, int(K * n))
        sub = [rows[j] for j in order[:cut]]
        cd = sum(1 for x in sub if x[2])
        clb = sum(1 for x in sub if x[4])
        print(f"    K={int(K*100):2}%  -> {cd}/{nd} disagreements "
              f"({100*cd/nd:.0f}%), {clb}/{nlb} lc0-better-than-lattice "
              f"({100*clb/max(1,nlb):.0f}%)")
    print("\nHybrid is EFFICIENT if a small K catches most lc0-better cases (margin")
    print("separates them). If catch% ~= K% (diagonal), margin doesn't detect them")
    print("and a uniform tree-everywhere would be needed -> hybrid not efficient.")
