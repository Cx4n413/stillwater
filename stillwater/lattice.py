"""The Lattice: a position-keyed store of beliefs with parent back-pointers.

There is no tree. Nodes are keyed by position (Zobrist, salted with a
fifty-move-counter bucket and a repetition flag so the legality-relevant
state splits the key), so transpositions merge, the whole table survives
from move to move, and "re-rooting" after the opponent replies is a no-op.
Parent back-pointers exist so that when a belief changes, the consequences
can be propagated rootward by the settling engine's dirty queue.
"""

from __future__ import annotations

import random

import chess
import chess.polyglot

from .beliefs import DRAW, LOSS, WIN, value as wdl_value, variance as wdl_variance

_rng = random.Random(0x57111A7E)
# Salts for halfmove-clock buckets (0-15, 16-31, ..., 112+): positions that are
# transpositions on the board but differ materially in fifty-move distance get
# distinct entries instead of poisoning each other.
_R50_SALTS = [0] + [_rng.getrandbits(64) for _ in range(7)]
# Salt for "this position was reached as a path repetition" terminal nodes.
_REP_SALT = _rng.getrandbits(64)


def position_key(board: chess.Board, rep: bool = False,
                 coarse: bool = False) -> int:
    # `coarse` mirrors the Rust core's R_COARSER50 (keys.rs::position_key_c):
    # below halfmove-clock 64 ALL maneuvering positions share bucket 0 instead
    # of the fine 16-ply buckets. coarse=False (default) reproduces the legacy
    # fine-only key byte-for-byte. MUST stay bit-identical to keys.rs:
    #   bucket = 0 if (coarse and clk < 64) else min(clk >> 4, 7).
    # The pure-Python engine.py/search.py lattice stores FINE keys, so they
    # MUST keep calling this with coarse left False; only engine_rs.py (which
    # keys into the Rust core's lattice) passes coarse. NOTE: R_FINER50 has no
    # Python keyer because the Python engine never runs the coarse core.
    if coarse and board.halfmove_clock < 64:
        bucket = 0
    else:
        bucket = min(board.halfmove_clock >> 4, 7)
    key = chess.polyglot.zobrist_hash(board)
    key ^= _R50_SALTS[bucket]
    if rep:
        key ^= _REP_SALT
    return key


class Node:
    __slots__ = (
        "key",        # position key
        "wdl",        # current settled belief (w, d, l), stm perspective
        "value",      # settled scalar, kept consistent with backups (discounted)
        "variance",   # uncertainty of the settled belief
        "raw_value",  # oracle output + palimpsest correction at creation time
        "raw_wdl",    # oracle WDL as evaluated
        "evals",      # oracle evaluations in this node's subtree (evidence mass)
        "moves",      # tuple of legal moves
        "priors",     # list of policy priors aligned with moves
        "child_keys", # list aligned with moves; None until that child is evaluated
        "parents",    # set of parent keys (back-pointers for the dirty queue)
        "terminal",   # None, or exact value for stm (terminal/proven leaf)
        "claim_floor",# the mover can CLAIM a draw here (3-fold/50-move): the
                      # value is floored at 0 for the mover, but it is NOT a
                      # terminal — a winning mover declines the claim and plays
                      # on (the Ra8 lesson: lichess has no arbiter, only claims)
        "path_cond",  # this belief depends on PATH history (repetition counts,
                      # claim rights) that its own key cannot fully represent:
                      # true for rep-salted terminals and claim nodes, and it
                      # propagates through proof derivation. Path-conditioned
                      # proofs are theorems about THIS game's history only and
                      # must never be persisted to the cross-game ledger.
        "proof",      # True => belief is exact, variance 0, never re-evaluated
        "proof_dist", # plies from here to the proven result (the proof's reach);
                      # checked against 50-move headroom by consumers (the envelope)
        "turn",       # True if WHITE to move here (chess.WHITE); the Mirror's
                      # backup operator differs at our-move vs opponent-move nodes
        "v_them",     # settled value assuming WE play best, THEY play fallibly
                      # (the Mirror); equals `value` when the opponent is optimal
        "context",    # palimpsest context key (pawn structure x material x stm)
        "observed",   # palimpsest has already ingested this node's lesson
        "mlh",        # settled moves-left estimate (conversion compass)
        "raw_mlh",    # oracle's moves-left at evaluation time
    )

    def __init__(self, key, wdl, raw_value, moves, priors, context, mlh=60.0,
                 turn=True):
        self.key = key
        self.wdl = wdl
        self.raw_wdl = wdl
        self.raw_value = raw_value
        self.value = raw_value
        self.variance = wdl_variance(wdl)
        self.evals = 1
        self.moves = moves
        self.priors = priors
        self.child_keys = [None] * len(moves)
        self.parents = set()
        self.terminal = None
        self.claim_floor = False
        self.path_cond = False
        self.proof = False
        self.proof_dist = 0
        self.turn = turn
        self.v_them = raw_value
        self.context = context
        self.observed = False
        self.mlh = mlh
        self.raw_mlh = mlh

    @classmethod
    def make_terminal(cls, key, result_for_stm: float, turn=True) -> "Node":
        """Exact leaf: checkmate (-1 for the mated side), stalemate/draw (0).
        A terminal is a proof of reach 0 — it is happening on the board now,
        so its validity envelope is trivially satisfied at any clock."""
        wdl = LOSS if result_for_stm < 0 else DRAW
        node = cls(key, wdl, result_for_stm, (), [], None, mlh=0.0, turn=turn)
        node.value = result_for_stm
        node.v_them = result_for_stm
        node.variance = 0.0
        node.terminal = result_for_stm
        node.proof = True
        node.proof_dist = 0
        node.evals = 0
        return node

    @classmethod
    def make_tablebase(cls, key, value_for_stm: float, dist: int, mlh: float,
                       turn=True) -> "Node":
        """A Syzygy probe is a proof oracle: an exact win/draw/loss with no
        further search needed. `dist` is the distance-to-zeroing-move (DTZ) in
        plies for a win/loss — the 50-move headroom the conversion requires.
        Cursed wins / blessed losses arrive here already collapsed to draws
        (value 0), so their envelope is clock-independent like any draw."""
        if value_for_stm > 0.5:
            wdl = WIN
        elif value_for_stm < -0.5:
            wdl = LOSS
        else:
            wdl = DRAW
        node = cls(key, wdl, value_for_stm, (), [], None,
                   mlh=max(0.0, mlh), turn=turn)
        node.value = value_for_stm
        node.v_them = value_for_stm
        node.variance = 0.0
        node.terminal = value_for_stm
        node.proof = True
        node.proof_dist = max(0, int(dist))
        node.evals = 0
        return node


class Lattice:
    def __init__(self, max_nodes: int = 2_500_000):
        self.nodes: dict[int, Node] = {}
        self.max_nodes = max_nodes
        self.evictions = 0

    def __len__(self) -> int:
        return len(self.nodes)

    def get(self, key) -> Node | None:
        if key is None:
            return None
        return self.nodes.get(key)

    def put(self, node: Node) -> None:
        self.nodes[node.key] = node

    def clear(self) -> None:
        self.nodes.clear()

    def over_capacity(self) -> bool:
        return len(self.nodes) > self.max_nodes
