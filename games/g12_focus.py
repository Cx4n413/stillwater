import chess, chess.engine

SF = r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe"
eng = chess.engine.SimpleEngine.popen_uci(SF, timeout=60)
eng.configure({"Threads":4, "Hash":1024})
LIM = chess.engine.Limit(depth=30)

# (label, fen-before-the-move-to-judge, uci move actually played by side-to-move or None just to show)
positions = [
 ("88...Qxg5 done; 89 W to move (whose move? White). show", "8/p4k2/P1p2p1Q/1pPp2q1/1P1P2P1/3K2P1/8/8 w - - 0 89", None),
 ("90 Qf5 done; 90...? Black to move. PLAYED Ke7", "5k2/p7/P1p2p2/1pPp1Qq1/1P1P2P1/3K2P1/8/8 b - - 3 90", "f8e7"),
 ("91 Qh7+ done; 91...? Black to move. PLAYED Ke6", "8/p3k2Q/P1p2p2/1pPp2q1/1P1P2P1/3K2P1/8/8 b - - 5 91", "e7e6"),
 ("91...Ke6 done; 92 W to move. (this is what SF faced -> Qc7)", "8/p6Q/P1p1kp2/1pPp2q1/1P1P2P1/3K2P1/8/8 w - - 6 92", None),
 ("92 Qc7 done; 92...? Black to move. PLAYED Qg6+", "8/p1Q5/P1p1kp2/1pPp2q1/1P1P2P1/3K2P1/8/8 b - - 7 92", "g5g6"),
 ("93 Kc3 done; 93...? Black to move. PLAYED Qb1", "8/p1Q5/P1p1kpq1/1pPp4/1P1P2P1/2K3P1/8/8 b - - 9 93", "g6b1"),
]

def show(board, label):
    info = eng.analyse(board, LIM, multipv=3)
    print("\n=== "+label, flush=True)
    print("    FEN:", board.fen(), "| STM:", "White" if board.turn else "Black", "| men:", chess.popcount(board.occupied), flush=True)
    for i, pv in enumerate(info):
        sc = pv["score"].white()
        s = sc.score(mate_score=100000)
        line = board.variation_san(pv["pv"][:8])
        print(f"    pv{i+1}: whitePOV={s:+7d}  {line}", flush=True)
    return info[0]["score"].white().score(mate_score=100000)

for label, fen, played in positions:
    b = chess.Board(fen)
    best_white = show(b, label)
    if played:
        m = chess.Move.from_uci(played)
        san = b.san(m)
        b.push(m)
        info = eng.analyse(b, LIM)
        sc = info["score"].white().score(mate_score=100000)
        # cp loss from Black's perspective (Black is mover here)
        # best for black before = -best_white ; after playing = -sc
        cploss = (-best_white) - (-sc) if not chess.Board(fen).turn else (best_white)-(sc)
        print(f"    --> PLAYED {san}: resulting whitePOV={sc:+7d}  | BlackPOV before-best={-best_white:+6d} after={-sc:+6d} cpLoss={(-best_white)-(-sc):+6d}", flush=True)

eng.quit()
