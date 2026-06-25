import chess.pgn, re
PGN = r"C:\Users\nonna\Downloads\ExperimentalChessEngine\games\placement_concentrate.pgn"
with open(PGN, encoding="utf-8") as f:
    game=None
    for i in range(11): game=chess.pgn.read_game(f)
board=game.board(); node=game; ply=0
print(f"{'ply':>3} {'mv':>3} side san     SWeval depth  time")
tot_w=0.0
while node.variations:
    node=node.variation(0); mv=node.move; w=board.turn; san=board.san(mv); board.push(mv); ply+=1
    c=node.comment.strip(); mvno=(ply+1)//2
    m=re.search(r'([+-]?\d+\.\d+|[+-]?M?\d+)/(\d+)\s+([\d.]+)s', c)
    if w and m:
        ev,dp,tm=m.group(1),m.group(2),float(m.group(3)); tot_w+=tm
        print(f"{ply:3d} {mvno:3d} W   {san:7s} {ev:>7} d{dp:>2}  {tm:7.3f}s")
    elif w:
        print(f"{ply:3d} {mvno:3d} W   {san:7s}  {c}")
print(f"total white time used: {tot_w:.1f}s  (clock 40/900 => 900s for 40 moves)")
