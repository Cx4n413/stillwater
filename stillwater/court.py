"""The Root Court: stopping as inference, time management as a corollary.

The court maintains a posterior over which root move is actually best
(each candidate's value modeled as Normal(settled value, variance scaled by
evidence mass), sampled jointly) and the engine moves the instant
P(current argmax is truly best) clears a clock-derived bar. Recaptures
resolve in milliseconds because the posterior snaps; critical decisions
absorb banked time because it refuses to. No move-time heuristics exist
anywhere else in the engine.
"""

from __future__ import annotations

import os

import numpy as np

from .search import (DRAWISH, GAMMA, LENS_FLOOR, LENS_W, eff_value,
                     proof_trusted_at)

SAMPLES = 1500
TAU2 = 0.0009          # irreducible doubt about any settled value
EARLY_STOP_P = 0.93    # before soft budget: stop if this confident
LATE_STOP_P = 0.55     # after soft budget: keep thinking only if truly torn
EXTEND_FACTOR = 1.6    # how far past soft budget confusion may carry us
MIN_SPEND = float(os.environ.get("STILLWATER_MIN_SPEND", "0.0"))
# Verify-draw gate (STILLWATER_VERIFY_DRAW): minimum FRESH, court-directed
# evals that must re-validate a root DRAW PROOF on the LIVE position before
# that proof may (a) end deliberation, (b) force min_work, or (c) break the
# think loop on an empty selection. 0 = legacy (a draw proof snaps instantly,
# exactly as today). The loss forensic found the DOMINANT snap mechanism is
# the draw-proof/COARSER50 bypass: a PATH-CONDITIONAL repetition draw (SW's
# own descent walked a cycle assuming the opponent cooperates; under the
# placement StrictDraws config an n=3 becomes a hard draw terminal) returns
# proven at the root and ends thinking at depth 1, ~70% of the clock unspent.
# CRITICAL: this delay fires ONLY when the proof is PATH-CONDITIONAL
# (path_cond, the Rust root_info 7th flag). UNCONDITIONAL draws (insufficient
# material, 50-move, stalemate, dead TB) are NOT delayed -- they snap as
# today -- so VERIFY_DRAW never burns the clock on a draw it cannot re-refute.
# A SOUND win/loss proof (|value|>DRAWISH with a valid 50-move envelope) and
# only-moves are NEVER gated. The delay never REFUSES a genuine forced draw:
# once fresh>=VERIFY_DRAW the proof is honored exactly as before, and a losing
# mover's claim_floor/perpetual-check defense is a CORE-side floor untouched
# by this root-proof stop.
VERIFY_DRAW = int(os.environ.get("STILLWATER_VERIFY_DRAW", "0"))
# Spend cap for the verify-draw delay (mirrors MIN_SPEND's elapsed-fraction
# guard): the delay is also released once elapsed >= VERIFY_DRAW_FRAC*soft so
# it can NEVER drain the bank on a position it cannot re-refute, independent
# of the empty_streak>=3 and hard-time escapes.
VERIFY_DRAW_FRAC = float(os.environ.get("STILLWATER_VERIFY_DRAW_FRAC", "0.25"))
# Spend-the-bank floor: minimum fraction of the soft budget to invest on a
# non-forced, unproven, equal-or-worse root before a confidence stop is allowed.
# 0.0 = legacy (snap as soon as confident). The loss forensic found SW snapping
# decisive equal positions in <1s with ~70% of its clock unspent (games 6/11);
# set ~0.3-0.4 to force it to actually look for a holding/saving resource.
# Game 1 vs SF-3000 lesson: at ~350 evals/s, "torn" is the common case in the
# middlegame; a generous extension drains the whole clock by move 30 and the
# endgame is then played on starvation rations. Bank time instead.


class RootCourt:
    def __init__(self, seed: int = 0x57111):
        self.rng = np.random.default_rng(seed)
        self.last_p_best = 0.0

    def root_stats(self, lattice, root, headroom=100, board=None, lens=False):
        """(moves, q, var, evidence, proven_win_idx) for evaluated root children.
        A win/loss proof whose fifty-move envelope is violated on this path is
        scored as the draw it really is, and is not counted as a proven win."""
        moves, qs, vs, ns = [], [], [], []
        proven_win = -1
        for i, ck in enumerate(root.child_keys):
            child = lattice.get(ck)
            if child is None:
                continue
            # zeroing moves (captures/pawn pushes) reset the fifty-move clock
            if board is not None and board.is_zeroing(root.moves[i]):
                child_hr = 100
            else:
                child_hr = headroom - 1
            cval = child.value
            demoted = (child.proof and abs(child.value) > DRAWISH
                       and not proof_trusted_at(child, child_hr))
            if demoted:
                cval = 0.0
            # eff keeps the court's argmax consistent with _best_move's choice
            q = -GAMMA * eff_value(cval, child.mlh)
            if lens and not demoted and q > LENS_FLOOR:
                q += LENS_W * child.wdl[2]    # same Lens as _best_move
            moves.append(root.moves[i])
            qs.append(q)
            vs.append(child.variance)
            ns.append(child.evals)
            if (child.proof and -GAMMA * child.value > 0.5
                    and proof_trusted_at(child, child_hr)):
                proven_win = len(moves) - 1
        return moves, np.array(qs), np.array(vs), np.array(ns), proven_win

    def p_best(self, qs: np.ndarray, vs: np.ndarray, ns: np.ndarray) -> float:
        """P(current argmax is truly best) by joint posterior sampling."""
        if len(qs) <= 1:
            return 1.0
        std = np.sqrt(vs / (1.0 + ns) + TAU2)
        draws = self.rng.normal(qs, std, size=(SAMPLES, len(qs)))
        wins = np.bincount(np.argmax(draws, axis=1), minlength=len(qs))
        p = wins[int(np.argmax(qs))] / SAMPLES
        self.last_p_best = float(p)
        return self.last_p_best

    def should_stop(self, lattice, root, elapsed, soft, hard, min_work_done,
                    headroom=100, board=None, lens=False, fresh=None,
                    pc=None) -> bool:
        if elapsed >= hard:
            return True
        moves, qs, vs, ns, proven = self.root_stats(lattice, root, headroom,
                                                    board, lens)
        if not moves:
            return False
        # Split the root proof into a SOUND-decisive branch (|value|>DRAWISH
        # with a valid 50-move envelope -- always ends deliberation) and a
        # DRAW branch (|value|<=DRAWISH). Under VERIFY_DRAW a PATH-CONDITIONAL
        # draw proof must first be re-bought with `fresh` court-directed evals
        # on the live position before it may stop. `pc` is the path_cond flag
        # (pure-Python: root.path_cond; Rust engine threads flags[6]); when pc
        # is None we fall back to root.path_cond. UNCONDITIONAL draws snap as
        # today. Bounded by VERIFY_DRAW_FRAC*soft so it cannot drain the bank.
        sound_proven = (root.proof and abs(root.value) > DRAWISH
                        and proof_trusted_at(root, headroom))
        draw_proven = root.proof and abs(root.value) <= DRAWISH
        path_cond = getattr(root, "path_cond", False) if pc is None else pc
        if (VERIFY_DRAW > 0 and fresh is not None and draw_proven
                and path_cond and not sound_proven
                and fresh < VERIFY_DRAW and elapsed < VERIFY_DRAW_FRAC * soft):
            draw_proven = False               # not yet re-validated: keep thinking
        if proven >= 0 or sound_proven or draw_proven:
            return True                       # a theorem ends deliberation
        if len(root.moves) == 1 and min_work_done:
            return True                       # only move: snap
        if not min_work_done:
            return False
        # Spend-the-bank floor (STILLWATER_MIN_SPEND): a saturated shallow
        # lattice can clear the confidence bar in <1s and snap a decisive move
        # with the clock full -- the forensic game-6 loss class (0.79s, ~640s
        # banked). On a NON-forced, UNPROVEN, not-clearly-winning root (equal or
        # moderately worse), invest >= MIN_SPEND*soft hunting a holding/saving
        # resource before any confidence stop. Proven theorems and only-moves
        # already returned above; clearly-won roots use the lens; clearly-lost
        # roots may still snap.
        if MIN_SPEND > 0.0 and -0.6 < root.value < 0.2 and elapsed < MIN_SPEND * soft:
            return False
        early, late = EARLY_STOP_P, LATE_STOP_P
        if lens and hard > 2.0 * soft and 0.2 < root.value < 0.9:
            # Conversion investment: a fat bank (pondering keeps it fat) plus a
            # winning-but-unproven position is exactly where precision decides
            # the half point — demand more certainty before moving. The old
            # bars never spent the surplus, because a slowly-converting win is
            # "clear" move-to-move and the court only extended when torn.
            early, late = 0.97, 0.75
        elif MIN_SPEND > 0.0 and -0.6 < root.value <= 0.2:
            # Symmetric to the conversion lens: on equal-or-worse criticals,
            # demand more certainty too (spend the bank to find the hold).
            early, late = max(early, 0.97), max(late, 0.70)
        # Throughput guard: a fast engine reaches 0.93 confidence in a
        # fraction of its budget and would bank time it never spends —
        # thinking LESS per move than a slower engine. Before half the soft
        # budget, only near-certainty may stop (forced recaptures still hit
        # it instantly; merely-confident positions convert speed into depth).
        if elapsed < 0.5 * soft:
            early = max(early, 0.985)
        p = self.p_best(qs, vs, ns)
        if elapsed < soft:
            return p >= early
        if elapsed < min(hard, soft * EXTEND_FACTOR):
            return p >= late                  # torn -> spend banked time
        return True

    @staticmethod
    def budgets(wtime=None, btime=None, winc=0, binc=0, side_white=True,
                movetime=None, moves_played=0) -> tuple[float, float]:
        """(soft, hard) seconds derived from the clock.

        Sustainability rule learned the hard way (runs 1-2 vs SF-3000):
        games here run 60-90 of our moves, so the per-move ration is
        clock/horizon with a horizon that shrinks as the game ages, and
        extensions beyond the ration are a luxury permitted only while at
        least ~8 such thinks remain banked. Steady state must never spend
        faster than the increment refills.
        """
        if movetime is not None:
            t = movetime * 0.95
            return t, t
        clock = wtime if side_white else btime
        inc = winc if side_white else binc
        if clock is None:
            return 5.0, 15.0                  # analysis default
        horizon = max(24.0, 64.0 - moves_played)
        soft = clock / horizon + 0.8 * inc
        rich = clock > 8.0 * soft
        # Safe no-flag cap. The deeper-budget experiment (2.2x/clock9) flagged
        # ~40% of games at 60+1 (0-7-3 over 10) — depth-via-budget is a dead
        # end. The real regression was the CUDA backend's GPU memory leak, not
        # the clock; this cap just needs to never flag.
        hard = soft * (1.5 if rich else 1.2)
        hard = min(hard, clock / 12.0)
        margin = max(0.08, clock * 0.04)
        soft = min(soft, max(0.05, clock - margin))
        hard = min(hard, max(0.05, clock - margin))
        return soft, max(soft, hard)
