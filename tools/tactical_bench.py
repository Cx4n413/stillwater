"""Tactical discriminator: solve-rate on an EPD suite at a fixed budget.

The per-eval efficiency instrument for the Lc0-gap campaign: run STILLWATER
and Lc0 (same BT4 net) on the same positions and compare solve rates at
matched eval budgets (use --nodes for lc0, --movetime tuned to the engine's
measured evals/s for SW).

Usage:
  python tools/tactical_bench.py --engine sw  --movetime 1000 [--limit 100]
  python tools/tactical_bench.py --engine lc0 --nodes 1000   [--limit 100]
  python tools/tactical_bench.py --engine sw --movetime 1000 --opt Lens=false
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import chess
import chess.engine

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LC0 = r"C:\Users\nonna\Downloads\lc0\cuda12\lc0.exe"
BT4 = os.path.join(REPO, "nets",
                   "BT4-1024x15x32h-swa-6147500-policytune-332.pb.gz")


def load_epd(path: str, limit: int | None):
    out = []
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line:
            continue
        board = chess.Board()
        try:
            ops = board.set_epd(line)
        except Exception:
            continue
        bms = ops.get("bm")
        if not bms:
            continue
        if not isinstance(bms, list):
            bms = [bms]
        out.append((str(ops.get("id", f"pos{len(out)}")), board,
                    {m.uci() for m in bms}))
        if limit and len(out) >= limit:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["sw", "lc0"], required=True)
    ap.add_argument("--movetime", type=int, default=0, help="ms per position")
    ap.add_argument("--nodes", type=int, default=0, help="node cap per position")
    ap.add_argument("--limit", type=int, default=0, help="first N positions")
    ap.add_argument("--epd", default=os.path.join(REPO, "games", "wac.epd"))
    ap.add_argument("--opt", action="append", default=[],
                    help="extra UCI option Key=Value (repeatable)")
    ap.add_argument("--tag", default="", help="label for the results file")
    args = ap.parse_args()
    if not args.movetime and not args.nodes:
        ap.error("need --movetime or --nodes")

    suite = load_epd(args.epd, args.limit or None)
    print(f"{len(suite)} positions from {os.path.basename(args.epd)}")

    if args.engine == "sw":
        cmd = [sys.executable, "-u", "-m", "stillwater.uci"]
        eng = chess.engine.SimpleEngine.popen_uci(cmd, cwd=REPO, timeout=120)
        opts = {"RustCore": True, "Batch": 128, "Harvest": False,
                "Ledger": False}
    else:
        eng = chess.engine.SimpleEngine.popen_uci([LC0], timeout=120)
        opts = {"WeightsFile": BT4}
    for kv in args.opt:
        k, v = kv.split("=", 1)
        opts[k] = {"true": True, "false": False}.get(v.lower(), v)
    legal = {o.name.lower() for o in eng.options.values()}
    eng.configure({k: v for k, v in opts.items() if k.lower() in legal})

    limit = chess.engine.Limit(
        time=args.movetime / 1000.0 if args.movetime else None,
        nodes=args.nodes or None)

    solved, failed, total_nodes = 0, [], 0
    t0 = time.time()
    for i, (pid, board, bms) in enumerate(suite, 1):
        info = eng.play(board, limit, info=chess.engine.INFO_ALL)
        mv = info.move.uci() if info.move else "(none)"
        n = (info.info or {}).get("nodes", 0)
        total_nodes += n or 0
        if mv in bms:
            solved += 1
        else:
            failed.append(pid)
        if i % 25 == 0:
            print(f"  {i}/{len(suite)}: {solved} solved "
                  f"({100*solved/i:.0f}%), {time.time()-t0:.0f}s")
    eng.quit()

    budget = f"mt{args.movetime}" if args.movetime else f"n{args.nodes}"
    pct = 100 * solved / max(1, len(suite))
    print(f"\n=== {args.engine}{('-' + args.tag) if args.tag else ''} {budget}: "
          f"{solved}/{len(suite)} ({pct:.1f}%), "
          f"avg nodes {total_nodes // max(1, len(suite))}, "
          f"{time.time()-t0:.0f}s total ===")
    print("failed:", " ".join(failed) if failed else "(none)")
    out = os.path.join(REPO, "games",
                       f"tact_{args.engine}{'_' + args.tag if args.tag else ''}"
                       f"_{budget}.txt")
    with open(out, "w") as f:
        f.write(f"{args.engine} {budget} {solved}/{len(suite)} {pct:.1f}%\n")
        f.write("failed: " + " ".join(failed) + "\n")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
