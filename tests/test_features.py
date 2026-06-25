"""Tests for the four architecture additions, on the GPU-free substrate.

  #6  proof certificates + the fifty-move validity envelope
  #4  Syzygy tablebases as a proof oracle (exercised with a fake prober so the
      integration is tested without downloading tables)
  #2  pondering: settling on the opponent's clock, retained on a ponder miss
  #1  opponent-aware play: the Effigy (opponent model) and the Mirror (v_them)

Run:  python tests/test_features.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess

from stillwater.court import RootCourt
from stillwater.engine import Engine
from stillwater.lattice import Lattice, Node, position_key
from stillwater.mock_oracle import MockOracle
from stillwater.opponent import OpponentModel
from stillwater.search import GAMMA, SettlingEngine, proof_trusted_at


def make_engine(**kw) -> Engine:
    kw.setdefault("harvest_on", False)   # tests don't write training data
    kw.setdefault("ledger_on", False)    # ...or touch the real proof ledger
    return Engine(oracle=MockOracle(), batch=kw.pop("batch", 64), **kw)


# --------------------------------------------------------------- #6 envelope

def test_proof_dist_on_mate():
    # A mate in one settles to a proof of reach 1 ply (one move to mate).
    board = chess.Board("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1")
    eng = make_engine()
    move, info = eng.think(board, node_budget=1500)
    assert move == chess.Move.from_uci("d1d8"), move
    assert info["proof"] and info["proof_dist"] == 1, info
    print(f"  proof_dist: mate in 1 -> proof_dist {info['proof_dist']}")


def test_envelope_blocks_clockbound_win():
    # A proven win of reach 14 plies is real with ample 50-move headroom but a
    # mirage when the clock would draw first. The court must agree.
    L = Lattice()
    court = RootCourt()
    root = Node(1, (0.5, 0.4, 0.1), 0.0,
                (chess.Move.from_uci("a2a3"),), [1.0], None, 30.0,
                turn=chess.WHITE)
    # child is a LOSS for the side to move there (reach 14) => root wins via it
    child = Node.make_tablebase(2, -1.0, dist=14, mlh=14.0, turn=chess.BLACK)
    L.put(root); L.put(child)
    root.child_keys[0] = 2

    assert proof_trusted_at(child, 20) and not proof_trusted_at(child, 5)
    _, _, _, _, proven_hi = court.root_stats(L, root, headroom=100)
    _, qs_lo, _, _, proven_lo = court.root_stats(L, root, headroom=8)
    assert proven_hi == 0, "ample headroom: a proven win"
    assert proven_lo == -1, "no headroom: the 50-move rule draws it"
    assert abs(qs_lo[0]) < 1e-6, "clock-bound win is scored as the draw it is"
    print("  envelope: reach-14 win trusted at headroom 100, voided at 8")


# --------------------------------------------------- #4 tablebase as a proof

class _FakeTB:
    """A stand-in proof oracle: any <=5-man position is a win for whoever is up
    a queen's worth of material (enough to test the seam without real tables)."""
    max_men = 5

    def probeable(self, board):
        return (chess.popcount(board.occupied) <= self.max_men
                and not board.castling_rights)

    def probe(self, board):
        val = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
               chess.ROOK: 5, chess.QUEEN: 9}
        edge = 0
        for pt, v in val.items():
            edge += v * (chess.popcount(board.pieces_mask(pt, board.turn))
                         - chess.popcount(board.pieces_mask(pt, not board.turn)))
        if edge >= 5:
            return 1.0, 10, 10.0
        if edge <= -5:
            return -1.0, 10, 10.0
        return 0.0, 0, 1.0


def test_tablebase_proof_oracle():
    # KQ vs K: every white move keeps a winning material edge, so the tablebase
    # proves the whole root won with zero GPU evaluations on the probed leaves.
    eng = make_engine()
    eng.broker.tb = _FakeTB()
    board = chess.Board("7k/8/8/8/8/8/8/KQ6 w - - 0 1")
    move, info = eng.think(board, node_budget=800)
    assert eng.broker.tb_hits > 0, "tablebase was never probed"
    assert info["proof"] and info["value"] > 0.5, info
    assert info["tb_hits"] == eng.broker.tb_hits
    print(f"  tablebase: KQvK proven won via {eng.broker.tb_hits} TB probes")


def test_tablebase_absent_is_noop():
    # With no tables the engine must build and run exactly as before. (Tables
    # may be installed on this machine, so assert on a path that has none
    # rather than on auto-discovery.)
    from stillwater.tablebase import open_tablebase
    assert open_tablebase(os.path.join(os.sep, "no_such_syzygy_dir_xyz")) is None
    eng = make_engine()
    eng.broker.tb = None
    move, _ = eng.think(chess.Board(), node_budget=200)
    assert move is not None
    print("  tablebase: absent -> clean no-op")


# ------------------------------------------------------------ #2 pondering

def test_ponder_then_hit_returns_move():
    eng = make_engine()
    board = chess.Board()
    board.push_uci("e2e4")
    hit = threading.Event()
    stop = threading.Event()
    out = {}

    def run():
        out["move"], out["info"] = eng.think(
            board, wtime=2.0, btime=2.0, winc=0.1, binc=0.1,
            ponder=True, ponder_hit_event=hit, stop_event=stop)

    th = threading.Thread(target=run)
    th.start()
    time.sleep(0.4)                      # settle on the opponent's clock
    assert th.is_alive(), "ponder must not return before ponderhit/stop"
    grew = len(eng.lattice)
    assert grew > 1, "pondering did no work"
    hit.set()                            # opponent played the expected move
    th.join(timeout=10.0)
    assert not th.is_alive() and out["move"] is not None
    print(f"  ponder+hit: settled {grew} nodes on opp time, then moved "
          f"{out['move'].uci()}")


def test_ponder_stop_is_prompt():
    eng = make_engine()
    hit = threading.Event()
    stop = threading.Event()
    out = {}

    def run():
        out["move"], _ = eng.think(
            chess.Board(), wtime=2.0, btime=2.0, ponder=True,
            ponder_hit_event=hit, stop_event=stop)

    th = threading.Thread(target=run)
    th.start()
    time.sleep(0.3)
    stop.set()                           # ponder miss: abandon
    th.join(timeout=10.0)
    assert not th.is_alive() and out["move"] is not None
    print(f"  ponder+stop: abandoned cleanly with {out['move'].uci()}")


# ------------------------------------------------------------------ the Lens

def test_lens_prefers_alive_over_dead():
    # Two root moves with identical honest value (W-L = 0): one leads to a
    # dead draw (W=.05 D=.90), one keeps real winning chances (W=.30 D=.40).
    # Against a FALLIBLE opponent the Lens must keep the game alive; with the
    # lens off — or the opponent too strong to err (the rho gate; measured
    # 0-2-8 vs SF-3190L when ungated) — the old evals tie-break must pick the
    # dead line (it has more evidence).
    def build(lens_on, rho=0.5):
        eng = make_engine(lens_on=lens_on)
        eng.settler.root_turn = chess.WHITE
        eng.settler.opp_rho = rho

        def leaf(key, wdl, evals):
            n = Node(key, wdl, wdl[0] - wdl[2], (), [], None, 20.0,
                     turn=chess.BLACK)   # children: opponent to move
            n.evals = evals
            return n

        # child wdl is from THEIR side: their W = our L
        dead = leaf(10, (0.05, 0.90, 0.05), 50)
        alive = leaf(11, (0.30, 0.40, 0.30), 20)
        mD, mA = chess.Move.from_uci("a2a3"), chess.Move.from_uci("b2b3")
        root = Node(1, (0.2, 0.6, 0.2), 0.0, (mD, mA), [0.5, 0.5], None, 30.0,
                    turn=chess.WHITE)
        root.child_keys = [10, 11]
        for n in (dead, alive, root):
            eng.lattice.put(n)
        return eng, root, mD, mA

    eng, root, mD, mA = build(lens_on=False)
    assert eng._best_move(root) == mD, "lens off: old evals tie-break"
    eng, root, mD, mA = build(lens_on=True, rho=1.0)
    assert eng._best_move(root) == mD, "perfect opponent: lens must stay shut"
    eng, root, mD, mA = build(lens_on=True)
    assert eng._best_move(root) == mA, "fallible opponent: alive beats dead"
    print("  lens: presses vs the fallible, stays honest vs the strong")


def test_lens_never_trades_real_value():
    # A move clearly better on honest value must win even if it is the
    # deader option: the Lens budget (LENS_W * W) must never override a
    # meaningful evaluation difference.
    eng = make_engine(lens_on=True)
    eng.settler.root_turn = chess.WHITE
    eng.settler.opp_rho = 0.5            # lens fully open

    def leaf(key, wdl, evals=30):
        n = Node(key, wdl, wdl[0] - wdl[2], (), [], None, 20.0,
                 turn=chess.BLACK)
        n.evals = evals
        return n

    # better-and-quiet: our value +0.20 (their W-L = -0.20), drawish
    better = leaf(10, (0.05, 0.70, 0.25))
    # equal-and-sharp: our value 0.00, lively
    sharp = leaf(11, (0.35, 0.30, 0.35))
    mB, mS = chess.Move.from_uci("a2a3"), chess.Move.from_uci("b2b3")
    root = Node(1, (0.3, 0.5, 0.2), 0.1, (mB, mS), [0.5, 0.5], None, 30.0,
                turn=chess.WHITE)
    root.child_keys = [10, 11]
    for n in (better, sharp, root):
        eng.lattice.put(n)
    assert eng._best_move(root) == mB, "a real +0.20 edge must beat liveliness"
    print("  lens: never trades a real advantage for sharpness")


# ------------------------------------------------- claimable draws (Ra8 bug)

def _shuffle_to_near_threefold():
    """White to move; playing Ra5 recreates (WRa5/BRh5, black to move) for the
    third time. Black is winning there (king-guarded a2 pawn: ...a1=Q Rxa1
    Kxa1 leaves Black a full rook up) and will decline any 'draw'."""
    board = chess.Board("8/8/8/7r/R7/8/pk4K1/8 w - - 20 40")
    for u in ("a4a5", "h5h4", "a5a4", "h4h5",
              "a4a5", "h5h4", "a5a4", "h4h5"):
        board.push_uci(u)
    return board


def test_claimable_rep_is_floor_not_terminal():
    # Regression for the lichess rook-gift (game Z6nlG9r3, 263. Ra8?? Kxa8):
    # threefold is a CLAIM, not an automatic draw. A repetition the opponent
    # can profitably decline must evaluate as their playing-on value, never as
    # a proven 0.00.
    board = _shuffle_to_near_threefold()
    after = board.copy()
    after.push_uci("a4a5")            # the move that creates the 3rd occurrence
    assert after.is_repetition(3)
    eng = make_engine()
    move, info = eng.think(board, node_budget=1500)
    cnode = eng.lattice.get(position_key(after, rep=True))
    assert cnode is not None, "claim node never created"
    assert cnode.claim_floor, "claimable rep must carry the claim_floor flag"
    # The heart of the bug: the old code pinned this node at a proven 0.00 and
    # the engine gave its rook away for the 'draw'. The mover is up a pawn and
    # declines, so the value must reflect playing on. (It may legitimately be
    # PROVEN at a positive value once the shuffle subspace fully resolves.)
    assert cnode.value > 0.05, \
        f"opponent is up a pawn and plays on; got {cnode.value:.3f}"
    assert not (info["proof"] and abs(info["value"]) < 0.1), \
        "root must not settle to a fake proven draw"
    print(f"  claim floor: decline-able rep reads {cnode.value:+.2f} "
          f"for the mover (not 0.00), no false proof")


def test_claim_floor_protects_the_loser():
    # The other direction: the MOVER at a claimable position who is LOSING
    # takes the claim — value floors at 0 (perpetuals still hold the draw).
    from stillwater.mock_oracle import MockOracle
    eng = make_engine()
    losing = chess.Board("8/1k6/8/8/8/8/q5K1/8 w - - 30 60")  # white down a Q
    ev = MockOracle().evaluate([losing])[0]
    node = eng._create_node(123456, losing, ev, claim_floor=True)
    assert node.claim_floor and node.value == 0.0, \
        f"losing mover claims the draw: value must floor at 0, got {node.value}"
    assert node.wdl[2] == 0.0, "floored belief carries no loss mass"
    print("  claim floor: losing mover keeps the draw in hand (perpetuals live)")


def test_strict_draws_restores_arbiter_rules():
    # Under cutechess-style auto-adjudication the old semantics are correct:
    # third occurrence IS the end of the game.
    board = _shuffle_to_near_threefold()
    after = board.copy()
    after.push_uci("a4a5")
    eng = make_engine(strict_draws=True)
    eng.think(board, node_budget=1200)
    cnode = eng.lattice.get(position_key(after, rep=True))
    assert cnode is not None and cnode.proof and cnode.value == 0.0, \
        "strict mode must adjudicate the third occurrence as a proven draw"
    print("  strict draws: arbiter semantics preserved for local matches")


# ------------------------------------------------------------ panic floor

def test_panic_floor_moves_instantly():
    # With a settled lattice and a clock too small to fund one batch, the
    # engine must move on existing beliefs instead of bleeding toward a flag.
    eng = make_engine()
    board = chess.Board()
    eng.think(board, node_budget=400)        # warm the pond
    t0 = time.perf_counter()
    mv, info = eng.think(board, wtime=0.4, btime=0.4, winc=0.05, binc=0.05)
    dt = time.perf_counter() - t0
    assert mv is not None and mv in board.legal_moves
    assert info.get("panic"), f"expected panic mode, info={info}"
    assert dt < 0.25, f"panic move took {dt:.3f}s"
    print(f"  panic floor: {mv.uci()} in {dt*1000:.0f}ms on settled beliefs")


# -------------------------------------------------- #1 Effigy + the Mirror

def test_effigy_tracks_strength():
    m = OpponentModel()
    assert m.rho() == 1.0, "no evidence -> assume a perfect opponent"
    for _ in range(6):
        m.observe(0.0)                   # always plays the best move
    assert m.rho() > 0.9, m.rho()
    m2 = OpponentModel()
    for _ in range(6):
        m2.observe(0.8)                  # repeatedly blunders badly
    assert m2.rho() < 0.5, m2.rho()
    print(f"  effigy: strong -> rho {m.rho():.2f}, weak -> rho {m2.rho():.2f}")


def test_effigy_ignores_estimation_noise():
    # Regression (game 2 vs SF-3190L, June 11): our own search noise makes a
    # perfect opponent's moves measure ~0.02-0.05 "worse than best". Counting
    # that as fallibility opened the trap band against an engine that never
    # errs, converting the old reliable draws into ground-down losses. Gaps
    # inside the deadzone must leave the opponent looking perfect.
    m = OpponentModel()
    for _ in range(40):                  # a long game of noisy near-best moves
        m.observe(0.04)
    assert m.rho() > 0.95, f"noise mistaken for blunders: rho={m.rho():.3f}"
    print(f"  effigy noise immunity: 40 noisy-best moves -> rho {m.rho():.2f}")


def _trap_lattice(rho):
    """Two honestly-equal root moves; mB hides a trap a fallible opponent may
    fall into. Returns (engine, root, mA, mB) after settling at the given rho."""
    eng = make_engine()
    L, S = eng.lattice, eng.settler
    S.root_turn = chess.WHITE
    S.opp_rho = rho

    def leaf(key, val, turn):
        n = Node(key, (max(0, val), 1 - abs(val), max(0, -val)), val,
                 (), [], None, 8.0, turn=turn)
        return n

    BG = leaf(10, 0.9, chess.WHITE)      # opponent blundered: white winning
    BS = leaf(11, 0.0, chess.WHITE)      # opponent's safe move: drawn
    AD = leaf(20, 0.0, chess.WHITE)      # dead-equal line
    mGood, mSafe = chess.Move.from_uci("a7a6"), chess.Move.from_uci("b7b6")
    B = Node(2, (0.33, 0.34, 0.33), 0.0, (mGood, mSafe), [0.9, 0.1], None, 12.0,
             turn=chess.BLACK)           # opponent to move; tempting move is bad
    B.child_keys = [10, 11]
    mDraw = chess.Move.from_uci("a7a6")
    A = Node(3, (0.33, 0.34, 0.33), 0.0, (mDraw,), [1.0], None, 12.0,
             turn=chess.BLACK)
    A.child_keys = [20]
    mA, mB = chess.Move.from_uci("a2a3"), chess.Move.from_uci("b2b3")
    R = Node(1, (0.33, 0.34, 0.33), 0.0, (mA, mB), [0.5, 0.5], None, 14.0,
             turn=chess.WHITE)
    R.child_keys = [3, 2]
    for n in (BG, BS, AD, B, A, R):
        L.put(n)
    for n in (B, A, R):                  # settle children before parents
        S.backup(n)
    return eng, R, mA, mB


def test_mirror_breaks_dead_draw_only_when_exploitable():
    # Perfect opponent: the trap has no value, both moves are equal, behaviour
    # is the engine's opponent-blind default.
    eng, R, mA, mB = _trap_lattice(rho=1.0)
    assert eng._best_move(R) == mA, "rho=1 must not chase phantom traps"
    # Fallible opponent: same honest eval, but mB poses a real problem -> take it.
    eng, R, mA, mB = _trap_lattice(rho=0.5)
    assert eng._best_move(R) == mB, "an exploitable opponent should be trapped"
    print("  mirror: ignores the trap vs a perfect foe, springs it vs a weak one")


# ------------------------------------------- Distillery + the Proof Ledger

def test_distillery_harvests_root_records():
    import json as _json
    import tempfile
    from stillwater.distillery import Distillery
    eng = make_engine()
    with tempfile.TemporaryDirectory() as tmp:
        eng.distillery = Distillery(True, out_dir=tmp)
        board = chess.Board()
        eng.think(board, node_budget=400)
        eng.distillery.close()
        files = os.listdir(tmp)
        assert files, "no harvest file written"
        lines = open(os.path.join(tmp, files[0]), encoding="utf-8").readlines()
        assert lines, "no records harvested"
        rec = _json.loads(lines[-1])
        assert rec["fen"].split()[1] == "w" and rec["evidence"] >= 32
        assert rec["raw"][0] != rec["settled"][0] or rec["moves"], \
            "record must carry first-impression vs verdict plus move targets"
    print(f"  distillery: harvested {len(lines)} labelled record(s) per think")


def test_proof_ledger_transfers_theorems_across_games():
    import tempfile
    from stillwater import ledger as _ledger
    old_default = _ledger.default_path
    with tempfile.TemporaryDirectory() as tmp:
        _ledger.default_path = lambda: os.path.join(tmp, "ledger.npz")
        try:
            # Game 1: prove the quiet-king-march mate in 2, bank the theorems.
            board = chess.Board("7k/8/5K2/8/8/8/8/4R3 w - - 0 1")
            a = make_engine(ledger_on=True)
            mv, info = a.think(board, node_budget=6000)
            assert info["proof"], "game 1 must prove the mate"
            banked = a.save_ledger()
            assert banked > 0, "no theorems banked"
            # Game 2: a fresh engine (new process in real life) must inherit
            # the proof and play the mate from a sliver of a budget.
            b = make_engine(ledger_on=True)
            assert b.ledger_seeded > 0, "ledger not loaded into the lattice"
            mv2, info2 = b.think(board, node_budget=400)
            assert mv2 in (chess.Move.from_uci("f6g6"),
                           chess.Move.from_uci("f6f7")), f"got {mv2}"
            assert info2["proof"], "inherited theorem should re-prove instantly"
            print(f"  ledger: {banked} theorems banked; fresh engine re-proved "
                  f"the mate with {info2['evals']} evals (was ~6000)")
        finally:
            _ledger.default_path = old_default


def test_ledger_rejects_path_conditioned_proofs():
    # A theorem proven through repetition/claim history is true only for THIS
    # game's path; persisting it would resurrect the Ra8 bug across games.
    import tempfile
    from stillwater import ledger as _ledger
    old_default = _ledger.default_path
    with tempfile.TemporaryDirectory() as tmp:
        _ledger.default_path = lambda: os.path.join(tmp, "ledger.npz")
        try:
            board = _shuffle_to_near_threefold()
            after = board.copy()
            after.push_uci("a4a5")
            eng = make_engine(ledger_on=True)
            eng.think(board, node_budget=1500)
            ck = position_key(after, rep=True)
            cnode = eng.lattice.get(ck)
            assert cnode is not None and cnode.path_cond, \
                "claim node must be marked path-conditioned"
            eng.save_ledger()
            stored = _ledger.load()
            assert ck not in stored, "claim node leaked into the ledger"
            assert position_key(board) not in stored, \
                "rep-derived root proof leaked into the ledger"
            print(f"  ledger taint: {len(stored)} clean theorems kept, "
                  f"path-conditioned ones quarantined")
        finally:
            _ledger.default_path = old_default


def test_ledger_refuses_arbiter_mode():
    # Strict-draw (cutechess) engines must neither read nor write the ledger:
    # an arbiter's "automatic threefold draw" is not a theorem under claim
    # semantics, and importing one would resurrect the Ra8 rook gift.
    eng = make_engine(ledger_on=True, strict_draws=True)
    assert not eng.ledger_on and eng.save_ledger() == 0
    print("  ledger: arbiter-mode engines are quarantined from the theorem store")


# ----------------------------------------------------------- UCI plumbing

def test_uci_ponder_smoke():
    env = dict(os.environ, STILLWATER_MOCK="1")
    proc = subprocess.run(
        [sys.executable, "-m", "stillwater.uci"],
        input=("uci\nisready\nposition startpos moves e2e4 e7e5\n"
               "go ponder wtime 2000 btime 2000\nponderhit\nquit\n"),
        capture_output=True, text=True, timeout=120, env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    out = proc.stdout
    assert "uciok" in out and "bestmove" in out, out
    assert "option name Ponder" in out and "option name SyzygyPath" in out, out
    print("  uci: go ponder + ponderhit -> "
          + [l for l in out.splitlines() if l.startswith("bestmove")][0])


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    print(f"STILLWATER features: {len(tests)} tests")
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print("ALL PASS" if failed == 0 else f"{failed} FAILED")
    sys.exit(1 if failed else 0)
