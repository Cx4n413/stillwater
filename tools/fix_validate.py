"""Validate the court fix (MIN_SPEND widened + FRESH_P) on the actual ceiling-
match collapses, WITH carried lattice state and TIMED think (the real regime --
node_budget replays bypass the court entirely, so this is the only test that
exercises the fix).

Replays each collapse game's moves at ~match budgets to rebuild the carried DAG;
at the labeled collapse FEN runs think(wtime=90,btime=90) and records time spent,
evals, and the pick. Run once per arm (env set by the caller):

  fix OFF:  STILLWATER_MIN_SPEND=0.0  STILLWATER_FRESH_P=0
  fix ON :  STILLWATER_MIN_SPEND=0.35 STILLWATER_FRESH_P=1

PASS: on the collapse positions, fix ON spends materially more time than OFF and
plays the losing match move less often (ideally the SF-verified save).
"""
import json
import os
import re
import sys
import time

import chess
import chess.pgn

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
NPS = 1500.0
ARM = sys.argv[1] if len(sys.argv) > 1 else "arm"

targets = {r["fen"]: r for r in json.load(open("games/collapse_labeled.json"))
           if r["cp_loss"] >= 150}
print(f"[{ARM}] {len(targets)} collapse FENs | MIN_SPEND="
      f"{os.environ.get('STILLWATER_MIN_SPEND')} FRESH_P="
      f"{os.environ.get('STILLWATER_FRESH_P')}", flush=True)

from stillwater.oracle import LeelaOracle
from stillwater.engine_rs import RustEngine
oracle = LeelaOracle()
eng = RustEngine(oracle=oracle, batch=128, refine=True, harvest_on=False,
                 ledger_on=False)

results = []
with open("games/lc0_ceiling.pgn", encoding="utf-8", errors="ignore") as fh:
    while True:
        g = chess.pgn.read_game(fh)
        if g is None:
            break
        h = g.headers
        sw_white = "SW" in h.get("White", "")
        sw_black = "SW" in h.get("Black", "")
        if not (sw_white or sw_black):
            continue
        # does this game reach a target FEN?
        probe, hits = g.board(), []
        for node in g.mainline():
            if probe.fen() in targets:
                hits.append(probe.fen())
            probe.push(node.move)
        if not hits:
            continue
        eng.new_game()
        board = g.board()
        for node in g.mainline():
            mv = node.move
            is_sw = (board.turn == chess.WHITE) == sw_white
            fen = board.fen()
            if fen in targets:
                r = targets[fen]
                t0 = time.perf_counter()
                pick, info = eng.think(board.copy(), wtime=90.0, btime=90.0)
                dt = time.perf_counter() - t0
                pu = pick.uci() if pick else "-"
                tag = ("SAVE" if pu == r["M"] else
                       ("LOSING-MOVE" if pu == r["played"] else "other"))
                results.append((r["round"], dt, info.get("evals", 0), pu, tag))
                print(f"  R{r['round']:>4}: spent {dt:5.2f}s "
                      f"({info.get('evals', 0):6} evals) pick {pu:7} [{tag}] "
                      f"(match blitzed {r['time_spent']:.2f}s -> {r['played']})",
                      flush=True)
            elif is_sw:
                c = node.comment or ""
                m = re.match(r"[^\d]*(?:/\d+)?\s*(?:([\d.]+)s)?", c)
                t = 0.0
                m2 = re.search(r"([\d.]+)s", c)
                if m2:
                    t = float(m2.group(1))
                if "book" not in c:
                    eng.think(board.copy(),
                              node_budget=max(256, int(t * NPS)))
            board.push(mv)

eng.shutdown()
import statistics as st
if results:
    print(f"\n[{ARM}] mean spend {st.mean(r[1] for r in results):.2f}s | "
          f"losing-move picked {sum(1 for r in results if r[4]=='LOSING-MOVE')}"
          f"/{len(results)} | save {sum(1 for r in results if r[4]=='SAVE')}"
          f"/{len(results)}")
json.dump(results, open(f"games/fix_validate_{ARM}.json", "w"))
