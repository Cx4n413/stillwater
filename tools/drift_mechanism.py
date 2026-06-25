"""Pin the drift mechanism: WHY does SW's backed-up value for Stockfish's move M
fall as nodes grow? Two hypotheses:
  (G) per-ply DISCOUNT gamma=0.997 over-discounts deep-payoff moves. If true,
      drift should hit NON-zeroing (quiet) M-moves harder than ZEROING ones
      (captures/pawn pushes are already gamma-exempt under R_GAMMA).
  (N) NOISY-REFUTATION: deeper minimax backs up an over-optimistic-for-opponent
      frontier leaf in M's subtree, devaluing M. If true, drift hits zeroing and
      non-zeroing M alike (the discount is irrelevant to the fall).

Reads games/gap_depth_eval.json; real-drift = decisive depth_unstable where M led
at a rung ABOVE the noisy lowest (768). No engine needed.
"""
import json
import os
import statistics as st

import chess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open(os.path.join(REPO, "games", "gap_depth_eval.json"),
                  encoding="utf-8"))
rungs = d["sw_rungs"]


def is_zeroing(fen, uci):
    b = chess.Board(fen)
    try:
        return b.is_zeroing(chess.Move.from_uci(uci))
    except Exception:
        return None


real = []
for r in d["records"]:
    if r["bucket"] != "depth_unstable" or not r["decisive"]:
        continue
    picks = [x["raw_pick"] for x in r["ladder"]]
    led = [i for i, p in enumerate(picks) if p == r["M"]]
    if led and led != [0]:           # led above the noisy lowest rung = real drift
        real.append(r)
print(f"real-drift positions: {len(real)}\n")

zero, quiet = [], []
for r in real:
    qs = [x["q_M"] for x in r["ladder"] if x["q_M"] is not None]
    fall = (max(qs) - qs[-1]) if len(qs) >= 2 else 0.0     # value drop peak->top
    z = is_zeroing(r["fen"], r["M"])
    drift_to = r["S_raw_top"]
    z_to = is_zeroing(r["fen"], drift_to)
    rec = {"M": r["M"], "zeroing_M": z, "fall": fall, "loss": r["loss"],
           "drift_to": drift_to, "zeroing_drift_to": z_to}
    (zero if z else quiet).append(rec)

print(f"M is ZEROING (capture/pawn push, gamma-EXEMPT): {len(zero)}")
print(f"M is QUIET (non-zeroing, gamma-SUBJECT):        {len(quiet)}")
if zero:
    print(f"  mean value-fall (zeroing M):  {st.mean(x['fall'] for x in zero):.3f}")
if quiet:
    print(f"  mean value-fall (quiet M):    {st.mean(x['fall'] for x in quiet):.3f}")
print("\nINTERPRETATION:")
if zero and quiet:
    fz, fq = st.mean(x['fall'] for x in zero), st.mean(x['fall'] for x in quiet)
    if len(zero) >= 3 and abs(fz - fq) < 0.05:
        print("  zeroing and quiet M drift SIMILARLY -> discount (gamma) is NOT the")
        print("  driver -> NOISY-REFUTATION backup bias is the mechanism.")
    elif fq > fz + 0.05:
        print("  quiet (gamma-subject) M drift MORE -> gamma discount is implicated.")
    else:
        print("  mixed; zeroing-M drift is non-trivial -> refutation bias present.")
elif zero:
    print("  drift occurs on gamma-EXEMPT zeroing moves -> NOT gamma -> refutation bias.")

# where does the search drift TO -- toward captures (tactical) or quiet?
both = zero + quiet
to_zero = sum(1 for x in both if x["zeroing_drift_to"])
print(f"\nSW drifts TO a zeroing/capture move in {to_zero}/{len(both)} cases "
      f"(rest = quiet move).")
print("\nexamples (M [zeroing?] value-fall -> drifted-to [zeroing?]):")
for x in both[:10]:
    print(f"  {x['M']} [{'Z' if x['zeroing_M'] else 'q'}] fall={x['fall']:.2f} "
          f"loss={x['loss']}cp -> {x['drift_to']} [{'Z' if x['zeroing_drift_to'] else 'q'}]")
