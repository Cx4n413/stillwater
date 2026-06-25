"""Validate the spend-the-bank fix (STILLWATER_MIN_SPEND) on game-6's blunder.

Replays placement game 6 to the position right before SW's losing 35...Ng5
(SF ground truth: dead equal +0.04 before, +2.49 after; only 35...Nxf2 held),
then runs the SW engine on that exact position with full move history under
MIN_SPEND=0.0 (legacy, expect a ~1s snap of Ng5) vs MIN_SPEND=0.4 (fix, expect
it to invest ~0.4*soft and ideally avoid Ng5 / find Nxf2). Confirms the floor
changes time-spending and the engine still runs.
"""
import chess, chess.pgn, chess.engine  # noqa
import subprocess, time, os, sys

REPO = r"C:\Users\nonna\Downloads\ExperimentalChessEngine"
PY = sys.executable
PGN = os.path.join(REPO, "games", "placement_concentrate.pgn")

# --- extract game 6, position before 35...Ng5 (after 35.Kg2 = ply 69) ---
with open(PGN, encoding="utf-8", errors="replace") as f:
    g = None
    for _ in range(6):
        g = chess.pgn.read_game(f)
start = g.board()
startfen = start.fen()
moves = list(g.mainline_moves())
ucis = [m.uci() for m in moves[:69]]
blunder_uci = moves[69].uci()
board = g.board()
for m in moves[:69]:
    board.push(m)
print("Black to move (before SW 35...Ng5). FEN:", board.fen())
print("SW's actual game move (ply 70):", moves[69].uci(), "(=35...Ng5, the blunder)")
print()


def run(min_spend):
    env = dict(os.environ)
    env["STILLWATER_MIN_SPEND"] = str(min_spend)
    p = subprocess.Popen([PY, "-u", "-m", "stillwater.uci"], cwd=REPO, env=env,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, bufsize=1)
    def send(c): p.stdin.write(c + "\n"); p.stdin.flush()
    for c in ("uci", "setoption name RustCore value true",
              "setoption name Batch value 128", "setoption name Refine value true",
              "setoption name DrawContempt value 10",
              "setoption name StrictDraws value true", "isready"):
        send(c)
    t0 = time.time()
    while time.time() - t0 < 120:
        l = p.stdout.readline()
        if not l or l.startswith("readyok"):
            break
    send(f"position fen {startfen} moves {' '.join(ucis)}")
    send("go wtime 700000 btime 700000")
    last = ""
    bm = None
    t0 = time.time()
    while True:
        l = p.stdout.readline()
        if not l:
            break
        if l.startswith("info") and (" pv " in l or l.rstrip().endswith(" pv")):
            last = l.strip()
        if l.startswith("bestmove"):
            bm = l.split()[1] if len(l.split()) > 1 else "?"
            break
    dt = time.time() - t0
    send("quit")
    try:
        p.wait(timeout=5)
    except Exception:
        p.kill()
    return bm, dt, last


for ms in (0.0, 0.4):
    bm, dt, info = run(ms)
    tag = "LEGACY (snap expected)" if ms == 0.0 else "FIX (spend-the-bank)"
    print(f"MIN_SPEND={ms}  [{tag}]")
    print(f"  bestmove = {bm}   wall_time = {dt:.1f}s")
    print(f"  last info: {info[:240]}")
    print(f"  -> {'AVOIDED the blunder' if bm != blunder_uci else 'still played the blunder ' + blunder_uci}\n")
