"""LINCHPIN TEST: is STILLWATER 'eval-bound (flat vs TC)' -- the assumption the
whole +164 'search-quality' framing rests on -- or does its move quality RISE
with nodes? If it rises, the +164 (measured with SW throttled to ~1770 nodes on
DirectML vs lc0 at ~3x nps) is largely THROUGHPUT, and a faster backend/net is the
lever. Uses the ladder gap_depth_eval already ran. Metric: how often SW's raw
value-pick == SF's best move M, at each node rung.
"""
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open(os.path.join(REPO, "games", "gap_depth_eval.json"), encoding="utf-8"))
rungs = d["sw_rungs"]
recs = [r for r in d["records"] if len(r.get("ladder", [])) == len(rungs)]

print(f"{len(recs)} positions | SF-best recovery rate vs node budget:\n")
print("  ALL positions:")
prev = None
for i, rung in enumerate(rungs):
    rec = sum(1 for r in recs if r["ladder"][i]["raw_pick"] == r["M"])
    pct = 100 * rec / len(recs)
    delta = f"  ({pct-prev:+.1f})" if prev is not None else ""
    print(f"    {rung:6} nodes: {rec:3}/{len(recs)} = {pct:.1f}%{delta}")
    prev = pct

# the decisive subset -- where Elo is actually won/lost
dec = [r for r in recs if r.get("decisive")]
print(f"\n  DECISIVE-loss positions (n={len(dec)}, the ones that cost Elo):")
prev = None
for i, rung in enumerate(rungs):
    rec = sum(1 for r in dec if r["ladder"][i]["raw_pick"] == r["M"])
    pct = 100 * rec / len(dec)
    delta = f"  ({pct-prev:+.1f})" if prev is not None else ""
    print(f"    {rung:6} nodes: {rec:3}/{len(dec)} = {pct:.1f}%{delta}")
    prev = pct

# also: cp-loss style -- fraction that IMPROVE vs WORSEN from low->high rung
improved = sum(1 for r in recs
               if r["ladder"][0]["raw_pick"] != r["M"] and r["ladder"][-1]["raw_pick"] == r["M"])
worsened = sum(1 for r in recs
               if r["ladder"][0]["raw_pick"] == r["M"] and r["ladder"][-1]["raw_pick"] != r["M"])
print(f"\n  low(768)->top(40k): IMPROVED to M {improved}  |  LOST M {worsened}  "
      f"(net {improved-worsened:+})")
print("\nVERDICT: if recovery RISES with nodes, SW scales -> the +164 is partly")
print("THROUGHPUT (SW was throttled on DirectML) -> faster backend/net is a real")
print("lever the original measurement dismissed. If FLAT, SW is saturated and")
print("throughput won't help.")
