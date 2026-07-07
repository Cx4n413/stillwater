"""Forensic on the +164 ceiling match (lc0 vs SW, 40/120) -- CPU-only, from the PGN.

Never done: the per-move comments carry eval/depth/TIME for both engines. Extract:
  1. TIME USE: how each engine actually spent the 40/120 clock (mean/max per move,
     variance = adaptivity). "SW is flat-vs-TC" was an assumption -- was SW even
     USING its time?
  2. LOSS ANATOMY: in each SW loss, the eval trajectory from SW's OWN view --
     one sudden collapse (blunder-shaped, fixable) vs slow grind (outplayed).
  3. DIVERGENCE: SW eval vs lc0 eval per position -- who saw trouble first.
"""
import re
import statistics as st
import sys

PGN = sys.argv[1] if len(sys.argv) > 1 else "games/lc0_ceiling.pgn"
text = open(PGN, encoding="utf-8", errors="ignore").read()
games = re.split(r"(?=\[Event )", text)
games = [g for g in games if g.startswith("[Event")]

MOVE_RE = re.compile(
    r"([a-hRNBQKO][\w=+#-]*|O-O(?:-O)?)\s*\{([+-]?[\d.]+|book|[+-]?M\d+)"
    r"(?:/(\d+))?\s*(?:([\d.]+)s)?")


def side(hdrs, name):
    if name in hdrs.get("White", ""):
        return "w"
    if name in hdrs.get("Black", ""):
        return "b"
    return None


sw_times, lc_times = [], []
sw_depths = []
loss_shapes = []   # per SW-loss: (plies, max_single_drop, drift_plies)
n_sw_losses = 0
for g in games:
    hdrs = dict(re.findall(r'\[(\w+) "([^"]*)"\]', g))
    sw = side(hdrs, "SW")
    if sw is None:
        continue
    res = hdrs.get("Result", "*")
    sw_won = (res == "1-0" and sw == "w") or (res == "0-1" and sw == "b")
    sw_lost = (res == "1-0" and sw == "b") or (res == "0-1" and sw == "w")
    body = g.split("\n\n", 1)[1] if "\n\n" in g else ""
    seq = MOVE_RE.findall(body)
    # comments alternate w,b,w,b... starting with white's move 1
    sw_evals = []
    for i, (mv, ev, dep, tm) in enumerate(seq):
        is_white = (i % 2 == 0)
        is_sw = (is_white and sw == "w") or (not is_white and sw == "b")
        if ev == "book":
            continue
        t = float(tm) if tm else None
        if is_sw:
            if t is not None:
                sw_times.append(t)
            if dep:
                sw_depths.append(int(dep))
            try:
                sw_evals.append(float(ev))
            except ValueError:
                sw_evals.append(10.0 if ev.startswith("+M") else -10.0)
        elif t is not None:
            lc_times.append(t)
    if sw_lost and len(sw_evals) > 5:
        n_sw_losses += 1
        drops = [sw_evals[i] - sw_evals[i + 1] for i in range(len(sw_evals) - 1)]
        maxdrop = max(drops) if drops else 0.0
        # plies spent between eval first crossing -0.7 and the end (death spiral len)
        below = next((i for i, e in enumerate(sw_evals) if e < -0.7),
                     len(sw_evals))
        loss_shapes.append((len(sw_evals), maxdrop, len(sw_evals) - below))

print(f"{len(games)} games | SW losses {n_sw_losses}")
print("\n=== TIME USE per move (40/120 repeating -> ~3s/move sustainable) ===")
for name, ts in (("SW ", sw_times), ("lc0", lc_times)):
    if ts:
        print(f"  {name}: mean {st.mean(ts):5.2f}s  median {st.median(ts):5.2f}s  "
              f"p90 {sorted(ts)[int(0.9 * len(ts))]:5.2f}s  max {max(ts):6.2f}s  "
              f"stdev {st.pstdev(ts):5.2f}  (n={len(ts)})")
print("\n=== SW reported depth (PV len) vs time ===")
if sw_depths:
    print(f"  depth: mean {st.mean(sw_depths):.1f}  median {st.median(sw_depths)}  "
          f"max {max(sw_depths)}")
print("\n=== LOSS ANATOMY (SW's own eval trajectory in its losses) ===")
for i, (plies, maxdrop, spiral) in enumerate(loss_shapes):
    shape = "BLUNDER-shaped" if maxdrop >= 1.0 else "grind"
    print(f"  loss {i+1}: {plies} sw-moves | max single eval drop "
          f"{maxdrop:4.2f} | plies below -0.7 before end {spiral:3d} | {shape}")
if loss_shapes:
    nb = sum(1 for _, d, _ in loss_shapes if d >= 1.0)
    print(f"\n  blunder-shaped {nb}/{len(loss_shapes)} | grind {len(loss_shapes)-nb}/{len(loss_shapes)}")
