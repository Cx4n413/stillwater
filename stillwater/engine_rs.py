"""RustEngine: the compiled STILLWATER core driven through the same think()
protocol as the Python Engine.

Division of labor: Rust (stillwater_core) owns everything per-node — movegen,
the lattice, settling, selection, plane encoding, Syzygy probes, palimpsest
arithmetic. Python keeps everything per-move or per-batch: the DirectML
oracle session, the Root Court, clock budgets, the Effigy, the trap band and
Lens at the decision site, panic floor, pondering, the Distillery and the
Proof Ledger. The loop is serial (select -> infer -> integrate): selection
costs single-digit milliseconds in Rust, so pipelining no longer pays.
"""

from __future__ import annotations

import math
import os
import time

import chess
import chess.syzygy
import numpy as np

import stillwater_core

from . import ledger
from .court import (EARLY_STOP_P, EXTEND_FACTOR, LATE_STOP_P, MIN_SPEND,
                    VERIFY_DRAW, VERIFY_DRAW_FRAC, RootCourt)
from .distillery import Distillery
from .lattice import position_key
from .opponent import OpponentModel
from .search import (DRAWISH, EPS_BASE, GAMMA, LENS_FLOOR, LENS_W, RHO_GATE,
                     TRAP_MARGIN, eff_value)

LESSON_EVIDENCE = 32
LEDGER_MAX_DIST = 180

# child tuple layout from core.root_children()/node_children()
(F_UCI, F_VAL, F_VTHEM, F_VAR, F_EVALS, F_PROOF, F_DIST, F_MLH,
 F_W, F_D, F_L, F_CLAIM) = range(12)


def _split_history(board: chess.Board):
    b = board.copy()
    moves = []
    while b.move_stack:
        moves.append(b.pop().uci())
    moves.reverse()
    return b.fen(), moves


def _syzygy_dir(explicit: str | None) -> str | None:
    if explicit and explicit.strip().lower() in ("none", "off", "<none>"):
        return None
    path = explicit or os.environ.get("STILLWATER_SYZYGY", "")
    if not path:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for cand in (os.path.join(here, "syzygy"),
                     os.path.join(here, "nets", "syzygy")):
            if os.path.isdir(cand):
                return cand
        return None
    return path if os.path.isdir(path) else None


def _trusted(proof: bool, value: float, dist: int, headroom: int) -> bool:
    if not proof:
        return False
    if abs(value) <= DRAWISH:
        return True
    return dist <= headroom


class RustEngine:
    def __init__(self, oracle=None, batch: int = 128, palimpsest_on: bool = True,
                 max_nodes: int = 2_500_000, syzygy_path: str | None = None,
                 opponent_model_on: bool = True, lens_on: bool = True,
                 strict_draws: bool = False, harvest_on: bool = True,
                 ledger_on: bool = True, proof_bursts: bool = True,
                 root_thompson: bool = False, corrector_on: bool = False,
                 refine: bool = False, draw_contempt: float = 0.0):
        # Gated draw contempt in value-units (0 == legacy). UCI DrawContempt is
        # centi-value (10 -> 0.10). Fight-when-winning / draw-when-equal; off by
        # default until the timed SF gauntlet clears the ship gate.
        self.draw_contempt = float(
            os.environ.get("STILLWATER_DRAW_CONTEMPT", draw_contempt))
        self.core = stillwater_core.Core(
            _syzygy_dir(syzygy_path), strict_draws, max_nodes, palimpsest_on, 5)
        self.proof_bursts = proof_bursts
        self.core.set_features(proof_bursts, root_thompson)
        # The Refine package (lc0-informed search semantics). Refine=true sets
        # the WAC-validated composition 0xAB = TEMP|CPUCT|MLH|GAMMA|TWOFOLD
        # (285/300 vs legacy 284). Excluded on per-bit tactical evidence:
        # R_UFLIGHT (-10: lc0's U-denominator collisions under-diversify our
        # 128-leaf serial batches; the evidence-damped Q-vloss stays),
        # R_FPU (-3) and R_LCB (-2) pending re-tune of their constants.
        # STILLWATER_REFINE_MASK overrides for attribution experiments.
        mask_env = os.environ.get("STILLWATER_REFINE_MASK", "")
        if mask_env:
            self.refine_mask = int(mask_env, 0)
        elif refine:
            # The parity-campaign package (C9): TEMP|CPUCT|FPU|MLH|LCB|GAMMA|
            # UFLIGHT|TWOFOLD|NOFLOOR|ROBUSTPICK|COARSER50. Validated vs
            # lc0-BT4 at fixed nodes: 79.2% -> 60.4% lc0 across iterations;
            # WAC 95 -> 98-99 at matched nodes.
            self.refine_mask = 0xBFF
        else:
            self.refine_mask = 0
        # rust bits: 0..8, 0x400 meanback, 0x800 coarse-r50 (0x200 = py pick)
        # rank-2 B: opt-in rep-floor forcibility (0x1000) and finer r50
        # buckets (0x2000), env-gated so the DEFAULT Rust mask is unchanged
        # (byte-identical to today). They are OR'd in only when explicitly
        # requested via env, never via the 0xBFF Refine package.
        rust_extra = 0
        if os.environ.get("STILLWATER_REPFORCE", "") not in ("", "0"):
            rust_extra |= 0x1000
        if os.environ.get("STILLWATER_FINER50", "") not in ("", "0"):
            rust_extra |= 0x2000
        # Structure lever (R_VISITREAD 0x4000): turns on the clean per-root-edge
        # visit counter in the rust core. STAGE 1 = counter + exposure only; the
        # readout stays on the shipped path (the visit-readout is a separate,
        # later Python gate). Default off = bit-identical.
        self.visit_readout = os.environ.get("STILLWATER_VISIT_READOUT", "") not in ("", "0")
        if self.visit_readout:
            rust_extra |= 0x4000
        self.core.set_refine((self.refine_mask & 0xDFF) | rust_extra)
        # Runtime tunables (no rebuild needed during constant sweeps).
        # Defaults = the parity-campaign tuned values; they only act when
        # the corresponding Refine bits are set.
        self.pick_k = float(os.environ.get("STILLWATER_PICK_K", "0.5"))
        # Policy-aware tie-break (value-first): among root moves whose settled
        # value is within this margin of the best, play the one BT4's POLICY
        # ranks highest, instead of the value-argmax / visit-tie-break. The
        # gap-decomposition (June 16) found ~63% of decisive losses are our
        # value-argmax readout DISCARDING the policy and tie-breaking to a worse
        # move on flat-value positions -- where the policy ranks SF's move #1
        # (median rank 1, 20/21) and lc0-on-BT4 (which reads out visits) plays
        # it (17/21). The margin is in value units; 0.0 == OFF (legacy). It is
        # eps-GATED so decisive tactical values (gap > margin) are NEVER
        # overridden -- the guard against the honest-max/VOI tactical crater.
        self.pol_tiebreak = float(os.environ.get("STILLWATER_POL_TIEBREAK", "0"))
        # Structure lever readout (active when self.visit_readout / R_VISITREAD):
        # value-first, then play the highest clean-per-root-edge VISIT-share move
        # (binomial lower bound, so thin moves can't win) among value-admissible
        # candidates (within vis_band of the LCB-max). Dual evidence floor
        # (vis_floor + vis_frac) falls back to the value-LCB pick when visits are
        # too thin to trust -- the low-visit guard. Band is FIXED/rho-independent
        # so the lever fires vs strong opponents (where eps collapses to 0).
        self.vis_k = float(os.environ.get("STILLWATER_VIS_K", "1.0"))
        self.vis_floor = int(os.environ.get("STILLWATER_VIS_FLOOR", "64"))
        self.vis_frac = float(os.environ.get("STILLWATER_VIS_FRAC", "0.10"))
        self.vis_band = float(os.environ.get("STILLWATER_VIS_BAND", "0.06"))
        # CONVERSION FIX (STILLWATER_CONVERT): the deployed bot drew dozens of
        # dead-won games by 3-fold -- up a queen, it shuffled its king aimlessly
        # because BT4's value SATURATES (every winning move ~equal) so there is
        # no gradient toward mate. Two gradients: (1) Syzygy DTZ-optimal play in
        # tablebase-won (<=5-man) positions, (2) a king-drive/progress heuristic
        # for >5-man won positions (drive the enemy king to the edge, bring our
        # king up, confine, prefer zeroing moves). Both value-gated so they never
        # sacrifice a tactic. Default off until gauntlet-confirmed.
        self.convert = os.environ.get("STILLWATER_CONVERT", "") not in ("", "0")
        self.convert_band = float(os.environ.get("STILLWATER_CONVERT_BAND", "0.10"))
        # ANTI-DRIFT readout (STILLWATER_ANTIDRIFT): the gap decomposition's biggest
        # decisive-loss bucket (49%, gap_depth_eval) is "depth_unstable" -- the search
        # finds SF's move M at a conviction rung then DRIFTS off it as it searches MORE
        # (M's backed-up value churns down on noise / an inferior sibling's LCB edges
        # past; M is still SF-best the whole time). This maintains a conviction
        # INCUMBENT through the search (the LCB-argmax once evals>=EFLOOR) and resists
        # abandoning it unless a challenger beats its CURRENT LCB by >= DELTA -- a
        # SIGNAL-gated hysteresis, never a blanket value floor (a blanket one re-creates
        # the q0-floor "deaf to bad news" regression; proofs + decisive gaps still flip
        # it). READOUT-ONLY: the backup is untouched. Default off until gauntlet-proven.
        self.antidrift = os.environ.get("STILLWATER_ANTIDRIFT", "") not in ("", "0")
        self.drift_delta = float(os.environ.get("STILLWATER_DRIFT_DELTA", "0.06"))
        self.drift_efloor = int(os.environ.get("STILLWATER_DRIFT_EFLOOR", "3000"))
        self._incumbent_uci = None
        # DISTRIBUTION-NATIVE RISK UTILITY (#1, STILLWATER_RISK=theta): the readout
        # plays the full (W,D,L) the search already produced instead of the W-L
        # mean it currently collapses to. Among value-admissible candidates
        # (within RISK_BAND of the best settled value -> a decisive tactic is a
        # singleton band and is NEVER overridden: the tactical-crater guard), play
        # the move maximizing  U = (1+max(0,-theta))*W_our - (1+max(0,theta))*L_our.
        #   theta < 0 -> RISK-SEEKING (fatten the win tail, accept the loss tail):
        #                convert more half-points vs a fallible opponent.
        #   theta > 0 -> RISK-AVERSE (shrink the loss tail): protect a lead / vs
        #                strong opposition.
        #   theta = 0 -> OFF, byte-identical (block skipped -> robustpick stands).
        # READOUT-ONLY: backup/search untouched, so it CANNOT detune the co-tuned
        # value distribution (the failure mode of value-recal). RISK_GATE picks
        # when it fires: always | weak (only vs proven-fallible rho<RHO_GATE, the
        # trap-band regime -> byte-identical vs strong) | strong (only vs strong).
        self.risk = float(os.environ.get("STILLWATER_RISK", "0"))
        self.risk_band = float(os.environ.get("STILLWATER_RISK_BAND", "0.10"))
        self.risk_gate = os.environ.get("STILLWATER_RISK_GATE", "always").strip().lower()
        # SELF-KNOWLEDGE LOSS-TAIL GOVERNOR (STILLWATER_GOVERNOR): the SAFE fragment
        # of the risk utility -- apply loss-aversion ONLY when WE are clearly ahead
        # (root value > GOV_AHEAD), where shrinking the give-back tail among
        # value-band-tied moves is pure upside (it attacks the documented won-game-
        # drawn-by-3fold conversion leak). This is NOT the blanket-averse posture,
        # which is MEASURED-NEGATIVE vs strong play (risk_vs_sf.log: averse 33.3%/
        # 21L vs base 40.2%/14L -- conceding variance in equal/worse positions loses
        # the grind to the better calculator). theta=0 unless ahead -> off is
        # byte-identical. Rides the lattice-unique full WDL + our own lead (self-
        # knowledge); no opponent model, nothing to overfit or transfer.
        self.governor = os.environ.get("STILLWATER_GOVERNOR", "") not in ("", "0")
        self.gov_ahead = float(os.environ.get("STILLWATER_GOV_AHEAD", "0.4"))
        self.gov_k = float(os.environ.get("STILLWATER_GOV_K", "2.0"))
        self.gov_theta_max = float(os.environ.get("STILLWATER_GOV_MAX", "1.0"))
        self._syzygy_path = _syzygy_dir(syzygy_path)
        self._tb = None
        self.core.set_tunables(
            float(os.environ.get("STILLWATER_LCB_K", "0.3")),
            float(os.environ.get("STILLWATER_FPU_RED", "0.2")),
            float(os.environ.get("STILLWATER_ML_THRESH", "0.8")),
            float(os.environ.get("STILLWATER_CPUCT_INIT", "1.745")),
            float(os.environ.get("STILLWATER_CPUCT_FACTOR", "3.894")),
            float(os.environ.get("STILLWATER_C_VAR", "0.35")),
            float(os.environ.get("STILLWATER_VLOSS_W", "0.85")))
        # Honest-max winner's-curse backup correction (0.0 == OFF/legacy).
        self.core.set_honest_k(float(os.environ.get("STILLWATER_HONEST_K", "0.0")))
        # Value-of-information selection (belief-driven descent). OFF == legacy
        # PUCT; ON replaces the descent rule and reads the propagated epistemic.
        if os.environ.get("STILLWATER_VOI", "0") == "1":
            self.core.set_voi(True)
        # Confidence-weighted backup: root cause of ~81% of decisive losses is the
        # MAX-backup over-trusting an over-estimated worst-case reply, tanking good
        # moves. Blend the adopted max toward the children-mean by the winning
        # child's uncertainty (thin -> mean, settled -> max). 0.0 == OFF (byte-id).
        self.core.set_confback(
            float(os.environ.get("STILLWATER_CONFBACK_W", "0.0")),
            float(os.environ.get("STILLWATER_CONFBACK_CAP", "0.0")))
        if corrector_on:
            try:
                here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                z = np.load(os.path.join(here, "corrector.npz"))
                self.core.set_corrector([float(x) for x in z["beta"]])
            except Exception:
                pass        # no trained corrector yet: run uncorrected
        self.court = RootCourt()
        self.opp_model = OpponentModel(opponent_model_on)
        self.distillery = Distillery(harvest_on)
        self.oracle = oracle
        self.batch = batch
        self.max_nodes = max_nodes
        self.lens_on = lens_on
        self.strict_draws = strict_draws
        self.total_evals = 0
        # coarse-r50 (0x800) is a DIFFERENT key scheme: the ledger fingerprint
        # carries the scheme id, so theorems never alias across modes (a
        # scheme switch starts a fresh ledger file).
        # rank-2 B: FINER50 (0x2000) is a DIFFERENT key scheme than plain
        # COARSER50 (0x800); fold BOTH into the ledger scheme id so a finer
        # ledger never aliases a coarse one (red-team ledger-aliasing guard).
        # FINER50 is enabled via the STILLWATER_FINER50 env (it is OR'd into the
        # core mask as 0x2000 above, NOT carried in refine_mask), so the scheme
        # id must consult the env to stay consistent with the active key scheme;
        # a refine_mask that already carries 0x2000 is also honored. Default off
        # for both -> ledger_scheme keeps its legacy value (byte-identical).
        finer50 = ((self.refine_mask & 0x2000) != 0
                   or os.environ.get("STILLWATER_FINER50", "") not in ("", "0"))
        self.ledger_scheme = ((1 if (self.refine_mask & 0x800) else 0)
                              | (2 if finer50 else 0))
        # Whether the Rust core stores COARSE r50 keys (R_COARSER50, 0x800).
        # _pv keys INTO the core's lattice for the DISPLAY pv only, so its
        # keying must match the core scheme or the pv truncates to depth 1.
        # This half is display-only and may follow 0x800 directly.
        self._coarse_keys = bool(self.refine_mask & 0x800)
        # note_opponent_move ALSO keys into the core, and it feeds
        # opp_model.rho() -> RHO_GATE/Lens/eps, which CAN drift move
        # selection. Because 0x800 is set under refine=True (the placement
        # config), making this coarse automatically would be a behavior
        # change in the running config. Gate the rho-affecting half behind
        # its OWN opt-in (default off) so placement stays byte-identical and
        # the rho change can be A/B'd independently.
        self._coarse_obs = (self._coarse_keys
                            and os.environ.get("STILLWATER_COARSE_OBS", "")
                            not in ("", "0"))
        self.ledger_on = ledger_on and not strict_draws
        self.ledger_seeded = 0
        self._seed_from_ledger()

    # ------------------------------------------------------------- plumbing

    def _ensure_oracle(self):
        if self.oracle is None:
            from .oracle import LeelaOracle
            self.oracle = LeelaOracle()
            if hasattr(self.oracle, "warmup"):
                self.oracle.warmup()
        return self.oracle

    def _seed_from_ledger(self) -> None:
        if not self.ledger_on:
            return
        entries = ledger.load(scheme=self.ledger_scheme)
        if not entries:
            return
        keys = np.fromiter(entries.keys(), dtype=np.uint64, count=len(entries))
        vals = np.fromiter((v[0] for v in entries.values()), dtype=np.float32,
                           count=len(entries))
        dists = np.fromiter((v[1] for v in entries.values()), dtype=np.uint16,
                            count=len(entries))
        mlhs = np.fromiter((v[2] for v in entries.values()), dtype=np.float32,
                           count=len(entries))
        turns = np.fromiter((v[3] for v in entries.values()), dtype=np.uint8,
                            count=len(entries))
        self.ledger_seeded += self.core.seed_proofs(keys, vals, dists, mlhs,
                                                    turns)

    def save_ledger(self) -> int:
        if not self.ledger_on:
            return 0
        k, v, d, m, t = self.core.export_proofs(LEDGER_MAX_DIST)
        k = np.asarray(k)
        if k.size == 0:
            return 0
        v, d, m, t = (np.asarray(v), np.asarray(d), np.asarray(m),
                      np.asarray(t))
        proofs = {int(k[i]): (float(v[i]), int(d[i]), float(m[i]), bool(t[i]))
                  for i in range(k.size)}
        return ledger.save(proofs, scheme=self.ledger_scheme)

    def new_game(self) -> None:
        self.save_ledger()
        self.core.clear(False)
        self.opp_model.clear()
        self.core.reset_flight()
        self._seed_from_ledger()

    def shutdown(self) -> None:
        try:
            self.save_ledger()
        except Exception:
            pass
        self.distillery.close()

    # -------------------------------------------------------------- oracle IO

    def _infer_pending(self, planes, n):
        """(policy, wdl, mlh) arrays for the pending batch. Real oracles get
        the pre-encoded planes; mock oracles get FEN boards."""
        oracle = self.oracle
        if hasattr(oracle, "infer_planes"):
            return oracle.infer_planes(np.asarray(planes), n)
        # mock path: evaluate FENs, convert move priors to logit vectors
        from .oracle import _MOVE_LUT
        fens = self.core.pending_fens()
        boards = [chess.Board(f) for f in fens]
        evs = oracle.evaluate(boards)
        policy = np.full((n, 1858), -80.0, dtype=np.float32)
        wdl = np.zeros((n, 3), dtype=np.float32)
        mlh = np.zeros(n, dtype=np.float32)
        for i, (b, ev) in enumerate(zip(boards, evs)):
            wdl[i] = ev.wdl
            mlh[i] = max(0.0, getattr(ev, "mlh", 60.0))
            for m, p in ev.policy.items():
                frm, to = m.from_square, m.to_square
                if b.is_castling(m) and not b.chess960:
                    to = chess.square(
                        7 if chess.square_file(to) > chess.square_file(frm)
                        else 0, chess.square_rank(frm))
                if b.turn == chess.BLACK:
                    frm ^= 56
                    to ^= 56
                promo = m.promotion
                if promo == chess.KNIGHT:
                    promo = None
                ix = _MOVE_LUT.get((frm, to, promo))
                if ix is not None:
                    policy[i, ix] = math.log(max(p, 1e-9))
        return policy, wdl, mlh

    # ----------------------------------------------------------- decisions

    def _scored_children(self, board: chess.Board, headroom: int, lens: bool):
        """[(q, qt, evals, uci, var, proof_dist, zeroing)] with envelopes/
        demotion/lens applied, plus the LIST of indices of trusted proven wins
        (was a single last-seen index -> the distance-blind bug) and raw stats
        arrays."""
        out = []
        proven_idxs = []
        qs, vs, ns = [], [], []
        for c in self.core.root_children():
            mv = chess.Move.from_uci(c[F_UCI])
            zeroing = board.is_zeroing(mv)
            child_hr = 100 if zeroing else headroom - 1
            demoted = (c[F_PROOF] and abs(c[F_VAL]) > DRAWISH
                       and not _trusted(True, c[F_VAL], c[F_DIST], child_hr))
            cval = 0.0 if demoted else c[F_VAL]
            cvt = 0.0 if demoted else c[F_VTHEM]
            q = -GAMMA * eff_value(cval, c[F_MLH])
            qt = -GAMMA * eff_value(cvt, c[F_MLH])
            if lens and not demoted and q > LENS_FLOOR:
                q += LENS_W * c[F_L]      # child's loss mass = our win mass
            if (c[F_PROOF] and -GAMMA * c[F_VAL] > 0.5
                    and _trusted(True, c[F_VAL], c[F_DIST], child_hr)):
                proven_idxs.append(len(out))
            # s[7:10] = our-perspective (win, draw, loss): the full distribution
            # the scalar mean q discards. Child's loss mass = our win mass (the
            # same perspective flip the Lens uses at F_L above). A DEMOTED proof
            # (a win the 50-move clock can't fund) is neutralized to a pure draw
            # so the risk readout treats it as the draw it really is -- mirroring
            # the cval=0 demotion above. Appended (not inserted) so s[0..6] are
            # unchanged and every default path is byte-identical when risk is off.
            cw, cd, cl = (0.0, 1.0, 0.0) if demoted else (c[F_L], c[F_D], c[F_W])
            out.append((q, qt, c[F_EVALS], c[F_UCI], c[F_VAR], c[F_DIST],
                        zeroing, cw, cd, cl))
            qs.append(q)
            vs.append(c[F_VAR])
            ns.append(c[F_EVALS])
        return out, proven_idxs, np.array(qs), np.array(vs), np.array(ns)

    def _get_tb(self):
        if self._tb is None and self._syzygy_path:
            try:
                self._tb = chess.syzygy.open_tablebase(self._syzygy_path)
            except Exception:
                self._tb = False
        return self._tb or None

    def _tb_best_move(self, board: chess.Board):
        """DTZ-optimal converting move when the side to move is tablebase-won.
        None if not a TB win / tables missing -> caller falls back. Prefers
        zeroing moves (reset the 50-move counter = guaranteed progress) then the
        fastest forced win; this is the gradient the saturated net value lacks."""
        tb = self._get_tb()
        if tb is None:
            return None
        try:
            if tb.probe_wdl(board) <= 0:        # not a win for the side to move
                return None
        except Exception:
            return None
        best_m = None
        best_key = None
        for m in board.legal_moves:
            z = board.is_zeroing(m)
            board.push(m)
            try:
                if board.is_checkmate():
                    board.pop()
                    return m
                opp_wdl = tb.probe_wdl(board)
                opp_dtz = tb.probe_dtz(board)
            except Exception:
                board.pop()
                continue
            board.pop()
            if opp_wdl is None or opp_wdl >= 0:   # move fails to keep the win
                continue
            key = (0 if z else 1, abs(opp_dtz) if opp_dtz is not None else 999)
            if best_key is None or key < best_key:
                best_key = key
                best_m = m
        return best_m

    @staticmethod
    def _cheby(a: int, b: int) -> int:
        return max(abs(chess.square_file(a) - chess.square_file(b)),
                   abs(chess.square_rank(a) - chess.square_rank(b)))

    def _progress(self, board: chess.Board, uci: str) -> float:
        """Conversion-progress score for a move when winning without a tablebase
        or forced-mate gradient: drive the enemy king to the edge, bring our king
        up, confine the enemy, prefer zeroing + checks. Higher = better. Hard-
        avoids stalemate / insufficient-material (never throw a won game)."""
        m = chess.Move.from_uci(uci)
        win = board.turn
        enemy = not win
        z = board.is_zeroing(m)
        chk = board.gives_check(m)
        board.push(m)
        try:
            if board.is_checkmate():
                return 1e9
            if board.is_stalemate() or board.is_insufficient_material():
                return -1e9
            ek = board.king(enemy)
            ok = board.king(win)
            ef, er = chess.square_file(ek), chess.square_rank(ek)
            edge = min(ef, 7 - ef, er, 7 - er)
            kk = self._cheby(ok, ek)
            enemy_mob = board.legal_moves.count()
        finally:
            board.pop()
        return (-4.0 * edge) + (-1.0 * kk) + (-0.25 * enemy_mob) \
            + (8.0 if z else 0.0) + (2.0 if chk else 0.0)

    def _update_incumbent(self):
        """Maintain the conviction INCUMBENT during the search: the LCB-argmax once
        evidence passed EFLOOR, switched away ONLY when a challenger beats the
        incumbent's CURRENT LCB by >= DRIFT_DELTA (decisive signal, not the noise
        churn that abandons a correctly-valued move). LCB, not raw value, so a thin
        inflated child cannot grab incumbency. Reads root_children only -> no search
        side-effects; called only when self.antidrift is on."""
        ch = self.core.root_children()
        if not ch:
            return

        def lcb(c):
            return (-c[F_VAL]) - self.pick_k / (1.0 + c[F_EVALS]) ** 0.5
        chal = max(ch, key=lcb)
        cu = chal[F_UCI]
        if self._incumbent_uci is None:
            self._incumbent_uci = cu                  # first conviction snapshot
            return
        if cu == self._incumbent_uci:
            return
        inc = next((c for c in ch if c[F_UCI] == self._incumbent_uci), None)
        inc_lcb = lcb(inc) if inc is not None else -1e9
        if lcb(chal) - inc_lcb >= self.drift_delta:
            self._incumbent_uci = cu                  # decisive overtake: follow it
        # else: non-decisive churn -> HOLD the incumbent (the anti-drift)

    def _gov_theta(self, root_value: float) -> float:
        """Loss-tail aversion strength for the self-knowledge governor: 0 unless we
        are clearly ahead (root_value > GOV_AHEAD), then ramps with our lead and
        caps at GOV_MAX. A bounded monotone function of our OWN value only -- nothing
        to overfit, nothing to transfer, fires only where giving back variance is
        pure upside."""
        return min(self.gov_theta_max,
                   self.gov_k * max(0.0, root_value - self.gov_ahead))

    def _best_move(self, board: chess.Board, headroom: int):
        rho = self.opp_model.rho()
        gate_open = rho < RHO_GATE
        # CONVERSION FIX #1: Syzygy DTZ-optimal play in tablebase-won (<=5-man)
        # positions -- the gradient toward mate that the saturated net value
        # lacks. Overrides all other readout logic when a clean TB win exists.
        if self.convert and chess.popcount(board.occupied) <= 5:
            tbm = self._tb_best_move(board)
            if tbm is not None:
                return tbm
        lens = self.lens_on and gate_open
        scored, proven_idxs, _, _, _ = self._scored_children(
            board, headroom, lens)
        if proven_idxs:
            # Among PROVEN wins, walk the SHORTEST proof (min proof_dist) so we
            # converge to mate monotonically and never let a far proof demote
            # past the 50-move headroom into a shuffle/3-fold draw. Tie-break:
            # higher value, then prefer a zeroing (progress) move. This was the
            # distance-blind bug: it kept the LAST proven child in move order,
            # so it threw won games away by repeating instead of converting.
            best = min(proven_idxs,
                       key=lambda i: (scored[i][5], -scored[i][0],
                                      not scored[i][6]))
            return chess.Move.from_uci(scored[best][3])
        if not scored:
            moves = self.core.root_moves()
            if not moves:
                return None
            best = max(moves, key=lambda m: m[1])
            return chess.Move.from_uci(best[0])
        if self.visit_readout:
            # STRUCTURE LEVER readout (lc0-style). Value-first: among moves whose
            # settled LCB is within a FIXED band of the best (so a decisive tactic
            # -- the unique LCB-max -> singleton band -> this is a no-op and the
            # value pick stands), play the highest VISIT-SHARE move by a binomial
            # LOWER bound (thin moves can't win the readout). Dual evidence floor
            # falls back to the value-LCB pick when visits are too thin to trust.
            # Visits are SEARCH-informed (a found tactic accrues them) -- the key
            # difference from the failed raw-policy tiebreak. Stage-1 verified the
            # clean visits point at SF's move 40% where value-argmax gets 2%.
            def _lcb(s):
                return s[0] - self.pick_k / (1.0 + s[2]) ** 0.5
            lcb_max = max(_lcb(s) for s in scored)
            lcb_pick = max(scored, key=lambda s: (_lcb(s), s[2]))
            vis = self.core.root_edge_visits()
            if len(vis) == len(scored) and scored:
                N = sum(vis)
                vmax = max(vis) if vis else 0
                uniform = 1.0 / len(scored)
                # GATE A: dual evidence floor -> else fall through to value-LCB
                if N > 0 and vmax >= self.vis_floor \
                        and (vmax / N) >= (uniform + self.vis_frac):
                    cands_i = [i for i, s in enumerate(scored)
                               if _lcb(s) >= lcb_max - self.vis_band]
                    if len(cands_i) >= 2:
                        def _vlcb(i):
                            sh = vis[i] / N
                            return sh - self.vis_k * (sh * (1.0 - sh) / N) ** 0.5
                        bi = max(cands_i, key=lambda i: (_vlcb(i), _lcb(scored[i]),
                                                         scored[i][2]))
                        chosen = scored[bi]
                        # The v_them trap-band is trappy-play vs FALLIBLE
                        # opponents only (gate_open). Vs strong play (gate
                        # closed, the gauntlet/structure regime) it must NOT
                        # override the visit pick -- doing so unconditionally was
                        # silently discarding ~5/55 of the recovery.
                        if gate_open:
                            best = max(scored, key=lambda s: (s[1], s[0], s[2]))
                            if best[1] - chosen[1] >= TRAP_MARGIN:
                                return chess.Move.from_uci(best[3])
                        return chess.Move.from_uci(chosen[3])
            return chess.Move.from_uci(lcb_pick[3])
        if self.pol_tiebreak > 0.0:
            # Value-first, POLICY breaks near-ties (see __init__). Among moves
            # within pol_tiebreak of the best settled value, play the one BT4's
            # policy ranks highest. Decisive value gaps (> margin) are untouched.
            qmax = max(s[0] for s in scored)
            cands = [s for s in scored if s[0] >= qmax - self.pol_tiebreak]
            if len(cands) > 1:
                pol = self._ensure_oracle().evaluate_one(board).policy
                pol = {(m.uci() if isinstance(m, chess.Move) else str(m)): p
                       for m, p in pol.items()}
                best = max(cands, key=lambda s: (pol.get(s[3], 0.0), s[0], s[2]))
            else:
                best = cands[0]
            return chess.Move.from_uci(best[3])
        if self.convert and chess.popcount(board.occupied) <= 10:
            # CONVERSION FIX #2: clearly winning in an endgame with no tablebase/
            # forced-mate gradient -- the saturated net value gives no reason to
            # prefer a converting move over an idle shuffle (the 3-fold bug).
            # Among moves within convert_band of the best settled value (a
            # decisive tactic -> singleton band -> untouched; never sacrifices
            # value), play the one that makes the most progress toward mate
            # (drive the enemy king to the edge, bring our king up, confine,
            # prefer zeroing + checks). Endgame-gated: winning middlegames, where
            # king-driving is wrong, are never disturbed.
            qv = max(s[0] for s in scored)
            if qv > 0.5:
                band = [s for s in scored if s[0] >= qv - self.convert_band]
                if len(band) > 1:
                    bp = max(band, key=lambda s: self._progress(board, s[3]))
                    return chess.Move.from_uci(bp[3])
        if self.risk != 0.0:
            # DISTRIBUTION-NATIVE RISK UTILITY (#1): re-rank the value-admissible
            # moves by a risk-posture utility over the full (W,D,L) the search
            # produced, rather than the W-L mean. Readout-only -> the search is
            # untouched. The band gate makes a decisive tactic a singleton (so it
            # is never overridden), exactly like the convert/pol-tiebreak guards.
            fire = (self.risk_gate == "always"
                    or (self.risk_gate == "weak" and gate_open)
                    or (self.risk_gate == "strong" and not gate_open))
            if fire:
                qmax = max(s[0] for s in scored)
                band = [s for s in scored if s[0] >= qmax - self.risk_band]
                if len(band) > 1:
                    w_w = 1.0 + max(0.0, -self.risk)   # seeking up-weights wins
                    w_l = 1.0 + max(0.0, self.risk)    # averse up-weights losses
                    bp = max(band, key=lambda s: (w_w * s[7] - w_l * s[9],
                                                  s[0], s[2]))
                    return chess.Move.from_uci(bp[3])
        if self.governor:
            # Self-knowledge loss-tail governor: ONLY when clearly ahead, pick the
            # lowest-loss-tail move among value-band-tied candidates -- pure-upside
            # variance reduction in won positions, where the engine currently bleeds
            # points (a won game shuffled into a 3-fold). Identity off / not ahead.
            theta = self._gov_theta(self.core.root_info()[0][0])
            if theta > 0.0:
                qmax = max(s[0] for s in scored)
                band = [s for s in scored if s[0] >= qmax - self.risk_band]
                if len(band) > 1:
                    w_l = 1.0 + theta
                    bp = max(band, key=lambda s: (s[7] - w_l * s[9], s[0], s[2]))
                    return chess.Move.from_uci(bp[3])
        eps = EPS_BASE * (1.0 - rho) if gate_open else 0.0
        if self.refine_mask & 0x200:
            # Robust pick (R_ROBUSTPICK): the move played is the one whose
            # LOWER confidence bound is best — a thinly-evaluated child with
            # an inflated value cannot win the argmax at the most expensive
            # decision in the engine (lc0 plays its most-visited move for
            # the same reason). Converges to the plain value pick as
            # evidence accumulates.
            def lcb(s):
                return s[0] - self.pick_k / (1.0 + s[2]) ** 0.5
            qmax = max(lcb(s) for s in scored)
            cands = [s for s in scored if lcb(s) >= qmax - eps]
            honest = max(cands, key=lambda s: (lcb(s), s[2]))
        else:
            qmax = max(s[0] for s in scored)
            cands = [s for s in scored if s[0] >= qmax - eps]
            honest = max(cands, key=lambda s: (s[0], s[2]))
        # ANTI-DRIFT end-gate: honor the conviction-incumbent maintained through the
        # search unless the natural objective pick beats it DECISIVELY (LCB margin
        # >= DELTA) in the FINAL children (re-checked here against the last batch).
        if self.antidrift and self._incumbent_uci is not None \
                and honest[3] != self._incumbent_uci:
            inc = next((s for s in scored if s[3] == self._incumbent_uci), None)
            if inc is not None:
                def _lv(s):
                    return s[0] - self.pick_k / (1.0 + s[2]) ** 0.5
                if _lv(honest) - _lv(inc) < self.drift_delta:
                    honest = inc
        best = max(cands, key=lambda s: (s[1], s[0], s[2]))
        if best[1] - honest[1] < TRAP_MARGIN:
            best = honest
        return chess.Move.from_uci(best[3])

    def _should_stop(self, board, headroom, elapsed, soft, hard,
                     min_work, fresh=None) -> bool:
        if elapsed >= hard:
            return True
        rho = self.opp_model.rho()
        lens = self.lens_on and rho < RHO_GATE
        scored, proven_idxs, qs, vs, ns = self._scored_children(
            board, headroom, lens)
        if not scored:
            return False
        (vals, flags) = self.core.root_info()
        root_value = vals[0]
        # flags = (proof, proof_dist, evals, claim_floor, exists, has_moves,
        # [path_cond]). path_cond is the additive 7th element from Fix C-Rust;
        # tolerate a pre-rebuild 6-tuple (path_cond defaults False -> no delay,
        # byte-identical). SOUND decisive proof = |value|>DRAWISH with a valid
        # 50-move envelope (flags[1]<=headroom): always snaps. A PATH-
        # CONDITIONAL draw proof is delayed under VERIFY_DRAW until `fresh`
        # evals re-validate it on the live position (bounded by
        # VERIFY_DRAW_FRAC*soft). Unconditional draws snap as today.
        path_cond = flags[6] if len(flags) > 6 else False
        sound_proven = (flags[0] and abs(root_value) > DRAWISH
                        and flags[1] <= headroom)
        draw_proven = flags[0] and abs(root_value) <= DRAWISH
        if (VERIFY_DRAW > 0 and fresh is not None and draw_proven
                and path_cond and not sound_proven
                and fresh < VERIFY_DRAW and elapsed < VERIFY_DRAW_FRAC * soft):
            draw_proven = False               # keep thinking until re-validated
        if proven_idxs or sound_proven or draw_proven:
            return True
        n_root_moves = len(self.core.root_moves())
        if n_root_moves == 1 and min_work:
            return True
        if not min_work:
            return False
        # Spend-the-bank floor (STILLWATER_MIN_SPEND): forensic game-6 class --
        # a saturated shallow lattice clears the confidence bar in <1s and snaps
        # a decisive move with the clock full (0.79s, ~640s banked). On a
        # NON-forced, UNPROVEN, not-clearly-winning root (equal or moderately
        # worse), invest >= MIN_SPEND*soft before any confidence stop. Proven
        # theorems and only-moves already returned above; winning roots use the
        # lens; clearly-lost roots may still snap.
        if MIN_SPEND > 0.0 and -0.6 < root_value < 0.2 and elapsed < MIN_SPEND * soft:
            return False
        early, late = EARLY_STOP_P, LATE_STOP_P
        if lens and hard > 2.0 * soft and 0.2 < root_value < 0.9:
            early, late = 0.97, 0.75
        elif MIN_SPEND > 0.0 and -0.6 < root_value <= 0.2:
            early, late = max(early, 0.97), max(late, 0.70)
        # Throughput guard (mirrors court.py): before half the soft budget,
        # only near-certainty stops — speed becomes depth, not idle bank.
        if elapsed < 0.5 * soft:
            early = max(early, 0.985)
        p = self.court.p_best(qs, vs, ns)
        if elapsed < soft:
            return p >= early
        if elapsed < min(hard, soft * EXTEND_FACTOR):
            return p >= late
        return True

    # --------------------------------------------------------------- think

    def think(self, board: chess.Board, movetime=None, wtime=None, btime=None,
              winc=0.0, binc=0.0, node_budget=None, stop_event=None,
              info_cb=None, ponder=False, ponder_hit_event=None):
        oracle = self._ensure_oracle()
        board = board.copy()
        self._incumbent_uci = None           # fresh conviction-incumbent per move
        if board.is_game_over(claim_draw=False):
            return None, {"reason": "game over"}

        fen, moves = _split_history(board)
        self.core.set_position(fen, moves)
        pending_obs = getattr(self, "_pending_obs", None)
        if pending_obs is not None:
            self._pending_obs = None
            self._observe_opponent(*pending_obs)   # deferred by a borrow race
        rho = self.opp_model.rho()
        # Snapshot our settled root assessment ONCE for draw-contempt gating.
        # The lattice persists across our moves, so the current root usually
        # carries evals from the prior think. HARD GUARD: only trust it with
        # >=256 evals (mirrors the min-work floor); a fresh/raw root -> q0=0 ->
        # contempt off (safe). Held fixed for the whole think (no feedback).
        q0 = 0.0
        if self.draw_contempt > 0.0:
            rvals, rflags = self.core.root_info()
            if rflags[4] and rflags[2] >= 256:        # exists and evals>=256
                q0 = max(-0.999, min(0.999, rvals[0]))
        self.core.set_search(rho, self.lens_on, self.draw_contempt, q0)
        headroom = 100 - board.halfmove_clock

        soft, hard = self.court.budgets(wtime, btime, winc, binc,
                                        board.turn == chess.WHITE, movetime,
                                        moves_played=board.fullmove_number)
        if node_budget is not None and movetime is None:
            soft = hard = float("inf")
        pondering = bool(ponder) and ponder_hit_event is not None
        t0 = time.perf_counter()
        self.core.reset_flight()

        # Panic floor: move instantly on settled beliefs when the bank
        # cannot fund a batch.
        if (not pondering and node_budget is None and hard < 0.14
                and self.core.root_children()):
            self.core.settle(4000)
            best = self._best_move(board, headroom)
            info = self.info(board, 0, t0)
            info["pv"] = [best] if best else []
            info["panic"] = True
            return best, info

        evals_this_move = 0
        evals_at_hit = 0
        batch_ema = 0.15
        last_info = t0
        empty_streak = 0
        eff_batch = self.batch
        if hard < 1.2:
            eff_batch = max(24, self.batch // 4)
        elif hard < 3.0:
            eff_batch = max(48, self.batch // 2)

        while True:
            if stop_event is not None and stop_event.is_set():
                break
            if pondering and ponder_hit_event.is_set():
                pondering = False
                t0 = time.perf_counter()
                evals_at_hit = evals_this_move
            (_rivals, _riflags) = self.core.root_info()
            root_proofed = _riflags[0]
            # PATH-CONDITIONAL draw proof? (|value|<=DRAWISH AND path_cond,
            # the additive 7th flag; pre-rebuild 6-tuple -> False -> no delay).
            _ripc = _riflags[6] if len(_riflags) > 6 else False
            draw_proofed = (root_proofed and abs(_rivals[0]) <= DRAWISH
                            and _ripc)
            force_proof = root_proofed
            if not pondering:
                if node_budget is not None and evals_this_move >= node_budget:
                    break
                elapsed = time.perf_counter() - t0
                if evals_this_move > 0 and elapsed + 1.1 * batch_ema >= hard:
                    break
                fresh = evals_this_move - evals_at_hit
                # VERIFY_DRAW: a not-yet-revalidated PATH-CONDITIONAL draw
                # proof must not force min_work / break-on-empty (bounded by
                # VERIFY_DRAW_FRAC*soft). force_proof == root_proofed in legacy
                # / sound / unconditional-draw / past-cap cases.
                if (VERIFY_DRAW > 0 and draw_proofed and fresh < VERIFY_DRAW
                        and elapsed < VERIFY_DRAW_FRAC * soft):
                    force_proof = False
                min_work = force_proof or (
                    evals_this_move >= max(256, 2 * self.batch)
                    and fresh >= max(128, eff_batch))
                if node_budget is None and self._should_stop(
                        board, headroom, elapsed, soft, hard, min_work,
                        fresh):
                    break

            bt0 = time.perf_counter()
            planes, n = self.core.select_batch(eff_batch)
            if n == 0:
                self.core.settle(20000)
                if pondering:
                    time.sleep(0.003)
                    continue
                empty_streak += 1
                # A not-yet-revalidated PATH-CONDITIONAL draw proof must not
                # break the loop on an empty selection (the depth-1 snap);
                # empty_streak>=3 still bounds it to ~3 idle settle rounds.
                # force_proof == root_proofed in legacy / sound / unconditional
                # / past-cap cases.
                if force_proof or empty_streak >= 3:
                    break
                continue
            empty_streak = 0
            policy, wdl, mlh = self._infer_pending(planes, n)
            evals_this_move += self.core.integrate(policy, wdl, mlh)
            if self.antidrift and evals_this_move >= self.drift_efloor:
                self._update_incumbent()
            self.total_evals += n
            # Serial loop: after integrate, no descent is in flight, so any
            # surviving vloss is duplicate-retry residue — clear it rather
            # than let phantom penalties steer the next batch.
            self.core.reset_flight()
            if self.proof_bursts:
                # promote saturated beliefs into theorems (~ms of CPU)
                self.core.prove_burst(12000)
            batch_ema = 0.7 * batch_ema + 0.3 * (time.perf_counter() - bt0)

            if self.core.node_count() > self.max_nodes:
                self.core.clear(True)     # eviction keeps the lessons
                self.core.reset_flight()
                self._seed_from_ledger()

            if info_cb is not None and time.perf_counter() - last_info > 1.0:
                last_info = time.perf_counter()
                info_cb(self.info(board, evals_this_move, t0))

        best = self._best_move(board, headroom)
        info = self.info(board, evals_this_move, t0)
        info["pv"] = self._pv(board, best)
        self._harvest(board, best, info)
        return best, info

    # ------------------------------------------------------------- helpers

    def _pv(self, board: chess.Board, best):
        pv = []
        if best is None:
            return pv
        b = board.copy()
        key = self.core.root_key()
        seen = set()
        mv = best
        while mv is not None and key not in seen and len(pv) < 12:
            seen.add(key)
            pv.append(mv)
            b.push(mv)
            key = position_key(b, coarse=self._coarse_keys)
            children = self.core.node_children(key)
            if not children:
                break
            hr = 100 - b.halfmove_clock
            nxt = None
            best_q = -1e9
            for c in children:
                child_hr = hr - 1
                demoted = (c[F_PROOF] and abs(c[F_VAL]) > DRAWISH
                           and not _trusted(True, c[F_VAL], c[F_DIST],
                                            child_hr))
                cval = 0.0 if demoted else c[F_VAL]
                q = -GAMMA * eff_value(cval, c[F_MLH])
                if q > best_q:
                    best_q = q
                    nxt = c[F_UCI]
            mv = chess.Move.from_uci(nxt) if nxt else None
        return pv

    def note_opponent_move(self, board_before: chess.Board, move) -> None:
        # coarse keying here changes which core node is found -> feeds rho ->
        # RHO_GATE/Lens/eps -> CAN drift move selection. Default off via
        # _coarse_obs (STILLWATER_COARSE_OBS) so the placement config (0x800
        # set) is byte-identical; opt in to A/B the rho change separately.
        ckey = position_key(board_before, coarse=self._coarse_obs)
        try:
            self._observe_opponent(ckey, move.uci())
        except RuntimeError:
            # search thread holds the core borrow (ponderhit race): defer the
            # observation to the start of the next think instead of losing it
            self._pending_obs = (ckey, move.uci())
        except Exception:
            pass

    def _observe_opponent(self, key: int, played_uci: str) -> None:
        try:
            children = self.core.node_children(key)
            best_q = None
            best_n = 0
            played_q = None
            played_n = 0
            for c in children:
                q = -GAMMA * eff_value(c[F_VAL], c[F_MLH])
                if best_q is None or q > best_q:
                    best_q, best_n = q, c[F_EVALS]
                if c[F_UCI] == played_uci:
                    played_q, played_n = q, c[F_EVALS]
            if (best_q is None or played_q is None
                    or played_n < 8 or best_n < 8):
                return
            self.opp_model.observe(max(0.0, best_q - played_q))
        except RuntimeError:
            raise
        except Exception:
            pass

    def _harvest(self, board, best, info) -> None:
        try:
            (vals, flags) = self.core.root_info()
            if not flags[4] or (flags[2] < LESSON_EVIDENCE and not flags[0]):
                return
            children = [[c[F_UCI], round(-c[F_VAL], 4), c[F_EVALS],
                         1 if c[F_PROOF] else 0]
                        for c in self.core.root_children()]
            self.distillery.harvest_raw({
                "fen": board.fen(),
                "raw": [round(vals[5], 4), None, round(vals[6], 1)],
                "settled": [round(vals[0], 4),
                            [round(vals[1], 4), round(vals[2], 4),
                             round(vals[3], 4)],
                            round(vals[4], 4), round(vals[7], 1)],
                "evidence": flags[2],
                "proof": 1 if flags[0] else 0,
                "claim": 1 if flags[3] else 0,
                "best": best.uci() if best else None,
                "rho": round(info.get("rho", 1.0), 3),
                "moves": children,
            })
        except Exception:
            pass

    def info(self, board, evals_this_move, t0) -> dict:
        elapsed = max(1e-6, time.perf_counter() - t0)
        (vals, flags) = self.core.root_info()
        v = max(-0.9999, min(0.9999, vals[0]))
        proof_dist = 0
        if flags[0] and abs(vals[0]) > DRAWISH:
            dists = [c[F_DIST] + 1 for c in self.core.root_children()
                     if c[F_PROOF] and -GAMMA * c[F_VAL] > 0.5]
            proof_dist = min(dists) if dists else flags[1]
        backups, terminals, tb_hits, lessons = self.core.stats()
        return {
            "value": vals[0],
            "cp": int(round(100.0 * math.tan(1.5620688 * v))),
            "wdl": (vals[1], vals[2], vals[3]),
            "proof": flags[0],
            "proof_dist": proof_dist,
            "p_best": self.court.last_p_best,
            "rho": self.opp_model.rho(),
            "evals": evals_this_move,
            "nps": int(evals_this_move / elapsed),
            "lattice": self.core.node_count(),
            "lessons": lessons,
            "tb_hits": tb_hits,
            "backups": backups,
            "time": elapsed,
        }
