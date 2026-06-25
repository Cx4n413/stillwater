"""FOUNDATIONAL re-examination: does the belief-lattice's relaxation CONVERGE, or
does it keep wandering with more compute? A fixed-point search only scales if its
operator contracts. Measure, across the node ladder [768,4000,16000,40000] that
gap_depth_eval already ran, how often the raw value-argmax PICK still CHANGES
between consecutive rungs -- especially at the high end (16k->40k), where a
converged search should be stable. High change at the top = non-convergent =
more compute wanders instead of improving (which would explain ~0-Elo-from-search
and the whole lc0 gap at the paradigm level, not the bucket level).
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open(os.path.join(REPO, "games", "gap_depth_eval.json"), encoding="utf-8"))
rungs = d["sw_rungs"]
recs = [r for r in d["records"] if len(r.get("ladder", [])) == len(rungs)]
print(f"rungs {rungs} | {len(recs)} positions with full ladder\n")

# pick-change rate between consecutive rungs (raw value-argmax pick)
print("=== how often the raw value-pick CHANGES between consecutive rungs ===")
for i in range(len(rungs) - 1):
    changed = 0
    for r in recs:
        a = r["ladder"][i]["raw_pick"]
        b = r["ladder"][i + 1]["raw_pick"]
        if a != b:
            changed += 1
    print(f"  {rungs[i]:6} -> {rungs[i+1]:6}:  {changed}/{len(recs)} = {100*changed/len(recs):.0f}% changed")

# still-moving at the TOP transition (a converged search should be ~stable)
top_changed = sum(1 for r in recs
                  if r["ladder"][-1]["raw_pick"] != r["ladder"][-2]["raw_pick"])
print(f"\nSTILL MOVING at the top rung ({rungs[-2]}->{rungs[-1]}): "
      f"{top_changed}/{len(recs)} = {100*top_changed/len(recs):.0f}%")

# how many DISTINCT picks each position cycles through over the whole ladder
import statistics as st
distinct = [len({l["raw_pick"] for l in r["ladder"]}) for r in recs]
print(f"distinct picks across the 4-rung ladder: mean {st.mean(distinct):.2f}, "
      f"median {st.median(distinct):.0f}  (1 = converged, >1 = wandered)")
nonconv = sum(1 for x in distinct if x >= 3)
print(f"positions visiting >=3 DIFFERENT picks (clear oscillation): "
      f"{nonconv}/{len(recs)} = {100*nonconv/len(recs):.0f}%")

# q_M still moving at the top? (value, not just pick)
qmoves = []
for r in recs:
    qs = [l["q_M"] for l in r["ladder"] if l["q_M"] is not None]
    if len(qs) >= 2:
        qmoves.append(abs(qs[-1] - qs[-2]))
if qmoves:
    print(f"\n|q_M change| at top rung: median {st.median(qmoves):.3f}, "
          f"mean {st.mean(qmoves):.3f}  (~0 = value converged)")
    big = sum(1 for x in qmoves if x > 0.05)
    print(f"  |q_M change| > 0.05 at the top (value still swinging): "
          f"{big}/{len(qmoves)} = {100*big/len(qmoves):.0f}%")
