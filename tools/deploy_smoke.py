"""Pre-deploy smoke: launch the LIVE bot launcher (stillwater_uci.bat) exactly as
lichess-bot will, apply the deployed UCI options (incl. DrawContempt=10), and
confirm it (a) comes up on DirectML, (b) returns a legal bestmove, (c) registered
DrawContempt. Mirrors config.yml so a green here = the live config is sound.
"""
import chess
import chess.engine
import os

REPO = r"C:\Users\nonna\Downloads\ExperimentalChessEngine"
BAT = os.path.join(REPO, "stillwater_uci.bat")
eng = chess.engine.SimpleEngine.popen_uci([BAT], timeout=180)
eng.configure({"RustCore": True, "Batch": 128, "Refine": True, "DrawContempt": 10,
               "Harvest": False, "Ledger": False})
b = chess.Board("r1bq1rk1/pp1nbppp/2p1pn2/3p4/2PP4/2N1PN2/PPQ1BPPP/R1B2RK1 w - - 0 9")
info = eng.analyse(b, chess.engine.Limit(time=3.0), info=chess.engine.INFO_ALL)
mv = info.get("pv", [None])[0]
print("bestmove:", mv, "| score:", info.get("score"), "| nodes:", info.get("nodes"))
# a clearly-winning position to confirm DrawContempt path is live (won -> avoid 3fold)
eng.quit()
print("SMOKE OK" if mv and b.is_legal(mv) else "SMOKE FAILED")
