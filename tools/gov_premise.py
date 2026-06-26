"""Part A (Self-Knowledge Loss-Tail Governor) PREMISE GATE -- direct think API, no gauntlet.

The governor fires ONLY when clearly ahead (root value > GOV_AHEAD) and re-ranks the
value-band-tied moves toward minimum loss-tail. For it to do anything, the lowest-loss
move must DIFFER from the neutral value-argmax pick in those positions. If they almost
always coincide, the won-position band is a singleton and the governor is inert.

PASS: in >= 25% of clearly-ahead multi-candidate positions, the governor's pick differs
      from the neutral value-argmax pick (the lever is actionable).
KILL: differ-rate < 25% -> structurally inert; do not spend a gauntlet.
"""
import json
import os
import sys

import chess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

NODES = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
N = int(sys.argv[2]) if len(sys.argv) > 2 else 250
GAMMA, MLH_W, MLH_SCALE = 0.997, 0.12, 80.0
AHEAD, BAND, K, THETA_MAX = 0.4, 0.10, 2.0, 1.0


def effv(v, mlh):
    return v * (1.0 + MLH_W * max(0.0, 1.0 - mlh / MLH_SCALE))


def gtheta(rv):
    return min(THETA_MAX, K * max(0.0, rv - AHEAD))


d = json.load(open(os.path.join(REPO, "games", "gap_depth_eval.json"),
                   encoding="utf-8"))
fens = [r["fen"] for r in d["records"] if r.get("fen")][:N]
print(f"{len(fens)} positions | nodes {NODES} | ahead>{AHEAD} band {BAND}", flush=True)

from stillwater.oracle import LeelaOracle
from stillwater.engine_rs import RustEngine
oracle = LeelaOracle()
print("provider:", oracle._sess.get_providers()[0], flush=True)
eng = RustEngine(oracle=oracle, batch=128, refine=True, harvest_on=False,
                 ledger_on=False)
core = eng.core

ahead = differ = 0
loss_drop = []  # how much loss-tail mass the governor pick saves vs neutral
for i, fen in enumerate(fens):
    eng.new_game()
    eng.think(chess.Board(fen), node_budget=NODES)
    rv = core.root_info()[0][0]
    if rv <= AHEAD:
        continue
    rc = core.root_children()
    if len(rc) < 2:
        continue
    # q (our perspective) = -GAMMA*eff_value(child.value, child.mlh)
    qs = [(-GAMMA * effv(c[1], c[7]), c) for c in rc]
    qmax = max(q for q, _ in qs)
    band = [(q, c) for q, c in qs if q >= qmax - BAND]
    if len(band) < 2:
        continue
    ahead += 1
    theta = gtheta(rv)
    w_l = 1.0 + theta
    # our_win = child loss = c[10]; our_loss = child win = c[8]
    neutral = max(band, key=lambda x: (x[0], x[1][4]))[1]
    govp = max(band, key=lambda x: (x[1][10] - w_l * x[1][8], x[0], x[1][4]))[1]
    if neutral[0] != govp[0]:
        differ += 1
        loss_drop.append(neutral[8] - govp[8])  # our-loss mass saved
    if (i + 1) % 25 == 0:
        print(f"  {i+1}/{len(fens)} (ahead-multi {ahead}, differ {differ})",
              flush=True)
eng.shutdown()

print(f"\nclearly-ahead multi-candidate positions: {ahead}")
if ahead == 0:
    print("none found -- need a more won-position-rich source.")
    sys.exit()
import statistics as st
print(f"governor differs from neutral: {differ}/{ahead} = {100*differ/ahead:.0f}%"
      f"   (PASS >=25%, KILL <25%)")
if loss_drop:
    print(f"median our-loss mass saved when it differs: {st.median(loss_drop):.3f}")
print(f"\nVERDICT: {'PASS -> governor is actionable, earn a gauntlet' if differ/ahead >= 0.25 else 'KILL -> inert (won-position band is a singleton)'}")
