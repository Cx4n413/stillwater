"""Build the TRT engines (cached) for the rust engine, then measure throughput.

First run builds a TRT engine per padded batch bucket (1..256); large buckets are
slow (minutes) but cached to nets/trt_cache, so later launches load fast. Then
measures steady nps vs the DirectML (930) / CUDA (1616) baselines.
Run with STILLWATER_TRT=1 in the environment.
"""
import chess, chess.engine, sys, time, os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
eng = chess.engine.SimpleEngine.popen_uci(
    [sys.executable, "-u", "-m", "stillwater.uci"], cwd=REPO,
    stderr=open(os.path.join(REPO, "games", "_trtb_ep.log"), "w"), timeout=240)
eng.configure({"RustCore": True, "Batch": 128, "Refine": True})
b = chess.Board("r2q1rk1/pp1bbppp/2n1pn2/2pp4/3P1B2/2NBPN2/PPP2PPP/R2Q1RK1 w - - 6 9")
print("building TRT engines (cached); first think absorbs the build...", flush=True)
t = time.time()
info = eng.analyse(b, chess.engine.Limit(time=10.0))
print(f"BUILD+THINK {time.time()-t:.0f}s nodes {info.get('nodes')}", flush=True)
best = 0
for i in range(3):
    t = time.time()
    info = eng.analyse(b, chess.engine.Limit(time=10.0))
    el = time.time() - t
    nps = (info.get("nodes") or 0) / el
    best = max(best, nps)
    print(f"M{i} {nps:.0f} nps", flush=True)
print(f"TRT_RUST_NPS {best:.0f}  (DirectML 930, CUDA 1616)", flush=True)
eng.quit()
