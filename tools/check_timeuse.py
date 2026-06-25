"""Confirm STILLWATER_TIMEUSE fires on CLEARLY-WINNING-BUT-UNPROVEN positions
(where SW is confident -> snaps -> banks, but there's no proof to short-circuit).
Single positions at 10+0 rapid (soft~9.4s, floor~5.6s). Expect ON > OFF where
OFF snaps below the floor."""
import chess, chess.engine, os, time
BAT = r"C:\Users\nonna\Downloads\ExperimentalChessEngine\stillwater_uci.bat"
POS = [
    ("recapture Nxe4",       "rnbqkb1r/pppp1ppp/8/8/3Pn3/2N5/PPP2PPP/R1BQKBNR w KQkq - 0 4"),
    ("recapture Qxd8",       "rnbQkb1r/ppp2ppp/5n2/8/8/8/PPPP1PPP/RNB1KBNR b KQkq - 0 5"),
    ("clear devel (e4 open)","rnbqkbnr/pppp1ppp/8/4p3/8/5N2/PPPPPPPP/RNBQKB1R w KQkq - 0 2"),
]
def run(timeuse, fen):
    if timeuse: os.environ["STILLWATER_TIMEUSE"] = "1"
    else: os.environ.pop("STILLWATER_TIMEUSE", None)
    eng = chess.engine.SimpleEngine.popen_uci([BAT], timeout=180)
    eng.configure({"RustCore": True, "Batch": 128, "Refine": True,
                   "DrawContempt": 10, "Harvest": False, "Ledger": False})
    b = chess.Board(fen)
    t0 = time.time()
    r = eng.play(b, chess.engine.Limit(white_clock=600, black_clock=600,
                                       white_inc=0, black_inc=0))
    dt = time.time() - t0
    eng.quit()
    return dt, r.move

for name, fen in POS:
    do, mo = run(False, fen)
    dn, mn = run(True, fen)
    flag = "  <-- TIMEUSE used the bank" if dn > do + 1.5 else ""
    print(f"{name:26} OFF={do:5.1f}s ({mo})  ON={dn:5.1f}s ({mn}){flag}", flush=True)
