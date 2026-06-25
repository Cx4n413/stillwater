"""Characterize the depth_unstable bucket: did SW genuinely DRIFT off Stockfish's
move M as nodes grew, or did M only ever lead at the thin lowest rung (artifact)?

For each decisive depth_unstable position, find the highest SW node-rung at which
M was the raw-value argmax, and track M's backed-up value across the ladder.
"""
import json
import os
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open(os.path.join(REPO, "games", "gap_depth_eval.json"),
                  encoding="utf-8"))
rungs = d["sw_rungs"]
recs = [r for r in d["records"]
        if r["bucket"] == "depth_unstable" and r["decisive"]]
print(f"rungs {rungs} | decisive depth_unstable: {len(recs)}\n")

last_led = Counter()       # highest rung index at which M was the pick
val_fell = 0               # M's value lower at top rung than where it peaked
only_lowest = 0            # M led ONLY at the lowest rung (artifact candidate)
for r in recs:
    picks = [x["raw_pick"] for x in r["ladder"]]
    led_idx = [i for i, p in enumerate(picks) if p == r["M"]]
    hi = max(led_idx)
    last_led[rungs[hi]] += 1
    if led_idx == [0]:
        only_lowest += 1
    qs = [x["q_M"] for x in r["ladder"] if x["q_M"] is not None]
    if len(qs) >= 2 and qs[-1] < max(qs) - 0.02:
        val_fell += 1

print("highest rung at which M was SW's pick (then abandoned by 40k):")
for rg in rungs:
    print(f"  led through {rg:6} nodes: {last_led.get(rg,0)}")
print(f"\nM led ONLY at the lowest rung ({rungs[0]}) [thin-rung artifact]: "
      f"{only_lowest}/{len(recs)}")
print(f"M led at a HIGHER rung then was abandoned [real drift]: "
      f"{len(recs)-only_lowest}/{len(recs)}")
print(f"M's backed-up VALUE actively fell from its peak by 40k: "
      f"{val_fell}/{len(recs)} (search devalued the good move)")
# a couple of concrete examples
print("\nexamples (pick per rung -> M):")
for r in recs[:6]:
    pl = " ".join(f"{rg}:{x['raw_pick']}" for rg, x in zip(rungs, r["ladder"]))
    print(f"  M={r['M']} loss={r['loss']}cp | {pl}")
