"""Is the lc0-vs-lattice drift gap the MAX-vs-MEAN aggregation?

lc0 (MCTS, mean-over-tree) recovers M on 85% of the drift positions; the lattice's
MAX-over-DAG backup gets 74%. If switching the lattice to MEAN backup (R_MEANBACK)
lifts recovery toward ~85%, the 11pp gap IS the aggregation rule and a selective/
gated mean is the lever. If it stays ~74% (or drops), the gap is deeper in lc0's
tree structure than max-vs-mean, and the mean is not the answer.

Control (deployed MAX) is the known 74%. Run this with:
    STILLWATER_REFINE_MASK=0xFFF   -> deployed + R_MEANBACK (MEAN backup)
"""
import json
import os
import sys

import chess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

NODES = int(sys.argv[1]) if len(sys.argv) > 1 else 16000
MLH_W, MLH_SCALE = 0.12, 80.0


def effv(v, mlh):
    return v * (1.0 + MLH_W * max(0.0, 1.0 - mlh / MLH_SCALE))


d = json.load(open(os.path.join(REPO, "games", "gap_depth_eval.json"),
                   encoding="utf-8"))
du = [r for r in d["records"] if r["bucket"] == "depth_unstable"]
mask = os.environ.get("STILLWATER_REFINE_MASK", "(default 0xBFF = MAX)")
print(f"{len(du)} drift positions | nodes {NODES} | refine_mask {mask}", flush=True)

from stillwater.oracle import LeelaOracle
from stillwater.engine_rs import RustEngine
oracle = LeelaOracle()
print("provider:", oracle._sess.get_providers()[0], flush=True)
eng = RustEngine(oracle=oracle, batch=128, refine=True, harvest_on=False,
                 ledger_on=False)
core = eng.core

hits = n = 0
for i, r in enumerate(du):
    board = chess.Board(r["fen"])
    eng.new_game()
    eng.think(board, node_budget=NODES)
    rc = core.root_children()
    if not rc:
        continue
    n += 1
    pick = min(rc, key=lambda c: effv(c[1], c[7]))[0]
    hits += (pick == r["M"])
    if (i + 1) % 10 == 0:
        print(f"  {i+1}/{len(du)}", flush=True)
eng.shutdown()

print(f"\nvalue-argmax recovers M: {hits}/{n} = {100*hits/n:.0f}%"
      f"   (lc0/MEAN target=85%, lattice MAX=74%)")
