"""Syzygy tablebases as a proof oracle.

The lattice already treats an exact result as a belief with variance zero, and
the settling engine already propagates such proofs rootward and lets the court
end deliberation the instant one reaches the root. A Syzygy tablebase is simply
a vast store of those exact results for positions with few enough pieces, so it
plugs into the same seam the engine uses for checkmates and stalemates — no
score-vs-window reconciliation, no special case in the search.

The 50-move rule is handled honestly. ``probe_wdl`` answers as if the halfmove
clock were zero; a win it reports is REAL only if the conversion's
distance-to-zeroing-move (DTZ) fits inside the live 50-move headroom, otherwise
the rule turns it into a draw (a "cursed win"). We resolve that here, against
the board's actual clock, and emit:

  * a win/loss as a proof of reach |DTZ| plies (the headroom the win needs),
  * a cursed win / blessed loss / true draw as a clock-independent draw proof.

If no tablebases are installed, :func:`open_tablebase` returns ``None`` and the
engine runs exactly as before.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

import chess
import chess.syzygy


class TablebaseProber:
    """Wraps a ``chess.syzygy.Tablebase`` with the engine's proof conventions."""

    def __init__(self, tablebase, max_men: int = 5):
        self._tb = tablebase
        self.max_men = max_men
        self.probes = 0

    def probeable(self, board: chess.Board) -> bool:
        # Syzygy tables do not encode castling rights; skip those rare <=Nman
        # positions rather than feed the prober something it cannot answer.
        return (chess.popcount(board.occupied) <= self.max_men
                and not board.castling_rights)

    def probe(self, board: chess.Board) -> Optional[Tuple[float, int, float]]:
        """Return (value_for_stm, proof_dist_plies, moves_left) or None.

        value_for_stm is +1 (win), 0 (draw / cursed), or -1 (loss), from the
        side-to-move's perspective. proof_dist is the 50-move headroom the
        result requires (0 for a draw). moves_left feeds the conversion urge.
        """
        try:
            wdl = self._tb.probe_wdl(board)          # -2..2, 50-move-naive
        except (KeyError, chess.syzygy.MissingTableError, ValueError):
            return None
        self.probes += 1
        if wdl == 0 or wdl == 1 or wdl == -1:
            # true draw, cursed win, or blessed loss — all draws under the rule
            return 0.0, 0, 1.0
        # A clean win (2) or loss (-2): does the live clock permit it?
        try:
            dtz = self._tb.probe_dtz(board)          # signed plies to zeroing
        except (KeyError, chess.syzygy.MissingTableError, ValueError):
            # WDL-only tables: cannot bound the envelope, so don't over-claim a
            # proof. Report a draw rather than an unsafe win. (Install DTZ
            # tables to convert these.)
            return 0.0, 0, 1.0
        need = abs(int(dtz))
        headroom = 100 - board.halfmove_clock
        if need > headroom:
            # The 50-move rule draws before the conversion lands: a cursed win.
            return 0.0, 0, 1.0
        return (1.0 if wdl > 0 else -1.0), need, float(need)

    def close(self) -> None:
        try:
            self._tb.close()
        except Exception:
            pass


def _has_tables(path: str) -> bool:
    try:
        for name in os.listdir(path):
            if name.endswith((".rtbw", ".rtbz")):
                return True
    except OSError:
        return False
    return False


def open_tablebase(path: Optional[str], max_men: int = 5
                   ) -> Optional[TablebaseProber]:
    """Open a directory of Syzygy tables, or return None if unavailable.

    Resolution order for ``path``: the explicit argument, then the
    ``STILLWATER_SYZYGY`` environment variable, then a ``syzygy`` folder beside
    the package. A directory with no ``.rtbw`` files yields None.
    """
    if path and path.strip().lower() in ("none", "off", "<none>"):
        return None          # explicit ablation: ignore any installed tables
    if not path:
        path = os.environ.get("STILLWATER_SYZYGY", "")
    if not path:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for cand in (os.path.join(here, "syzygy"),
                     os.path.join(here, "nets", "syzygy")):
            if os.path.isdir(cand):
                path = cand
                break
    if not path or not os.path.isdir(path) or not _has_tables(path):
        return None
    try:
        tb = chess.syzygy.open_tablebase(path)
    except Exception:
        return None
    return TablebaseProber(tb, max_men=max_men)
