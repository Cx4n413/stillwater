import chess, chess.pgn, chess.engine, io, sys

PGN = r"C:\Users\nonna\Downloads\ExperimentalChessEngine\games\placement_concentrate.pgn"
SF  = r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe"

DEPTH = 27

# read the 6th game (index 5)
games = []
with open(PGN) as f:
    while True:
        g = chess.pgn.read_game(f)
        if g is None:
            break
        games.append(g)

game = games[5]
print("Game6 White=%s Black=%s Result=%s" % (game.headers["White"], game.headers["Black"], game.headers["Result"]))

# collect moves and SW reported comments
nodes = list(game.mainline())
print("plies:", len(nodes))

eng = chess.engine.SimpleEngine.popen_uci(SF)
eng.configure({"Threads":6, "Hash":2048})

def evalcp(info):
    # POV White, in cp; mate scored as large
    sc = info["score"].white()
    return sc.score(mate_score=100000)

board = game.board()
records = []  # per ply: ply, mover, san, white_cp_after, comment
# eval start position
info = eng.analyse(board, chess.engine.Limit(depth=DEPTH))
prev_white_cp = evalcp(info)
print("startpos white_cp=%d" % prev_white_cp)

ply = 0
for node in nodes:
    mv = node.move
    mover = "W" if board.turn == chess.WHITE else "B"
    san = board.san(mv)
    comment = node.comment.strip()
    board.push(mv)
    ply += 1
    info = eng.analyse(board, chess.engine.Limit(depth=DEPTH))
    white_cp = evalcp(info)
    bestmove = None
    # also compute best move from position BEFORE this move to get cploss precisely
    records.append({
        "ply": ply, "mover": mover, "san": san,
        "white_cp_after": white_cp,
        "comment": comment,
    })
    fullmove = (ply+1)//2
    print("ply %3d %s %-7s white_cp=%6d  {%s}" % (ply, mover, san, white_cp, comment))
    sys.stdout.flush()

eng.quit()

# Save records
import json
with open(r"C:\Users\nonna\Downloads\ExperimentalChessEngine\games\g6_records.json","w") as f:
    json.dump(records, f)
print("saved")
