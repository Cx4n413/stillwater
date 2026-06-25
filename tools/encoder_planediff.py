"""Decisive test: do the RUST encoder and the PYTHON oracle encoder feed BT4
IDENTICAL 112-plane inputs for the same real-game positions-with-history?
A systematic difference = the rust engine evaluates different inputs than the
validated python path = uniformly worse moves. CPU-only (no net inference)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chess, chess.pgn, numpy as np
import stillwater_core
from stillwater.oracle import LeelaOracle

orc = LeelaOracle()                                   # net loads; we only encode
core = stillwater_core.Core(None, False, 2_000_000, True, 5)

g = chess.pgn.read_game(open(os.path.join(os.path.dirname(__file__), "..",
                                          "games", "sf_gauntlet_3190.pgn")))
start_fen = g.board().fen()
moves, samples, b = [], [], g.board()
for mv in g.mainline_moves():
    moves.append(mv.uci()); b.push(mv)
    if len(moves) in (6, 10, 16, 24, 32, 44, 56):
        samples.append((list(moves), b.copy()))
    if len(moves) > 60:
        break

print("start_fen:", start_fen)
worst = 0.0
for mvs, bd in samples:
    py = np.asarray(orc._encode_batch([bd])).reshape(112, 64).astype(np.float32)
    core.set_position(start_fen, mvs)
    pl, n = core.select_batch(1)
    rs = np.asarray(pl).reshape(n, 112, 64)[0].astype(np.float32)
    d = np.abs(py - rs)
    big = [p for p in range(112) if d[p].max() > 0.01]
    print(f"ply {len(mvs):2}: max|diff|={d.max():.4f}  planes>0.01: {big}")
    worst = max(worst, d.max())
print(f"\nWORST max|diff| across samples: {worst:.4f}")
print("VERDICT:", "ENCODERS MATCH (within fp16)" if worst < 0.02
      else "ENCODERS DIFFER -> rust feeds BT4 different inputs")
