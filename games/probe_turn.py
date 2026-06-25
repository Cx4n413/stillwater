import chess, chess.engine, asyncio
asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
SF = r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe"
eng = chess.engine.SimpleEngine.popen_uci(SF, timeout=60)
eng.configure({"Threads": 4, "Hash": 1024})
LIM = chess.engine.Limit(depth=30)

# Positions of interest (White to move) from the endgame
fens = {
 "after 43.Kd2 (ply85, B to move, before f4)":"8/pp6/1n6/1P1k1pp1/P1p5/2P2PP1/1N1K4/8 b - - 1 43",
 "after 44.gxf4 gxf4 (ply88, W to move=45)":"8/pp6/1n6/1P1k4/P1p2p2/2P2P2/1N1K4/8 w - - 0 45",
 "before 45.Ke2 (ply88 W to move)":"8/pp6/1n6/1P1k4/P1p2p2/2P2P2/1N1K4/8 w - - 0 45",
 "after 45.Ke2 (ply89 B to move)":"8/pp6/1n6/1Pk5/P1p2p2/2P2P2/1N2K3/8 b - - 1 45",
 "before 46.Kd2 (ply90 W to move=46)":"8/pp6/1n6/1Pk5/P1p2p2/2P2P2/1N2K3/8 w - - 2 46",
 "after 46.Kd2 (ply91 B to move)":"8/pp6/1n6/1Pk5/P1p2p2/2P2P2/1N1K4/8 b - - 3 46",
}
def cpw(s): return s.white().score(mate_score=100000)
for name,fen in fens.items():
    b=chess.Board(fen)
    info=eng.analyse(b, LIM, multipv=4)
    print("\n==",name)
    print("   fen",fen)
    for i,pv in enumerate(info):
        mv=pv["pv"][0]; sc=cpw(pv["score"])
        line=" ".join(b.san(m) for m in pv["pv"][:6])
        print(f"   pv{i+1} {b.san(mv):6s} wPOV={sc:>7}  {line}")
eng.quit()
print("PROBE_DONE")
