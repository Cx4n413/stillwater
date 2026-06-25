"""DIRECT +164 CHARACTERIZATION: where do lc0 and the lattice DISAGREE?

The whole prior decomposition buckets positions by lattice-vs-SF (does the engine
match Stockfish's best). But the +164 Elo is lc0-vs-lattice on the SAME BT4 net.
A position where lc0 AND the lattice play the same move -- even a non-SF one --
contributes NOTHING to the gap; they agree. The gap lives entirely on positions
where lc0 and the lattice DISAGREE. This measures that directly, at matched nodes
and the deployed config:

  - disagreement rate (how often they differ at all)
  - on disagreements: lattice-matches-M%  vs  lc0-matches-M%   (who is right when they differ)
  - the decisive subset (where the gap actually costs Elo)

If on disagreements lc0 matches M far more than the lattice, the gap is real and
SEARCH-shaped. If lc0 ~= lattice on disagreements (both miss M equally), the gap
is not about move-correctness on these positions -> look elsewhere (eval scale,
time, the long tail).
"""
import json
import os
import sys

import chess
import chess.engine

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
LC0 = r"C:\Users\nonna\Downloads\lc0\cuda12\lc0.exe"
BT4 = os.path.join(REPO, "nets",
                   "BT4-1024x15x32h-swa-6147500-policytune-332.pb.gz")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 150
NODES = int(sys.argv[2]) if len(sys.argv) > 2 else 16000
MLH_W, MLH_SCALE = 0.12, 80.0


def effv(v, mlh):
    return v * (1.0 + MLH_W * max(0.0, 1.0 - mlh / MLH_SCALE))


d = json.load(open(os.path.join(REPO, "games", "gap_depth_eval.json"),
                   encoding="utf-8"))
recs = [r for r in d["records"] if r.get("fen") and r.get("M")][:N]
print(f"{len(recs)} positions | matched nodes {NODES} (lattice value-argmax vs lc0)",
      flush=True)

from stillwater.oracle import LeelaOracle
from stillwater.engine_rs import RustEngine
oracle = LeelaOracle()
print("SW provider:", oracle._sess.get_providers()[0], flush=True)
eng = RustEngine(oracle=oracle, batch=128, refine=True, harvest_on=False,
                 ledger_on=False)
core = eng.core
lc0 = chess.engine.SimpleEngine.popen_uci([LC0], timeout=180)
lc0.configure({"WeightsFile": BT4})

agree = 0
sw_M = lc0_M = 0
dis = []          # disagreement rows: (sw_pick, lc0_pick, M, decisive)
for i, r in enumerate(recs):
    board = chess.Board(r["fen"])
    M = r["M"]
    eng.new_game()
    eng.think(board, node_budget=NODES)
    rc = core.root_children()
    if not rc:
        continue
    sw = min(rc, key=lambda c: effv(c[1], c[7]))[0]
    try:
        mv = lc0.play(board, chess.engine.Limit(nodes=NODES)).move
        lp = mv.uci() if mv else None
    except Exception:
        lp = None
    sw_M += (sw == M)
    lc0_M += (lp == M)
    if sw == lp:
        agree += 1
    else:
        dis.append((sw, lp, M, r.get("decisive", False)))
    if (i + 1) % 20 == 0:
        print(f"  {i+1}/{len(recs)} (disagree {len(dis)})", flush=True)

eng.shutdown()
lc0.quit()

n = agree + len(dis)
print(f"\nanalyzed {n} | AGREE {agree} ({100*agree/n:.0f}%) | DISAGREE {len(dis)} "
      f"({100*len(dis)/n:.0f}%)")
print(f"overall recovers SF-best M:  lattice {100*sw_M/n:.0f}%   lc0 {100*lc0_M/n:.0f}%")
if dis:
    dn = len(dis)
    swdm = sum(1 for sw, lp, M, _ in dis if sw == M)
    lcdm = sum(1 for sw, lp, M, _ in dis if lp == M)
    neither = sum(1 for sw, lp, M, _ in dis if sw != M and lp != M)
    print(f"\nON THE {dn} DISAGREEMENTS (where the gap lives):")
    print(f"  lattice plays M: {swdm}/{dn} = {100*swdm/dn:.0f}%")
    print(f"  lc0 plays M:     {lcdm}/{dn} = {100*lcdm/dn:.0f}%   <- if >> lattice, gap is real+search-shaped")
    print(f"  neither plays M: {neither}/{dn} = {100*neither/dn:.0f}%   <- if high, disagreements are net-limited noise")
    dec = [x for x in dis if x[3]]
    if dec:
        print(f"  decisive disagreements: {len(dec)}; lc0-M {sum(1 for x in dec if x[1]==x[2])}, "
              f"lattice-M {sum(1 for x in dec if x[0]==x[2])}")
