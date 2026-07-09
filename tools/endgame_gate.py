"""PREMISE GATE for piece-count-gated deep thinking: replay the mined 8-13 man
leak positions at deployed-ish budget vs 3x. If the pick changes materially at
3x on >=half, budget is the lever -> build the gated court boost. If picks are
identical, the net simply can't see it (structural) -> do not build."""
import json, os, sys
sys.path.insert(0, ".")
os.environ.setdefault("STILLWATER_LCB_K", "0.0")
os.environ.setdefault("STILLWATER_PICK_K", "1.1")
os.environ.setdefault("STILLWATER_FPU_RED", "0.22")
os.environ.setdefault("STILLWATER_ML_THRESH", "0.9")
os.environ.setdefault("STILLWATER_CPUCT_INIT", "2.045")
os.environ.setdefault("STILLWATER_CPUCT_FACTOR", "4.894")
os.environ.setdefault("STILLWATER_C_VAR", "0.2")
os.environ.setdefault("STILLWATER_CONVERT", "1")
os.environ.setdefault("STILLWATER_VERIFY_DRAW", "256")
import chess
from stillwater.oracle import LeelaOracle
from stillwater.engine_rs import RustEngine
oracle = LeelaOracle()
print("provider:", oracle._sess.get_providers()[0], flush=True)
eng = RustEngine(oracle=oracle, batch=64, refine=True, harvest_on=False, ledger_on=False)
recs = json.load(open("games/endgame_leaks.json"))
changed = 0
for r in recs:
    picks = {}
    for n in (9000, 27000):
        eng.new_game()
        mv, info = eng.think(chess.Board(r["fen"]), node_budget=n)
        picks[n] = (mv.uci() if mv else "-", round(info.get("value", 0), 2))
    diff = picks[9000][0] != picks[27000][0]
    changed += diff
    print(f"{r['opp']:12} mv{r['mv']:3} ({r['men']:2} men) played:{r['played']:7} "
          f"9k:{picks[9000][0]:7}({picks[9000][1]:+.2f}) 27k:{picks[27000][0]:7}({picks[27000][1]:+.2f})"
          f"{'  CHANGED' if diff else ''}", flush=True)
eng.shutdown()
print(f"\npick changed at 3x budget: {changed}/{len(recs)}")
print("VERDICT:", "PASS -> build piece-count-gated deep think" if changed >= len(recs)//2 else "KILL -> structural, do not build")
