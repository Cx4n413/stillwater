"""MCTS COMPARISON on the drift positions.

On the SAME depth_unstable positions where the lattice's value-argmax drifts off
the SF-best M, does lc0 (MCTS on the SAME BT4 net) recover M -- and does its
recovery RISE with nodes where the lattice's falls? This isolates whether the +164
shows up exactly here: if lc0 >> the lattice on these positions and SCALES up with
compute, the prize is real here and the gap is in the SEARCH (how MCTS allocates/
aggregates compute into a tree that separates M from its rival), not the net and
not any readout of the lattice's current state.

Baseline to beat: lattice value-argmax recovers M ~74% of depth_unstable at 16k
(measured), and FALLS with compute on the decisive subset (38%->0% over 768->40k).
"""
import json
import os
import sys

import chess
import chess.engine

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LC0 = r"C:\Users\nonna\Downloads\lc0\cuda12\lc0.exe"
BT4 = os.path.join(REPO, "nets",
                   "BT4-1024x15x32h-swa-6147500-policytune-332.pb.gz")
RUNGS = [int(x) for x in (sys.argv[1].split(",") if len(sys.argv) > 1
                          else ["4000", "16000", "40000"])]

d = json.load(open(os.path.join(REPO, "games", "gap_depth_eval.json"),
                   encoding="utf-8"))
du = [r for r in d["records"] if r["bucket"] == "depth_unstable"]
print(f"{len(du)} depth_unstable positions | lc0 rungs {RUNGS}", flush=True)

lc0 = chess.engine.SimpleEngine.popen_uci([LC0], timeout=180)
lc0.configure({"WeightsFile": BT4})

hits = {r: 0 for r in RUNGS}
for i, rec in enumerate(du):
    board = chess.Board(rec["fen"])
    M = rec["M"]
    for rung in RUNGS:
        try:
            mv = lc0.play(board, chess.engine.Limit(nodes=rung)).move
        except Exception:
            mv = None
        if mv is not None and mv.uci() == M:
            hits[rung] += 1
    if (i + 1) % 10 == 0:
        print(f"  {i+1}/{len(du)}", flush=True)
lc0.quit()

n = len(du)
print("\nlc0 (MCTS on BT4) -- SF-best recovery on the lattice's drift positions:")
prev = None
for rung in RUNGS:
    pct = 100 * hits[rung] / n
    delta = f"  ({pct-prev:+.0f})" if prev is not None else ""
    print(f"  {rung:6} nodes: {hits[rung]:3}/{n} = {pct:.0f}%{delta}")
    prev = pct
print("\nlattice value-argmax on the same set: ~74% at 16k (FLAT/falling with nodes).")
print("If lc0 recovery is high AND rises with nodes, MCTS extracts M here where the")
print("lattice drifts -> the gap is the SEARCH dynamics, and a tree-like separating")
print("statistic (not any readout of the current DAG state) is the categorical lever.")
