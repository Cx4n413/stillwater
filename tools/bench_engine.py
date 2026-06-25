"""End-to-end engine throughput benchmark (real oracle, pipelined loop).
Run: python tools/bench_engine.py [seconds] [fen]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess

from stillwater.engine import Engine

MIDDLEGAME = "r2q1rk1/pp1bbppp/2n1pn2/2pp4/3P1B2/2NBPN2/PPP2PPP/R2Q1RK1 w - - 6 9"

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
fen = sys.argv[2] if len(sys.argv) > 2 else MIDDLEGAME

print("loading oracle...")
eng = Engine()
eng._ensure_oracle()
board = chess.Board(fen)
move, info = eng.think(board, movetime=secs)
print(f"move={move.uci() if move else '-'}")
print(f"evals={info['evals']}  nps={info['nps']}  time={info['time']:.1f}s")
print(f"lattice={info['lattice']}  backups={info['backups']}  "
      f"p_best={info['p_best']:.2f}  cp={info['cp']:+d}")
