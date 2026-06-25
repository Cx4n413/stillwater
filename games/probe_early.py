import chess, chess.engine, asyncio
asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
SF = r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe"
eng = chess.engine.SimpleEngine.popen_uci(SF, timeout=60)
eng.configure({"Threads": 3, "Hash": 1024})
LIM = chess.engine.Limit(depth=28)
# positions BEFORE each White move (W to move) and the eval before/after, moves 33-43
seq = [
 ("33 W before Kxe2 (ply64 done, W=33 to move Kxe2 forced recap)","8/pppk1pp1/4n3/8/PP2N2p/2P2P2/4r1PP/5K2 w - - 0 33"),
 ("34 W before Nf2 (ply66)","8/pppk2p1/4n3/5p2/PP2N2p/2P2P2/4K1PP/8 w - - 0 34"),
 ("36 W before Nd1 (ply70)","8/pppk2p1/8/3n1p2/PP5p/2P2P2/5NPP/5K2 w - - 4 36"),
 ("37 W before b5 (ply72)","8/pp1k2p1/8/2pn1p2/PP5p/2P2P2/6PP/3N1K2 w - - 0 37"),
 ("38 W before Ke2 (ply74)","8/pp4p1/3k4/1Ppn1p2/P6p/2P2P2/6PP/3N1K2 w - - 1 38"),
 ("39 W before Nb2 (ply76)","8/pp4p1/1n1k4/1Pp2p2/P6p/2P2P2/4K1PP/3N4 w - - 3 39"),
 ("40 W before g3 (ply78)","8/pp4p1/1n6/1Ppk1p2/P6p/2P2P2/1N2K1PP/8 w - - 5 40"),
 ("41 W before hxg3 (ply80)","8/pp4p1/1n6/1Ppk1p2/P7/2P2Pp1/1N2K2P/8 w - - 0 41"),
 ("42 W before Kd3 (ply82)","8/pp6/1n6/1Ppk1pp1/P7/2P2PP1/1N2K3/8 w - - 0 42"),
 ("43 W before Kd2 (ply84)","8/pp6/1n6/1P1k1pp1/P1p5/2PK1PP1/1N6/8 w - - 0 43"),
]
def cpw(s): return s.white().score(mate_score=100000)
def lsan(b, pv, n=6):
    bb=b.copy(); out=[]
    for m in pv[:n]:
        out.append(bb.san(m)); bb.push(m)
    return " ".join(out)
for name,fen in seq:
    b=chess.Board(fen)
    info=eng.analyse(b, LIM, multipv=3)
    print(f"\n== {name}")
    for i,pv in enumerate(info):
        print(f"   pv{i+1} wPOV={cpw(pv['score']):>7}  {lsan(b, pv['pv'])}")
eng.quit()
print("EARLY_DONE")
