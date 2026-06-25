import chess, chess.engine, asyncio
asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
SF = r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe"
eng = chess.engine.SimpleEngine.popen_uci(SF, timeout=60)
eng.configure({"Threads": 3, "Hash": 1024})
LIM = chess.engine.Limit(depth=28)
fens = {
 "ply85 after 43.Kd2 (B to move)":"8/pp6/1n6/1P1k1pp1/P1p5/2P2PP1/1N1K4/8 b - - 1 43",
 "ply86 after 43...f4 (W to move=44)":"8/pp6/1n6/1P1k2p1/P1p2p2/2P2PP1/1N1K4/8 w - - 0 44",
 "ply88 after 44.gxf4 gxf4 (W to move=45)":"8/pp6/1n6/1P1k4/P1p2p2/2P2P2/1N1K4/8 w - - 0 45",
 "ply89 after 45.Ke2 (B to move)":"8/pp6/1n6/1Pk5/P1p2p2/2P2P2/1N2K3/8 b - - 1 45",
 "ply90 before 46.? (W to move=46)":"8/pp6/1n6/1Pk5/P1p2p2/2P2P2/1N2K3/8 w - - 2 46",
 "ply91 after 46.Kd2 (B to move)":"8/pp6/1n6/1Pk5/P1p2p2/2P2P2/1N1K4/8 b - - 3 46",
}
def cpw(s): return s.white().score(mate_score=100000)
def lsan(b, pv, n=6):
    bb=b.copy(); out=[]
    for m in pv[:n]:
        out.append(bb.san(m)); bb.push(m)
    return " ".join(out)
for name,fen in fens.items():
    b=chess.Board(fen)
    info=eng.analyse(b, LIM, multipv=5)
    print(f"\n== {name}")
    for i,pv in enumerate(info):
        sc=cpw(pv["score"]);
        print(f"   pv{i+1} wPOV={sc:>7}  {lsan(b, pv['pv'])}")
eng.quit()
print("PROBE2_DONE")
