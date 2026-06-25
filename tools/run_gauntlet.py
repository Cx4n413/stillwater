"""Rating-ladder gauntlet driver.

Phase A: STILLWATER vs 10 Stockfish tiers (UCI_Elo 3100/3190; full-strength
SF node-capped 8k..2M; unthrottled), 10 games each, 60+1, concurrency 2.
Phase B: bridge matches between adjacent SF tiers so the strong (uncalibrated)
tiers connect to the UCI_Elo-anchored scale; needed for an identifiable fit.

Run detached:  python tools/run_gauntlet.py
Output: games/gauntlet.pgn, games/bridges.pgn, progress on stdout.
"""

import subprocess
import sys
import time

CUTECHESS = r"C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe"
SF = r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe"
REPO = r"C:\Users\nonna\Downloads\ExperimentalChessEngine"

STILLWATER = ["name=STILLWATER", "cmd=python", "arg=-m", "arg=stillwater.uci",
              f"dir={REPO}", "proto=uci", "restart=off"]


def sf_limited(elo):
    return [f"name=SF-{elo}L", f"cmd={SF}", "proto=uci",
            "option.UCI_LimitStrength=true", f"option.UCI_Elo={elo}",
            "option.Threads=1"]


def sf_nodes(label, nodes):
    return [f"name=SF-{label}", f"cmd={SF}", "proto=uci",
            "option.Threads=1", "option.Hash=128", f"nodes={nodes}"]


def sf_full():
    return ["name=SF-FULL", f"cmd={SF}", "proto=uci",
            "option.Threads=1", "option.Hash=256"]


TIERS = [
    ("SF-3100L", sf_limited(3100)),
    ("SF-3190L", sf_limited(3190)),
    ("SF-N8k",   sf_nodes("N8k", 8000)),
    ("SF-N20k",  sf_nodes("N20k", 20000)),
    ("SF-N50k",  sf_nodes("N50k", 50000)),
    ("SF-N125k", sf_nodes("N125k", 125000)),
    ("SF-N320k", sf_nodes("N320k", 320000)),
    ("SF-N800k", sf_nodes("N800k", 800000)),
    ("SF-N2M",   sf_nodes("N2M", 2000000)),
    ("SF-FULL",  sf_full()),
]

BRIDGES = [
    (sf_limited(3190), sf_nodes("N20k", 20000)),
    (sf_nodes("N20k", 20000), sf_nodes("N125k", 125000)),
    (sf_nodes("N125k", 125000), sf_nodes("N800k", 800000)),
    (sf_nodes("N800k", 800000), sf_full()),
]

COMMON = ["-each", "tc=60+1", "timemargin=2500",
          "-recover", "-ratinginterval", "2",
          "-openings", rf"file={REPO}\games\openings.pgn", "format=pgn",
          "order=random", "plies=12",
          "-draw", "movenumber=80", "movecount=10", "score=10",
          "-resign", "movecount=5", "score=1000"]

# Tiers already completed from the start position with adequate game
# diversity (verified unique by tools/uniq_check.py); skipped on rerun.
SKIP = {"SF-3100L", "SF-3190L"}


def run(args):
    proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            bufsize=1, cwd=REPO)
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    return proc.wait()


def main():
    t0 = time.time()
    for name, spec in TIERS:
        if name in SKIP:
            print(f"=== TIER {name} SKIPPED (already complete) ===", flush=True)
            continue
        print(f"=== TIER {name} START ({time.time()-t0:.0f}s elapsed) ===",
              flush=True)
        run([CUTECHESS, "-engine", *STILLWATER, "-engine", *spec,
             *COMMON, "-concurrency", "3", "-rounds", "5", "-games", "2",
             "-repeat", "-pgnout", rf"{REPO}\games\gauntlet_book.pgn"])
        print(f"=== TIER {name} DONE ===", flush=True)
    print("=== PHASE A COMPLETE — starting bridges ===", flush=True)
    for a, b in BRIDGES:
        an = a[0].split("=")[1]
        bn = b[0].split("=")[1]
        print(f"=== BRIDGE {an} vs {bn} START ===", flush=True)
        run([CUTECHESS, "-engine", *a, "-engine", *b,
             *COMMON, "-concurrency", "4", "-rounds", "6", "-games", "2",
             "-repeat", "-pgnout", rf"{REPO}\games\bridges.pgn"])
        print(f"=== BRIDGE {an} vs {bn} DONE ===", flush=True)
    print(f"=== GAUNTLET COMPLETE in {(time.time()-t0)/60:.0f} min ===",
          flush=True)


if __name__ == "__main__":
    main()
