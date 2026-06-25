"""Validate the conversion fix on REAL legal positions: the actual lichess
games STILLWATER drew while up material, plus canonical won endgames. Plays
each out as self-play and reports the outcome with the fix OFF vs ON.
The winning side = the side with more material; if it mates -> fixed; if it
3-folds / hits the 50-move rule -> still broken.
"""
import chess, chess.engine, os, sys

REPO = r"C:\Users\nonna\Downloads\ExperimentalChessEngine"
BAT = os.path.join(REPO, "stillwater_uci.bat")
VAL = {chess.PAWN:1, chess.KNIGHT:3, chess.BISHOP:3, chess.ROOK:5, chess.QUEEN:9, chess.KING:0}
MT = float(sys.argv[1]) if len(sys.argv) > 1 else 0.8
MAXPLY = int(sys.argv[2]) if len(sys.argv) > 2 else 120

POSITIONS = [
    ("KQ vs K (legal canonical)", "8/8/8/4k3/8/8/8/3QK3 w - - 0 1"),
    ("real sseh-c (black up Q)",  "3k4/8/5P2/8/8/1P2K3/8/5q2 b - - 4 72"),
    ("real Martuni (white K+R+B)","5K2/8/6B1/2k5/8/2p5/4R3/8 w - - 7 72"),
    ("real CCI-9 (black up Q)",   "4q1k1/6P1/7K/8/5P2/8/8/8 b - - 0 61"),
    ("real Evil2Root (black up Q)","7k/8/8/6PN/7K/8/2q5/8 b - - 0 71"),
    ("real pawny_bot (white +R)", "5N2/4k1r1/p7/P4RPp/4P3/r4P2/3K4/1R6 b - - 6 53"),
]

def matdiff(board):  # white - black material
    s = 0
    for _, pc in board.piece_map().items():
        s += VAL[pc.piece_type] * (1 if pc.color == chess.WHITE else -1)
    return s

def play_out(eng, fen):
    b = chess.Board(fen)
    if not b.is_valid():
        return "ILLEGAL POSITION"
    win_white = matdiff(b) > 0
    for ply in range(MAXPLY):
        r = eng.play(b, chess.engine.Limit(time=MT))
        if r.move is None:
            return "no move"
        b.push(r.move)
        if b.is_checkmate():
            return f"MATE in {ply+1} plies" + (" (winner mated)" if (b.turn != win_white) else " (LOSER mated?!)")
        if b.is_stalemate():
            return f"STALEMATE ply {ply+1} (threw the win)"
        if b.is_repetition(3):
            return f"3-FOLD ply {ply+1} (DREW won game)"
        if b.is_fifty_moves():
            return f"50-MOVE ply {ply+1} (DREW won game)"
        if b.is_insufficient_material():
            return "insufficient material"
    return f"maxply (no result in {MAXPLY})"

def run(convert):
    if convert:
        os.environ["STILLWATER_CONVERT"] = "1"
    else:
        os.environ.pop("STILLWATER_CONVERT", None)
    eng = chess.engine.SimpleEngine.popen_uci([BAT], timeout=180)
    eng.configure({"RustCore": True, "Batch": 128, "Refine": True,
                   "DrawContempt": 10, "Harvest": False, "Ledger": False})
    out = {}
    for name, fen in POSITIONS:
        out[name] = play_out(eng, fen)
        print(f"  [{'ON ' if convert else 'OFF'}] {name:30} -> {out[name]}", flush=True)
    eng.quit()
    return out

print("=== convert OFF (baseline) ===")
off = run(False)
print("=== convert ON (fix) ===")
on = run(True)
print("\n=== SUMMARY ===")
for name, _ in POSITIONS:
    print(f"  {name:30} OFF: {off[name]:32} | ON: {on[name]}")
