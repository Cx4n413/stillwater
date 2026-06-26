"""Build the Aquifer opening book from the bot's real game records.

Offline: parse every PGN in the lichess-bot game_records, attribute each game's
final result (from STILLWATER's perspective, weighted by opponent Elo) to each
early move STILLWATER actually played, and write stillwater/aquifer.npz. Re-run
as games accumulate -- the book sharpens with every game, which is the whole point.

  python tools/build_aquifer.py [PLY_MAX=20]
"""
import collections
import glob
import os
import sys

import chess
import chess.pgn

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from stillwater import aquifer

RECORDS = r"C:\Users\nonna\Downloads\lichess-bot\game_records"
PLY_MAX = int(sys.argv[1]) if len(sys.argv) > 1 else 20
SW = "STILLWATER"

pgns = glob.glob(os.path.join(RECORDS, "*.pgn"))
print(f"{len(pgns)} game records | ply<={PLY_MAX}", flush=True)

# epd -> move -> [games, score_sum, opp_elo_sum]
book = collections.defaultdict(lambda: collections.defaultdict(
    lambda: [0, 0.0, 0.0]))
used = 0
for p in pgns:
    try:
        with open(p, encoding="utf-8", errors="ignore") as fh:
            g = chess.pgn.read_game(fh)
    except Exception:
        continue
    if g is None:
        continue
    h = g.headers
    white, black = h.get("White", ""), h.get("Black", "")
    if SW in white:
        sw_white, opp_elo = True, h.get("BlackElo", "")
    elif SW in black:
        sw_white, opp_elo = False, h.get("WhiteElo", "")
    else:
        continue
    res = h.get("Result", "*")
    if res == "1-0":
        sw_score = 1.0 if sw_white else 0.0
    elif res == "0-1":
        sw_score = 0.0 if sw_white else 1.0
    elif res == "1/2-1/2":
        sw_score = 0.5
    else:
        continue
    try:
        opp_elo = float(int(opp_elo))
    except (ValueError, TypeError):
        opp_elo = 0.0
    used += 1
    board = g.board()
    ply = 0
    for mv in g.mainline_moves():
        if ply >= PLY_MAX:
            break
        if (board.turn == chess.WHITE) == sw_white:
            rec = book[board.epd()][mv.uci()]
            rec[0] += 1
            rec[1] += sw_score
            rec[2] += opp_elo
        board.push(mv)
        ply += 1

# convert to plain dict for save
out = {e: {m: (r[0], r[1], r[2]) for m, r in mv.items()}
       for e, mv in book.items()}
n = aquifer.save(out)
nodes = len(out)
multi = sum(1 for mv in out.values() if len(mv) >= 2)
print(f"games used: {used}")
print(f"book: {n} (epd,move) rows across {nodes} positions; "
      f"{multi} positions have >=2 played moves")
print(f"saved -> {aquifer.default_path()}")
