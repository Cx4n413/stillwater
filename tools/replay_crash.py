"""Replay the run2 round-1 loss move by move and probe, at every STILLWATER
turn, whether think() would refuse to move (and why). Mock oracle, CPU only.

Run: python tools/replay_crash.py
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess

from stillwater.engine import Engine
from stillwater.mock_oracle import MockOracle

MOVETEXT = """
1. d4 c6 2. e4 d5 3. e5 Bf5 4. Be2 e6 5. Nf3 h6 6. O-O a6 7. c4 Nd7 8. c5 g5
9. Ne1 Bg7 10. Nd3 h5 11. Nc3 Qe7 12. Na4 f6 13. Bxh5+ Kd8 14. Bg4 Bxg4
15. Qxg4 Nh6 16. Qd1 fxe5 17. dxe5 Nxe5 18. Nb6 Rb8 19. Re1 Nef7 20. h4 Nf5
21. hxg5 Nxg5 22. Qg4 Ne4 23. Rxe4 dxe4 24. Bg5 Bf6 25. Qf4 Rc8 26. Bxf6 Qxf6
27. Ne5 Rc7 28. Nxc6+ Rxc6 29. Qb8+ Ke7 30. Qxb7+ Ke8 31. Qxc6+ Kf7
32. Qb7+ Ne7 33. Qxe4 Qh6 34. Qf3+ Nf5 35. Qh3 Qf6 36. Qf3 Qh4 37. Qh3 Qf6
38. Qc3 Qh4 39. Qh3 Qd4 40. Qc3 Qh4 41. Nc8 Qh1#
"""


def main() -> None:
    board = chess.Board()
    moves = []
    for tok in MOVETEXT.split():
        if "." in tok or tok in ("1-0", "0-1", "1/2-1/2"):
            continue
        moves.append(board.parse_san(tok))
        board.push(moves[-1])

    board = chess.Board()
    eng = Engine(oracle=MockOracle(), batch=48)
    print(f"{'mv':>4} {'played':<8} {'claim3':>6} {'claim50':>7} "
          f"{'go_claim':>8} {'think result':<12} note")
    for i, mv in enumerate(moves):
        if board.turn == chess.WHITE:  # STILLWATER's turns
            c3 = board.can_claim_threefold_repetition()
            c50 = board.can_claim_fifty_moves()
            go = board.is_game_over(claim_draw=True)
            note = ""
            result = "-"
            if go or c3 or c50 or i >= 56:  # probe the suspicious tail closely
                try:
                    out, info = eng.think(board, node_budget=200)
                    result = out.uci() if out else "NONE"
                    if out is None:
                        first = next(iter(board.legal_moves))
                        note = f"-> UCI fallback would play {first.uci()}"
                except Exception:
                    result = "RAISED"
                    note = traceback.format_exc(limit=3).replace("\n", " | ")
            mark = " <<<" if (go and result == "NONE") else ""
            print(f"{board.fullmove_number:>4} {board.san(mv):<8} "
                  f"{str(c3):>6} {str(c50):>7} {str(go):>8} {result:<12} "
                  f"{note}{mark}")
        board.push(mv)


if __name__ == "__main__":
    main()
