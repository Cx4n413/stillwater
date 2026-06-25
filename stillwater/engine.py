"""STILLWATER engine orchestration: the GPU batch loop.

Each iteration: the Broker selects a diverse batch of frontier leaves, the
Oracle evaluates them in one GPU pass, new beliefs enter the Lattice, the
Settling Engine relaxes the consequences rootward through the dirty queue,
the Palimpsest ingests lessons from well-evidenced nodes, and the Root Court
decides — by inference, not heuristics — whether deliberation still pays.
"""

from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor

import chess

from . import ledger
from .court import RootCourt, VERIFY_DRAW, VERIFY_DRAW_FRAC
from .distillery import Distillery
from .lattice import Lattice, Node, position_key
from .opponent import OpponentModel
from .palimpsest import Palimpsest, context_key
from .search import (DRAWISH, EPS_BASE, GAMMA, LENS_FLOOR, LENS_W, RHO_GATE,
                     TRAP_MARGIN, Broker, SettlingEngine, eff_value,
                     proof_trusted_at)
from .tablebase import open_tablebase

LESSON_EVIDENCE = 32   # subtree evals before a node's lesson is trusted


class Engine:
    def __init__(self, oracle=None, batch: int = 128, palimpsest_on: bool = True,
                 max_nodes: int = 2_500_000, syzygy_path: str | None = None,
                 opponent_model_on: bool = True, lens_on: bool = True,
                 strict_draws: bool = False, harvest_on: bool = True,
                 ledger_on: bool = True):
        self.lattice = Lattice(max_nodes)
        self.settler = SettlingEngine(self.lattice)
        self.broker = Broker(self.lattice, self.settler,
                             strict_draws=strict_draws)
        self.palimpsest = Palimpsest(palimpsest_on)
        self.court = RootCourt()
        self.opp_model = OpponentModel(opponent_model_on)
        self.lens_on = lens_on
        self.settler.lens_on = lens_on
        self.distillery = Distillery(harvest_on)
        # The proof ledger only exists under claim semantics: arbiter-mode
        # "automatic draws" are not theorems in the claim world, and one false
        # pin re-imported into a real game would be the Ra8 bug reborn.
        self.ledger_on = ledger_on and not strict_draws
        self.ledger_seeded = 0
        self._seed_from_ledger()
        self.oracle = oracle
        self.batch = batch
        self.total_evals = 0
        # Syzygy proof oracle, if tables are installed; None otherwise (the
        # engine then behaves exactly as it did with no tablebase support).
        self.broker.tb = open_tablebase(syzygy_path)
        # One worker thread owns all oracle calls; onnxruntime releases the
        # GIL during inference, so the broker selects batch N+1 while the GPU
        # evaluates batch N (the async pipeline: CPU and GPU overlap).
        self._gpu = ThreadPoolExecutor(max_workers=1, thread_name_prefix="oracle")

    # ------------------------------------------------------------------ setup

    def _ensure_oracle(self):
        if self.oracle is None:
            from .oracle import LeelaOracle
            self.oracle = LeelaOracle()
            if hasattr(self.oracle, "warmup"):
                self.oracle.warmup()  # hide DirectML per-shape JIT compiles
        return self.oracle

    def new_game(self) -> None:
        self.save_ledger()           # bank this game's theorems first
        self.lattice.clear()
        self.palimpsest.clear()
        self.opp_model.clear()
        self.broker.reset_flight()
        self._seed_from_ledger()     # multi-game hosts inherit theorems too

    def _seed_from_ledger(self) -> None:
        if not self.ledger_on:
            return
        for key, (val, dist, mlh, turn) in ledger.load().items():
            if key not in self.lattice.nodes:
                self.lattice.put(Node.make_tablebase(
                    key, val, dist, mlh, turn=turn))
                self.ledger_seeded += 1

    # Beyond this reach, GAMMA**dist drifts a proven win's stored value toward
    # the DRAWISH boundary (0.997**233 < 0.5) and a reloaded theorem would be
    # misread as a clock-immune draw by every consumer. 180 keeps |value| of
    # decisive proofs safely above 0.58.
    LEDGER_MAX_DIST = 180

    def save_ledger(self) -> int:
        """Persist transferable theorems. Returns the ledger's total size.

        Transferable means: proven, non-trivial (reach >= 2), NOT conditioned
        on this game's path history (no claim rights, no repetition-derived
        ancestry — the Ra8 class), and shallow enough that the discounted
        value cannot be misclassified on reload."""
        if not self.ledger_on:
            return 0
        proofs = {}
        # snapshot: a still-draining search thread may mutate the dict
        for key in list(self.lattice.nodes):
            n = self.lattice.nodes.get(key)
            if (n is not None and n.proof
                    and 2 <= n.proof_dist <= self.LEDGER_MAX_DIST
                    and not n.claim_floor and not n.path_cond):
                proofs[key] = (n.value, n.proof_dist, n.mlh, n.turn)
        if not proofs:
            return 0
        return ledger.save(proofs)

    def shutdown(self) -> None:
        """Flush persistent state at process end (UCI quit)."""
        try:
            self.save_ledger()
        except Exception:
            pass
        self.distillery.close()

    # -------------------------------------------------------- opponent model

    def note_opponent_move(self, board_before, move) -> None:
        """Fold the opponent's actual move into the Effigy. board_before is the
        position they moved from; if it is resident with evaluated children we
        can see, for free, how their choice ranked — the evidence that decides
        whether (and how hard) the engine plays for practical chances."""
        try:
            node = self.lattice.get(position_key(board_before))
            if node is None or not node.moves or move not in node.moves:
                return
            best_q = None
            best_n = 0
            played_q = None
            played_n = 0
            idx = node.moves.index(move)
            for i, ck in enumerate(node.child_keys):
                child = self.lattice.get(ck)
                if child is None:
                    continue
                q = -GAMMA * eff_value(child.value, child.mlh)
                if best_q is None or q > best_q:
                    best_q = q
                    best_n = child.evals
                if i == idx:
                    played_q = q
                    played_n = child.evals
            # A "gap" read off a barely-explored child is search noise, not
            # evidence about the opponent: require real evidence on both the
            # move they played and the move we think was best.
            if (best_q is None or played_q is None
                    or played_n < 8 or best_n < 8):
                return
            self.opp_model.observe(max(0.0, best_q - played_q))
        except Exception:
            pass             # the opponent model must never break a search

    # ------------------------------------------------------------- node birth

    def _create_node(self, key: int, board: chess.Board, ev,
                     claim_floor: bool = False) -> Node:
        ctx = context_key(board)
        raw_v = ev.value + self.palimpsest.correction(ctx)
        raw_v = max(-0.999, min(0.999, raw_v))
        moves = tuple(board.legal_moves)
        if ev.policy:
            priors = [max(ev.policy.get(m, 1e-5), 1e-6) for m in moves]
            s = sum(priors)
            priors = [p / s for p in priors]
        else:
            priors = [1.0 / max(1, len(moves))] * len(moves)
        node = Node(key, ev.wdl, raw_v, moves, priors, ctx,
                    mlh=max(0.0, getattr(ev, "mlh", 60.0)), turn=board.turn)
        node.value = raw_v
        if claim_floor:
            # The mover holds a draw claim (3-fold/50-move): worst case 0.
            node.claim_floor = True
            node.path_cond = True        # claim rights are path history
            if node.value < 0.0:
                node.value = 0.0
                w, d, l = node.wdl
                node.wdl = (w, d + l, 0.0)
                node.v_them = 0.0
        return node

    # ------------------------------------------------------------------ think

    def think(self, board: chess.Board, movetime=None, wtime=None, btime=None,
              winc=0.0, binc=0.0, node_budget=None, stop_event=None,
              info_cb=None, ponder=False, ponder_hit_event=None):
        """Returns (best_move | None, info dict). Times in seconds.

        With ponder=True the engine settles indefinitely on the given root
        (the opponent's clock) — no time budget, no court stopping — until
        ponder_hit_event fires (the opponent played the expected move; start
        the clock and finish normally) or stop_event fires (abandon, return
        the best move found). Because the lattice is position-keyed, nothing
        thought during pondering is wasted even on a ponder miss: the work
        simply stays in the pond for whatever position arises next.
        """
        oracle = self._ensure_oracle()
        board = board.copy()
        # claim_draw must be False: with True, python-chess reports "over"
        # whenever a threefold COULD be claimed (even one we could merely
        # walk into), and an engine that refuses to think there ends up
        # playing legal_moves[0]. That single word cost two games to mate.
        if board.is_game_over(claim_draw=False):
            return None, {"reason": "game over"}

        root_key = position_key(board)
        root = self.lattice.get(root_key)
        if root is None or not root.moves:
            # A ledger-seeded proof pin has no move list: useful as a child
            # value, but the root must offer real moves — rebuild it fresh.
            ev = self._gpu.submit(oracle.evaluate, [board]).result()[0]
            root = self._create_node(root_key, board, ev)
            self.lattice.put(root)
            self.total_evals += 1

        # The Mirror and the envelope both need to know who is to move and how
        # much fifty-move headroom the root has.
        self.settler.root_turn = board.turn
        self.settler.opp_rho = self.opp_model.rho()
        headroom = 100 - board.halfmove_clock

        soft, hard = self.court.budgets(wtime, btime, winc, binc,
                                        board.turn == chess.WHITE, movetime,
                                        moves_played=board.fullmove_number)
        if node_budget is not None and movetime is None:
            soft = hard = float("inf")  # 'go nodes N' is governed by N alone
        pondering = bool(ponder) and ponder_hit_event is not None
        t0 = time.perf_counter()
        self.broker.reset_flight()
        # Panic floor: below this hard budget the bank cannot fund even one
        # GPU batch, so any "think" would overspend and bleed toward a flag.
        # Moving instantly on the lattice's existing settled beliefs (which
        # persistence and pondering keep warm) is strictly better than losing
        # on time — stale evidence beats forfeit.
        if (not pondering and node_budget is None and hard < 0.14
                and any(ck is not None for ck in root.child_keys)):
            self.settler.settle(4000)
            best, pv = self._best_line(board, root, headroom)
            info = self.info(board, root, 0, t0)
            info["pv"] = pv
            info["panic"] = True
            return best, info
        evals_this_move = 0
        evals_at_hit = 0
        batch_ema = 0.15
        last_info = t0
        empty_streak = 0
        # Short budgets get small batches: 4-6 quick settling rounds beat one
        # monolithic batch when living on the increment.
        eff_batch = self.batch
        if hard < 1.2:
            eff_batch = max(24, self.batch // 4)
        elif hard < 3.0:
            eff_batch = max(48, self.batch // 2)

        pending = None  # (future, leaves) currently on the GPU
        while True:
            if stop_event is not None and stop_event.is_set():
                break
            if pondering and ponder_hit_event.is_set():
                # The opponent played the expected move: the lattice is already
                # warm. Start the clock now and let the normal stopping logic
                # take over — a pre-settled root stops quickly and banks time.
                pondering = False
                t0 = time.perf_counter()
                evals_at_hit = evals_this_move
            if not pondering:
                in_flight = len(pending[1]) if pending else 0
                if node_budget is not None and \
                        evals_this_move + in_flight >= node_budget:
                    break
                elapsed = time.perf_counter() - t0
                if evals_this_move > 0 and elapsed + 1.3 * batch_ema >= hard:
                    break  # never move on zero fresh evidence, though
                # Ponder evals warm the lattice but must not stand in for live
                # scrutiny: after a ponderhit the court still owes the current
                # position at least a batch of fresh, court-directed evals
                # before it may stop. (Without this the engine snap-moved on
                # stale confidence all game and banked time it never spent.)
                fresh = evals_this_move - evals_at_hit
                # VERIFY_DRAW: a PATH-CONDITIONAL root DRAW proof must not
                # force min_work / break-on-empty until re-validated by `fresh`
                # evals on the live position (bounded by VERIFY_DRAW_FRAC*soft).
                # force_proof == root.proof in legacy / sound-proof /
                # unconditional-draw / past-cap cases (byte-identical).
                draw_proofed = (root.proof and abs(root.value) <= DRAWISH
                                and root.path_cond)
                force_proof = root.proof
                if (VERIFY_DRAW > 0 and draw_proofed and fresh < VERIFY_DRAW
                        and elapsed < VERIFY_DRAW_FRAC * soft):
                    force_proof = False
                min_work = force_proof or (
                    evals_this_move >= max(256, 2 * self.batch)
                    and fresh >= max(128, eff_batch))
                if node_budget is None and self.court.should_stop(
                        self.lattice, root, elapsed, soft, hard, min_work,
                        headroom, board,
                        self.lens_on and self.settler.opp_rho < RHO_GATE,
                        fresh, root.path_cond):
                    break

            bt0 = time.perf_counter()
            # Select the NEXT batch while the previous one is on the GPU;
            # in-flight vloss marks keep the two batches disjoint.
            leaves = self.broker.select(board, root_key, eff_batch)
            fut = (self._gpu.submit(oracle.evaluate,
                                    [lb for (_, lb, _, _, _, _) in leaves])
                   if leaves else None)
            if pending is not None:
                evals_this_move += self._integrate(*pending)
            pending = (fut, leaves) if leaves else None

            if pending is None:
                self.settler.settle()
                if pondering:
                    # Nothing left to expand right now (e.g. a proven root):
                    # idle on the opponent's clock rather than returning early,
                    # which UCI would mistake for a bestmove.
                    time.sleep(0.003)
                    continue
                empty_streak += 1
                # Mirror the stop block: a not-yet-revalidated PATH-CONDITIONAL
                # draw proof must not break on an empty selection under
                # VERIFY_DRAW; the empty_streak>=3 escape still bounds it to
                # ~3 idle settle rounds (no hang). force_proof == root.proof in
                # legacy / sound / unconditional-draw / past-cap cases.
                if force_proof or empty_streak >= 3:
                    break
                continue
            empty_streak = 0
            batch_ema = 0.7 * batch_ema + 0.3 * (time.perf_counter() - bt0)

            if self.lattice.over_capacity():
                # v0 eviction: drain the pond, keep the lessons (palimpsest).
                if pending is not None:
                    evals_this_move += self._integrate(*pending)
                    pending = None
                self.lattice.clear()
                self.lattice.evictions += 1
                self.broker.reset_flight()
                ev = self._gpu.submit(oracle.evaluate, [board]).result()[0]
                root = self._create_node(root_key, board, ev)
                self.lattice.put(root)

            if info_cb is not None and time.perf_counter() - last_info > 1.0:
                last_info = time.perf_counter()
                info_cb(self.info(board, root, evals_this_move, t0))

        if pending is not None:
            evals_this_move += self._integrate(*pending)

        best, pv = self._best_line(board, root, headroom)
        info = self.info(board, root, evals_this_move, t0)
        info["pv"] = pv
        # Distillery: one labelled record per move — the net's first
        # impression of this root next to the search's settled verdict.
        self.distillery.harvest_root(board, root, self.lattice, best, info)
        return best, info

    def _integrate(self, fut, leaves) -> int:
        """Fold a completed GPU batch into the lattice and settle. Returns
        the number of evaluations integrated."""
        evs = fut.result()
        for (key, lb, pkey, midx, path, claim), ev in zip(leaves, evs):
            parent = self.lattice.get(pkey)
            existing = self.lattice.get(key)
            if existing is None:
                node = self._create_node(key, lb, ev, claim_floor=claim)
                self.lattice.put(node)
            else:
                node = existing  # linked by a sibling path meanwhile
            node.parents.add(pkey)
            if parent is not None:
                parent.child_keys[midx] = key
                self.settler.mark_dirty(pkey, 1.0)
            self.broker.vloss.pop((pkey, midx), None)
            for k in path:
                pn = self.lattice.get(k)
                if pn is None:
                    continue
                pn.evals += 1
                if (pn.evals == LESSON_EVIDENCE and not pn.observed
                        and pn.context is not None):
                    self.palimpsest.observe(pn.context, pn.value - pn.raw_value)
                    pn.observed = True
            self.total_evals += 1
        self.settler.settle()
        return len(leaves)

    # ------------------------------------------------------------- best & info

    def _best_line(self, board: chess.Board, root: Node, headroom: int = 100):
        best = self._best_move(root, headroom, board)
        pv = []
        if best is None:
            return None, pv
        node, b = root, board.copy()
        seen = set()
        hr = headroom
        while node is not None and node.key not in seen and len(pv) < 12:
            seen.add(node.key)
            mv = self._best_move(node, hr, b)
            if mv is None or mv not in node.moves:
                break
            pv.append(mv)
            idx = node.moves.index(mv)
            try:
                b.push(mv)
                hr = 100 - b.halfmove_clock     # exact clock for the next node
            except Exception:
                hr = max(0, hr - 1)
            node = self.lattice.get(node.child_keys[idx])
        return best, pv

    def _best_move(self, node: Node, headroom: int = 100, board=None):
        """Pick the move to play. Among moves that are honestly within eps of
        the best (eps == 0 against a perfect opponent, so this reduces to the
        plain argmax), prefer the one that gives a fallible opponent the most
        room to go wrong — the Mirror's v_them. A proven win is taken outright,
        but only when the fifty-move clock actually permits the conversion."""
        rho = self.settler.opp_rho
        eps = 0.0 if rho >= RHO_GATE else EPS_BASE * (1.0 - rho)
        # Liveliness is exploitation: the Lens opens with the trap band, never
        # against opponents too strong to err (they win sharp arguments).
        lens = self.lens_on and rho < RHO_GATE
        scored = []
        for i, ck in enumerate(node.child_keys):
            child = self.lattice.get(ck)
            if child is None:
                continue
            # A capture or pawn move resets the fifty-move clock, so the child
            # enjoys full headroom; without a board to ask, stay conservative.
            if board is not None and board.is_zeroing(node.moves[i]):
                child_hr = 100
            else:
                child_hr = headroom - 1
            if (child.proof and -GAMMA * child.value > 0.5
                    and proof_trusted_at(child, child_hr)):
                return node.moves[i]          # a clock-valid proven win wins
            cval, cvt = child.value, child.v_them
            demoted = (child.proof and abs(child.value) > DRAWISH
                       and not proof_trusted_at(child, child_hr))
            if demoted:
                # the 50-move rule draws this line: don't decide on a stale win
                cval = cvt = 0.0
            q = -GAMMA * eff_value(cval, child.mlh)
            qt = -GAMMA * eff_value(cvt, child.mlh)
            if lens and not demoted and q > LENS_FLOOR:
                q += LENS_W * child.wdl[2]    # keep winning chances alive
            scored.append((q, qt, child.evals, node.moves[i]))
        if not scored:
            if node.moves:
                i = max(range(len(node.moves)), key=lambda j: node.priors[j])
                return node.moves[i]
            return None
        qmax = max(s[0] for s in scored)
        cands = [s for s in scored if s[0] >= qmax - eps]
        # The honest argmax is the default; a trap candidate must promise a
        # real exploit edge over it (TRAP_MARGIN) to displace it. Without that
        # bar, phantom edges of +0.001 had the engine declining repetition
        # draws move after move against opposition too strong to err.
        honest = max(cands, key=lambda s: (s[0], s[2]))
        best = max(cands, key=lambda s: (s[1], s[0], s[2]))
        if best[1] - honest[1] < TRAP_MARGIN:
            best = honest
        return best[3]

    def info(self, board, root, evals_this_move, t0) -> dict:
        elapsed = max(1e-6, time.perf_counter() - t0)
        v = max(-0.9999, min(0.9999, root.value))
        # Distance (plies, from the root) of the proven line through the best
        # child, for an exact mate display instead of a discount back-out.
        proof_dist = 0
        if root.proof and abs(root.value) > DRAWISH:
            best_d = None
            for ck in root.child_keys:
                child = self.lattice.get(ck)
                if child is not None and child.proof and -GAMMA * child.value > 0.5:
                    if best_d is None or child.proof_dist < best_d:
                        best_d = child.proof_dist
            proof_dist = (best_d + 1) if best_d is not None else root.proof_dist
        return {
            "value": root.value,
            "cp": int(round(100.0 * math.tan(1.5620688 * v))),
            "wdl": root.wdl,
            "proof": root.proof,
            "proof_dist": proof_dist,
            "p_best": self.court.last_p_best,
            "rho": self.opp_model.rho(),
            "evals": evals_this_move,
            "nps": int(evals_this_move / elapsed),
            "lattice": len(self.lattice),
            "lessons": self.palimpsest.observations,
            "tb_hits": self.broker.tb_hits,
            "backups": self.settler.backups,
            "time": elapsed,
        }
