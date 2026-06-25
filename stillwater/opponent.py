"""The Effigy: an in-game model of how fallible the opponent is.

Like the Palimpsest, this is a small posterior learned mid-game from cheap
observations and discarded at game end. The observation is free here in a way
no tree engine gets: because the lattice persists across moves, the position
the opponent just moved from is usually still resident with its children
already evaluated, so we can see at once whether their move was best, fine, or
a clear error — no extra search.

The model is one number: rho in [0, 1], the probability the opponent finds the
best move (rho = 1 is perfect play). It drives two things downstream — the
Mirror's opponent move distribution, and how far the engine may stray from the
objectively-best move to pose practical problems.

It begins certain the opponent is strong (rho = 1 until evidence arrives) so
that against an unknown or strong opponent the engine's behaviour is exactly
what it was before this model existed. Only demonstrated mistakes unlock
exploitation — the same machinery that wins more against weak players keeps the
engine honest against Stockfish, which it quickly concludes does not err.
"""

from __future__ import annotations

import math


class OpponentModel:
    PRIOR_A = 4.0          # pseudo-observations of "played the best move"
    PRIOR_B = 0.6          # pseudo-observations of "erred"  (prior mean ~0.87)
    SCALE = 0.15           # value gap (stm units) that reads as a clear error
    DEADZONE = 0.06        # gaps below this are OUR estimation noise, not their
                           # error: at ~450 evals/s the search's own value noise
                           # makes perfect moves measure a few centi-values
                           # "worse than best" — counting that as fallibility
                           # made the model exploit opponents who never blunder
    MIN_OBS = 4            # moves observed before the model dares to speak

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.a = self.PRIOR_A
        self.b = self.PRIOR_B
        self.observations = 0

    def rho(self) -> float:
        """Posterior-mean P(opponent plays best). 1.0 until evidence exists, so
        the engine assumes a perfect opponent — and behaves identically to its
        opponent-blind self — until the opponent proves otherwise. Disabling
        the model pins it at 1.0 (the ablation baseline)."""
        if not self.enabled or self.observations < self.MIN_OBS:
            return 1.0
        return self.a / (self.a + self.b)

    def observe(self, gap: float) -> None:
        """Fold in one opponent move. gap = (best child value) - (their move's
        value), in side-to-move units, >= 0. A gap near 0 is evidence of best
        play; a large gap is evidence of an error, weighted smoothly so that a
        single second-best move barely moves the estimate while a blunder does.
        """
        if not self.enabled:
            return
        # Inside the deadzone the move is indistinguishable from best play.
        excess = max(0.0, gap - self.DEADZONE)
        s = math.exp(-excess / self.SCALE)          # 1.0 = best, -> 0 = worse
        self.a += s
        self.b += 1.0 - s
        self.observations += 1

    def clear(self) -> None:
        self.a = self.PRIOR_A
        self.b = self.PRIOR_B
        self.observations = 0
