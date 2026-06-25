"""CUDA EP VRAM-leak gate: sustained fresh inference, sample GPU memory.

The June-12 CUDA revert was due to ~4GB/3.5min VRAM growth (ORT 1.26 CUDA arena).
The fix (arena_extend_strategy=kSameAsRequested + bounded cudnn workspace) is in
oracle.py _default_providers. This confirms it: analyse a stream of DIFFERENT
positions (fresh lattice each -> sustained NEW inferences) and watch VRAM. Flat
=> fixed (CUDA EP shippable). Linear growth => leak still present.

Run: python tools/leak_test.py [iters] [secs_each]
"""
import chess, chess.engine, subprocess, sys, time, os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def vram():
    r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                        "--format=csv,noheader,nounits"],
                       capture_output=True, text=True)
    return int(r.stdout.strip().split("\n")[0])


def main():
    iters = int(sys.argv[1]) if len(sys.argv) > 1 else 22
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0
    fens = [l.strip() for l in open(os.path.join(REPO, "games",
            "harvest_fens.txt"), encoding="utf-8") if l.strip()][:iters]
    eng = chess.engine.SimpleEngine.popen_uci(
        [sys.executable, "-u", "-m", "stillwater.uci"], cwd=REPO, timeout=240)
    eng.configure({"RustCore": True, "Batch": 128, "Refine": True})
    time.sleep(1)
    v0 = vram()
    print(f"start VRAM {v0} MiB", flush=True)
    t0 = time.time()
    total = 0
    samples = [v0]
    for i, fen in enumerate(fens):
        info = eng.analyse(chess.Board(fen), chess.engine.Limit(time=secs))
        total += info.get("nodes") or 0
        v = vram()
        samples.append(v)
        print(f"  iter {i+1}/{iters}: VRAM {v} MiB (+{v-v0}), "
              f"cum_evals~{total}, {time.time()-t0:.0f}s", flush=True)
    eng.quit()
    growth = samples[-1] - samples[1]
    mins = (time.time() - t0) / 60.0
    print(f"\nVRAM: start {v0} -> end {samples[-1]} MiB | growth after warmup "
          f"{growth} MiB over {mins:.1f} min ({total} evals)")
    print("VERDICT:", "LEAK (still broken)" if growth > 800
          else "FLAT -- leak fixed, CUDA EP shippable")


if __name__ == "__main__":
    sys.exit(main())
