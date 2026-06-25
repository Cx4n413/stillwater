"""Build + cache the TRT engines for the deployment batch buckets (<=128) via a
direct oracle.warmup() (no UCI protocol timeout), then read batch-128 eval/s.
Run with STILLWATER_TRT=1. The trt_cache persists so later engine launches load
fast. nets/trt_cache/*.timing already exists, which speeds the build.
"""
import time, os, sys, numpy as np, chess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stillwater.oracle import LeelaOracle

print("TRT warmup build start (batch_max=128)", flush=True)
t0 = time.time()
o = LeelaOracle(batch_max=128)
print("PROVIDER", o._sess.get_providers()[0], flush=True)
o.warmup()
print(f"WARMUP_DONE {time.time()-t0:.0f}s", flush=True)

b = chess.Board("r2q1rk1/pp1bbppp/2n1pn2/2pp4/3P1B2/2NBPN2/PPP2PPP/R2Q1RK1 w - - 6 9")
one = np.asarray(o._encode_batch([b])).reshape(1, -1)
batch = np.repeat(one, 128, axis=0).ravel()
o.infer_planes(batch, 128)  # warm
t = time.time(); N = 80
for _ in range(N):
    o.infer_planes(batch, 128)
print(f"TRT_BATCH128_EVALS_PER_S {128*N/(time.time()-t):.0f}  "
      f"(DirectML batch128 oracle was ~1500-1900 evals/s)", flush=True)
