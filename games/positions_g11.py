import chess, chess.pgn
PGN = r"C:\Users\nonna\Downloads\ExperimentalChessEngine\games\placement_concentrate.pgn"
with open(PGN, encoding="utf-8") as f:
    game = None
    for i in range(11):
        game = chess.pgn.read_game(f)
board = game.board()
node = game
ply = 0
targets = {44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97}
while node.variations:
    node = node.variation(0)
    mv = node.move
    san = board.san(mv)
    board.push(mv)
    ply += 1
    mvno = (ply+1)//2
    if ply in targets:
        men = chess.popcount(board.occupied)
        print(f"ply{ply:3d} {mvno}{'.' if ply%2==1 else '...'}{san:7s} men={men} fen={board.fen()}")
