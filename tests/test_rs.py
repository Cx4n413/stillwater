"""Behavioral suite for the compiled (Rust) core through RustEngine.

Mirrors the load-bearing scenarios of test_core/test_features at the public
interface: proofs, claims, the Ra8 regression, ledger transfer, pondering,
panic floor, tablebases. White-box internals stay covered by the Python
suites; what matters here is that the compiled engine REACHES THE SAME
CONCLUSIONS.

Run:  python tests/test_rs.py
"""

from __future__ import annotations

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess

from stillwater.engine_rs import RustEngine
from stillwater.lattice import position_key
from stillwater.mock_oracle import MockOracle


def make_engine(**kw) -> RustEngine:
    kw.setdefault("harvest_on", False)
    kw.setdefault("ledger_on", False)
    kw.setdefault("syzygy_path", "none")
    return RustEngine(oracle=MockOracle(), batch=kw.pop("batch", 64), **kw)


def test_mate_in_one():
    eng = make_engine()
    move, info = eng.think(
        chess.Board("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1"), node_budget=1500)
    assert move == chess.Move.from_uci("d1d8"), move
    assert info["proof"] and info["proof_dist"] == 1
    print("  rs mate in 1: found and PROVEN, dist 1")


def test_mate_in_two_quiet():
    # The mock oracle's priors are deliberately dumb, and evidence-scaled
    # virtual loss concentrates the search, so the quiet key move takes more
    # mock-budget to surface (the real oracle proves this mate in <1000).
    eng = make_engine()
    move, info = eng.think(
        chess.Board("7k/8/5K2/8/8/8/8/4R3 w - - 0 1"), node_budget=30000)
    assert move in (chess.Move.from_uci("f6g6"), chess.Move.from_uci("f6f7")), move
    assert info["proof"]
    print("  rs mate in 2 (quiet king move): PROVEN")


def test_wins_hanging_queen():
    eng = make_engine()
    move, _ = eng.think(
        chess.Board("k7/8/8/3q4/8/8/3R4/K7 w - - 0 1"), node_budget=1500)
    assert move == chess.Move.from_uci("d2d5"), move
    print("  rs hanging queen: taken")


def test_thinks_in_claimable_threefold():
    board = chess.Board()
    for u in ("g1f3", "g8f6", "f3g1", "f6g8", "g1f3", "g8f6", "f3g1"):
        board.push_uci(u)
    assert board.can_claim_threefold_repetition()
    eng = make_engine()
    move, _ = eng.think(board, node_budget=300)
    assert move is not None and move in board.legal_moves
    print(f"  rs claimable threefold: still thinks, plays {move.uci()}")


def _shuffle_to_near_threefold():
    board = chess.Board("8/8/8/7r/R7/8/pk4K1/8 w - - 20 40")
    for u in ("a4a5", "h5h4", "a5a4", "h4h5",
              "a4a5", "h5h4", "a5a4", "h4h5"):
        board.push_uci(u)
    return board


def test_claimable_rep_is_not_a_free_draw():
    # The Ra8 regression at the compiled core: walking into a declinable
    # threefold while the opponent is winning must read as LOSING.
    board = _shuffle_to_near_threefold()
    eng = make_engine()
    move, info = eng.think(board, node_budget=1500)
    reps = [c for c in eng.core.root_children() if c[0] == "a4a5"]
    assert reps, "repetition move never explored"
    c = reps[0]
    assert c[1] > 0.05, f"opponent declines and wins; child value {c[1]:+.3f}"
    assert not (info["proof"] and abs(info["value"]) < 0.1), \
        "root must not settle to a fake proven draw"
    print(f"  rs claim floor: rep child reads {c[1]:+.2f} for the mover")


def test_strict_draws_arbiter_mode():
    board = _shuffle_to_near_threefold()
    eng = make_engine(strict_draws=True)
    eng.think(board, node_budget=1200)
    reps = [c for c in eng.core.root_children() if c[0] == "a4a5"]
    assert reps and reps[0][5] and reps[0][1] == 0.0, \
        "strict mode must adjudicate the third occurrence as a proven draw"
    print("  rs strict draws: arbiter semantics preserved")


def test_ledger_roundtrip():
    import tempfile
    from stillwater import ledger as _ledger
    old_default = _ledger.default_path
    with tempfile.TemporaryDirectory() as tmp:
        _ledger.default_path = lambda: os.path.join(tmp, "ledger.npz")
        try:
            board = chess.Board("7k/8/5K2/8/8/8/8/4R3 w - - 0 1")
            a = make_engine(ledger_on=True)
            mv, info = a.think(board, node_budget=30000)
            assert info["proof"]
            banked = a.save_ledger()
            assert banked > 0
            b = make_engine(ledger_on=True)
            assert b.ledger_seeded > 0
            mv2, info2 = b.think(board, node_budget=400)
            assert mv2 in (chess.Move.from_uci("f6g6"),
                           chess.Move.from_uci("f6f7"))
            assert info2["proof"]
            print(f"  rs ledger: {banked} theorems banked, re-proved with "
                  f"{info2['evals']} evals")
        finally:
            _ledger.default_path = old_default


def test_ledger_rejects_path_conditioned():
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
            eng.save_ledger()
            stored = _ledger.load()
            assert position_key(after, rep=True) not in stored
            assert position_key(board) not in stored
            print(f"  rs ledger taint: {len(stored)} clean theorems, "
                  "claims quarantined")
        finally:
            _ledger.default_path = old_default


def test_ponder_then_hit():
    eng = make_engine()
    board = chess.Board()
    board.push_uci("e2e4")
    hit, stop = threading.Event(), threading.Event()
    out = {}

    def run():
        out["mv"], out["info"] = eng.think(
            board, wtime=2.0, btime=2.0, winc=0.1, binc=0.1,
            ponder=True, ponder_hit_event=hit, stop_event=stop)

    th = threading.Thread(target=run)
    th.start()
    time.sleep(0.4)
    assert th.is_alive(), "ponder returned before ponderhit"
    grew = 0
    for _ in range(50):       # the search thread may briefly hold the borrow
        try:
            grew = eng.core.node_count()
            break
        except RuntimeError:
            time.sleep(0.01)
    assert grew > 50
    hit.set()
    th.join(timeout=15.0)
    assert not th.is_alive() and out["mv"] is not None
    print(f"  rs ponder: {grew} nodes settled on opp time, then "
          f"{out['mv'].uci()}")


def test_panic_floor():
    eng = make_engine()
    board = chess.Board()
    eng.think(board, node_budget=400)
    t0 = time.perf_counter()
    mv, info = eng.think(board, wtime=0.4, btime=0.4, winc=0.05, binc=0.05)
    dt = time.perf_counter() - t0
    assert mv is not None and mv in board.legal_moves
    assert info.get("panic") and dt < 0.25
    print(f"  rs panic floor: {mv.uci()} in {dt*1000:.0f}ms")


def test_real_tablebase_if_present():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tb_dir = os.path.join(here, "nets", "syzygy")
    if not os.path.isdir(tb_dir):
        print("  rs tablebase: (skipped, no tables)")
        return
    eng = RustEngine(oracle=MockOracle(), batch=64, harvest_on=False,
                     ledger_on=False, syzygy_path=tb_dir)
    assert eng.core.tb_open()
    board = chess.Board("7k/8/8/8/8/8/8/KQ6 w - - 0 1")
    mv, info = eng.think(board, node_budget=800)
    assert info["proof"] and info["value"] > 0.5
    _, _, tb_hits, _ = eng.core.stats()
    assert tb_hits > 0
    print(f"  rs tablebase: KQvK proven via {tb_hits} probes")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    print(f"STILLWATER compiled core: {len(tests)} tests")
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
