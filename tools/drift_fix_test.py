"""Does the policy-aware tie-break recover the drift losses? For the 21 real-drift
positions, think with the tie-break OFF (deployed value/LCB readout) vs ON
(value-first, policy breaks near-ties) at the budget where they drifted, and count
how many chosen moves become Stockfish's move M.  Run with STILLWATER_TRT=1.
"""
import json
import os
import sys

import chess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 40000
EPS = float(sys.argv[2]) if len(sys.argv) > 2 else 0.10

d = json.load(open(os.path.join(REPO, "games", "gap_depth_eval.json"),
                  encoding="utf-8"))
real = []
for r in d["records"]:
    if r["bucket"] != "depth_unstable" or not r["decisive"]:
        continue
    picks = [x["raw_pick"] for x in r["ladder"]]
    led = [i for i, p in enumerate(picks) if p == r["M"]]
    if led and led != [0]:
        real.append((r["fen"], r["M"]))
print(f"real-drift positions: {len(real)} | budget {N} | eps {EPS}", flush=True)

from stillwater.oracle import LeelaOracle
from stillwater.engine_rs import RustEngine
oracle = LeelaOracle()
print("provider:", oracle._sess.get_providers()[0], flush=True)
eng = RustEngine(oracle=oracle, batch=128, refine=True,
                 harvest_on=False, ledger_on=False)

off_M = on_M = changed = 0
rows = []
for fen, M in real:
    b = chess.Board(fen)
    eng.pol_tiebreak = 0.0
    eng.new_game()
    bo, _ = eng.think(b, node_budget=N)
    mo = bo.uci() if bo else None
    eng.pol_tiebreak = EPS
    eng.new_game()
    bn, _ = eng.think(b, node_budget=N)
    mn = bn.uci() if bn else None
    off_M += (mo == M)
    on_M += (mn == M)
    changed += (mo != mn)
    rows.append((M, mo, mn))

n = len(real)
print(f"\n==== POLICY-TIEBREAK DRIFT RECOVERY (n={n}) ====")
print(f"chose M with tie-break OFF: {off_M}/{n}")
print(f"chose M with tie-break ON : {on_M}/{n}")
print(f"readout changed the move  : {changed}/{n}")
print("\nrows: M | off-pick | on-pick")
for M, mo, mn in rows:
    flag = " <-FIXED" if (mn == M and mo != M) else (" <-BROKE" if (mo == M and mn != M) else "")
    print(f"  {M} | {mo} | {mn}{flag}")
