"""Belief algebra over (win, draw, loss) outcome distributions.

Every value in the lattice is a belief about the game outcome from the
perspective of the side to move at that node. value = W - L in [-1, 1];
variance is the variance of the outcome random variable r in {+1, 0, -1}:
Var[r] = (W + L) - (W - L)^2. Exact results (checkmate, stalemate, proven
positions) are the same datatype with variance zero.
"""

from __future__ import annotations

WDL = tuple  # (w, d, l), nonnegative, sums to ~1

WIN: WDL = (1.0, 0.0, 0.0)
DRAW: WDL = (0.0, 1.0, 0.0)
LOSS: WDL = (0.0, 0.0, 1.0)


def value(wdl: WDL) -> float:
    return wdl[0] - wdl[2]


def variance(wdl: WDL) -> float:
    w, _, l = wdl
    v = w - l
    return max(0.0, (w + l) - v * v)


def flip(wdl: WDL) -> WDL:
    """The same belief seen by the other player."""
    return (wdl[2], wdl[1], wdl[0])


def normalize(wdl: WDL) -> WDL:
    w, d, l = (max(0.0, x) for x in wdl)
    s = w + d + l
    if s <= 1e-9:
        return DRAW
    return (w / s, d / s, l / s)
