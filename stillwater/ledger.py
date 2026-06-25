"""The Proof Ledger: theorems outlive the game.

A proven node is exact — a forced mate, a forced draw, a tablebase fact —
and its position key already carries every condition the proof depends on
(fifty-move bucket salt, repetition salt). So unlike beliefs, proofs can be
persisted verbatim and reloaded into any later game: the engine accumulates
a personal endgame tablebase of everything it has ever proven.

Safety rails (each one earned):
  * Only transferable theorems are accepted — the ENGINE filters out proofs
    of trivial reach, proofs conditioned on a game's path history (claim
    rights / repetition ancestry: the Ra8 class), and proofs so deep that the
    discounted value would be misread as a draw on reload.
  * Engines running with strict_draws (cutechess arbiter semantics) neither
    read nor write the ledger: an arbiter-mode "automatic threefold draw" is
    NOT a theorem under claim semantics.
  * The file carries a salt fingerprint: if the key-salting scheme ever
    changes, old ledgers are discarded instead of aliasing wrong positions.
  * Saves write to a per-writer temp file and replace atomically (with retry
    for Windows sharing violations); concurrent saves cannot corrupt the
    file. The merge itself is last-writer-wins per save, which can drop a
    sibling process's newest theorems — accepted and documented.
"""

from __future__ import annotations

import os
import time
import numpy as np

from .lattice import _R50_SALTS, _REP_SALT

CAP = 2_000_000          # entries on disk; ~50MB at the cap, years of play
SEED_CAP = 250_000       # max entries seeded into one game's lattice
FORMAT_VERSION = 1
# If the salting scheme changes, every stored key means a different position.
SALT_FINGERPRINT = np.uint64(FORMAT_VERSION) ^ np.uint64(_R50_SALTS[1]) \
    ^ np.uint64(_REP_SALT)
# Key-scheme variants (coarse r50 bucketing, R_COARSER50) fold into the
# fingerprint: ledgers never transfer across schemes (keys would alias).
_SCHEME_MIX = np.uint64(0x9E3779B97F4A7C15)


def _fp(scheme: int) -> np.uint64:
    return SALT_FINGERPRINT ^ (np.uint64(scheme & 0xFFFF) * _SCHEME_MIX)


def default_path() -> str:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "proof_ledger.npz")


def load(path: str | None = None, scheme: int = 0) -> dict:
    """key -> (value, proof_dist, mlh, turn). Empty dict if no/stale ledger."""
    path = path or default_path()
    try:
        with np.load(path) as z:
            if np.uint64(z["fingerprint"][0]) != _fp(scheme):
                return {}        # different salting scheme: keys are aliases
            keys = z["keys"]
            vals = z["vals"]
            dists = z["dists"]
            mlhs = z["mlhs"]
            turns = z["turns"]
        out = {int(k): (float(v), int(d), float(m), bool(t))
               for k, v, d, m, t in zip(keys, vals, dists, mlhs, turns)}
        if len(out) > SEED_CAP:
            # bound per-game seeding cost; keep the deepest (most expensive
            # to rediscover) theorems
            items = sorted(out.items(), key=lambda kv: kv[1][1], reverse=True)
            out = dict(items[:SEED_CAP])
        return out
    except Exception:
        return {}


def save(proofs: dict, path: str | None = None, scheme: int = 0) -> int:
    """Merge `proofs` into the ledger on disk; returns total entries kept."""
    path = path or default_path()
    merged = load(path, scheme)
    merged.update(proofs)
    if len(merged) > CAP:
        # keep the deepest theorems — they are the expensive ones to rediscover
        items = sorted(merged.items(), key=lambda kv: kv[1][1], reverse=True)
        merged = dict(items[:CAP])
    n = len(merged)
    keys = np.fromiter(merged.keys(), dtype=np.uint64, count=n)
    vals = np.fromiter((v[0] for v in merged.values()), dtype=np.float32,
                       count=n)
    dists = np.fromiter((v[1] for v in merged.values()), dtype=np.uint16,
                        count=n)
    mlhs = np.fromiter((v[2] for v in merged.values()), dtype=np.float32,
                       count=n)
    turns = np.fromiter((v[3] for v in merged.values()), dtype=np.uint8,
                        count=n)
    # per-writer temp name: concurrent saves must never share scratch files
    tmp = f"{path}.{os.getpid()}.{time.monotonic_ns()}.tmp"
    written = tmp + ".npz"               # np.savez appends .npz to non-.npz names
    try:
        np.savez_compressed(tmp, fingerprint=np.array([_fp(scheme)],
                                                      dtype=np.uint64),
                            keys=keys, vals=vals, dists=dists,
                            mlhs=mlhs, turns=turns)
        for attempt in range(4):
            try:
                os.replace(written, path)
                break
            except PermissionError:
                # Windows: destination briefly open elsewhere (a sibling's
                # load). Short retry; give up quietly after that.
                if attempt == 3:
                    raise
                time.sleep(0.05)
    except Exception:
        try:
            os.remove(written)
        except OSError:
            pass
        return 0
    return n
