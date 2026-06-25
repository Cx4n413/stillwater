"""Mass Distillery harvest over a fixed diverse FEN set.

Feeds each FEN to STILLWATER at a fixed think budget with Harvest=true, so every
think yields ONE high-evidence (raw vs settled) training record. Far more
sample-efficient than self-play: no wasted replayed positions, maximal
diversity, every record clears build_dataset's evidence>=64 filter.

Design:
  * fresh engine PER SHARD -> new PID -> new harvest/<date>_<pid>.jsonl file, so
    build_dataset.py sees MANY groups (its train/val split needs >1 group; a
    single file would break it).
  * deployed-ish config = the environment the corrector will run under:
    RustCore/Batch128/Refine/DrawContempt10, Harvest ON, Ledger OFF (clean
    independent per-position targets, no cross-position proof seeding).
  * resume via harvest/_progress.txt: a restart picks up where it left off.

Run: python tools/harvest_positions.py <fens.txt> [movetime_ms] [shard]
"""

from __future__ import annotations

import os
import sys
import time

import chess
import chess.engine

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRESS = os.path.join(REPO, "harvest", "_progress.txt")

OPTS = {
    "RustCore": True, "Batch": 128, "Refine": True, "DrawContempt": 10,
    "Harvest": True, "Ledger": False, "StrictDraws": False,
}


def read_progress() -> int:
    try:
        return int(open(PROGRESS).read().strip())
    except Exception:
        return 0


def write_progress(n: int) -> None:
    try:
        with open(PROGRESS, "w") as f:
            f.write(str(n))
    except Exception:
        pass


def new_engine() -> chess.engine.SimpleEngine:
    cmd = [sys.executable, "-u", "-m", "stillwater.uci"]
    eng = chess.engine.SimpleEngine.popen_uci(cmd, cwd=REPO, timeout=180)
    legal = {o.name.lower() for o in eng.options.values()}
    eng.configure({k: v for k, v in OPTS.items() if k.lower() in legal})
    return eng


def main() -> int:
    fen_path = sys.argv[1]
    movetime = (int(sys.argv[2]) if len(sys.argv) > 2 else 1500) / 1000.0
    shard = int(sys.argv[3]) if len(sys.argv) > 3 else 1500

    fens = [ln.strip() for ln in open(fen_path, encoding="utf-8") if ln.strip()]
    start = read_progress()
    total = len(fens)
    print(f"{total} FENs; resuming at {start}; movetime {movetime}s; "
          f"shard {shard}", flush=True)

    done = start
    t0 = time.time()
    while done < total:
        chunk = fens[done:done + shard]
        eng = new_engine()
        for fen in chunk:
            try:
                board = chess.Board(fen)
            except Exception:
                done += 1
                continue
            try:
                eng.play(board, chess.engine.Limit(time=movetime),
                         info=chess.engine.INFO_NONE)
            except Exception as e:
                print(f"  play error at {done}: {e}", flush=True)
            done += 1
            if done % 100 == 0:
                rate = (done - start) / max(1e-9, time.time() - t0)
                eta = (total - done) / max(1e-9, rate) / 3600.0
                print(f"  {done}/{total}  ({rate:.2f} pos/s, ETA {eta:.1f}h)",
                      flush=True)
        try:
            eng.quit()
        except Exception:
            pass
        write_progress(done)
        print(f"  shard done -> {done}/{total} (engine recycled)", flush=True)

    print(f"HARVEST POSITIONS COMPLETE: {done} positions in "
          f"{(time.time()-t0)/3600:.2f}h", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
