import chess, chess.pgn, chess.engine, asyncio
asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

SF = r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe"
PGN = r"C:\Users\nonna\Downloads\ExperimentalChessEngine\games\placement_concentrate.pgn"
OUT = r"C:\Users\nonna\Downloads\ExperimentalChessEngine\games\g11_results.csv"

with open(PGN, encoding="utf-8") as f:
    game = None
    for i in range(11):
        game = chess.pgn.read_game(f)

eng = chess.engine.SimpleEngine.popen_uci(SF, timeout=60)
eng.configure({"Threads": 6, "Hash": 2048})
LIM = chess.engine.Limit(depth=27)

def cpw(score):
    return score.white().score(mate_score=100000)

board = game.board()
info = eng.analyse(board, LIM)
prev = cpw(info["score"])

out = open(OUT, "w", encoding="utf-8", buffering=1)
out.write("ply,mvno,side,san,after_wpov_cp,cploss,sw_comment\n")
out.flush()

node = game
ply = 0
while node.variations:
    node = node.variation(0)
    mv = node.move
    mover_white = board.turn
    san = board.san(mv)
    board.push(mv)
    ply += 1
    info = eng.analyse(board, LIM)
    cur = cpw(info["score"])
    loss = (prev - cur) if mover_white else (cur - prev)
    comment = node.comment.strip().replace(","," ").replace("\n"," ")
    mvno = (ply+1)//2
    side = "W" if mover_white else "B"
    out.write(f"{ply},{mvno},{side},{san},{cur},{loss},{comment}\n")
    out.flush()
    prev = cur

out.close()
eng.quit()
print("DONE_ANALYSIS")
