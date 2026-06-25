"""Characterize the search_structure bucket (lc0-on-BT4 finds SF's move M, the
lattice never does). Decides the imagination-head's flavor:
  - M IN BT4's policy top-k but lattice misses it -> EXPLORATION problem -> a cheap
    policy-boost / candidate-injection can recover it.
  - M OUTSIDE BT4's policy -> BLINDNESS -> need a generator that ADDS candidates.
Also reports the lattice's own value for M (q_M from the ladder): does it UNDERVALUE
M, or just under-visit it?
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import chess

d = json.load(open(os.path.join(REPO, "games", "gap_depth_eval.json"), encoding="utf-8"))
ss = [r for r in d["records"] if r["bucket"] == "search_structure"]
print(f"{len(ss)} search_structure positions", flush=True)

from stillwater.oracle import LeelaOracle
o = LeelaOracle()

import statistics as st
ranks = []
probs = []
qM_top = []
for r in ss:
    b = chess.Board(r["fen"])
    pol = o.evaluate_one(b).policy
    pol = {(m.uci() if isinstance(m, chess.Move) else str(m)): p for m, p in pol.items()}
    ranked = sorted(pol.items(), key=lambda kv: -kv[1])
    Mu = r["M"]
    rank = next((i for i, (m, _) in enumerate(ranked) if m == Mu), 999)
    ranks.append(rank)
    probs.append(pol.get(Mu, 0.0))
    qMs = [x["q_M"] for x in r["ladder"] if x["q_M"] is not None]
    qM_top.append(qMs[-1] if qMs else None)

n = len(ss)
print("\n=== M's rank in BT4 policy (0 = top-1) ===")
for k in (1, 3, 5, 10):
    print(f"  M in top-{k:<2}: {sum(1 for x in ranks if x < k)}/{n}")
print(f"  M blind (>top-20): {sum(1 for x in ranks if x >= 20)}/{n}")
print(f"  median rank {st.median(ranks):.0f} | median policy prob {st.median(probs):.4f}")
qv = [q for q in qM_top if q is not None]
print(f"\n=== lattice's top-rung value for M (q_M, mover POV; >0 good) ===")
if qv:
    print(f"  median q_M {st.median(qv):+.3f} | M valued >0 in {sum(1 for q in qv if q>0)}/{len(qv)}")
print("\nVERDICT:")
in5 = sum(1 for x in ranks if x < 5)
if in5 >= 0.7 * n:
    print("  M is mostly ON BT4's radar (in policy) but the lattice under-explores it")
    print("  -> EXPLORATION problem -> a Python-side candidate-injection/boost is the")
    print("     cheap test, and a learned big generator may be unnecessary.")
else:
    print("  M is often OUTSIDE BT4's top candidates -> BLINDNESS -> the imagination-")
    print("  head must ADD moves BT4 misses (a real generator), not just re-explore.")
