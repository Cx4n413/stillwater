"""Core substrate tests on the GPU-free mock oracle.

The mock evaluator is material-only and its priors are barely informed, so
every pass here is evidence about the SEARCH: terminal pinning, proof
propagation through the settling queue, transposition linking, court
stopping, and the UCI plumbing.

Run:  python tests/test_core.py   (or pytest tests/test_core.py)
"""

from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess

from stillwater.engine import Engine
from stillwater.mock_oracle import MockOracle


def make_engine(**kw) -> Engine:
    kw.setdefault("harvest_on", False)   # tests don't write training data
    kw.setdefault("ledger_on", False)    # ...or touch the real proof ledger
    return Engine(oracle=MockOracle(), batch=kw.pop("batch", 64), **kw)


def test_mate_in_one():
    # 1.Rd8# — back rank, escape squares blocked by own pawns.
    board = chess.Board("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1")
    eng = make_engine()
    move, info = eng.think(board, node_budget=1200)
    assert move == chess.Move.from_uci("d1d8"), f"got {move}"
    assert info["proof"], "mate should be a proven (variance-zero) belief"
    print("  mate in 1: found and PROVEN")


def test_wins_hanging_queen():
    # Rxd5 wins the undefended queen.
    board = chess.Board("k7/8/8/3q4/8/8/3R4/K7 w - - 0 1")
    eng = make_engine()
    move, info = eng.think(board, node_budget=1500)
    assert move == chess.Move.from_uci("d2d5"), f"got {move}"
    print("  hanging queen: taken")


def test_mate_in_two_quiet_key_move():
    # 1.Kg6!! Kg8 2.Re8#  — or the cook 1.Kf7! Kh7 2.Rh1#. Either way the
    # search must back a QUIET king move purely off terminal pinning
    # propagated through the dirty queue.
    board = chess.Board("7k/8/5K2/8/8/8/8/4R3 w - - 0 1")
    eng = make_engine()
    move, info = eng.think(board, node_budget=6000)
    assert move in (chess.Move.from_uci("f6g6"),
                    chess.Move.from_uci("f6f7")), f"got {move}"
    assert info["proof"], "mate in 2 should settle to a proof"
    print("  mate in 2 (quiet key move): found and PROVEN")


def test_avoids_losing_queen():
    # Black queen attacked by pawn; engine (black) must move/defend it.
    board = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/4P1q1/5N1P/PPPP1PP1/RNBQKB1R b KQkq - 0 3")
    eng = make_engine()
    move, info = eng.think(board, node_budget=2500)
    board.push(move)
    # after our move, the queen must not be capturable for free
    hangs = False
    for reply in board.legal_moves:
        if board.is_capture(reply) and board.piece_at(reply.to_square) and \
                board.piece_at(reply.to_square).piece_type == chess.QUEEN:
            attacker = board.piece_at(reply.from_square)
            if attacker and attacker.piece_type == chess.PAWN:
                hangs = True
    assert not hangs, f"{move} leaves the queen hanging to a pawn"
    print(f"  queen attack: answered with {move.uci()}")


def test_persistent_lattice_reuse():
    # Thinking twice in a row on successive positions must reuse the pond.
    board = chess.Board()
    eng = make_engine()
    eng.think(board, node_budget=400)
    size_before = len(eng.lattice)
    board.push_uci("e2e4")
    eng.think(board, node_budget=10)
    assert len(eng.lattice) >= size_before, "lattice was not preserved between moves"
    print(f"  persistence: {size_before} nodes survive re-rooting")


def test_thinks_in_claimable_threefold():
    # Regression: a position where a threefold COULD be claimed must still
    # get a real move (the run2 bug: think() treated claimable as game-over
    # and the UCI fallback played legal_moves[0] into mate).
    board = chess.Board()
    for u in ("g1f3", "g8f6", "f3g1", "f6g8", "g1f3", "g8f6", "f3g1"):
        board.push_uci(u)
    assert board.can_claim_threefold_repetition()
    assert not board.is_game_over(claim_draw=False)
    eng = make_engine()
    move, info = eng.think(board, node_budget=300)
    assert move is not None and move in board.legal_moves, f"got {move}"
    print(f"  claimable-threefold position: still thinks, plays {move.uci()}")


def test_court_budgets():
    from stillwater.court import RootCourt
    soft, hard = RootCourt.budgets(wtime=60.0, btime=60.0, winc=0.6, binc=0.6)
    assert 0 < soft < hard <= 60.0
    soft, hard = RootCourt.budgets(movetime=5.0)
    assert abs(soft - 4.75) < 1e-6 and hard == soft
    print("  court budgets: sane")


def test_uci_smoke():
    env = dict(os.environ, STILLWATER_MOCK="1")
    proc = subprocess.run(
        [sys.executable, "-m", "stillwater.uci"],
        input="uci\nisready\nposition startpos moves e2e4\ngo nodes 300\nquit\n",
        capture_output=True, text=True, timeout=120, env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    out = proc.stdout
    assert "uciok" in out, out
    assert "readyok" in out, out
    assert "bestmove" in out, out
    bm = [l for l in out.splitlines() if l.startswith("bestmove")][0]
    mv = bm.split()[1]
    assert chess.Move.from_uci(mv) in chess.Board(
        "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1").legal_moves
    print(f"  uci: handshake + {bm}")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"STILLWATER core: {len(tests)} tests")
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
