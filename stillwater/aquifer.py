"""The Aquifer: the engine's own results outlive the game.

The proof ledger persists THEOREMS (what is forced). The Aquifer persists
OUTCOMES (what actually scored) -- a compounding opening memory of how THIS
engine, with THIS net and search, has historically fared after each early move.
lc0 discards its tree every move and starts every game blank; the Aquifer is a
slope only a persistent belief engine can climb.

It is a READOUT-ONLY steering asset: among opening moves the search already rates
as value-admissible (within a small band of the best settled value), prefer the
one whose realized score for us is best -- by a Wilson lower bound, so a thin or
cold entry shrinks to baseline and the engine plays exactly as if the book were
empty. It can never sacrifice objective value (band-gated) and never poisons the
relaxation or the proof ledger.

Keyed by EPD (piece placement + side + castling + ep -- not the move clocks), so
the SAME key is computed offline from PGNs and online from the live board, with
no dependence on the core's salted position-key scheme. Built offline from the
bot's game records by tools/build_aquifer.py; rebuild as games accumulate.
"""
from __future__ import annotations

import math
import os
import time

import numpy as np

FORMAT_VERSION = 2
CAP = 500_000


def default_path() -> str:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "aquifer.npz")


def wilson_lcb(games: int, score_sum: float, z: float = 1.0) -> float:
    """Lower confidence bound on the realized score in [0,1]. Shrinks toward 0
    with few games, so a cold/thin entry never out-ranks a well-sampled one and a
    book with no evidence == baseline."""
    if games <= 0:
        return 0.0
    n = float(games)
    p = max(0.0, min(1.0, score_sum / n))
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = p + z2 / (2.0 * n)
    margin = z * math.sqrt(max(0.0, p * (1.0 - p) / n + z2 / (4.0 * n * n)))
    return (centre - margin) / denom


def load(path: str | None = None) -> dict:
    """epd -> {move_uci: (games, score_sum, opp_elo_sum)}. Empty if no/stale book."""
    path = path or default_path()
    try:
        with np.load(path, allow_pickle=False) as z:
            if int(z["version"][0]) != FORMAT_VERSION:
                return {}
            epds = z["epds"]
            moves = z["moves"]
            games = z["games"]
            scores = z["scores"]
            oelo = z["opp_elo"]
    except Exception:
        return {}
    out: dict[str, dict[str, tuple]] = {}
    for e, m, g, s, o in zip(epds, moves, games, scores, oelo):
        out.setdefault(str(e), {})[str(m)] = (int(g), float(s), float(o))
    return out


def save(book: dict, path: str | None = None) -> int:
    """Persist a {epd: {move: (games, score_sum, opp_elo_sum)}} book; returns rows."""
    path = path or default_path()
    rows = [(e, m, g, s, o)
            for e, mv in book.items()
            for m, (g, s, o) in mv.items()]
    if len(rows) > CAP:
        rows.sort(key=lambda r: r[2], reverse=True)   # keep the best-sampled
        rows = rows[:CAP]
    n = len(rows)
    epds = np.array([r[0] for r in rows], dtype="<U92")
    moves = np.array([r[1] for r in rows], dtype="<U6")
    games = np.fromiter((r[2] for r in rows), dtype=np.uint32, count=n)
    scores = np.fromiter((r[3] for r in rows), dtype=np.float32, count=n)
    oelo = np.fromiter((r[4] for r in rows), dtype=np.float32, count=n)
    tmp = f"{path}.{os.getpid()}.{time.monotonic_ns()}.tmp"
    written = tmp + ".npz"
    try:
        np.savez_compressed(tmp, version=np.array([FORMAT_VERSION], dtype=np.int64),
                            epds=epds, moves=moves, games=games, scores=scores,
                            opp_elo=oelo)
        for attempt in range(4):
            try:
                os.replace(written, path)
                break
            except PermissionError:
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
