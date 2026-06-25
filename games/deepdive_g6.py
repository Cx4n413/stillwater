import chess, chess.engine

SF = r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe"

# Critical positions to deep-analyze (FEN before SW's move, the move SW played)
POSITIONS = [
    ("28...Bxd4 (ply56)", "r3qrk1/2b2p2/2p1n2p/N2pP1p1/2pP2P1/7P/P4PP1/1BBQRRK1 b - - 0 28? CHECK", "Bxd4"),
]

eng = chess.engine.SimpleEngine.popen_uci(SF)
eng.configure({"Threads":6, "Hash":2048})

def show(label, fen, played_san=None):
    b = chess.Board(fen)
    print("="*70)
    print(label, " stm=", "W" if b.turn else "B")
    print("FEN:", fen, " pieces:", chess.popcount(b.occupied))
    info = eng.analyse(b, chess.engine.Limit(depth=30), multipv=4)
    for i, pv in enumerate(info):
        sc = pv["score"].pov(b.turn)  # from side-to-move POV (SW=Black here)
        line = b.variation_san(pv["pv"][:8])
        print("  pv%d  %s   %s" % (i+1, str(sc), line))
    if played_san:
        try:
            mv = b.parse_san(played_san)
            b2 = b.copy(); b2.push(mv)
            info2 = eng.analyse(b2, chess.engine.Limit(depth=30))
            sc2 = info2["score"].pov(b.turn)  # POV of the mover (SW)
            pv2 = b2.variation_san(info2["pv"][:8])
            print("  PLAYED %s -> SW-POV %s  ; reply PV: %s" % (played_san, str(sc2), pv2))
        except Exception as e:
            print("  parse error:", e)

# We'll call show() from a driver that passes correct FENs.
import sys
fen = sys.argv[1] if len(sys.argv)>1 else None
played = sys.argv[2] if len(sys.argv)>2 else None
label = sys.argv[3] if len(sys.argv)>3 else "POS"
if fen:
    show(label, fen, played)
eng.quit()
