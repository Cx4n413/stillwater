"""Reproduce the conversion bug: play the LIVE engine config (incl DrawContempt=10)
out from dead-won endgames, self-play, and see if it MATES or 3-folds. Prints the
outcome, whether Syzygy is active, and the eval trajectory (does it stay saturated
/ does it walk into a repetition). KRK = TB-covered (isolates tablebase); the
>5-man ones isolate no-TB conversion.
"""
import chess, chess.engine, os, sys

REPO = r"C:\Users\nonna\Downloads\ExperimentalChessEngine"
BAT = os.path.join(REPO, "stillwater_uci.bat")
TESTS = [
    ("KRK (3-man, TB-covered)",        "8/8/8/4k3/8/8/8/R3K3 w - - 0 1"),
    ("KQ vs 2P (5-man, TB-covered)",   "8/8/8/3k4/8/2P1P3/8/3QK3 w - - 0 1"),
    ("up a ROOK +pawns (7-man, no TB)","8/5pp1/8/4k3/8/8/5PP1/R3K3 w - - 0 1"),
]
MT = float(sys.argv[1]) if len(sys.argv) > 1 else 0.8
MAXPLY = int(sys.argv[2]) if len(sys.argv) > 2 else 120

eng = chess.engine.SimpleEngine.popen_uci([BAT], timeout=180)
eng.configure({"RustCore": True, "Batch": 128, "Refine": True, "DrawContempt": 10,
               "Harvest": False, "Ledger": False})

for name, fen in TESTS:
    b = chess.Board(fen)
    print(f"\n=== {name} ===\n{fen}", flush=True)
    scores = []
    outcome = "maxply"
    for ply in range(MAXPLY):
        r = eng.play(b, chess.engine.Limit(time=MT), info=chess.engine.INFO_SCORE)
        mv = r.move
        if mv is None:
            outcome = "no move"; break
        sc = r.info.get("score")
        if ply < 16 or ply % 8 == 0:
            scores.append((ply, b.san(mv), str(sc.pov(chess.WHITE)) if sc else "?"))
        b.push(mv)
        if b.is_checkmate(): outcome = f"CHECKMATE in {ply+1} plies (converted!)"; break
        if b.is_stalemate(): outcome = "stalemate"; break
        if b.is_repetition(3): outcome = f"3-FOLD REPETITION at ply {ply+1} (DREW a won game)"; break
        if b.is_fifty_moves(): outcome = "50-move draw"; break
        if b.is_insufficient_material(): outcome = "insufficient material"; break
    print("  trajectory (ply, move, eval-from-White):")
    for p, m, s in scores[:14]:
        print(f"    {p:3} {m:6} {s}")
    print(f"  OUTCOME: {outcome}", flush=True)
eng.quit()
