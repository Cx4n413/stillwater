"""VISIT PREMISE GATE -- the last unmeasured internal signal (IVR, highest-rerank runner-up).

SMAB killed the value-GEOMETRY signal; confback/anti-drift killed the raw VALUE.
The only internal statistic left is the VISIT distribution. On the depth_unstable
(drift) positions, does the lattice's per-root-edge visit count point at the
SF-best M more often than the value-argmax does? MCTS decides by visits and is
+164 Elo; if the lattice's visits ALSO carry the M signal, a visit readout (IVR)
is alive. If visit-argmax is no better than value-argmax (the synthesis's
prediction, here MEASURED), then NO internal lattice signal separates M from its
drifting rival -> the discriminator is absent at the state level; only the search
DYNAMICS differ from MCTS.

PASS (IVR alive): visit-argmax recovers M on >=15% MORE depth_unstable positions
                  than value-argmax does.
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import chess

NODES = int(sys.argv[1]) if len(sys.argv) > 1 else 16000
MLH_W, MLH_SCALE = 0.12, 80.0


def effv(v, mlh):
    return v * (1.0 + MLH_W * max(0.0, 1.0 - mlh / MLH_SCALE))


d = json.load(open(os.path.join(REPO, "games", "gap_depth_eval.json"),
                   encoding="utf-8"))
du = [r for r in d["records"] if r["bucket"] == "depth_unstable"]
print(f"{len(du)} depth_unstable positions | nodes {NODES}", flush=True)

from stillwater.oracle import LeelaOracle
from stillwater.engine_rs import RustEngine
oracle = LeelaOracle()
print("provider:", oracle._sess.get_providers()[0], flush=True)
eng = RustEngine(oracle=oracle, batch=128, refine=True, harvest_on=False,
                 ledger_on=False)
core = eng.core

val_hits = vis_hits = 0
both = 0
val_lost_vis_saved = 0     # the money case: value drifts off M, visits keep M
n = 0
share_rows = []
for i, r in enumerate(du):
    board = chess.Board(r["fen"])
    eng.new_game()
    eng.think(board, node_budget=NODES)
    rc = core.root_children()
    vis = core.root_edge_visits()
    if not rc or len(vis) != len(rc):
        continue
    M = r["M"]
    if M not in {c[0] for c in rc}:
        continue
    n += 1
    val_pick = min(rc, key=lambda c: effv(c[1], c[7]))[0]
    vis_pick = rc[max(range(len(rc)), key=lambda j: vis[j])][0]
    vh = (val_pick == M)
    sh = (vis_pick == M)
    val_hits += vh
    vis_hits += sh
    both += (vh and sh)
    if (not vh) and sh:
        val_lost_vis_saved += 1
    # visit share of M vs the value-overtaker
    vtot = sum(vis) or 1
    mi = next(j for j, c in enumerate(rc) if c[0] == M)
    oi = next((j for j, c in enumerate(rc) if c[0] == val_pick), mi)
    share_rows.append((vis[mi] / vtot, vis[oi] / vtot, vh))
    if (i + 1) % 10 == 0:
        print(f"  {i+1}/{len(du)}", flush=True)

eng.shutdown()

print(f"\nanalyzable: {n}")
print(f"  value-argmax recovers M:  {val_hits}/{n} = {100*val_hits/n:.0f}%")
print(f"  VISIT-argmax recovers M:  {vis_hits}/{n} = {100*vis_hits/n:.0f}%")
print(f"  delta (visit - value):    {100*(vis_hits-val_hits)/n:+.0f}%   <- IVR alive needs >=+15%")
print(f"  money case (value lost M, visits KEPT M): {val_lost_vis_saved}/{n}")
import statistics as st
print(f"  median visit-share: M={st.median([x[0] for x in share_rows]):.2f}  "
      f"value-overtaker={st.median([x[1] for x in share_rows]):.2f}")
alive = (vis_hits - val_hits) / n >= 0.15
print(f"\nVERDICT: {'IVR ALIVE -> visit readout carries signal, build it' if alive else 'visits WASH too -> NO internal signal separates M from rival (state-level discriminator absent)'}")
