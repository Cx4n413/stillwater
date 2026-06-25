"""Write games/openings.pgn: ~60 balanced mainline openings (8-12 plies),
each as a PGN game stub. cutechess plays each with colors swapped under
-repeat, order=random — diversity for deterministic engine tiers.
Run: python tools/make_book.py
"""

import os

import chess
import chess.pgn

LINES = [
    # 1.e4 e5
    "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7",
    "e4 e5 Nf3 Nc6 Bb5 Nf6 O-O Nxe4 d4 Nd6",
    "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d3 d6",
    "e4 e5 Nf3 Nc6 Bc4 Nf6 d3 Bc5 c3 d6",
    "e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Nf6 Nxc6 bxc6",
    "e4 e5 Nf3 Nf6 Nxe5 d6 Nf3 Nxe4 d4 d5",
    "e4 e5 Nc3 Nf6 f4 d5 fxe5 Nxe4",
    # Sicilian
    "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6 Be2 e5",
    "e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 g6 Be3 Bg7",
    "e4 c5 Nf3 Nc6 d4 cxd4 Nxd4 e5 Nb5 d6",
    "e4 c5 Nf3 e6 d4 cxd4 Nxd4 Nc6 Nc3 Qc7",
    "e4 c5 Nf3 Nc6 Bb5 g6 O-O Bg7 c3 Nf6",
    "e4 c5 c3 Nf6 e5 Nd5 d4 cxd4 Nf3 Nc6",
    "e4 c5 Nc3 Nc6 g3 g6 Bg2 Bg7 d3 d6",
    # French / Caro-Kann / others vs 1.e4
    "e4 e6 d4 d5 Nc3 Bb4 e5 c5 a3 Bxc3+ bxc3 Ne7",
    "e4 e6 d4 d5 Nd2 Nf6 e5 Nfd7 Bd3 c5 c3 Nc6",
    "e4 e6 d4 d5 e5 c5 c3 Nc6 Nf3 Qb6",
    "e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5 Ng3 Bg6",
    "e4 c6 d4 d5 e5 Bf5 Nf3 e6 Be2 c5",
    "e4 c6 d4 d5 exd5 cxd5 c4 Nf6 Nc3 e6",
    "e4 d5 exd5 Qxd5 Nc3 Qa5 d4 Nf6 Nf3 c6",
    "e4 d6 d4 Nf6 Nc3 g6 f4 Bg7 Nf3 c5",
    "e4 g6 d4 Bg7 Nc3 d6 f4 Nf6 Nf3 O-O",
    "e4 Nf6 e5 Nd5 d4 d6 Nf3 dxe5 Nxe5 c6",
    # 1.d4 d5
    "d4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 h6",
    "d4 d5 c4 e6 Nc3 Nf6 cxd5 exd5 Bg5 Be7",
    "d4 d5 c4 c6 Nf3 Nf6 Nc3 e6 e3 Nbd7 Bd3 dxc4",
    "d4 d5 c4 c6 Nf3 Nf6 e3 Bf5 Nc3 e6",
    "d4 d5 c4 dxc4 Nf3 Nf6 e3 e6 Bxc4 c5 O-O a6",
    "d4 d5 Nf3 Nf6 c4 e6 g3 Be7 Bg2 O-O O-O dxc4",
    "d4 d5 Bf4 Nf6 e3 c5 c3 Nc6 Nd2 e6",
    "d4 d5 Nf3 Nf6 Bf4 c5 e3 Nc6 Nbd2 cxd4 exd4 Bf5",
    # Indian defenses
    "d4 Nf6 c4 e6 Nc3 Bb4 e3 O-O Bd3 d5 Nf3 c5",
    "d4 Nf6 c4 e6 Nc3 Bb4 Qc2 O-O a3 Bxc3+ Qxc3 b6",
    "d4 Nf6 c4 e6 Nf3 b6 g3 Ba6 b3 Bb4+ Bd2 Be7",
    "d4 Nf6 c4 e6 Nf3 d5 g3 Be7 Bg2 O-O O-O dxc4",
    "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6 Nf3 O-O Be2 e5",
    "d4 Nf6 c4 g6 Nc3 Bg7 e4 d6 f3 O-O Be3 e5",
    "d4 Nf6 c4 g6 Nc3 d5 cxd5 Nxd5 e4 Nxc3 bxc3 Bg7",
    "d4 Nf6 c4 g6 Nf3 Bg7 g3 O-O Bg2 d6 O-O Nbd7",
    "d4 Nf6 c4 c5 d5 b5 cxb5 a6 bxa6 g6",
    "d4 Nf6 c4 c5 d5 e6 Nc3 exd5 cxd5 d6 e4 g6",
    "d4 f5 g3 Nf6 Bg2 e6 Nf3 Be7 O-O O-O c4 d6",
    "d4 Nf6 Bg5 Ne4 Bf4 c5 f3 Qa5+ c3 Nf6",
    "d4 d6 e4 Nf6 Nc3 g6 Nf3 Bg7 Be2 O-O",
    # English / Reti / flank
    "c4 e5 Nc3 Nf6 Nf3 Nc6 g3 d5 cxd5 Nxd5 Bg2 Nb6",
    "c4 e5 Nc3 Nc6 g3 g6 Bg2 Bg7 d3 d6",
    "c4 c5 Nf3 Nf6 d4 cxd4 Nxd4 e6 g3 d5",
    "c4 Nf6 Nc3 e6 e4 d5 e5 d4 exf6 dxc3 bxc3 Qxf6",
    "c4 c5 Nc3 Nc6 g3 g6 Bg2 Bg7 Nf3 Nf6 O-O O-O",
    "Nf3 d5 g3 Nf6 Bg2 e6 O-O Be7 d3 O-O Nbd2 c5",
    "Nf3 Nf6 c4 b6 g3 Bb7 Bg2 e6 O-O Be7 Nc3 O-O",
    "Nf3 d5 d4 Nf6 c4 e6 Nc3 c5 cxd5 Nxd5 e3 Nc6",
    "Nf3 c5 c4 Nc6 Nc3 e5 e3 Nf6 d4 cxd4 exd4 e4",
    "g3 d5 Bg2 Nf6 Nf3 e6 O-O Be7 d3 O-O Nbd2 c5",
    "e4 e5 Nf3 Nc6 Nc3 Nf6 Bb5 Bb4 O-O O-O d3 d6",
    "d4 e6 c4 b6 e4 Bb7 Bd3 Nc6 Nf3 Nb4",
    "e4 c5 Nf3 d6 Bb5+ Bd7 Bxd7+ Qxd7 c4 Nf6 Nc3 g6",
    "d4 g6 e4 Bg7 Nc3 d6 Be3 a6 Nf3 b5",
    "c4 g6 e4 Bg7 d4 d6 Nc3 Nf6 Be2 O-O Bg5 c5",
]

repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out_path = os.path.join(repo, "games", "openings.pgn")
n = 0
with open(out_path, "w", encoding="utf-8") as f:
    for line in LINES:
        board = chess.Board()
        game = chess.pgn.Game()
        node = game
        ok = True
        for san in line.split():
            try:
                mv = board.parse_san(san)
            except ValueError:
                ok = False
                break
            board.push(mv)
            node = node.add_variation(mv)
        if not ok:
            print(f"SKIPPED illegal line: {line}")
            continue
        game.headers["Event"] = "book"
        game.headers["Result"] = "*"
        f.write(str(game) + "\n\n")
        n += 1
print(f"wrote {n} openings to {out_path}")
