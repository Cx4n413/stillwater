"""Per-net throughput probe: evals/s for a SPECIFIC net on a fixed position.

Unlike bench_engine.py (which auto-discovers the net and so cannot select the
name-excluded 'fallback'), this injects the oracle explicitly, so any .onnx --
including fallback.onnx -- can be measured. Same search config across nets, so
the only variable is the evaluator. A middlegame position is used so the root is
never proven within the budget => the full movetime is spent => clean evals/s.

Run: python tools/net_throughput.py <net.onnx> [seconds]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess

from stillwater.engine import Engine
from stillwater.oracle import LeelaOracle

MIDDLEGAME = "r2q1rk1/pp1bbppp/2n1pn2/2pp4/3P1B2/2NBPN2/PPP2PPP/R2Q1RK1 w - - 6 9"

net = sys.argv[1]
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0

print(f"loading oracle: {os.path.basename(net)}")
oracle = LeelaOracle(onnx_path=net)
if hasattr(oracle, "warmup"):
    oracle.warmup()  # absorb DirectML per-shape JIT so it is OUT of the timing
eng = Engine(oracle=oracle, batch=128)
board = chess.Board(MIDDLEGAME)
move, info = eng.think(board, movetime=secs)
print(f"NET={os.path.basename(net)}  evals={info['evals']}  "
      f"nps={info['nps']:.1f}  time={info['time']:.1f}s  "
      f"lattice={info['lattice']}  backups={info['backups']}  "
      f"cp={info['cp']:+d}  p_best={info['p_best']:.2f}")
