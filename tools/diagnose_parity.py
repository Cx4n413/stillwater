"""Extract the disagreement windows from the parity match.

For each decisive game: find the earliest ply where the eventual winner's
own eval claims a clear edge (>= +1.0 from its perspective) while SW's
nearest own eval still reads roughly equal (>= -0.5). The FEN at SW's move
in that window is where SW's search misjudged — the dossier these positions
form is the per-eval gap, made concrete.

Run anytime; reads games/parity_match.pgn as far as it has gotten.
"""

from __future__ import annotations

import json
import os
import re
import sys

import chess.pgn

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    games = []
    with open(os.path.join(REPO, "games", "parity_match.pgn")) as f:
        while True:
            g = chess.pgn.read_game(f)
            if g is None:
                break
            games.append(g)

    dossier = []
    for gi, g in enumerate(games, 1):
        h = g.headers
        if h["Result"] not in ("1-0", "0-1"):
            continue
        sw_white = h["White"].startswith("SW")
        lc_won = (h["Result"] == "1-0") != sw_white
        if not lc_won:
            continue
        board = g.board()
        node = g
        ply = 0
        moves = []  # (ply, san, fen_before, eval_float_or_None, is_sw)
        while node.variations:
            nxt = node.variation(0)
            ply += 1
            san = board.san(nxt.move)
            fen = board.fen()
            m = re.search(r"([+-]?\d+\.\d+|[+-]?M\d+)/\d+ (\d+\.\d+)s",
                          nxt.comment)
            ev = None
            if m and not m.group(1).lstrip("+-").startswith("M"):
                ev = float(m.group(1))
            is_white_move = ply % 2 == 1
            moves.append((ply, san, fen, ev, is_white_move == sw_white))
            board.push(nxt.move)
            node = nxt

        # earliest lc0 move with own-eval >= +1.0 where SW's PREVIOUS own
        # eval was >= -0.5 (SW thought it was fine going in)
        found = None
        for i, (p, san, fen, ev, is_sw) in enumerate(moves):
            if is_sw or ev is None or ev < 1.0:
                continue
            prev_sw = [m for m in moves[:i] if m[4] and m[3] is not None]
            if prev_sw and prev_sw[-1][3] >= -0.5:
                found = (i, prev_sw[-1])
                break
        if not found:
            continue
        i, sw_last_ok = found
        lc_move = moves[i]
        # the SW move(s) between "fine" and lc0's claim are the suspects
        suspects = [m for m in moves[sw_last_ok[0] - 1:i] if m[4]]
        entry = {
            "game": gi,
            "white": h["White"], "black": h["Black"], "result": h["Result"],
            "sw_last_ok": {"ply": sw_last_ok[0], "san": sw_last_ok[1],
                           "fen": sw_last_ok[2], "eval": sw_last_ok[3]},
            "lc0_claim": {"ply": lc_move[0], "san": lc_move[1],
                          "fen": lc_move[2], "eval": lc_move[3]},
            "sw_suspect_moves": [
                {"ply": m[0], "san": m[1], "fen": m[2], "eval": m[3]}
                for m in suspects],
        }
        dossier.append(entry)
        print(f"g{gi}: SW ok at ply {sw_last_ok[0]} ({sw_last_ok[3]:+.2f}) "
              f"-> lc0 claims {lc_move[3]:+.2f} at ply {lc_move[0]}; "
              f"suspects: {' '.join(m[1] for m in suspects)}")

    out = os.path.join(REPO, "games", "parity_dossier.json")
    with open(out, "w") as f:
        json.dump(dossier, f, indent=1)
    print(f"{len(dossier)} disagreement windows -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
