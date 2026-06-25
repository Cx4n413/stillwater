"""Palimpsest layer: the evaluator rewrites itself during the move.

v0 is the context-gated scalar form of the architecture's Bayesian linear
layer: per (pawn structure x material x side) context, a conjugate Normal
posterior over a correction to the oracle's value, updated in closed form
from settled-search-vs-raw-eval disagreements at well-evidenced nodes, and
applied (shrunk by its own uncertainty) to every future evaluation in the
same context — re-pricing positions the search has never visited. The full
512-d feature-space version arrives with the trained Oracle; the seam and
the ablation flag are what v0 must get right.
"""

from __future__ import annotations

import chess

PRIOR_VAR = 0.02 ** 2 * 25          # prior: corrections are usually small
OBS_VAR = 0.18 ** 2                  # one search lesson is a noisy teacher
MAX_CORRECTION = 0.12                # never let memory overrule the net by much
MIN_EVIDENCE = 3                     # observations before a context speaks


def context_key(board: chess.Board) -> tuple:
    return (
        int(board.pieces_mask(chess.PAWN, chess.WHITE)),
        int(board.pieces_mask(chess.PAWN, chess.BLACK)),
        # material signature: counts per (piece, color)
        tuple(
            chess.popcount(board.pieces_mask(pt, color))
            for color in (chess.WHITE, chess.BLACK)
            for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
        ),
        board.turn,
    )


class Palimpsest:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.store: dict[tuple, list] = {}   # context -> [n, sum_y]
        self.observations = 0

    def observe(self, context: tuple, lesson: float) -> None:
        """lesson = settled value - raw value, in the node-stm perspective."""
        if not self.enabled or context is None:
            return
        cell = self.store.get(context)
        if cell is None:
            self.store[context] = [1, lesson]
        else:
            cell[0] += 1
            cell[1] += lesson
        self.observations += 1

    def correction(self, context: tuple) -> float:
        """Posterior-mean correction, shrunk toward 0 by remaining uncertainty."""
        if not self.enabled or context is None:
            return 0.0
        cell = self.store.get(context)
        if cell is None or cell[0] < MIN_EVIDENCE:
            return 0.0
        n, total = cell
        # Conjugate Normal posterior mean with known obs noise:
        post_mean = (total / OBS_VAR) / (1.0 / PRIOR_VAR + n / OBS_VAR)
        return max(-MAX_CORRECTION, min(MAX_CORRECTION, post_mean))

    def clear(self) -> None:
        self.store.clear()
        self.observations = 0
