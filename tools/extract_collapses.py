"""Extract the collapse-decision positions from the ceiling match: for each SW
loss with a sharp 2-move collapse, the FEN right before SW's losing decision,
the move SW played, and the time it spent. Output JSON for the premise gate.
"""
import json
import re
import sys

import chess
import chess.pgn

PGN = sys.argv[1] if len(sys.argv) > 1 else "games/lc0_ceiling.pgn"
OUT = sys.argv[2] if len(sys.argv) > 2 else "games/collapse_positions.json"


def cap(e):
    return max(-3.0, min(3.0, e))


out = []
with open(PGN, encoding="utf-8", errors="ignore") as fh:
    while True:
        g = chess.pgn.read_game(fh)
        if g is None:
            break
        h = g.headers
        sw_white = "SW" in h.get("White", "")
        sw_black = "SW" in h.get("Black", "")
        if not (sw_white or sw_black):
            continue
        res = h.get("Result", "*")
        sw_lost = (res == "1-0" and sw_black) or (res == "0-1" and sw_white)
        if not sw_lost:
            continue
        board = g.board()
        sw_moves = []   # (fen_before, uci, eval, time)
        for node in g.mainline():
            mv = node.move
            is_sw = (board.turn == chess.WHITE) == sw_white
            c = node.comment or ""
            m = re.match(r"([+-]?[\d.]+|[+-]?M\d+)(?:/\d+)?\s*(?:([\d.]+)s)?", c)
            if is_sw and m and "book" not in c:
                ev = m.group(1)
                try:
                    e = cap(float(ev))
                except ValueError:
                    e = 3.0 if ev.startswith("+M") else -3.0
                t = float(m.group(2)) if m.group(2) else 0.0
                sw_moves.append((board.fen(), mv.uci(), e, t))
            board.push(mv)
        col = None
        for j in range(2, len(sw_moves)):
            if sw_moves[j][2] <= -0.9 and sw_moves[j - 2][2] >= -0.35:
                col = j
                break
        if col is None:
            continue
        dec = col - 2 if sw_moves[col - 1][2] <= -0.9 else col - 1
        fen, uci, e, t = sw_moves[dec]
        out.append({"round": h.get("Round", "?"), "fen": fen, "played": uci,
                    "eval_before": e, "time_spent": t})

json.dump(out, open(OUT, "w"), indent=1)
print(f"{len(out)} collapse decisions -> {OUT}")
for r in out:
    print(f"  R{r['round']:>4} {r['played']:8} {r['time_spent']:5.2f}s "
          f"eval {r['eval_before']:+.2f}")
