"""Play STILLWATER in the terminal.

    python play.py                 # you play White, 10s/move engine
    python play.py --black         # you play Black
    python play.py --movetime 30   # deeper thought
    python play.py --mock          # no GPU needed (weak; plumbing demo)

Enter moves as UCI (e2e4) or SAN (Nf3). Commands: 'fen' to dump, 'quit'.
"""

from __future__ import annotations

import argparse
import sys

import chess

from stillwater.engine import Engine

UNICODE = True


def render(board: chess.Board, flipped: bool = False) -> str:
    s = board.unicode(invert_color=True, borders=False, empty_square=".")
    rows = s.split("\n")
    if flipped:
        rows = [r[::-1].replace(". ", " .") for r in reversed(rows)]
    out = []
    ranks = range(8, 0, -1) if not flipped else range(1, 9)
    for rank, row in zip(ranks, rows):
        out.append(f"{rank}  {row}")
    files = "   a b c d e f g h" if not flipped else "   h g f e d c b a"
    out.append(files)
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--black", action="store_true", help="you play Black")
    ap.add_argument("--movetime", type=float, default=10.0,
                    help="engine seconds per move")
    ap.add_argument("--mock", action="store_true", help="use the mock oracle")
    args = ap.parse_args()

    if args.mock:
        from stillwater.mock_oracle import MockOracle
        engine = Engine(oracle=MockOracle())
    else:
        engine = Engine()  # loads the Lc0 oracle from nets/

    board = chess.Board()
    human_white = not args.black
    print("STILLWATER — the engine that thinks by letting the water settle.\n")

    while not board.is_game_over(claim_draw=True):
        print(render(board, flipped=args.black))
        print()
        if board.turn == chess.WHITE and human_white or \
           board.turn == chess.BLACK and not human_white:
            raw = input("your move> ").strip()
            if raw in ("quit", "exit"):
                return
            if raw == "fen":
                print(board.fen())
                continue
            try:
                move = chess.Move.from_uci(raw)
                if move not in board.legal_moves:
                    raise ValueError
            except ValueError:
                try:
                    move = board.parse_san(raw)
                except ValueError:
                    print("  illegal / unparseable, try again")
                    continue
            board.push(move)
        else:
            print("  ... settling ...")
            move, info = engine.think(board, movetime=args.movetime)
            if move is None:
                break
            board.push(move)
            wdl = info.get("wdl", (0, 0, 0))
            print(f"  STILLWATER plays {move.uci()}   "
                  f"[eval {info.get('cp', 0):+d}cp  "
                  f"W/D/L {wdl[0]:.2f}/{wdl[1]:.2f}/{wdl[2]:.2f}  "
                  f"P(best) {info.get('p_best', 0):.2f}  "
                  f"{info.get('evals', 0)} evals  "
                  f"{info.get('lessons', 0)} lessons]")
        print()

    print(render(board, flipped=args.black))
    print(f"\nResult: {board.result(claim_draw=True)}")


if __name__ == "__main__":
    sys.exit(main())
