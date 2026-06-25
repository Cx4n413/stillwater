"""Extract a large, diverse, deduplicated FEN set from real-game PGN databases.

Purpose: build the position corpus for the Distillery harvest (corrector
training). Real-game positions across all phases are far more diverse and
on-distribution than draw-saturated self-play, and every one yields a usable
high-evidence record when STILLWATER analyses it at a fixed budget.

Strategy: walk each game's mainline, sample a few plies spread across the game
(opening/middle/endgame), dedup by piece-placement+stm+castling+ep (ignores the
halfmove/fullmove counters so near-identical positions collapse). Skip terminal
and barely-started positions.

Run: python tools/extract_fens.py <out.txt> <target_count> <pgn1> [pgn2 ...]
"""

from __future__ import annotations

import os
import random
import sys

import chess
import chess.pgn

random.seed(0x57111A7E)  # match the project's lattice salt seed, for tidiness

# fractions of game length to sample -> covers opening through endgame
FRACTIONS = (0.12, 0.28, 0.45, 0.62, 0.80)
MIN_PLY = 6          # skip book-trivial opening positions
MAX_GAMES_PER_FILE = 100_000


def dedup_key(board: chess.Board) -> str:
    # piece placement + side + castling + ep only (no move clocks)
    return board.board_fen() + " " + ("w" if board.turn else "b") + " " \
        + board.castling_xfen() + " " + (chess.square_name(board.ep_square)
                                         if board.ep_square else "-")


def main() -> int:
    out_path = sys.argv[1]
    target = int(sys.argv[2])
    pgns = sys.argv[3:]
    if not pgns:
        print("need at least one PGN path")
        return 1

    seen: set[str] = set()
    fens: list[str] = []
    games_read = 0

    for path in pgns:
        if not os.path.exists(path):
            print(f"  (missing {path}, skipping)")
            continue
        print(f"reading {os.path.basename(path)} ...")
        fh = open(path, encoding="utf-8", errors="replace")
        file_games = 0
        while len(fens) < target and file_games < MAX_GAMES_PER_FILE:
            try:
                game = chess.pgn.read_game(fh)
            except Exception:
                continue
            if game is None:
                break
            file_games += 1
            games_read += 1
            moves = list(game.mainline_moves())
            n = len(moves)
            if n < MIN_PLY + 2:
                continue
            want = sorted({max(MIN_PLY, min(n - 1, int(f * n)))
                           for f in FRACTIONS})
            board = game.board()
            for ply, mv in enumerate(moves):
                board.push(mv)
                if ply in want and not board.is_game_over(claim_draw=False):
                    k = dedup_key(board)
                    if k not in seen:
                        seen.add(k)
                        fens.append(board.fen())
            if file_games % 2000 == 0:
                print(f"  {file_games} games, {len(fens)} unique FENs")
        fh.close()
        print(f"  done {os.path.basename(path)}: {file_games} games")
        if len(fens) >= target:
            break

    random.shuffle(fens)
    fens = fens[:target]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(fens) + "\n")
    print(f"\n{len(fens)} unique FENs from {games_read} games -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
