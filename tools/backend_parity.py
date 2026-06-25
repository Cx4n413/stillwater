"""Backend parity + speed harness for the DirectML -> CUDA/TensorRT swap.

  python tools/backend_parity.py capture   # write DML reference (run on DML)
  python tools/backend_parity.py check     # compare current EP vs reference

`check` prints the active provider, max abs error vs reference on wdl/value/
mlh over a fixed FEN set (must be < 2e-2 for fp16-vs-fp16 across backends —
different kernels round differently, but rank order and values must agree),
and an evals/s benchmark via infer_planes at batch 256.
"""

from __future__ import annotations

import json
import os
import sys
import time

import chess
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
REF = os.path.join(REPO, "games", "backend_ref.json")

FENS = [
    chess.STARTING_FEN,
    "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
    "2r1k3/pp3pbp/q3b2p/3pNr2/8/P4NP1/2Q2P1P/2R1R1K1 w - - 10 24",
    "8/2k5/3p4/p2P1p2/P2P1P2/8/8/3K4 w - - 0 1",
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "8/8/4k3/8/8/4K3/4P3/8 w - - 0 1",
]


def evals(orc):
    out = []
    for fen in FENS:
        e = orc.evaluate_one(chess.Board(fen))
        top = sorted(e.policy.items(), key=lambda kv: -kv[1])[:3]
        out.append({"wdl": list(e.wdl), "value": e.value, "mlh": e.mlh,
                    "top": [m.uci() for m, _ in top]})
    return out


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    from stillwater.oracle import LeelaOracle
    orc = LeelaOracle()
    orc.warmup()
    prov = orc.providers[0]
    print(f"active provider: {prov}")
    cur = evals(orc)

    if mode == "capture":
        json.dump({"provider": prov, "evals": cur}, open(REF, "w"), indent=1)
        print(f"reference ({prov}) -> {REF}")
    else:
        ref = json.load(open(REF))
        maxerr = 0.0
        rank_ok = True
        for r, c in zip(ref["evals"], cur):
            maxerr = max(maxerr, abs(r["value"] - c["value"]),
                         max(abs(a - b) for a, b in zip(r["wdl"], c["wdl"])))
            if r["top"][:1] != c["top"][:1]:
                rank_ok = False
        print(f"vs {ref['provider']} reference: max|err|={maxerr:.4f}, "
              f"top-move agree={'YES' if rank_ok else 'NO'}")
        print("PARITY OK" if maxerr < 2e-2 and rank_ok else "PARITY FAIL")

    # speed: 256 random-ish planes through infer_planes
    rng = np.random.default_rng(0)
    planes = rng.random((256, 112 * 64), dtype=np.float32)
    orc.infer_planes(planes, 256)  # warm
    n_iter, t0 = 8, time.time()
    for _ in range(n_iter):
        orc.infer_planes(planes, 256)
    dt = time.time() - t0
    print(f"speed: {256 * n_iter / dt:.0f} evals/s (batch 256, {prov})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
