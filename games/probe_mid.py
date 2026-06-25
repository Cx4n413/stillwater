import chess, chess.engine, asyncio
asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
SF = r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe"
eng = chess.engine.SimpleEngine.popen_uci(SF, timeout=60)
eng.configure({"Threads": 3, "Hash": 1024})
LIM = chess.engine.Limit(depth=28)
import chess.pgn
PGN = r"C:\Users\nonna\Downloads\ExperimentalChessEngine\games\placement_concentrate.pgn"
with open(PGN, encoding="utf-8") as f:
    g=None
    for i in range(11): g=chess.pgn.read_game(f)
# walk and eval after every move for plies 18..64 (middlegame->endgame entry)
b=g.board(); node=g; ply=0
def cpw(s): return s.white().score(mate_score=100000)
info=eng.analyse(b, LIM); prev=cpw(info["score"])
while node.variations:
    node=node.variation(0); mv=node.move; w=b.turn; san=b.san(mv); b.push(mv); ply+=1
    if 14 <= ply <= 64:
        info=eng.analyse(b, LIM); cur=cpw(info["score"])
        loss=(prev-cur) if w else (cur-prev)
        mvno=(ply+1)//2
        print(f"ply{ply:3d} {mvno:2d}{'.' if w else '...'}{san:6s} wPOV={cur:>6} {'WLOSS='+str(loss) if w else ''}")
        prev=cur
    else:
        if 14 <= ply <= 64: pass
        # still need prev updated for boundary; cheap eval skip -> recompute prev only at entry
        if ply==13:
            info=eng.analyse(b, LIM); prev=cpw(info["score"])
eng.quit()
print("MID_DONE")
