"""Honesty check: scan a finished A/B pgn for WON-GAMES-THROWN — draws where one
engine was up material at the end. Tells convON-drew-won (fix FAILED) apart from
convOFF-drew-won (expected) apart from balanced legit draws."""
import sys, chess, chess.pgn
VAL = {chess.PAWN:1, chess.KNIGHT:3, chess.BISHOP:3, chess.ROOK:5, chess.QUEEN:9, chess.KING:0}
path = sys.argv[1]
def matdiff(b, color):
    s = 0
    for _, pc in b.piece_map().items():
        s += VAL[pc.piece_type]*(1 if pc.color==color else -1)
    return s
won_drawn = {"SW-convON":0, "SW-convOFF":0, "other":0}
balanced_draws = 0; decisive = 0; total = 0
with open(path) as f:
    while True:
        g = chess.pgn.read_game(f)
        if g is None: break
        total += 1
        res = g.headers.get("Result","*")
        w, bl = g.headers.get("White",""), g.headers.get("Black","")
        b = g.board()
        for mv in g.mainline_moves(): b.push(mv)
        if res != "1/2-1/2":
            decisive += 1; continue
        if b.is_insufficient_material():
            balanced_draws += 1; continue       # KBvK etc -- dead draw, not thrown
        dw = matdiff(b, chess.WHITE)
        if abs(dw) >= 4:                         # clear edge beyond a lone minor
            up = w if dw > 0 else bl   # engine that was up material
            won_drawn[up if up in won_drawn else "other"] = \
                won_drawn.get(up if up in won_drawn else "other", 0) + 1
            print(f"  WON-DRAWN: {up} was +{abs(dw)} | {w} vs {bl} | end {b.fen()}")
        else:
            balanced_draws += 1
print(f"\n{path}")
print(f"  games {total} | decisive {decisive} | balanced draws {balanced_draws}")
print(f"  WON-then-DRAWN by: convON={won_drawn['SW-convON']} "
      f"convOFF={won_drawn['SW-convOFF']} other={won_drawn['other']}")
