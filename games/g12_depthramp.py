import chess, chess.engine
SF = r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe"
eng = chess.engine.SimpleEngine.popen_uci(SF, timeout=60)
eng.configure({"Threads":2, "Hash":512})
# Position BEFORE 91...Ke6 : Black to move. fen:
fen = "8/p3k2Q/P1p2p2/1pPp2q1/1P1P2P1/3K2P1/8/8 b - - 5 91"
b = chess.Board(fen)
print("Position before 91...Ke6 (Black to move). Does a shallow search avoid Ke6?")
for d in [6,8,9,10,12,14,16,18,22,26,30]:
    info = eng.analyse(b, chess.engine.Limit(depth=d), multipv=2)
    out=[]
    for pv in info:
        sc=pv["score"].pov(chess.BLACK).score(mate_score=100000)
        mv=b.san(pv["pv"][0])
        out.append(f"{mv}={sc:+d}")
    print(f"  depth {d:2d}: best -> {', '.join(out)}")
# Also: evaluate Ke6 explicitly at each depth (Black POV)
print("\nForced line: after 91...Ke6, white-to-move eval (BlackPOV) by depth:")
b2 = chess.Board(fen); b2.push(chess.Move.from_uci("e7e6"))
for d in [6,8,9,10,12,16,22,30]:
    info = eng.analyse(b2, chess.engine.Limit(depth=d))
    sc = info["score"].pov(chess.BLACK).score(mate_score=100000)
    print(f"  depth {d:2d}: Ke6 leads to BlackPOV {sc:+d}")
# Post-blunder move quality (shallow truth d=24) — were SW's follow-ups forced?
print("\nPost-blunder follow-ups (Black POV, depth 24):")
checks = [
 ("92...Qg6+ vs best", "8/p1Q5/P1p1kp2/1pPp2q1/1P1P2P1/3K2P1/8/8 b - - 7 92", "g5g6"),
 ("93...Qb1 vs best",  "8/p1Q5/P1p1kpq1/1pPp4/1P1P2P1/2K3P1/8/8 b - - 9 93", "g6b1"),
]
for label, fen, played in checks:
    bb = chess.Board(fen)
    info = eng.analyse(bb, chess.engine.Limit(depth=24), multipv=2)
    best = info[0]["score"].pov(chess.BLACK).score(mate_score=100000)
    bestmv = bb.san(info[0]["pv"][0])
    pm = chess.Move.from_uci(played); psan = bb.san(pm); bb.push(pm)
    aft = eng.analyse(bb, chess.engine.Limit(depth=24))["score"].pov(chess.BLACK).score(mate_score=100000)
    print(f"  {label}: best={bestmv}({best:+d})  played={psan}({aft:+d})  cpLoss={best-aft:+d}")
eng.quit()

