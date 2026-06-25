"""Lock the concurrency-2 compensation factor, checking phase-uniformity.

The audit's concern: the synthetic 0.87 (conc_bench.py) was measured on ONE
middlegame position. If SW's per-game nps penalty at concurrency 2 is NOT
uniform across opening/middlegame/endgame, a single clock multiplier leaks
Elo asymmetrically. So measure SW's per-process median nps at concurrency 1 vs
2 for THREE position types; the factor = nps(conc1)/nps(conc2) and the SW clock
multiplier = that factor. If the factor's spread across phases is small (<~0.06)
lock concurrency-2 + the mean multiplier; if it varies a lot, drop concentrate
to concurrency 1 (zero bias, ~1.74x slower).

Positions deliberately avoid TB/forced-mate hits (which return instantly and
would corrupt nps): two middlegames + one 13-man rook endgame.
"""
import subprocess, sys, threading, time, re, os, statistics

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
MOVETIME_MS = 4000
SEARCHES = 6
STARTUP_TIMEOUT = 120

POSITIONS = {
    "middlegame-najdorf": "position startpos moves e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6 b1c3 a7a6 c1g5 e7e6 f2f4 f8e7 d1f3 d8c7",
    "middlegame-closed":  "position fen r1bq1rk1/pp2nppp/2n1p3/2ppP3/3P4/2PB1N2/PP3PPP/R1BQ1RK1 w - - 0 10",
    "endgame-rook-13man": "position fen 6k1/5pp1/4p3/p2pP3/P2P1P2/1r6/5RK1/8 w - - 0 1",
}


def drive(idx, posline, results, errors):
    try:
        p = subprocess.Popen([PY, "-u", "-m", "stillwater.uci"], cwd=REPO,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1)
    except Exception as e:
        errors[idx] = f"spawn {e!r}"; return
    def send(c): p.stdin.write(c + "\n"); p.stdin.flush()
    for c in ("uci", "setoption name RustCore value true",
              "setoption name Batch value 128", "setoption name Refine value true",
              "setoption name DrawContempt value 10", "isready"):
        send(c)
    t0 = time.time(); ready = False
    while time.time() - t0 < STARTUP_TIMEOUT:
        ln = p.stdout.readline()
        if not ln: break
        if ln.startswith("readyok"): ready = True; break
    if not ready:
        errors[idx] = "no readyok"
        try: p.kill()
        except Exception: pass
        return
    npss = []
    for _ in range(SEARCHES):
        send(posline); send(f"go movetime {MOVETIME_MS}")
        last = None
        while True:
            ln = p.stdout.readline()
            if not ln: break
            if ln.startswith("info") and "nps" in ln:
                m = re.search(r"\bnps (\d+)", ln)
                if m: last = int(m.group(1))
            if ln.startswith("bestmove"): break
        if last: npss.append(last)
    send("quit")
    try: p.wait(timeout=10)
    except Exception:
        try: p.kill()
        except Exception: pass
    results[idx] = statistics.median(npss) if npss else 0


def measure(posline, N):
    results, errors = {}, {}
    ts = [threading.Thread(target=drive, args=(i, posline, results, errors)) for i in range(N)]
    for t in ts: t.start()
    for t in ts: t.join()
    per = [results.get(i, 0) for i in range(N)]
    ok = all(per)
    return (statistics.mean(per) if ok else None), per, errors


if __name__ == "__main__":
    print(f"movetime={MOVETIME_MS}ms x {SEARCHES}; SW conc-1 vs conc-2 per-process median nps by phase\n", flush=True)
    factors = []
    for name, pos in POSITIONS.items():
        c1, p1, e1 = measure(pos, 1)
        c2, p2, e2 = measure(pos, 2)
        if c1 and c2:
            f = c1 / c2
            factors.append(f)
            print(f"{name:22s} conc1={int(c1):5d}  conc2/proc={int(c2):5d} {[int(x) for x in p2]}  -> factor={f:.3f} (SW clock x{f:.3f})", flush=True)
        else:
            print(f"{name:22s} FAILED  c1={c1} c2={c2}  e1={e1} e2={e2}", flush=True)
    if factors:
        m = statistics.mean(factors)
        print(f"\nfactors: {[round(x,3) for x in factors]}", flush=True)
        print(f"mean factor = {m:.3f}  -> SW clock multiplier = {m:.3f}  (tc=40/{int(round(900*m))})", flush=True)
        print(f"phase spread = {max(factors)-min(factors):.3f}", flush=True)
        print("UNIFORM -> lock concurrency-2 + this multiplier. spread>~0.06 -> drop concentrate to concurrency-1.", flush=True)
