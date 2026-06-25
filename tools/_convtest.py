"""Focused: play out ONLY the KQ+2P-vs-K won position with the live engine,
capturing every [dbg] line, to see exactly which branch of _best_move fires."""
import chess, chess.engine, os
BAT = r"C:\Users\nonna\Downloads\ExperimentalChessEngine\stillwater_uci.bat"
FEN = "8/8/8/3k4/8/2P1P3/8/3QK3 w - - 0 1"
eng = chess.engine.SimpleEngine.popen_uci([BAT], timeout=180)
eng.configure({"RustCore": True, "Batch": 128, "Refine": True, "DrawContempt": 10,
               "Harvest": False, "Ledger": False})
b = chess.Board(FEN)
for ply in range(14):
    r = eng.play(b, chess.engine.Limit(time=0.5))
    if r.move is None:
        print("OUTCOME no move"); break
    print(f"ply {ply}: {b.san(r.move)}", flush=True)
    b.push(r.move)
    if b.is_checkmate(): print("OUTCOME CHECKMATE"); break
    if b.is_repetition(3): print("OUTCOME 3-FOLD"); break
eng.quit()
