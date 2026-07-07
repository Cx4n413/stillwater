"""PREMISE GATE for the time-manager fix (the court blitzed game-losing moves).

For each ceiling-match collapse where a >=150cp-better move existed: run SW at
  (a) the nodes it ACTUALLY got (time_spent * ~1.5Knps DirectML, min 256)
  (b) 6000 nodes  (~ what a 3-4s minimum-think buys on DirectML)
  (c) 20000 nodes (~ what CUDA + full time buys)
Corrected = pick differs from the played losing move AND is >=150cp better (SF).

PASS: >=3/7 corrected at (b) or (c) -> the court fix converts directly into match
points; build it. KILL: <=1 corrected -> the collapses are eval-blindness (no
budget helps); the court fix only buys comfort, not points.
"""
import json
import os
import sys

import chess
import chess.engine

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
SF = (r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages"
      r"\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe"
      r"\stockfish\stockfish-windows-x86-64-avx2.exe")
NPS = 1500.0
RUNGS = [6000, 20000]

recs = [r for r in json.load(open("games/collapse_labeled.json"))
        if r["cp_loss"] >= 150]
print(f"{len(recs)} collapse positions with a >=150cp-better move", flush=True)

from stillwater.oracle import LeelaOracle
from stillwater.engine_rs import RustEngine
oracle = LeelaOracle()
print("provider:", oracle._sess.get_providers()[0], flush=True)
eng = RustEngine(oracle=oracle, batch=128, refine=True, harvest_on=False,
                 ledger_on=False)
sf = chess.engine.SimpleEngine.popen_uci([SF])
sf.configure({"Threads": 1, "Hash": 256})


def sf_cp(board, uci):
    mv = chess.Move.from_uci(uci)
    i = sf.analyse(board, chess.engine.Limit(depth=20), root_moves=[mv])
    return i["score"].pov(board.turn).score(mate_score=3000)


corrected_any = 0
repro = 0
for r in recs:
    board = chess.Board(r["fen"])
    actual = max(256, int(r["time_spent"] * NPS))
    row = [f"R{r['round']:>4} played {r['played']:7}"]
    picks = {}
    for n in [actual] + RUNGS:
        eng.new_game()
        mv, _ = eng.think(chess.Board(r["fen"]), node_budget=n)
        picks[n] = mv.uci() if mv else "-"
    if picks[actual] == r["played"]:
        repro += 1
    fixed = False
    for n in RUNGS:
        p = picks[n]
        if p != r["played"]:
            gain = sf_cp(board, p) - r["sf_played_cp"]
            if gain >= 150:
                fixed = True
                row.append(f"| {n}: {p} (+{gain}cp) CORRECTED")
            else:
                row.append(f"| {n}: {p} (+{gain}cp)")
        else:
            row.append(f"| {n}: same")
    row.insert(1, f"@actual({actual}): {picks[actual]}"
                  f"{' =repro' if picks[actual] == r['played'] else ''}")
    corrected_any += fixed
    print("  " + " ".join(row), flush=True)

eng.shutdown()
sf.quit()
print(f"\nreproduced the losing move at actual nodes: {repro}/{len(recs)}")
print(f"CORRECTED by budget the court refused to spend: {corrected_any}/{len(recs)}")
print(f"\nVERDICT: {'PASS -> build the court fix (min-think + uncertainty extension)' if corrected_any >= 3 else 'KILL -> collapses are eval-blind, budget does not save them'}")
