"""Inspect repetition-draw games: who stood better when the draw hit?
Run: python tools/draw_check.py games/sf3000_run4.pgn
"""

import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "games/gauntlet_book.pgn"
txt = open(path, encoding="utf-8", errors="replace").read()

for g in txt.split("[Event ")[1:]:
    if "3-fold" not in g:
        continue
    white = re.search(r'\[White "([^"]+)"\]', g).group(1)
    plies = re.search(r'\[PlyCount "(\d+)"\]', g).group(1)
    # SF's eval comments (from SF's own perspective; negative = SF worse)
    evals = re.findall(r"\{([+-]?\d+\.\d+|[+-]M\d+)/", g)
    print(f"White={white} plies={plies}")
    print(f"  SF eval first 8: {evals[:8]}")
    print(f"  SF eval last 12: {evals[-12:]}")
