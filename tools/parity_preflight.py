"""Pre-flight for the eval-parity match: no margin for error.

1. SW honors `go nodes 800` (reports actual evals spent).
2. lc0 honors `go nodes 800`.
3. NET IDENTITY: lc0's root policy ranking (verbose-move-stats, nodes=1)
   must match our oracle's policy ranking on diverse positions — rank
   order is softmax-temperature-invariant, so identical weights must give
   identical rankings up to fp16 jitter on near-ties.
"""

from __future__ import annotations

import os
import subprocess
import sys

import chess
import chess.engine

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
LC0 = r"C:\Users\nonna\Downloads\lc0\cuda12\lc0.exe"
BT4PB = os.path.join(REPO, "nets",
                     "BT4-1024x15x32h-swa-6147500-policytune-332.pb.gz")

FENS = [
    chess.STARTING_FEN,
    "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
    "8/2k5/3p4/p2P1p2/P2P1P2/8/8/3K4 w - - 0 1",
    "2rr3k/pp3pp1/1nnqbN1p/3pN3/2pP4/2P3Q1/PPB4P/R4RK1 w - - 0 1",
]


def lc0_top(fen: str, k: int = 5) -> list[str]:
    p = subprocess.Popen([LC0], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         text=True, bufsize=1, cwd=os.path.dirname(LC0))
    p.stdin.write(f"setoption name WeightsFile value {BT4PB}\n"
                  "setoption name VerboseMoveStats value true\n"
                  "isready\n")
    p.stdin.flush()
    for line in p.stdout:
        if line.startswith("readyok"):
            break
    p.stdin.write(f"position fen {fen}\ngo nodes 1\n")
    p.stdin.flush()
    stats = []
    for line in p.stdout:
        # info string e2e4  (322 ) N:    0 (+ 0) (P: 24.30%) ...
        if line.startswith("info string") and "(P:" in line:
            mv = line.split()[2]
            pct = float(line.split("(P:")[1].split("%")[0])
            stats.append((pct, mv))
        if line.startswith("bestmove"):
            break
    p.stdin.write("quit\n")
    p.stdin.flush()
    p.wait(timeout=30)
    stats.sort(reverse=True)
    return [m for _, m in stats[:k]]


def main() -> int:
    print("-- 1) SW go nodes 800 --")
    sw = chess.engine.SimpleEngine.popen_uci(
        [sys.executable, "-u", "-m", "stillwater.uci"], cwd=REPO, timeout=120)
    sw.configure({"Refine": True, "StrictDraws": True, "Harvest": False,
                  "Ledger": False})
    for fen in FENS[:2]:
        r = sw.play(chess.Board(fen), chess.engine.Limit(nodes=800),
                    info=chess.engine.INFO_ALL)
        print(f"  sw nodes={r.info.get('nodes')} best={r.move}")
    sw.quit()

    print("-- 2) lc0 go nodes 800 --")
    lc = chess.engine.SimpleEngine.popen_uci([LC0], timeout=180)
    lc.configure({"WeightsFile": BT4PB})
    r = lc.play(chess.Board(), chess.engine.Limit(nodes=800),
                info=chess.engine.INFO_ALL)
    print(f"  lc0 nodes={r.info.get('nodes')} best={r.move}")
    lc.quit()

    print("-- 3) net identity: policy rank agreement --")
    from stillwater.oracle import LeelaOracle
    orc = LeelaOracle()
    if hasattr(orc, "warmup"):
        orc.warmup()
    ok = True
    for fen in FENS:
        board = chess.Board(fen)
        ours = orc.evaluate_one(board)
        our_top = [m.uci() for m, _ in sorted(
            ours.policy.items(), key=lambda kv: -kv[1])[:5]]
        lc_top = lc0_top(fen, 5)
        agree3 = our_top[:3] == lc_top[:3]
        ok = ok and agree3
        print(f"  {'OK ' if agree3 else 'MISMATCH'} ours={our_top[:3]} "
              f"lc0={lc_top[:3]}  (top5 ours={our_top} lc0={lc_top})")
    print("IDENTITY " + ("CONFIRMED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
