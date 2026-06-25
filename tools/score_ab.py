"""Summarize the v0.2 feature A/B: arm NEW vs arm BASE, each vs SF-3190L.

Run:  python tools/score_ab.py
"""

from __future__ import annotations

import math
import re
import sys

ARMS = [
    ("BASE (features off, old engine)", "games/feature_ab_base.pgn", "SW-base"),
    ("NEW (ponder+TB+effigy)", "games/feature_ab_new.pgn", "SW-new"),
    ("LENS (NEW + lens + conversion time + 5-man TB)",
     "games/feature_ab_lens.pgn", "SW-lens"),
]


def wilson(p, n, z=1.96):
    if n == 0:
        return 0.0, 1.0
    den = 1 + z * z / n
    c = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - half) / den, (c + half) / den


def analyze(path, us):
    try:
        txt = open(path, encoding="utf-8", errors="replace").read()
    except FileNotFoundError:
        return None
    games = []
    for g in txt.split("[Event ")[1:]:
        w = re.search(r'\[White "([^"]+)"\]', g)
        r = re.search(r'\[Result "([^"]+)"\]', g)
        term = re.search(r'\[Termination "([^"]*)"\]', g)
        plies = re.search(r'\[PlyCount "(\d+)"\]', g)
        if not (w and r) or r.group(1) == "*":
            continue
        we_white = w.group(1) == us
        res = r.group(1)
        score = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}[res]
        if not we_white:
            score = 1.0 - score
        # our per-move clock spend from the comments
        times = [float(t) for t in re.findall(r"\{[^}]*?([0-9]+\.[0-9]+)s\}", g)]
        ours = [t for i, t in enumerate(times) if (i % 2 == 0) == we_white]
        games.append({
            "score": score,
            "term": term.group(1) if term else "normal",
            "plies": int(plies.group(1)) if plies else len(times),
            "our_times": ours,
        })
    return games


def main():
    for label, path, us in ARMS:
        games = analyze(path, us)
        if not games:
            print(f"{label}: no games yet ({path})")
            continue
        n = len(games)
        pts = sum(g["score"] for g in games)
        wins = sum(1 for g in games if g["score"] == 1.0)
        draws = sum(1 for g in games if g["score"] == 0.5)
        losses = n - wins - draws
        forfeits = sum(1 for g in games if "time" in g["term"].lower())
        lo, hi = wilson(pts / n, n)
        all_times = [t for g in games for t in g["our_times"]]
        mean_t = sum(all_times) / max(1, len(all_times))
        mean_plies = sum(g["plies"] for g in games) / n
        print(f"{label}")
        print(f"  {wins}-{losses}-{draws}  = {100*pts/n:.0f}%  "
              f"(95% CI {100*lo:.0f}-{100*hi:.0f}%)  over {n} games")
        print(f"  draw rate {100*draws/n:.0f}%   time forfeits {forfeits}   "
              f"mean game {mean_plies:.0f} plies   "
              f"our mean move time {mean_t:.2f}s")
        terms = {}
        for g in games:
            terms[g["term"]] = terms.get(g["term"], 0) + 1
        print(f"  terminations: {terms}")
    print("\nbaseline memory: old engine scored 50% vs SF-3190L "
          "(rating-gauntlet tier, 60+1, no book-phase draws excluded)")


if __name__ == "__main__":
    sys.exit(main())
