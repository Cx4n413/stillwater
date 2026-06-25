import chess, chess.pgn, chess.engine, sys, io

SF = r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe"
PGN = r"C:\Users\nonna\Downloads\ExperimentalChessEngine\games\game12.pgn"

game = chess.pgn.read_game(open(PGN))
print("White:", game.headers["White"], "Black:", game.headers["Black"], "Result:", game.headers["Result"])

eng = chess.engine.SimpleEngine.popen_uci(SF, timeout=60)
eng.configure({"Threads":6, "Hash":2048})
LIM = chess.engine.Limit(depth=27)

def cp_white(board):
    info = eng.analyse(board, LIM)
    sc = info["score"].white()
    if sc.is_mate():
        m = sc.mate()
        return ((30000 - abs(m)*10) if m>0 else -(30000 - abs(m)*10)), info.get("pv",[None])[0]
    return sc.score(), info.get("pv",[None])[0]

moves = list(game.mainline_moves())
sw_evals = {}
n = game
while n.variations:
    n = n.variations[0]
    if n.comment:
        sw_evals[n.ply()] = n.comment.strip()

board = game.board()
prev_white, prev_pv = cp_white(board)
print("Start eval (White POV cp):", prev_white)
results = []
ply = 0
for mv in moves:
    ply += 1
    mover_is_white = board.turn == chess.WHITE
    san = board.san(mv)
    board.push(mv)
    cur_white, best_pv = cp_white(board)
    if mover_is_white:
        before_mover = prev_white; after_mover = cur_white
    else:
        before_mover = -prev_white; after_mover = -cur_white
    cploss = before_mover - after_mover
    movenum = (ply+1)//2
    comment = sw_evals.get(ply, "")
    bestsan = ""
    results.append((ply, movenum, "W" if mover_is_white else "B", san, before_mover, after_mover, cploss, cur_white, comment))
    prev_white = cur_white

eng.quit()

print("\nply move side san  beforeMoverCP afterMoverCP cpLoss  whitePOVafter  SWcomment")
for r in results:
    ply, mn, side, san, bm, am, cl, cw, cm = r
    flag = " <<<SW_ERR" if (side=="B" and cl>=80) else ""
    print(f"{ply:3d} {mn:3d} {side} {san:7s} {bm:7d} {am:7d} {cl:7d}  {cw:7d}  {cm}{flag}")

print("\n=== TOP SW (Black) errors by cp loss ===")
sw_errs = [r for r in results if r[2]=="B"]
sw_errs.sort(key=lambda r:-r[6])
for r in sw_errs[:8]:
    ply, mn, side, san, bm, am, cl, cw, cm = r
    print(f"ply{ply} move {mn}...{san}  cpLoss={cl}  beforeBlackPOV={bm} afterBlackPOV={am}  SWcomment={cm}")
