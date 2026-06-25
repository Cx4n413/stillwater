"""STAGE 1 GATE for the structure lever (readout UNCHANGED; only the clean
per-root-edge visit counter is on, R_VISITREAD via STILLWATER_VISIT_READOUT=1).

The one load-bearing hypothesis: on the positions where value-argmax FAILS
(drift + search_structure buckets, where SF's move M is right and lc0 plays it),
do the CLEAN per-root-edge VISITS point at M better than value-argmax does?
  - If YES -> the visit-readout has signal; build GATE-A/GATE-B and proceed.
  - If NO  -> no readout variant can work; KILL the build, save the spend.

Also sanity: vis[] aligns with root_children() (uci-by-uci) and sum(vis) ~ evals.
Run with STILLWATER_TRT=1 STILLWATER_VISIT_READOUT=1.
"""
import json
import os
import sys
from collections import Counter

import chess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 40000
F_UCI, F_VAL, F_EVALS = 0, 1, 4
GAMMA = 0.997


def main():
    d = json.load(open(os.path.join(REPO, "games", "gap_depth_eval.json"),
                       encoding="utf-8"))
    # the buckets where value-argmax fails: drift (depth_unstable) + structure
    pos = []
    for r in d["records"]:
        if not r["decisive"]:
            continue
        if r["bucket"] in ("depth_unstable", "search_structure"):
            pos.append((r["fen"], r["M"], r["bucket"]))
    print(f"{len(pos)} value-fails positions (drift+structure) | budget {N}",
          flush=True)

    assert os.environ.get("STILLWATER_VISIT_READOUT") not in (None, "", "0"), \
        "set STILLWATER_VISIT_READOUT=1 so the counter runs"
    from stillwater.oracle import LeelaOracle
    from stillwater.engine_rs import RustEngine
    oracle = LeelaOracle()
    print("provider:", oracle._sess.get_providers()[0], flush=True)
    eng = RustEngine(oracle=oracle, batch=128, refine=True,
                     harvest_on=False, ledger_on=False)

    stats = {b: {"n": 0, "vis_hits_M": 0, "val_hits_M": 0, "vis_eq_val": 0}
             for b in ("depth_unstable", "search_structure")}
    align_ok = True
    consv = []
    examples = []
    for fen, M, bucket in pos:
        board = chess.Board(fen)
        eng.new_game()
        best, info = eng.think(board, node_budget=N)
        kids = eng.core.root_children()
        vis = eng.core.root_edge_visits()
        if len(vis) != len(kids):
            align_ok = False
            continue
        ucis = [c[F_UCI] for c in kids]
        # value-argmax (mover view): q = -GAMMA*value, higher=better
        qs = [-GAMMA * c[F_VAL] for c in kids]
        val_arg = ucis[max(range(len(kids)), key=lambda i: qs[i])]
        vis_arg = ucis[max(range(len(kids)), key=lambda i: vis[i])] if sum(vis) else None
        s = stats[bucket]
        s["n"] += 1
        s["vis_hits_M"] += (vis_arg == M)
        s["val_hits_M"] += (val_arg == M)
        s["vis_eq_val"] += (vis_arg == val_arg)
        # conservation: sum(vis) vs realized evals (sum child evals proxy)
        ev = sum(c[F_EVALS] for c in kids)
        consv.append((sum(vis), ev))
        if len(examples) < 8:
            mi = ucis.index(M) if M in ucis else -1
            examples.append((bucket, M, val_arg, vis_arg,
                             vis[mi] if mi >= 0 else None, sum(vis)))

    print("\n==== STAGE-1 VISIT-SIGNAL GATE ====")
    print(f"alignment vis<->children OK: {align_ok}")
    if consv:
        import statistics as st
        ratio = st.mean(v / e for v, e in consv if e > 0)
        print(f"conservation sum(vis)/sum(child_evals): mean {ratio:.2f} "
              f"(visits are root-edge realized leaves; <=1 expected)")
    for b, s in stats.items():
        if s["n"]:
            print(f"\n[{b}] N={s['n']}")
            print(f"  value-argmax == M : {s['val_hits_M']}/{s['n']} "
                  f"({100*s['val_hits_M']/s['n']:.0f}%)  (these are value-FAILS, expect LOW)")
            print(f"  VISITS-argmax == M: {s['vis_hits_M']}/{s['n']} "
                  f"({100*s['vis_hits_M']/s['n']:.0f}%)  <- the signal")
            print(f"  vis-arg == val-arg: {s['vis_eq_val']}/{s['n']}")
    print("\nexamples (bucket | M | val-arg | vis-arg | vis-on-M | sum-vis):")
    for ex in examples:
        print(f"  {ex[0]:16} M={ex[1]:6} val={ex[2]:6} vis={str(ex[3]):6} "
              f"visM={ex[4]} sum={ex[5]}")
    tot_n = sum(s["n"] for s in stats.values())
    tot_vis = sum(s["vis_hits_M"] for s in stats.values())
    tot_val = sum(s["val_hits_M"] for s in stats.values())
    print(f"\nVERDICT (pooled): VISITS hit M {tot_vis}/{tot_n}, value hits M "
          f"{tot_val}/{tot_n}.")
    if tot_n and tot_vis >= tot_val + max(3, 0.15 * tot_n):
        print("  SIGNAL: clean visits point at M materially more than value-argmax")
        print("  -> the visit-readout has a real target -> BUILD the gated readout.")
    else:
        print("  NO SIGNAL: visits do NOT point at M more than value -> NO readout")
        print("  variant can work -> KILL the build (save the tune+gauntlet spend).")


if __name__ == "__main__":
    sys.exit(main())
