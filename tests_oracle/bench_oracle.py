"""Benchmark stillwater.oracle end-to-end (encoding + GPU inference).

Run from the repo root:  python tests_oracle/bench_oracle.py
"""

import random
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import chess  # noqa: E402

from stillwater.oracle import LeelaOracle  # noqa: E402

NETS = [
    ("BT4 (default)", REPO / "nets" / "BT4-1024x15x32h-policytune.onnx"),
    ("t3-512x15x16h", REPO / "nets" / "t3-512x15x16h-distill.onnx"),
    ("t1-256x10 (fallback)", REPO / "nets" / "fallback.onnx"),
]
BATCHES = [32, 64, 128, 256, 512]
EVALS_PER_CONFIG = 2048


def board_pool(n=512, seed=7):
    """Random-playout boards carrying real move history (realistic load)."""
    rng = random.Random(seed)
    pool = []
    while len(pool) < n:
        b = chess.Board()
        depth = rng.randint(2, 70)
        for _ in range(depth):
            moves = list(b.legal_moves)
            if not moves:
                break
            b.push(rng.choice(moves))
        if b.legal_moves:
            pool.append(b)
    return pool


def main():
    pool = board_pool()
    print(f"{'net':22s} {'batch':>5s} {'evals/s':>9s} {'ms/board':>9s}")
    for name, path in NETS:
        for bs in BATCHES:
            o = LeelaOracle(onnx_path=str(path), batch_max=bs)
            boards = [pool[i % len(pool)] for i in range(bs)]
            o.evaluate(boards)  # warmup / DML graph compile
            o.evaluate(boards)
            n_iters = max(2, EVALS_PER_CONFIG // bs)
            t0 = time.perf_counter()
            for _ in range(n_iters):
                o.evaluate(boards)
            dt = time.perf_counter() - t0
            rate = bs * n_iters / dt
            print(f"{name:22s} {bs:5d} {rate:9.0f} {1000 * dt / (bs * n_iters):9.3f}")
        # encoding-only timing at batch 256
        boards = [pool[i % len(pool)] for i in range(256)]
        t0 = time.perf_counter()
        for _ in range(8):
            o._encode_batch(boards)
        enc_ms = (time.perf_counter() - t0) / (8 * 256) * 1000
        print(f"{name:22s}   enc {enc_ms:9.3f} ms/board (cpu, batch 256)")
    print(f"providers in use: {o.providers}")


if __name__ == "__main__":
    main()
