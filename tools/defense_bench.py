"""Defense suite: the first real error from every parity-match loss.

Run the engine at 768 nodes on each position; a config scores a point when
it avoids the move that lost the game (anything else counts — the question
is whether the specific failure mode is gone, SF-best matching is graded
separately for info).

  python tools/defense_bench.py --mask 0xBFF --batch 32 [--lcb 0.3 ...]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import chess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mask", default="0xBFF")
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lcb", type=float, default=0.3)
    ap.add_argument("--fpu", type=float, default=0.2)
    ap.add_argument("--pick", type=float, default=0.5)
    ap.add_argument("--mlt", type=float, default=0.8)
    ap.add_argument("--nodes", type=int, default=768)
    args = ap.parse_args()
    mask = int(args.mask, 0)

    suite = json.load(open(os.path.join(REPO, "games",
                                        "defense_suite.json")))
    from stillwater.oracle import LeelaOracle
    from stillwater.engine_rs import RustEngine
    orc = LeelaOracle()
    if hasattr(orc, "warmup"):
        orc.warmup()
    eng = RustEngine(oracle=orc, batch=args.batch, harvest_on=False,
                     ledger_on=False)
    eng.refine_mask = mask
    eng.core.set_refine(mask & 0xDFF)
    eng.core.set_tunables(args.lcb, args.fpu, args.mlt)
    eng.pick_k = args.pick

    avoided, matched = 0, 0
    for e in suite:
        board = chess.Board(e["fen"])
        eng.new_game()
        mv = eng.think(board, node_budget=args.nodes)
        move = str(mv[0] if isinstance(mv, tuple) else mv)
        a = move != e["played"]
        m = move == e["sf_best"]
        avoided += a
        matched += m
        print(f"  {e['arm']}{e['game']} ply{e['ply']}: played {move} "
              f"(blunder was {e['played']}, sf {e['sf_best']}) "
              f"{'AVOID' if a else 'REPEAT'}{' +SF' if m else ''}")
    print(f"=== mask {args.mask} b{args.batch} lcb{args.lcb} fpu{args.fpu} "
          f"pick{args.pick} mlt{args.mlt}: avoided {avoided}/{len(suite)}, "
          f"sf-matched {matched}/{len(suite)} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
