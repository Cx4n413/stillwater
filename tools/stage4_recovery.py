"""STAGE 4: does the ACTUAL gated GATE-A/GATE-B visit-readout recover the
value-fail losses (drift + structure)? Stage 1 showed the raw visit-argmax
points at SF's move M ~40%; the real readout adds the value-band + dual floor +
binomial-LCB gates, which may filter that down. Measure the chosen move (what
the engine would PLAY) with the readout OFF vs ON. Counter is on for both arms;
only the Python readout flag toggles. Run with STILLWATER_TRT=1.
"""
import json
import os
import sys
from collections import Counter

import chess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 40000

d = json.load(open(os.path.join(REPO, "games", "gap_depth_eval.json"),
                  encoding="utf-8"))
pos = [(r["fen"], r["M"], r["bucket"]) for r in d["records"]
       if r["decisive"] and r["bucket"] in ("depth_unstable", "search_structure")]
print(f"{len(pos)} value-fail positions | budget {N}", flush=True)

os.environ["STILLWATER_VISIT_READOUT"] = "1"   # counter ON for both arms
from stillwater.oracle import LeelaOracle
from stillwater.engine_rs import RustEngine
oracle = LeelaOracle()
print("provider:", oracle._sess.get_providers()[0], flush=True)
eng = RustEngine(oracle=oracle, batch=128, refine=True,
                 harvest_on=False, ledger_on=False)

stats = {b: {"n": 0, "off_M": 0, "on_M": 0, "fixed": 0, "broke": 0}
         for b in ("depth_unstable", "search_structure")}
for fen, M, bucket in pos:
    b = chess.Board(fen)
    eng.visit_readout = False
    eng.new_game(); bo, _ = eng.think(b, node_budget=N)
    mo = bo.uci() if bo else None
    eng.visit_readout = True
    eng.new_game(); bn, _ = eng.think(b, node_budget=N)
    mn = bn.uci() if bn else None
    s = stats[bucket]; s["n"] += 1
    s["off_M"] += (mo == M); s["on_M"] += (mn == M)
    s["fixed"] += (mn == M and mo != M); s["broke"] += (mo == M and mn != M)

print("\n==== STAGE-4 READOUT RECOVERY (chosen move == SF's M) ====")
tot = {"n": 0, "off_M": 0, "on_M": 0, "fixed": 0, "broke": 0}
for b, s in stats.items():
    if not s["n"]:
        continue
    for k in tot:
        tot[k] += s[k]
    print(f"[{b}] N={s['n']}: readout OFF -> M {s['off_M']}, ON -> M {s['on_M']} "
          f"(fixed {s['fixed']}, broke {s['broke']})")
print(f"\nPOOLED N={tot['n']}: OFF->M {tot['off_M']}, ON->M {tot['on_M']} "
      f"(net {tot['on_M']-tot['off_M']:+d}; fixed {tot['fixed']}, broke {tot['broke']})")
print("READING: ON-M materially > OFF-M with broke ~0 -> the gated readout "
      "captures the visit signal safely -> proceed to the DirectML gauntlet.")
