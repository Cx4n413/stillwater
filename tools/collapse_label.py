"""SF-label the 12 ceiling-match collapse decisions (CPU-only).

For each position: SF's best move M and the cp-loss of the move SW actually
played. Tells us (a) how bad each blitzed decision really was, and (b) whether a
clearly better move EXISTED for search to find -- the precondition for the
time-manager premise gate (if no better move existed, no budget would help).
"""
import json
import sys

import chess
import chess.engine

SF = (r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages"
      r"\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe"
      r"\stockfish\stockfish-windows-x86-64-avx2.exe")
DEPTH = int(sys.argv[1]) if len(sys.argv) > 1 else 22

recs = json.load(open("games/collapse_positions.json"))
sf = chess.engine.SimpleEngine.popen_uci([SF])
sf.configure({"Threads": 1, "Hash": 256})

out = []
for r in recs:
    board = chess.Board(r["fen"])
    info = sf.analyse(board, chess.engine.Limit(depth=DEPTH), multipv=2)
    best = info[0]["pv"][0]
    bs = info[0]["score"].pov(board.turn).score(mate_score=3000)
    played = chess.Move.from_uci(r["played"])
    pi = sf.analyse(board, chess.engine.Limit(depth=DEPTH), root_moves=[played])
    ps = pi["score"].pov(board.turn).score(mate_score=3000)
    loss = bs - ps
    r2 = dict(r, M=best.uci(), sf_best_cp=bs, sf_played_cp=ps, cp_loss=loss)
    out.append(r2)
    print(f"R{r['round']:>4} played {r['played']:7} ({r['time_spent']:.2f}s) "
          f"cp {ps:+6} | SF best {best.uci():7} cp {bs:+6} | LOSS {loss:5}")
sf.quit()
json.dump(out, open("games/collapse_labeled.json", "w"), indent=1)
avoid = sum(1 for r in out if r["cp_loss"] >= 150)
print(f"\npositions where a >=150cp-better move EXISTED: {avoid}/{len(out)}")
print("(these are the ones more search time could in principle have saved)")
