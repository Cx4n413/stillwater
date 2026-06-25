"""Probe the parity-match drift positions under candidate Refine configs.

For each dossier FEN (where SW read ~-0.3 in positions SF scores -1.0..-1.8):
run a 768-eval think under each config and dump the root value, the picked
move, and the top children with their evidence. The config that moves root
values toward SF truth without wrecking the picked moves wins iteration 1.
"""

from __future__ import annotations

import json
import os
import sys

import chess
import chess.engine

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
SF = (r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages"
      r"\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe"
      r"\stockfish\stockfish-windows-x86-64-avx2.exe")

# (name, mask, lcb_k, fpu_red, pick_k, batch)
CONFIGS = [
    ("live-0xAB",       0x0AB, 0.30, 0.33, 0.5, 128),
    ("C1 nf+lcb+pick",  0x3BB, 0.30, 0.33, 0.5, 128),
    ("C2 C1+uflight",   0x3FB, 0.30, 0.33, 0.5, 128),
    ("C3 C2+fpu.2",     0x3FF, 0.30, 0.20, 0.5, 128),
    ("C4 C1 @b32",      0x3BB, 0.30, 0.33, 0.5, 32),
    ("C5 C3 @b32",      0x3FF, 0.30, 0.20, 0.5, 32),
]


def main() -> int:
    dossier = json.load(open(os.path.join(REPO, "games",
                                          "parity_dossier.json")))
    fens = [(e["game"], e["sw_last_ok"]["fen"], e["sw_last_ok"]["eval"])
            for e in dossier]

    sf = chess.engine.SimpleEngine.popen_uci([SF])
    sf.configure({"Threads": 2, "Hash": 512})
    truth = {}
    for g, fen, _ in fens:
        b = chess.Board(fen)
        info = sf.analyse(b, chess.engine.Limit(depth=24))
        truth[g] = info["score"].pov(b.turn).score(mate_score=10000) / 100.0
    sf.quit()

    from stillwater.oracle import LeelaOracle
    orc = LeelaOracle()
    if hasattr(orc, "warmup"):
        orc.warmup()
    from stillwater.engine_rs import RustEngine

    for name, mask, lcb_k, fpu_red, pick_k, batch in CONFIGS:
        eng = RustEngine(oracle=orc, batch=batch, harvest_on=False,
                         ledger_on=False)
        eng.refine_mask = mask
        eng.core.set_refine(mask & 0x1FF)
        eng.core.set_tunables(lcb_k, fpu_red)
        eng.pick_k = pick_k
        print(f"\n== {name} (mask 0x{mask:X} lcb={lcb_k} fpu={fpu_red} "
              f"b={batch}) ==")
        err = 0.0
        for g, fen, sw_said in fens:
            board = chess.Board(fen)
            eng.new_game()
            mv = eng.think(board, node_budget=768)
            move = mv[0] if isinstance(mv, tuple) else mv
            vals, _ = eng.core.root_info()
            kids = eng.core.root_children()
            conc = max((c[4] for c in kids), default=0)
            chosen = next((c[4] for c in kids if c[0] == str(move)), 0)
            # SF cp -> rough value scale for an error metric
            import math
            sf_v = math.tanh(truth[g] / 3.0)
            err += abs(vals[0] - sf_v)
            print(f"  g{g}: SF={truth[g]:+.2f} now={vals[0]:+.2f} "
                  f"plays={move}(n={chosen}) conc={conc}")
        print(f"  -> mean |value err| = {err / len(fens):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
