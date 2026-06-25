"""Decisive test for the UNIFYING lever. On the real-drift positions, SW's value
barely separates Stockfish's move M from the (much worse) move it drifts to.
Hypothesis: BT4's POLICY does separate them, and lc0-on-the-same-BT4 (which breaks
near-value-ties with policy via visit counts) picks M -- so a policy-aware
tie-break in our readout/selection would fix BOTH drift and search_structure.

For each real-drift position:
  * BT4 policy prior of M vs of the move SW drifts to (and M's policy RANK).
  * lc0-on-BT4 @100k nodes: does it pick M?
If policy favors M and lc0 picks M in most -> lever CONFIRMED.

Run with STILLWATER_TRT=1.
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

d = json.load(open(os.path.join(REPO, "games", "gap_depth_eval.json"),
                  encoding="utf-8"))
real = []
for r in d["records"]:
    if r["bucket"] != "depth_unstable" or not r["decisive"]:
        continue
    picks = [x["raw_pick"] for x in r["ladder"]]
    led = [i for i, p in enumerate(picks) if p == r["M"]]
    if led and led != [0]:
        real.append(r)
print(f"real-drift positions: {len(real)}", flush=True)

from stillwater.oracle import LeelaOracle
oracle = LeelaOracle()
print("provider:", oracle._sess.get_providers()[0], flush=True)
lc0 = chess.engine.SimpleEngine.popen_uci([LC0], timeout=120)
lc0.configure({"WeightsFile": BT4})

pol_favors_M = 0
lc0_picks_M = 0
m_ranks = []
rows = []
for r in real:
    board = chess.Board(r["fen"])
    M, drift_to = r["M"], r["S_raw_top"]
    pol = oracle.evaluate_one(board).policy
    pol = {(m.uci() if isinstance(m, chess.Move) else str(m)): p
           for m, p in pol.items()}
    pM = pol.get(M, 0.0)
    pD = pol.get(drift_to, 0.0)
    ranked = sorted(pol, key=pol.get, reverse=True)
    rank_M = ranked.index(M) + 1 if M in ranked else 99
    m_ranks.append(rank_M)
    favors = pM > pD
    pol_favors_M += favors
    lc0_mv = lc0.play(board, chess.engine.Limit(nodes=100000)).move
    lc0_M = (lc0_mv.uci() == M) if lc0_mv else False
    lc0_picks_M += lc0_M
    rows.append((M, rank_M, pM, drift_to, pD, lc0_M))
lc0.quit()

n = len(real)
print(f"\n==== UNIFYING-LEVER TEST (n={n}) ====")
print(f"BT4 policy prior favors M over the drifted-to move: {pol_favors_M}/{n}")
print(f"M's mean BT4-policy RANK: {sum(m_ranks)/n:.1f} "
      f"(median {sorted(m_ranks)[n//2]}); M in policy top-3: "
      f"{sum(1 for x in m_ranks if x<=3)}/{n}")
print(f"lc0-on-BT4 @100k picks M (the move SW drifts off): {lc0_picks_M}/{n}")
print("\nrows: M (polRank, p) -> drift_to (p) | lc0=M?")
for M, rk, pM, dT, pD, lM in rows:
    print(f"  {M} (r{rk}, {pM:.2f}) -> {dT} ({pD:.2f}) | lc0={'M' if lM else 'X'}")
print("\nVERDICT:")
if lc0_picks_M >= 0.6 * n and pol_favors_M >= 0.6 * n:
    print("  CONFIRMED: policy favors M and lc0-on-BT4 extracts M -> a policy-aware")
    print("  tie-break (value-first, policy breaks near-ties) should fix drift AND")
    print("  search_structure. Build it (gated) and test for tactical crater.")
elif lc0_picks_M >= 0.6 * n:
    print("  lc0 extracts M but policy doesn't cleanly favor it -> lc0's gain is from")
    print("  visit-accumulation/search, not raw policy rank -> the readout lever is")
    print("  subtler than a simple policy tie-break.")
else:
    print("  lc0-on-BT4 ALSO misses M on the drift positions -> not a tie-break/")
    print("  extraction issue; M needs depth or a better eval. Reconsider.")
