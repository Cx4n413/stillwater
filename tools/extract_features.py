"""#90 step 3: extract the value-head feature vector (/value/reshape, 8192-d) for
every child position in the ranking dataset, using the ENGINE'S OWN encoder so
train-time features match deploy-time. Stores a memmap of features + per-child
metadata (ranking target, group id, proof flag, BT4's native value for the
magnitude leash). ~1M positions; GPU inference, ~10-15 min.

    python tools/extract_features.py
"""
from __future__ import annotations
import json
import os
import sys
import time

import numpy as np
import chess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from stillwater.oracle import LeelaOracle  # noqa: E402

DATA = os.path.join(REPO, "games", "rank_dataset.jsonl")
EMB = os.path.join(REPO, "nets", "BT4-embed.onnx")
OUTDIR = os.path.join(REPO, "games", "rankfeat")
os.makedirs(OUTDIR, exist_ok=True)

DFEAT = 8192
FEAT_OUT = "/value/reshape"
WDL_OUT = "/output/wdl"
B = 256


def main():
    # pass 1: load groups, count children
    groups = []
    N = 0
    with open(DATA, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            groups.append(r)
            N += len(r["moves"])
    print(f"groups={len(groups)}  children N={N}  feat_dim={DFEAT}")
    gb = N * DFEAT * 2 / 1e9
    print(f"feature memmap size ~ {gb:.1f} GB")

    feats = np.memmap(os.path.join(OUTDIR, "feats.f16"), dtype=np.float16,
                      mode="w+", shape=(N, DFEAT))
    targets = np.empty(N, np.float32)
    gid = np.empty(N, np.int32)
    proof = np.empty(N, np.int8)
    baseval = np.empty(N, np.float32)

    oracle = LeelaOracle(onnx_path=EMB, batch_max=B)
    sess = oracle._sess
    in_name, in_dtype = oracle._in_name, oracle._in_dtype

    buf_boards, buf_idx = [], []

    def flush():
        n = len(buf_boards)
        if n == 0:
            return
        planes = oracle._encode_batch(buf_boards)
        if planes.dtype != in_dtype:
            planes = planes.astype(in_dtype)
        if n < B:                      # pad to fixed bucket -> no DML recompiles
            planes = np.concatenate(
                [planes, np.zeros((B - n,) + planes.shape[1:], in_dtype)], axis=0)
        outs = sess.run([FEAT_OUT, WDL_OUT], {in_name: planes})
        fz = np.asarray(outs[0], np.float16)[:n]
        wz = np.asarray(outs[1], np.float32)[:n]
        for k, idx in enumerate(buf_idx):
            feats[idx] = fz[k]
            baseval[idx] = float(wz[k, 0] - wz[k, 2])
        buf_boards.clear()
        buf_idx.clear()

    i = 0
    t0 = time.time()
    for gi, r in enumerate(groups):
        try:
            pb = chess.Board(r["fen"])
        except Exception:
            # still must advance i for the moves we counted -> but we counted
            # len(moves); skip whole group consistently by NOT counting it.
            # To keep indices aligned we instead fill zeros; simplest: re-handle
            # by writing zeros for these children.
            for _ in r["moves"]:
                targets[i] = 0.0; gid[i] = gi; proof[i] = 0; baseval[i] = 0.0
                i += 1
            continue
        for m in r["moves"]:
            uci, tgt, mevals, mpf = m[0], float(m[1]), int(m[2]), int(m[3])
            try:
                cb = pb.copy()
                cb.push(chess.Move.from_uci(uci))
            except Exception:
                targets[i] = tgt; gid[i] = gi; proof[i] = mpf; baseval[i] = 0.0
                i += 1
                continue
            buf_boards.append(cb)
            buf_idx.append(i)
            targets[i] = tgt
            gid[i] = gi
            proof[i] = mpf
            i += 1
            if len(buf_boards) >= B:
                flush()
        if (gi & 4095) == 0 and gi:
            el = time.time() - t0
            rate = i / max(el, 1e-6)
            print(f"  group {gi}/{len(groups)}  child {i}/{N}  "
                  f"{rate:.0f}/s  eta {((N - i) / max(rate,1)):.0f}s", flush=True)
    flush()
    feats.flush()
    np.savez(os.path.join(OUTDIR, "meta.npz"),
             targets=targets, gid=gid, proof=proof, baseval=baseval,
             N=np.int64(N), dfeat=np.int64(DFEAT))
    print(f"DONE: {N} feature rows in {time.time()-t0:.0f}s -> {OUTDIR}")


if __name__ == "__main__":
    main()
