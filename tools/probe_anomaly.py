"""Trace the +1.00 child-value anomaly: which children claim forced wins,
are they proofs, and does the anomaly exist under the legacy mask too?"""

from __future__ import annotations

import json
import os
import sys

import chess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

FEN = json.load(open(os.path.join(REPO, "games", "parity_dossier.json")))[2][
    "sw_last_ok"]["fen"]   # g4, SF says -2.10


def dump(eng, board, label):
    vals, flags = eng.core.root_info()
    print(f"  [{label}] root value={vals[0]:+.3f} evals={flags[2]} "
          f"proof={flags[0]}")
    kids = sorted(eng.core.root_children(), key=lambda c: -c[1])
    for c in kids[:6]:
        print(f"    {c[0]:7} v={c[1]:+.3f} vt={c[2]:+.3f} var={c[3]:.3f} "
              f"n={c[4]:4} proof={c[5]} dist={c[6]} mlh={c[7]:.0f} "
              f"wdl=({c[8]:.2f},{c[9]:.2f},{c[10]:.2f}) cf={c[11]}")
    return [c for c in kids if c[1] > 0.99]


def main() -> int:
    from stillwater.oracle import LeelaOracle
    from stillwater.engine_rs import RustEngine
    orc = LeelaOracle()
    if hasattr(orc, "warmup"):
        orc.warmup()
    board = chess.Board(FEN)
    print(f"FEN: {FEN}")

    for label, mask in (("legacy mask 0", 0), ("live 0xAB", 0xAB)):
        eng = RustEngine(oracle=orc, batch=128, harvest_on=False,
                         ledger_on=False)
        eng.refine_mask = mask
        eng.core.set_refine(mask & 0xFF)
        eng.new_game()
        eng.think(board, node_budget=768)
        print(f"== {label} ==")
        weird = dump(eng, board, "root")
        if weird:
            w = weird[0]
            print(f"  descending into {w[0]} (v={w[1]:+.3f}, proof={w[5]}):")
            b2 = board.copy()
            b2.push(chess.Move.from_uci(w[0]))
            eng.core.set_position(b2.fen(), [])
            kids2 = sorted(eng.core.node_children(eng.core.root_key),
                           key=lambda c: -c[1])
            if not kids2:
                print("    (no children in lattice at re-rooted key — "
                      "rep-salted or fresh key mismatch)")
            for c in kids2[:6]:
                print(f"    {c[0]:7} v={c[1]:+.3f} n={c[4]:4} proof={c[5]} "
                      f"dist={c[6]} cf={c[11]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
