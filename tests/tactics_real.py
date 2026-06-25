"""Integration smoke: STILLWATER + the real BT4 oracle on tactical positions.

Run:  python tests/tactics_real.py [seconds-per-move]

Not a strength benchmark — a check that lattice + oracle + court cooperate on
positions with one clearly best move (classic WAC items plus proof tests).
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess

from stillwater.engine import Engine

SUITE = [
    # (fen, accepted UCI moves, label)
    ("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1", {"d1d8"}, "back-rank mate in 1"),
    ("7k/8/5K2/8/8/8/8/4R3 w - - 0 1", {"f6g6", "f6f7"},
     "quiet king march, mate in 2"),  # f6f7 is the cook: Kf7 Kh7 Rh1#
    ("2rr3k/pp3pp1/1nnqbN1p/3pN3/2pP4/2P3Q1/PB3PPP/R4RK1 w - - 0 1",
     {"g3g6"}, "WAC.001 Qg6"),
    ("8/7p/5k2/5p2/p1p2P2/Pr1pPK2/1P1R3P/8 b - - 0 1",
     {"b3b2"}, "WAC.002 Rxb2"),
    ("5rk1/1ppb3p/p1pb4/6q1/3P1p1r/2P1R2P/PP1BQ1P1/5RKN w - - 0 1",
     {"e3g3"}, "WAC.003 Rg3"),
    ("r1bq2rk/pp3pbp/2p1p1pQ/7P/3P4/2PB1N2/PP3PPR/2KR4 w - - 0 1",
     {"h6h7"}, "WAC.004 Qxh7+"),
]


def main() -> int:
    per_move = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
    print("loading oracle (BT4 on DirectML)...")
    if os.environ.get("STILLWATER_RS"):
        from stillwater.engine_rs import RustEngine
        eng = RustEngine(batch=256)
        print("(compiled core)")
    else:
        eng = Engine()
    eng._ensure_oracle()
    passed = 0
    for fen, accepted, label in SUITE:
        eng.new_game()
        board = chess.Board(fen)
        t0 = time.perf_counter()
        move, info = eng.think(board, movetime=per_move)
        dt = time.perf_counter() - t0
        ok = move is not None and move.uci() in accepted
        passed += ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {move.uci() if move else '-'} "
              f"({info.get('evals', 0)} evals, {dt:.1f}s, "
              f"P(best) {info.get('p_best', 0):.2f}, "
              f"{'PROVEN' if info.get('proof') else 'cp %+d' % info.get('cp', 0)})")
    print(f"{passed}/{len(SUITE)} tactical positions")
    return 0 if passed == len(SUITE) else 1


if __name__ == "__main__":
    sys.exit(main())
