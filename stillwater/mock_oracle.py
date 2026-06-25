"""A deliberately dumb oracle (material + light mobility, capture-biased
priors) so the lattice, settling engine, broker, court, and UCI layer can be
developed and unit-tested without the GPU. If search-over-mock finds mates
and wins material that the mock eval itself cannot see, the substrate works.
"""

from __future__ import annotations

import math

import chess

PIECE_VALUE = {
    chess.PAWN: 1.0, chess.KNIGHT: 3.05, chess.BISHOP: 3.25,
    chess.ROOK: 5.0, chess.QUEEN: 9.2, chess.KING: 0.0,
}


class OracleEval:
    __slots__ = ("wdl", "value", "policy", "mlh")

    def __init__(self, wdl, value, policy, mlh=60.0):
        self.wdl = wdl
        self.value = value
        self.policy = policy
        self.mlh = mlh


class MockOracle:
    def evaluate(self, boards):
        return [self._one(b) for b in boards]

    def _one(self, board: chess.Board) -> OracleEval:
        moves = list(board.legal_moves)
        if not moves:
            return OracleEval((0.0, 1.0, 0.0), 0.0, {}, 0.0)
        mat = 0.0
        for pt, val in PIECE_VALUE.items():
            mat += val * (chess.popcount(board.pieces_mask(pt, board.turn))
                          - chess.popcount(board.pieces_mask(pt, not board.turn)))
        v = math.tanh(mat / 4.0 + 0.01 * len(moves) * (1 if mat >= 0 else -1))
        d = 0.35 * (1.0 - abs(v))
        w = (1.0 + v) / 2.0 * (1.0 - d)
        l = max(0.0, 1.0 - d - w)
        weights = {}
        for m in moves:
            wgt = 1.0
            if board.is_capture(m):
                wgt += 3.0
            if m.promotion == chess.QUEEN:
                wgt += 6.0
            if board.gives_check(m):
                wgt += 2.0
            weights[m] = wgt
        s = sum(weights.values())
        policy = {m: wg / s for m, wg in weights.items()}
        mlh = 20.0 + 60.0 * (1.0 - abs(v))   # decisive positions end sooner
        return OracleEval((w, d, l), w - l, policy, mlh)
