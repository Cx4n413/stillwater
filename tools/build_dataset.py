"""Distillery corpus -> training arrays.

Each harvest record holds the net's first impression (raw) and the search's
settled verdict for one root position. The learning target is the RESIDUAL
(settled - raw): what hundreds of evals of search discovered that the net's
glance missed. Features are deliberately cheap (computable in the Rust core
at node creation): the net's own outputs plus material/phase summaries.

Run:  python tools/build_dataset.py          (writes harvest/dataset.npz)
"""

from __future__ import annotations

import glob
import json
import os
import sys

import chess
import numpy as np

MIN_EVIDENCE = 64          # only well-settled verdicts are labels
FEATURE_VERSION = 1

PIECE_VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
             chess.ROOK: 5, chess.QUEEN: 9}


def features_of(fen: str, raw_v: float, raw_mlh: float) -> list[float]:
    """Must stay in lockstep with the Rust corrector's feature builder."""
    board = chess.Board(fen)
    us, them = board.turn, not board.turn
    mat_us = sum(v * len(board.pieces(p, us)) for p, v in PIECE_VAL.items())
    mat_them = sum(v * len(board.pieces(p, them)) for p, v in PIECE_VAL.items())
    pawns = len(board.pieces(chess.PAWN, us)) + len(board.pieces(chess.PAWN, them))
    pieces = chess.popcount(board.occupied)
    return [
        1.0,
        raw_v,
        raw_v * abs(raw_v),
        min(raw_mlh, 160.0) / 80.0,
        (mat_us + mat_them) / 78.0,
        (mat_us - mat_them) / 9.0,
        pawns / 16.0,
        pieces / 32.0,
    ]


def main() -> int:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    argv = sys.argv[1:]
    sf_path = argv[argv.index("--sf") + 1] if "--sf" in argv else None
    out_name = argv[argv.index("--out") + 1] if "--out" in argv else "dataset.npz"
    sf_map = {}
    if sf_path:
        for line in open(sf_path, encoding="utf-8"):
            try:
                rr = json.loads(line)
                sf_map[rr["fen"]] = rr["sf_v"]
            except Exception:
                pass
        print(f"SF-teacher target: {len(sf_map)} labels from "
              f"{os.path.basename(sf_path)}")
    # The SF target uses the net's RAW value (search-independent), so relax the
    # settled-evidence gate; the self target needs a well-settled verdict.
    min_ev = 1 if sf_path else MIN_EVIDENCE
    files = sorted(glob.glob(os.path.join(here, "harvest", "*.jsonl")))
    files = [f for f in files if "sf_labels" not in os.path.basename(f)
             and "dataset" not in os.path.basename(f)]
    X, y, w, gid = [], [], [], []
    skipped = 0
    for fi, path in enumerate(files):
        for line in open(path, encoding="utf-8"):
            try:
                r = json.loads(line)
                if r.get("claim") or r.get("proof"):
                    continue          # floored/pinned values aren't net targets
                if r["evidence"] < min_ev:
                    continue
                raw_v, _, raw_mlh = r["raw"][0], r["raw"][1], r["raw"][2]
                settled_v = r["settled"][0]
                if sf_path is not None:
                    sv = sf_map.get(r["fen"])
                    if sv is None:
                        skipped += 1
                        continue
                    target = sv - raw_v
                else:
                    target = settled_v - raw_v
                X.append(features_of(r["fen"], raw_v, raw_mlh))
                y.append(target)
                w.append(min(r["evidence"] / 256.0, 4.0))
                gid.append(fi)        # group by source file: no leakage in split
            except Exception:
                skipped += 1
    if not X:
        print("no usable records yet — run the harvester first")
        return 1
    out = os.path.join(here, "harvest", out_name)
    np.savez_compressed(out, X=np.array(X, dtype=np.float32),
                        y=np.array(y, dtype=np.float32),
                        w=np.array(w, dtype=np.float32),
                        gid=np.array(gid, dtype=np.int32),
                        version=np.array([FEATURE_VERSION]))
    print(f"{len(y)} examples from {len(files)} files ({skipped} skipped) -> {out}")
    print(f"residual stats: mean {np.mean(y):+.4f}, std {np.std(y):.4f}, "
          f"|residual|>0.1 in {100*np.mean(np.abs(y)>0.1):.1f}% of positions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
