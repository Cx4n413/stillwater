"""Reproduce the cross-game decline directly: spawn ONE engine (as cutechess
reuses it across a match), hammer it with successive searches with ucinewgame
between 'games', and log nps + GPU temp/clock/memory over time. A declining nps
or rising temp/memory across the run = the mechanism behind the per-game
accuracy decay. GPU must be otherwise free."""
import subprocess, sys, time, re, os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def gpu():
    try:
        o = subprocess.run(["nvidia-smi",
            "--query-gpu=temperature.gpu,clocks.sm,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.strip()
        return o.replace("\n", " | ")
    except Exception:
        return "?"


def main():
    p = subprocess.Popen([sys.executable, "-u", "-m", "stillwater.uci"], cwd=REPO,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, bufsize=1)
    for c in ["uci", "setoption name RustCore value true",
              "setoption name Batch value 128", "setoption name Refine value true",
              "setoption name StrictDraws value true", "isready"]:
        p.stdin.write(c + "\n")
    p.stdin.flush()
    for line in p.stdout:
        if line.startswith("readyok"):
            break
    # a midgame position with history (replayed via startpos + moves)
    mv = "e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6 b1c3 a7a6 f1e2 e7e5 d4b3 f8e7 e1g1 e8g8"
    print(f"start: {gpu()}", flush=True)
    t0 = time.time()
    npss = []
    for i in range(140):
        if i % 12 == 0:                       # simulate a new game every ~12 'moves'
            p.stdin.write("ucinewgame\n")
        p.stdin.write(f"position startpos moves {mv}\ngo movetime 1500\n")
        p.stdin.flush()
        nps = nodes = None
        for line in p.stdout:
            if line.startswith("info") and "nps" in line:
                m = re.search(r"nodes (\d+).*nps (\d+)", line)
                if m:
                    nodes, nps = int(m.group(1)), int(m.group(2))
            if line.startswith("bestmove"):
                break
        npss.append(nps or 0)
        if i % 10 == 0 or i >= 135:
            print(f"iter {i:3} t={time.time()-t0:5.0f}s nps={nps} nodes={nodes} "
                  f"gpu[temp,clk,mem,util]={gpu()}", flush=True)
    p.stdin.write("quit\n"); p.stdin.flush()
    first = sum(npss[:10]) / 10
    last = sum(npss[-10:]) / 10
    print(f"\nFIRST-10 avg nps={first:.0f}  LAST-10 avg nps={last:.0f}  "
          f"change={100*(last-first)/max(1,first):+.1f}%")
    print("VERDICT:", "nps DECLINED across run (throttle/leak)" if last < first*0.9
          else "nps STABLE (decline is not throughput)")


if __name__ == "__main__":
    main()
