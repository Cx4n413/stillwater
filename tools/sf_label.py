"""Stockfish teacher labels for the harvest FEN set (knowledge distillation).

For each FEN, record SF's WDL verdict from the side-to-move POV as an
expected-score value in [-1,1] (== same scale as BT4's raw value head). The
corrector then learns to pull BT4's raw eval toward SF's (a genuinely stronger
evaluator), not merely toward our own settled search. CPU-only: runs in parallel
with the GPU harvest.

Output: harvest/sf_labels.jsonl  ->  {"fen": <normalized fen>, "sf_v": float}
Resume via harvest/_sf_progress.txt.

Run: python tools/sf_label.py <fens.txt> [depth] [threads]
"""

from __future__ import annotations

import json
import os
import sys
import time

import chess
import chess.engine

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SF = (r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages"
      r"\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe"
      r"\stockfish\stockfish-windows-x86-64-avx2.exe")
OUT = os.path.join(REPO, "harvest", "sf_labels.jsonl")
PROG = os.path.join(REPO, "harvest", "_sf_progress.txt")


def stm_value(info, board) -> float | None:
    """SF expected score in [-1,1] from side-to-move POV."""
    wdl = info.get("wdl")
    if wdl is not None:
        try:
            w, d, l = wdl.pov(board.turn)
            return (w - l) / 1000.0
        except Exception:
            pass
    sc = info.get("score")
    if sc is not None:
        try:
            w, d, l = sc.pov(board.turn).wdl(model="sf", ply=board.ply())
            return (w - l) / 1000.0
        except Exception:
            pass
    return None


def read_prog() -> int:
    try:
        return int(open(PROG).read().strip())
    except Exception:
        return 0


def main() -> int:
    fen_path = sys.argv[1]
    depth = int(sys.argv[2]) if len(sys.argv) > 2 else 16
    threads = int(sys.argv[3]) if len(sys.argv) > 3 else 4

    fens = [ln.strip() for ln in open(fen_path, encoding="utf-8") if ln.strip()]
    start = read_prog()
    eng = chess.engine.SimpleEngine.popen_uci(SF, timeout=60)
    legal = {o.name.lower() for o in eng.options.values()}
    cfg = {"Threads": threads, "Hash": 256}
    if "uci_showwdl" in legal:
        cfg["UCI_ShowWDL"] = True
    eng.configure(cfg)

    fh = open(OUT, "a", encoding="utf-8")
    t0 = time.time()
    done = start
    buf = []
    for i in range(start, len(fens)):
        try:
            board = chess.Board(fens[i])
            info = eng.analyse(board, chess.engine.Limit(depth=depth))
            v = stm_value(info, board)
            if v is not None:
                buf.append(json.dumps({"fen": board.fen(), "sf_v": round(v, 4)},
                                      separators=(",", ":")) + "\n")
        except Exception as e:
            print(f"  sf error at {i}: {e}", flush=True)
        done = i + 1
        if len(buf) >= 25:
            fh.write("".join(buf)); fh.flush(); buf.clear()
            try:
                open(PROG, "w").write(str(done))
            except Exception:
                pass
        if done % 200 == 0:
            rate = (done - start) / max(1e-9, time.time() - t0)
            eta = (len(fens) - done) / max(1e-9, rate) / 60.0
            print(f"  {done}/{len(fens)} ({rate:.1f}/s, ETA {eta:.0f}m)", flush=True)
    if buf:
        fh.write("".join(buf)); fh.flush()
    open(PROG, "w").write(str(done))
    fh.close()
    eng.quit()
    print(f"SF LABEL COMPLETE: {done} positions in {(time.time()-t0)/60:.1f}m",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
