"""The settling engine and the broker.

Settling: beliefs relax toward the fixed point of the discounted distributional
negamax operator. Nothing recurses over a tree — a dirty queue (prioritized
sweeping) re-backs-up any node whose belief moved and enqueues its parents, so
a refutation discovered at the frontier reaches the root in one prioritized
pass. The per-ply discount gamma makes the operator a contraction: repetition
cycles damp toward zero (a draw) instead of oscillating, and nearer mates
score above farther ones for free.

Broker: chooses which leaves to buy next. Selection descends the lattice by
settled value + prior-weighted exploration + an uncertainty bonus; proven
subtrees price at zero (no information left to buy there). This is the v0
stand-in for trajectory-head pricing — reach x expected-revision / cost.
"""

from __future__ import annotations

import heapq
import math

import chess

from .beliefs import flip, variance as wdl_variance
from .lattice import Lattice, Node, position_key

GAMMA = 0.997          # per-ply discount: contraction + prefer-shorter-wins
SETTLE_EPS = 0.004     # belief moves smaller than this don't propagate
FPU_PENALTY = 0.10     # unexpanded moves priced at parent belief minus this
C_PUCT = 1.7           # prior-weighted exploration
C_VAR = 0.35           # uncertainty bonus on under-evidenced children
VLOSS = 0.85           # in-flight penalty so one GPU batch diversifies
MLH_W = 0.12           # conversion urge: how much moves-left scales value
MLH_SCALE = 80.0       # moves-left horizon beyond which the urge vanishes
DRAWISH = 0.5          # |value| <= this: a proof of a draw, clock-independent
EPS_BASE = 0.06        # widest honest-value sacrifice the Mirror may ever make,
                       # scaled down by opponent strength (0 against a perfect foe)
RHO_GATE = 0.90        # no trap band at all unless the opponent is DEMONSTRABLY
                       # fallible: vs near-perfect opposition even a hair of
                       # band lets the engine decline repetition draws forever,
                       # compounding micro-sacrifices into ground-down losses
                       # (game 2 vs SF-3190L, June 11 — 259 plies, -1.7 to 0-1)
TRAP_MARGIN = 0.02     # within the band, deviating from the honest-best move
                       # requires at least this much promised exploit edge —
                       # never trade real value for phantom trap value
LENS_W = 0.10          # the Lens: liveliness preference. The engine stores
                       # (W,D,L) but compared only W-L, so "equal but alive"
                       # (W=.30 D=.55 L=.15) and "equal and dead" (W=.15 D=.85
                       # L=0) were indistinguishable and the engine never
                       # resisted drifting into dead draws. At comparison sites
                       # OUR moves earn + LENS_W * P(we win), trading at most a
                       # few centi-value to keep winning chances on the board.
LENS_FLOOR = -0.05     # no liveliness bonus when clearly worse: a losing side
                       # WANTS the draw mass it still has


def proof_trusted_at(node, headroom_plies: int) -> bool:
    """Does this proof actually hold given the live 50-move clock? (the envelope)

    Keys deliberately alias positions within a 16-ply fifty-move bucket, so a
    'mate in 14' proven on one path can be reached on another with only a few
    plies of headroom, where the 50-move rule draws first. A draw proof is
    immune (the rule cannot un-draw a draw); a win/loss proof holds only if the
    result lands before the clock expires. Consumers that decide or stop check
    this; the broker leaves interior propagation clock-naive and self-corrects
    at the frontier.
    """
    if not node.proof:
        return False
    if abs(node.value) <= DRAWISH:
        return True
    return node.proof_dist <= headroom_plies


def eff_value(v: float, mlh: float) -> float:
    """Comparison value with the conversion urge applied.

    WDL saturates when a position is clearly won: 'win in 10' and 'win in 60'
    are both value ~1.0, so a winning engine drifts. The moves-left head
    breaks the tie: multiplying |v| up as predicted game length shrinks makes
    the winning side prefer the FASTEST win and the losing side prefer the
    SLOWEST loss (both fall out of one formula because v carries the sign).
    Only comparisons use this; stored beliefs stay honest.
    """
    return v * (1.0 + MLH_W * max(0.0, 1.0 - mlh / MLH_SCALE))


class SettlingEngine:
    """Prioritized dirty-queue relaxation over the lattice."""

    def __init__(self, lattice: Lattice):
        self.lattice = lattice
        self._heap: list = []
        self._seq = 0
        self.backups = 0
        # Set per search by the engine. root_turn + opp_rho drive the Mirror's
        # second value field; opp_rho == 1.0 (a perfect opponent) makes v_them
        # collapse to value and the extra work is skipped entirely. lens_on
        # enables the liveliness preference at OUR decision nodes.
        self.root_turn = True
        self.opp_rho = 1.0
        self.lens_on = True

    def mark_dirty(self, key: int, priority: float) -> None:
        self._seq += 1
        heapq.heappush(self._heap, (-priority, self._seq, key))

    def backup(self, node: Node) -> float:
        """Recompute node's belief from its children. Returns |delta value|."""
        if node.proof or not node.moves:
            return 0.0
        lattice = self.lattice
        rho = self.opp_rho
        # The Mirror runs ONLY when its output can influence a decision (the
        # trap band opens below RHO_GATE). backup() is the engine's hottest
        # CPU loop: computing v_them against opponents the gate ignores taxed
        # every settle ~50% for zero benefit and measurably weakened play.
        mirror = rho < RHO_GATE
        opp_node = mirror and (node.turn != self.root_turn)
        # The Lens applies only where WE choose, and ONLY against a
        # demonstrably fallible opponent (same gate as the Mirror): liveliness
        # is exploitation. At fixed W-L, a sharper position has more W *and*
        # more L, and which side cashes them depends on who converts errors
        # better — measured 0-2-8 vs SF-3190L when ungated (June 11), because
        # the stronger calculator wins sharp arguments. At opponent nodes the
        # backup must keep predicting THEIR best reply honestly regardless.
        lens = self.lens_on and rho < RHO_GATE and (node.turn == self.root_turn)
        best_q = None
        best_eff = None
        best_child = None
        any_unexpanded = False
        all_proven = True
        any_path_cond = False           # do consulted children carry history?
        them_q = []                     # per-move v_them values, when mirroring
        them_p = []                     # aligned move priors
        for idx, ck in enumerate(node.child_keys):
            child = lattice.get(ck)
            if child is None:
                any_unexpanded = True
                all_proven = False
                if mirror:
                    them_q.append(node.raw_value)
                    them_p.append(node.priors[idx])
                continue
            if not child.proof:
                all_proven = False
            if child.path_cond:
                any_path_cond = True
            q = -GAMMA * child.value
            qe = -GAMMA * eff_value(child.value, child.mlh)
            if lens and qe > LENS_FLOOR:
                qe += LENS_W * child.wdl[2]   # child stm = them; their L = our W
            if best_eff is None or qe > best_eff:
                best_q = q
                best_eff = qe
                best_child = child
            if mirror:
                them_q.append(-GAMMA * child.v_them)
                them_p.append(node.priors[idx])
        if any_unexpanded:
            # Unexplored moves stay alive at the oracle's own belief about this
            # node: the net's value already assumes best play, so the frontier
            # never collapses onto a poor explored subset.
            q0 = node.raw_value
            q0e = eff_value(node.raw_value, node.raw_mlh)
            if lens and q0e > LENS_FLOOR:
                q0e += LENS_W * node.raw_wdl[0]   # raw_wdl is in node's own stm
            if best_eff is None or q0e > best_eff:
                best_q = q0
                best_eff = q0e
                best_child = None

        old = node.value
        node.value = best_q
        if best_child is not None:
            node.wdl = flip(best_child.wdl)
            node.variance = best_child.variance
            node.mlh = best_child.mlh + 1.0
            # Proof propagation: a proven losing child (for the mover there)
            # proves this node won regardless of unexplored siblings; an
            # entirely proven move list proves the exact max. proof_dist counts
            # the plies to the result along the winning/maximal line, so the
            # 50-move envelope can be checked wherever the proof is consumed.
            if (best_child.proof and best_q > 0.5) or all_proven:
                node.proof = True
                node.variance = 0.0
                node.proof_dist = best_child.proof_dist + 1
                # A proof inherits path-conditioning from every child its
                # derivation consulted: the win rule rests on best_child, the
                # all-proven rule on all of them. Tainted theorems are true
                # only for this game's history and never enter the ledger.
                if all_proven:
                    node.path_cond = node.path_cond or any_path_cond
                else:
                    node.path_cond = node.path_cond or best_child.path_cond
        else:
            node.wdl = node.raw_wdl
            node.variance = wdl_variance(node.raw_wdl)
            node.mlh = node.raw_mlh

        # The Mirror: value assuming we keep playing best while the opponent
        # plays fallibly. At our nodes we still take the max; at opponent nodes
        # we take the expectation over their move distribution — best move with
        # probability rho, else spread over the policy prior. rho -> 1 makes
        # this a point mass on their best move, i.e. v_them == value, so the
        # whole feature vanishes against a perfect opponent.
        if mirror and them_q:
            if opp_node:
                qbest = max(them_q)
                tot = sum(them_p) or 1.0
                blend = sum(q * p for q, p in zip(them_q, them_p)) / tot
                node.v_them = rho * qbest + (1.0 - rho) * blend
            else:
                node.v_them = max(them_q)
        else:
            node.v_them = node.value

        # Draw-in-hand: at a claimable position the mover takes
        # max(claim = 0, best playing-on move). Flooring after the backup
        # keeps the operator a contraction (max(0, .) is non-expansive). A
        # fully-proven losing subtree resolves to a proven CLAIMED draw.
        if node.claim_floor and node.value < 0.0:
            node.value = 0.0
            w, d, l = node.wdl
            node.wdl = (w, d + l, 0.0)
            node.v_them = max(0.0, node.v_them)
            if node.proof:
                node.proof_dist = 0
        self.backups += 1
        return abs(node.value - old)

    def settle(self, max_ops: int = 20000) -> int:
        """Drain the dirty queue (bounded); returns number of backups done."""
        done = 0
        lattice = self.lattice
        while self._heap and done < max_ops:
            _, _, key = heapq.heappop(self._heap)
            node = lattice.get(key)
            if node is None:
                continue
            delta = self.backup(node)
            done += 1
            if delta > SETTLE_EPS:
                for pk in node.parents:
                    self.mark_dirty(pk, delta)
        return done


class Broker:
    """Selects batches of frontier leaves to evaluate, and links/creates
    terminal nodes encountered on the way (exact beliefs, variance zero)."""

    def __init__(self, lattice: Lattice, settler: SettlingEngine,
                 strict_draws: bool = False):
        self.lattice = lattice
        self.settler = settler
        self.strict_draws = strict_draws
        self.vloss: dict[tuple[int, int], int] = {}  # (node_key, move_idx) -> in-flight count
        self.terminals_found = 0
        self.tb = None          # optional TablebaseProber (Syzygy proof oracle)
        self.tb_hits = 0

    def reset_flight(self) -> None:
        self.vloss.clear()

    def _score_moves(self, node: Node):
        """Score every move at a node; returns (best_idx, child_or_None)."""
        lattice = self.lattice
        sqrt_n = math.sqrt(node.evals + 1)
        best_s = -1e9
        best_i = -1
        best_child = None
        for i, ck in enumerate(node.child_keys):
            child = lattice.get(ck)
            if child is None:
                q = node.raw_value - FPU_PENALTY
                u = C_PUCT * node.priors[i] * sqrt_n
            else:
                if child.proof:
                    # Nothing left to learn there; usable for value, not for search.
                    continue
                q = -GAMMA * eff_value(child.value, child.mlh)
                u = (C_PUCT * node.priors[i] * sqrt_n / (1 + child.evals)
                     + C_VAR * math.sqrt(child.variance / (1 + child.evals)))
            q -= VLOSS * self.vloss.get((node.key, i), 0)
            s = q + u
            if s > best_s:
                best_s = s
                best_i = i
                best_child = child
        return best_i, best_child

    def _terminal_value(self, board: chess.Board) -> float | None:
        """Exact result for the side to move, or None if not terminal here.
        Repetition/fifty-move are judged on the true path (the board carries
        real game history), which is where they are decidable.

        ONLY rules that end the game with no choice are terminals: checkmate,
        stalemate, dead position, 75-move, fivefold. Threefold and 50-move are
        CLAIMS — the side to move may take the draw or play on, so they are
        floors handled at node creation/backup, not exact results. (Treating
        them as terminals cost a rook on lichess: the engine 'drew' by walking
        into a third occurrence, and the opponent declined by capturing.)
        With strict_draws (cutechess-style arbiter that auto-adjudicates),
        claims become terminals again, matching that referee's actual rules.
        """
        if not any(board.generate_legal_moves()):
            return -1.0 if board.is_check() else 0.0   # mate / stalemate
        if board.is_insufficient_material():
            return 0.0
        if board.halfmove_clock >= 150:
            return 0.0                                 # 75-move rule: automatic
        if board.halfmove_clock >= 8 and board.is_repetition(5):
            return 0.0                                 # fivefold: automatic
        if self.strict_draws:
            if board.halfmove_clock >= 100:
                return 0.0
            if board.halfmove_clock >= 8 and board.is_repetition(3):
                return 0.0
        return None

    @staticmethod
    def claimable_draw(board: chess.Board) -> bool:
        """The side to move could claim a draw here (3-fold or 50-move)."""
        return (board.halfmove_clock >= 100
                or (board.halfmove_clock >= 8 and board.is_repetition(3)))

    def select(self, board: chess.Board, root_key: int, want: int):
        """Descend up to `want` times; returns list of (leaf_board_copy,
        parent_key, move_idx, path_keys). Terminal discoveries are settled
        immediately and don't consume batch slots."""
        out = []
        out_keys = set()
        misses = 0
        lattice = self.lattice
        while len(out) < want and misses < want * 2 + 8:
            node = lattice.get(root_key)
            if node is None or node.proof or not node.moves:
                break
            path = [root_key]
            seen = {root_key}
            pushed = 0
            try:
                leaf = None
                while True:
                    i, child = self._score_moves(node)
                    if i < 0:
                        # every move proven: this node will settle to proof itself
                        self.settler.mark_dirty(node.key, 1.0)
                        misses += 1
                        break
                    board.push(node.moves[i])
                    pushed += 1
                    if child is not None:
                        if child.key in seen or len(path) > 128:
                            # Search-path repetition: by the contraction theorem
                            # this line settles toward a draw; don't walk in
                            # circles waiting for it. (Also breaks the bucket-7
                            # halfmove trap where key salting can't split.)
                            self.settler.mark_dirty(node.key, 0.5)
                            misses += 1
                            break
                        node = child
                        path.append(node.key)
                        seen.add(node.key)
                        continue
                    # Unevaluated edge. Terminal, transposition, or fresh leaf?
                    tv = self._terminal_value(board)
                    # A claimable draw (3-fold/50-move) is NOT a terminal: the
                    # mover chooses max(claim, play on). It gets the rep salt
                    # so this path-dependent state never aliases the base
                    # position, and a claim_floor flag the node will carry.
                    claim = (tv is None and not self.strict_draws
                             and self.claimable_draw(board))
                    rep = claim or (tv == 0.0 and not (
                        board.is_stalemate() or board.is_insufficient_material()
                    ) and not board.is_checkmate())
                    key = position_key(board, rep=rep)
                    if tv is not None:
                        term = lattice.get(key)
                        if term is None:
                            term = Node.make_terminal(key, tv, turn=board.turn)
                            if rep:
                                # repetition/clock draws depend on history the
                                # key only partially encodes: game-local truth
                                term.path_cond = True
                            lattice.put(term)
                            self.terminals_found += 1
                        term.parents.add(node.key)
                        node.child_keys[i] = key
                        self.settler.mark_dirty(node.key, 1.0)
                        misses += 1
                        break
                    existing = lattice.get(key)
                    if existing is not None:
                        # Transposition: link and keep descending through it.
                        node.child_keys[i] = key
                        existing.parents.add(node.key)
                        self.settler.mark_dirty(node.key, 0.5)
                        if key in seen or len(path) > 128:
                            misses += 1
                            break
                        node = existing
                        path.append(key)
                        seen.add(key)
                        continue

                    # Tablebase: a proof oracle. Inside its piece bound, probe
                    # instead of spending a GPU slot; the result enters as an
                    # exact (variance-zero) pinned belief and proof-propagates
                    # rootward. This is the same terminal-admission seam — a
                    # tablebase hit is just a guess at its highest precision.
                    # Claimable positions are skipped: TB values ignore claim
                    # rights, and the mover may prefer the draw in hand.
                    if self.tb is not None and not claim and self.tb.probeable(board):
                        tbres = self.tb.probe(board)
                        if tbres is not None:
                            tv_tb, dist_tb, mlh_tb = tbres
                            tnode = Node.make_tablebase(
                                key, tv_tb, dist_tb, mlh_tb, turn=board.turn)
                            lattice.put(tnode)
                            self.tb_hits += 1
                            tnode.parents.add(node.key)
                            node.child_keys[i] = key
                            self.settler.mark_dirty(node.key, 1.0)
                            misses += 1
                            break
                    if key in out_keys:
                        # Already in this batch via another path; penalize and retry.
                        self.vloss[(node.key, i)] = self.vloss.get((node.key, i), 0) + 1
                        misses += 1
                        break
                    leaf = (key, board.copy(stack=8), node.key, i, tuple(path),
                            claim)
                    break
                if leaf is not None:
                    self.vloss[(leaf[2], leaf[3])] = self.vloss.get((leaf[2], leaf[3]), 0) + 1
                    out.append(leaf)
                    out_keys.add(leaf[0])
            finally:
                for _ in range(pushed):
                    board.pop()
        return out
