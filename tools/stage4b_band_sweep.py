"""Map visit-readout RECOVERY vs the value-band. Think each value-fail position
ONCE (visit counter on), capture per-move (value, evals, visits, v_them), then
SIMULATE the GATE-A/GATE-B readout at many bands offline -> recovery(band) with
no re-thinking. Finds whether a WIDER band readmits the large-value-fall drifts
(more recovery) before the separate WAC crater-check says it costs tactics.
Run with STILLWATER_TRT=1.
"""
import json
import math
import os
import sys

import chess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 40000
GAMMA = 0.997
PICK_K = 0.5; VIS_FLOOR = 64; VIS_FRAC = 0.10; VIS_K = 1.0
F_UCI, F_VAL, F_VTHEM, F_EVALS = 0, 1, 2, 4
BANDS = [0.04, 0.06, 0.10, 0.15, 0.20, 0.30, 0.50]

d = json.load(open(os.path.join(REPO, "games", "gap_depth_eval.json"), encoding="utf-8"))
pos = [(r["fen"], r["M"]) for r in d["records"]
       if r["decisive"] and r["bucket"] in ("depth_unstable", "search_structure")]
print(f"{len(pos)} value-fail positions | budget {N}", flush=True)

os.environ["STILLWATER_VISIT_READOUT"] = "1"
from stillwater.oracle import LeelaOracle
from stillwater.engine_rs import RustEngine
oracle = LeelaOracle()
print("provider:", oracle._sess.get_providers()[0], flush=True)
eng = RustEngine(oracle=oracle, batch=128, refine=True, harvest_on=False, ledger_on=False)

caps = []
for fen, M in pos:
    b = chess.Board(fen)
    eng.new_game(); eng.think(b, node_budget=N)
    kids = eng.core.root_children(); vis = eng.core.root_edge_visits()
    if len(vis) != len(kids) or not kids:
        continue
    rows = [(c[F_UCI], -GAMMA * c[F_VAL], c[F_EVALS], vis[i], c[F_VTHEM])
            for i, c in enumerate(kids)]
    caps.append((M, rows))
print(f"captured {len(caps)}", flush=True)


def lcb(r): return r[1] - PICK_K / (1.0 + r[2]) ** 0.5


def readout(rows, band):
    """faithful GATE-A/GATE-B sim; returns chosen uci."""
    lcb_max = max(lcb(r) for r in rows)
    lcb_pick = max(rows, key=lambda r: (lcb(r), r[2]))[0]
    N_ = sum(r[3] for r in rows); vmax = max((r[3] for r in rows), default=0)
    uniform = 1.0 / len(rows)
    if N_ > 0 and vmax >= VIS_FLOOR and (vmax / N_) >= (uniform + VIS_FRAC):
        cand = [r for r in rows if lcb(r) >= lcb_max - band]
        if len(cand) >= 2:
            def vlcb(r):
                sh = r[3] / N_
                return sh - VIS_K * (sh * (1.0 - sh) / N_) ** 0.5
            chosen = max(cand, key=lambda r: (vlcb(r), lcb(r), r[2]))
            return chosen[0]
    return lcb_pick


off_M = sum(1 for M, rows in caps if max(rows, key=lambda r: (lcb(r), r[2]))[0] == M)
print(f"\nreadout OFF (value-LCB) -> M: {off_M}/{len(caps)}")
print("band   ON->M   net   (recovery vs the value-LCB baseline)")
for band in BANDS:
    on_M = sum(1 for M, rows in caps if readout(rows, band) == M)
    print(f" {band:.2f}   {on_M:3d}    {on_M-off_M:+d}")
print("\nREADING: pick the band that maximizes net recovery; then WAC-crater-check"
      " THAT band (wider band = more recovery but more tactic risk).")
