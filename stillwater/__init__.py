"""STILLWATER — the engine that thinks by letting the water settle.

A chess engine with no game tree: a position-keyed belief lattice relaxed to
its fixed point by prioritized distributional backups. A neural guess, a lesson
learned mid-move, and an exact terminal result are the same object at three
precisions — a belief with variance, a belief whose variance is being updated,
and a belief with variance zero.
"""

__version__ = "0.1.0"
