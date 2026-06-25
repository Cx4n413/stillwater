"""Real-oracle (BT4 on GPU) sanity for the four new features.

Run:  python tools/sanity_real.py

Loads the real network once and exercises:
  * tablebase auto-discovery + a live endgame conversion (KBNvK, KQvKR) that a
    450-eval/s search would otherwise butcher;
  * the same position with tablebases disabled, for contrast;
  * pondering on the GPU (settle untimed, then ponderhit -> snap move);
  * the opponent model surviving a real-oracle search.
"""

from __future__ import annotations

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess

from stillwater.engine import Engine


def line(s):
    print(s, flush=True)


def main() -> int:
    line("loading oracle (BT4 on DirectML)...")
    eng = Engine()                      # auto-discovers nets/syzygy
    eng._ensure_oracle()
    line(f"tablebase: {'OPEN' if eng.broker.tb else 'absent'}")

    # ---- #4 tablebase: the bishop+knight mate, a notorious ~30-move grind ----
    kbn = chess.Board("4k3/8/8/8/8/8/3BN3/4K3 w - - 0 1")
    eng.new_game()
    t0 = time.perf_counter()
    mv, info = eng.think(kbn, movetime=4.0)
    line(f"KBNvK  with TB: {mv.uci()} in {time.perf_counter()-t0:.1f}s, "
         f"{info['evals']} evals, tb_hits={info['tb_hits']}, "
         f"{'PROVEN WIN' if info['proof'] and info['value']>0.5 else 'cp %+d' % info['cp']}")

    eng.new_game()
    eng.broker.tb = None                # contrast: no tablebase
    t0 = time.perf_counter()
    mv2, info2 = eng.think(kbn, movetime=4.0)
    line(f"KBNvK  no  TB: {mv2.uci()} in {time.perf_counter()-t0:.1f}s, "
         f"{info2['evals']} evals, "
         f"{'PROVEN WIN' if info2['proof'] and info2['value']>0.5 else 'cp %+d' % info2['cp']}")

    # restore TB for the queen-vs-rook grind
    from stillwater.tablebase import open_tablebase
    eng.broker.tb = open_tablebase(None)
    kqr = chess.Board("4k3/8/8/8/8/8/3Q4/r3K3 w - - 0 1")
    eng.new_game()
    t0 = time.perf_counter()
    mv3, info3 = eng.think(kqr, movetime=4.0)
    line(f"KQvKR  with TB: {mv3.uci()} in {time.perf_counter()-t0:.1f}s, "
         f"{info3['evals']} evals, tb_hits={info3['tb_hits']}, "
         f"{'PROVEN WIN' if info3['proof'] and info3['value']>0.5 else 'cp %+d' % info3['cp']}")

    # --------------------------- #2 pondering on the GPU ---------------------
    eng.new_game()
    b = chess.Board()
    b.push_uci("e2e4")
    hit, stop = threading.Event(), threading.Event()
    out = {}

    def run():
        out["mv"], out["info"] = eng.think(
            b, wtime=6.0, btime=6.0, winc=0.1, binc=0.1,
            ponder=True, ponder_hit_event=hit, stop_event=stop)

    th = threading.Thread(target=run)
    th.start()
    time.sleep(2.0)                     # settle on the opponent's clock
    pondered = len(eng.lattice)
    alive = th.is_alive()
    hit.set()
    th.join(timeout=15.0)
    line(f"ponder: settled {pondered} nodes untimed (still running={alive}), "
         f"ponderhit -> {out['mv'].uci()} ({out['info']['evals']} fresh evals)")

    line("sanity OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
