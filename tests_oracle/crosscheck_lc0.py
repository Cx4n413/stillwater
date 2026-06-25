"""Cross-check stillwater.oracle against lc0's own evaluation.

Drives tools/lc0/lc0.exe (onnx-cpu backend, PolicyTemperature=1.0, contempt
disabled) on a set of positions and compares, for every legal move, the prior
probability and the policy index lc0 reports against what LeelaOracle
computes for the SAME network.  Also compares the root raw value V.

Run from the repo root:  python tests_oracle/crosscheck_lc0.py
"""

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import chess  # noqa: E402

from stillwater.oracle import LeelaOracle  # noqa: E402

LC0 = REPO / "tools" / "lc0" / "lc0.exe"
NET_PB = REPO / "nets" / "t1-256x10-distilled-swa-2432500.pb.gz"
NET_ONNX = REPO / "nets" / "fallback.onnx"  # t1-256x10-distilled, same as NET_PB

# (description, fen or None for startpos, uci move list)
POSITIONS = [
    ("startpos, no history", None, []),
    ("black to move, 1 ply history", None, ["e2e4"]),
    ("open sicilian, 6 plies history", None,
     ["e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4"]),
    ("italian, castling available, bare FEN",
     "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
     []),
    ("black to move, castled white, bare FEN",
     "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQ1RK1 b kq - 0 5",
     []),
    ("en passant from FEN, no history",
     "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3",
     []),
    ("repetition: knights out and back twice", None,
     ["g1f3", "g8f6", "f3g1", "f6g8", "g1f3", "g8f6", "f3g1", "f6g8"]),
    ("promotion race",
     "8/4P1k1/8/8/8/8/K5p1/8 w - - 0 1",
     []),
    ("KQR vs K",
     "4k3/8/8/8/8/8/8/RQ2K3 w - - 0 1",
     []),
]

_STAT = re.compile(
    r"info string (\S+)\s+\(\s*(\d+)\s*\).*\(P:\s*([\d.]+)%\)")
_ROOT_V = re.compile(r"info string node.*\(V:\s*(-?[\d.]+)\)")


def lc0_eval(fen, moves):
    """Returns ({uci: (nn_index, prior)}, root_v) from lc0 (onnx-cpu)."""
    p = subprocess.Popen(
        [str(LC0), f"--weights={NET_PB}", "--backend=onnx-cpu"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, bufsize=1)

    def send(c):
        p.stdin.write(c + "\n")
        p.stdin.flush()

    send("uci")
    while p.stdout.readline().strip() != "uciok":
        pass
    send("setoption name VerboseMoveStats value true")
    send("setoption name PolicyTemperature value 1.0")
    send("setoption name ContemptMode value disable")
    send("isready")
    while p.stdout.readline().strip() != "readyok":
        pass
    pos = "position " + ("startpos" if fen is None else "fen " + fen)
    if moves:
        pos += " moves " + " ".join(moves)
    send(pos)
    send("go nodes 2")
    priors, root_v = {}, None
    while True:
        line = p.stdout.readline()
        if not line:
            break
        m = _STAT.match(line.strip())
        if m and m.group(1) != "node":
            priors[m.group(1)] = (int(m.group(2)), float(m.group(3)) / 100.0)
        m = _ROOT_V.match(line.strip())
        if m:
            root_v = float(m.group(1))
        if line.startswith("bestmove"):
            break
    send("quit")
    p.wait(timeout=30)
    return priors, root_v


def board_for(fen, moves):
    b = chess.Board() if fen is None else chess.Board(fen)
    for u in moves:
        b.push_uci(u)
    return b


_CASTLE_UCI = {"e1h1": "e1g1", "e1a1": "e1c1", "e8h8": "e8g8", "e8a8": "e8c8"}


def normalize_lc0_uci(uci, board):
    """lc0 verbose stats print castling as king-takes-rook (e1h1)."""
    fixed = _CASTLE_UCI.get(uci)
    if fixed and board.piece_at(chess.parse_square(uci[:2])) == chess.Piece(
            chess.KING, board.turn):
        return fixed
    return uci


def main():
    oracle = LeelaOracle(onnx_path=str(NET_ONNX))
    print(f"oracle net: {oracle.onnx_path}")
    print(f"providers : {oracle.providers}")
    worst_p, worst_v = 0.0, 0.0
    ok = True
    for desc, fen, moves in POSITIONS:
        board = board_for(fen, moves)
        ev = oracle.evaluate([board])[0]
        priors, root_v = lc0_eval(fen, moves)
        priors = {normalize_lc0_uci(u, board): v for u, v in priors.items()}
        my = {m.uci(): p for m, p in ev.policy.items()}
        assert set(my) == set(priors), (
            f"[{desc}] legal move set mismatch:\n  only mine: "
            f"{set(my) - set(priors)}\n  only lc0: {set(priors) - set(my)}")
        pdiff = max(abs(my[u] - pr) for u, (_, pr) in priors.items())
        vdiff = abs(ev.value - root_v) if root_v is not None else float("nan")
        worst_p = max(worst_p, pdiff)
        worst_v = max(worst_v, vdiff)
        status = "OK " if pdiff < 0.02 and vdiff < 0.05 else "FAIL"
        if status == "FAIL":
            ok = False
        print(f"[{status}] {desc}: {len(my)} moves, "
              f"max |dP| = {pdiff:.4f}, |dV| = {vdiff:.4f} "
              f"(V lc0 {root_v:+.4f} vs oracle {ev.value:+.4f})")
        if status == "FAIL":
            for u, (_, pr) in sorted(priors.items(),
                                     key=lambda kv: -kv[1][1])[:8]:
                print(f"    {u}: lc0 {pr:.4f} oracle {my[u]:.4f}")
    print(f"\nworst |dP| = {worst_p:.4f}, worst |dV| = {worst_v:.4f}")
    print("CROSSCHECK " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
