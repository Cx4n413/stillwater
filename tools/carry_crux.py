"""CRUX: do the ceiling-match blunders come from the CARRIED lattice?

Fresh-lattice replays do NOT reproduce the losing moves (0/7) -- but the real
games played them. Difference: in a real game the lattice PERSISTS across moves.
Here we rebuild that carried state by replaying each game's actual moves,
calling think() at every SW turn with ~the nodes it actually got (pgn time x
1.5Knps), pushing the actual game moves regardless. At the collapse position,
think() with the actual blitz budget:

  reproduces losing move WITH carry (but not fresh) -> PERSISTENCE POISONS +
      court snaps on it (both fixes needed; every prior premise gate was blind
      to this because they all replayed fresh).
  still not reproduced -> match blunders came from DML numerics/timing; the
      court fix stands on the 6/7 correction evidence alone.
"""
import json
import os
import re
import sys

import chess
import chess.pgn

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
NPS = 1500.0
PGN = "games/lc0_ceiling.pgn"

targets = {(r["round"], r["played"]): r
           for r in json.load(open("games/collapse_labeled.json"))
           if r["cp_loss"] >= 150}
print(f"{len(targets)} collapse targets", flush=True)

from stillwater.oracle import LeelaOracle
from stillwater.engine_rs import RustEngine
oracle = LeelaOracle()
print("provider:", oracle._sess.get_providers()[0], flush=True)
eng = RustEngine(oracle=oracle, batch=128, refine=True, harvest_on=False,
                 ledger_on=False)

repro = tested = 0
with open(PGN, encoding="utf-8", errors="ignore") as fh:
    while True:
        g = chess.pgn.read_game(fh)
        if g is None:
            break
        h = g.headers
        rnd = h.get("Round", "?")
        sw_white = "SW" in h.get("White", "")
        sw_black = "SW" in h.get("Black", "")
        if not (sw_white or sw_black):
            continue
        # does this game contain a target?
        my_targets = {(r, p): v for (r, p), v in targets.items() if r == rnd}
        if not my_targets:
            continue
        eng.new_game()
        board = g.board()
        for node in g.mainline():
            mv = node.move
            is_sw = (board.turn == chess.WHITE) == sw_white
            c = node.comment or ""
            m = re.match(r"([+-]?[\d.]+|[+-]?M\d+)(?:/\d+)?\s*(?:([\d.]+)s)?", c)
            t = float(m.group(2)) if (m and m.group(2)) else 0.0
            if is_sw and "book" not in c:
                budget = max(256, int(t * NPS))
                key = (rnd, mv.uci())
                if key in my_targets:
                    tested += 1
                    pick, _ = eng.think(board.copy(), node_budget=budget)
                    pu = pick.uci() if pick else "-"
                    hit = (pu == mv.uci())
                    repro += hit
                    print(f"  R{rnd:>4} carried-lattice @ {budget}: played-in-match "
                          f"{mv.uci():7} replay-pick {pu:7} "
                          f"{'REPRODUCED' if hit else 'different'}", flush=True)
                else:
                    eng.think(board.copy(), node_budget=budget)  # rebuild carry
            board.push(mv)

eng.shutdown()
print(f"\nreproduced WITH carried lattice: {repro}/{tested} (fresh was 0/7)")
if tested:
    if repro >= max(2, tested // 3):
        print("VERDICT: PERSISTENCE POISONS -- carried-DAG state is a real blunder "
              "source, invisible to every fresh-replay premise gate. Court fix + "
              "carry hygiene both in play.")
    else:
        print("VERDICT: carry does not explain the match blunders either -> "
              "DML-numerics/timing; court fix stands on the 6/7 correction alone.")
