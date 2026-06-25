"""Profile a small think() to find the hot spot. Run from repo root:
    python -u tools/profile_repro.py [node_budget]
"""

import cProfile
import os
import pstats
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess

from stillwater.engine import Engine
from stillwater.mock_oracle import MockOracle

budget = int(sys.argv[1]) if len(sys.argv) > 1 else 600
board = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/4P1q1/5N1P/PPPP1PP1/RNBQKB1R b KQkq - 0 3")
eng = Engine(oracle=MockOracle(), batch=64)

t0 = time.perf_counter()
prof = cProfile.Profile()
prof.enable()
move, info = eng.think(board, node_budget=budget)
prof.disable()
dt = time.perf_counter() - t0

print(f"\nmove={move} evals={info.get('evals')} time={dt:.1f}s "
      f"eps={info.get('evals', 0)/max(dt,1e-9):.0f}/s "
      f"backups={info.get('backups')} lattice={info.get('lattice')}")
stats = pstats.Stats(prof)
stats.sort_stats("cumulative").print_stats(22)
