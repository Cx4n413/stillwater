import chess, chess.pgn, chess.engine, io, sys

PGN = r"C:\Users\nonna\Downloads\ExperimentalChessEngine\games\placement_concentrate.pgn"
SF  = r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe"

# Read 12th game
with open(PGN, encoding="utf-8") as f:
    games = []
    while True:
        g = chess.pgn.read_game(f)
        if g is None:
            break
        games.append(g)

game = games[11]  # 0-indexed -> 12th
print("White:", game.headers["White"], "Black:", game.headers["Black"], "Result:", game.headers["Result"])
print("PlyCount:", game.headers.get("PlyCount"))

eng = chess.engine.SimpleEngine.popen_uci(SF)
eng.configure({"Threads": 6, "Hash": 2048})
LIMIT = chess.engine.Limit(depth=27)

board = game.board()
# eval AFTER each move, White POV in cp; mate -> +/-100000-ish scaled
def score_cp(info_score, board_after):
    s = info_score.white()
    return s.score(mate_score=100000)

# starting eval
info = eng.analyse(board, LIMIT)
prev_white_cp = score_cp(info["score"], board)
records = []  # (ply, movno, side, san, white_cp_after, comment_eval_from_pgn)

node = game
ply = 0
for node in game.mainline():
    move = node.move
    side = "W" if board.turn == chess.WHITE else "B"
    movno = board.fullmove_number
    san = board.san(move)
    comment = node.comment.strip()
    board.push(move)
    info = eng.analyse(board, LIMIT)
    wcp = score_cp(info["score"], board)
    ply += 1
    records.append((ply, movno, side, san, wcp, comment))
    sys.stderr.write(f"ply {ply} {movno}{'.' if side=='W' else '...'} {san} -> white_cp={wcp}\n")

eng.quit()

# Now compute SW (Black) per-move cp loss.
# white_cp before SW's move vs after. From Black POV, eval = -white_cp.
# cp loss for Black move = (black_eval_before_best) - (black_eval_after_actual)
# We approximate using SF eval before and after the move. Loss = black_cp_before - black_cp_after
# where black_cp = -white_cp. A drop means Black got worse.
print("\n=== SW (Black) move cp-loss (SF depth27, White-POV cp; BlackPOV=-that) ===")
prev = prev_white_cp
out = []
for (ply, movno, side, san, wcp, comment) in records:
    if side == "B":
        black_before = -prev          # black eval before this black move (=eval after prior white move)
        black_after  = -wcp           # black eval after this black move
        loss = black_before - black_after  # positive = SW lost cp
        out.append((movno, san, black_before, black_after, loss, comment))
    prev = wcp

for (movno, san, bb, ba, loss, comment) in out:
    flag = ""
    if loss >= 300: flag = "   <<< BIG BLUNDER"
    elif loss >= 150: flag = "  << error"
    elif loss >= 80: flag = " < inaccuracy"
    print(f"{movno}... {san:8s} BlackEval before={bb/100:+.2f} after={ba/100:+.2f} loss={loss/100:+.2f}  PGN{{{comment}}}{flag}")

# Full per-ply white-cp table for turning point
print("\n=== Full white-POV cp after each ply ===")
for (ply, movno, side, san, wcp, comment) in records:
    print(f"ply{ply:3d} {movno:3d}{'.' if side=='W' else '...'} {san:8s} whiteCP={wcp/100:+.2f}  {{{comment}}}")
