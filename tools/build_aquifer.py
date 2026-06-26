"""Build the Aquifer opening book from the engine's games.

Sources: the bot's REAL game records (lichess, vs varied opponents) AND overnight
self-play (tools/selfplay.py, both sides are the engine -> both recorded). Each
game's result is attributed (from STILLWATER's perspective) to each early move it
played, and the book is written to stillwater/aquifer.npz. Re-run as games
accumulate -- the book sharpens with every game, which is the whole point.

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
BASE = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}

pgns = (glob.glob(os.path.join(RECORDS, "*.pgn"))
        + glob.glob(os.path.join(REPO, "games", "selfplay_*.pgn")))
print(f"{len(pgns)} PGN files | ply<={PLY_MAX}", flush=True)


def _elo(s):
    try:
        return float(int(s))
    except (ValueError, TypeError):
        return 0.0


# epd -> move -> [games, score_sum, opp_elo_sum]
book = collections.defaultdict(lambda: collections.defaultdict(
    lambda: [0, 0.0, 0.0]))
used = real = self_play = 0
for p in pgns:
    try:
        fh = open(p, encoding="utf-8", errors="ignore")
    except Exception:
        continue
    while True:                       # read EVERY game (self-play files are multi-game)
        try:
            g = chess.pgn.read_game(fh)
        except Exception:
            break
        if g is None:
            break
        h = g.headers
        white, black = h.get("White", ""), h.get("Black", "")
        base = BASE.get(h.get("Result", "*"))
        if base is None:
            break
        # sides STILLWATER played: (sw_is_white, sw_score, opp_elo)
        if SW in white and SW in black:               # self-play -> both sides
            sides = [(True, base, 0.0), (False, 1.0 - base, 0.0)]
            self_play += 1
        elif SW in white:
            sides = [(True, base, _elo(h.get("BlackElo")))]
            real += 1
        elif SW in black:
            sides = [(False, 1.0 - base, _elo(h.get("WhiteElo")))]
            real += 1
        else:
            break
        used += 1
        for sw_white, sw_score, opp_elo in sides:
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
    fh.close()

out = {e: {m: (r[0], r[1], r[2]) for m, r in mv.items()}
       for e, mv in book.items()}
n = aquifer.save(out)
nodes = len(out)
multi = sum(1 for mv in out.values() if len(mv) >= 2)
robust = sum(1 for mv in out.values()
             if sum(1 for r in mv.values() if r[0] >= 4) >= 2)
print(f"games used: {used} ({real} real, {self_play} self-play)")
print(f"book: {n} (epd,move) rows | {nodes} positions | {multi} multi-move | "
      f"{robust} with >=2 moves played >=4x")
print(f"saved -> {aquifer.default_path()}")
