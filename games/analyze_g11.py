import chess, chess.pgn, chess.engine, io, sys, asyncio
asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

SF = r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe"
PGN = r"C:\Users\nonna\Downloads\ExperimentalChessEngine\games\placement_concentrate.pgn"

# Read the 11th game
with open(PGN, encoding="utf-8") as f:
    game = None
    for i in range(11):
        game = chess.pgn.read_game(f)

print("White:", game.headers["White"], "Black:", game.headers["Black"], "Result:", game.headers["Result"])

eng = chess.engine.SimpleEngine.popen_uci(SF, timeout=60)
eng.configure({"Threads": 6, "Hash": 2048})
LIM = chess.engine.Limit(depth=27)

def cp_white(score):
    # score POV white, in cp; mate mapped to large
    return score.white().score(mate_score=100000)

board = game.board()
node = game

# eval of starting position
info = eng.analyse(board, LIM)
prev_eval = cp_white(info["score"])
print(f"start eval (white POV cp): {prev_eval}")

rows = []
ply = 0
while node.variations:
    node = node.variation(0)
    mv = node.move
    mover_is_white = board.turn  # True if white to move (about to move)
    san = board.san(mv)
    board.push(mv)
    ply += 1
    info = eng.analyse(board, LIM)
    cur_eval = cp_white(info["score"])
    # centipawn loss from mover's perspective:
    # eval before move (white POV) = prev_eval ; after = cur_eval
    if mover_is_white:
        # white wants high; loss = prev - cur
        loss = prev_eval - cur_eval
    else:
        loss = cur_eval - prev_eval  # black wants low white-eval; loss = (after - before) from white pov means black gained if positive... fix:
        loss = -(cur_eval - prev_eval)  # black loss = increase in white eval
    comment = node.comment.strip()
    rows.append((ply, "W" if mover_is_white else "B", san, prev_eval, cur_eval, loss, comment))
    prev_eval = cur_eval
    mvno = (ply + 1) // 2
    print(f"{ply:3d} {mvno:2d}{'.' if mover_is_white else '...'} {san:7s} before={prev_eval if False else ''} after_whitePOV={cur_eval:7d} loss={loss:7d}  {comment}")

eng.quit()

print("\n=== SW (WHITE) moves sorted by cp loss ===")
sw = [r for r in rows if r[1]=="W"]
for r in sorted(sw, key=lambda x: -x[5])[:12]:
    ply, side, san, bef, aft, loss, comment = r
    mvno = (ply+1)//2
    print(f"move {mvno}. {san:7s} ply{ply:3d}  afterWPOV={aft:7d}  cploss={loss:6d}  SWcomment={comment}")
