"""Concurrency degradation benchmark.

Spawns N independent SW UCI engine processes (exactly as cutechess does at
-concurrency N) and drives each with repeated fixed-time searches, measuring
each process's nps. If per-process nps at N=3 stays within ~10% of the N=1
single-game baseline, concurrent games do NOT weaken SW -> the placement can
run at that concurrency with zero strength bias. If nps drops, we see the
exact penalty and pick the highest safe level.

The metric that matters: at a TIME control, strength is set by evals-per-move.
movetime is fixed here, so per-process nps IS the per-move eval rate. Same nps
under concurrency == same strength == valid measurement.
"""
import subprocess, sys, threading, time, re, os, statistics

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
# A normal middlegame after a Najdorf-ish opening: realistic branching/eval load.
MOVES = "e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6 b1c3 a7a6 c1g5 e7e6 f2f4 f8e7 d1f3 d8c7"
MOVETIME_MS = 4000
SEARCHES_PER_PROC = 8          # ~32s of search per process per level
STARTUP_TIMEOUT = 90           # DirectML session load can be slow under N-way contention


def drive(idx, results, errors):
    try:
        p = subprocess.Popen(
            [PY, "-u", "-m", "stillwater.uci"], cwd=REPO,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
    except Exception as e:
        errors[idx] = f"spawn: {e!r}"; return
    def send(c): p.stdin.write(c + "\n"); p.stdin.flush()
    for c in ("uci", "setoption name RustCore value true",
              "setoption name Batch value 128", "setoption name Refine value true",
              "isready"):
        send(c)
    # wait for readyok (oracle/DirectML load)
    t0 = time.time(); ready = False
    while time.time() - t0 < STARTUP_TIMEOUT:
        line = p.stdout.readline()
        if not line: break
        if line.startswith("readyok"): ready = True; break
    if not ready:
        errors[idx] = "no readyok";
        try: p.kill()
        except Exception: pass
        return
    npss = []
    for _ in range(SEARCHES_PER_PROC):
        send(f"position startpos moves {MOVES}")
        send(f"go movetime {MOVETIME_MS}")
        last_nps = None
        while True:
            line = p.stdout.readline()
            if not line: break
            if line.startswith("info") and "nps" in line:
                m = re.search(r"\bnps (\d+)", line)
                if m: last_nps = int(m.group(1))
            if line.startswith("bestmove"): break
        if last_nps: npss.append(last_nps)
    send("quit")
    try: p.wait(timeout=10)
    except Exception:
        try: p.kill()
        except Exception: pass
    results[idx] = npss


def run_level(N):
    results, errors = {}, {}
    threads = [threading.Thread(target=drive, args=(i, results, errors)) for i in range(N)]
    t0 = time.time()
    for t in threads: t.start()
    for t in threads: t.join()
    wall = time.time() - t0
    per = []
    for i in range(N):
        s = results.get(i, [])
        if s: per.append(statistics.median(s))
        else: per.append(0.0)
    ok = all(per) and not errors
    line = (f"N={N}: per-process median nps = {[int(x) for x in per]}  "
            f"mean/proc={int(statistics.mean(per)) if per else 0}  "
            f"aggregate={int(sum(per))}  wall={wall:.0f}s")
    if errors: line += f"  ERRORS={errors}"
    print(line, flush=True)
    return statistics.mean(per) if ok else None


if __name__ == "__main__":
    print(f"movetime={MOVETIME_MS}ms x {SEARCHES_PER_PROC} searches/proc; median nps per process\n", flush=True)
    base = run_level(1)
    if not base:
        print("baseline failed; aborting"); sys.exit(1)
    for N in (2, 3):
        m = run_level(N)
        if m:
            pct = 100 * m / base
            verdict = "CLEAN (no degradation)" if pct >= 90 else ("MILD" if pct >= 80 else "DEGRADED")
            print(f"   -> N={N} per-process nps = {pct:.0f}% of single-game baseline  [{verdict}]\n", flush=True)
        else:
            print(f"   -> N={N} FAILED to produce nps\n", flush=True)
    print("Decision rule: run the placement at the highest N whose per-process nps >= ~90% of baseline.", flush=True)
