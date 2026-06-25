"""Quick forensics over match PGNs: STILLWATER's clock usage per game.
Run: python tools/autopsy.py games/sf3000_run1.pgn
"""

import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "games/gauntlet_book.pgn"
txt = open(path, encoding="utf-8", errors="replace").read()

for g in txt.split("[Event ")[1:]:
    white = re.search(r'\[White "([^"]+)"\]', g)
    result = re.search(r'\[Result "([^"]+)"\]', g)
    rnd = re.search(r'\[Round "([^"]+)"\]', g)
    plies = re.search(r'\[PlyCount "(\d+)"\]', g)
    term = re.search(r'\[Termination "([^"]+)"\]', g)
    if not (white and result):
        continue
    sw_white = white.group(1) == "STILLWATER"
    # comments: SF's have eval/depth ("-0.33/24 7.0s"), ours have bare "3.7s"
    times = re.findall(r"\{([^}]*)\}", g)
    ours = []
    for i, t in enumerate(times):
        is_white_move = i % 2 == 0
        if is_white_move == sw_white:
            m = re.search(r"(\d+\.?\d*)s", t)
            if m:
                ours.append(float(m.group(1)))
    if not ours:
        continue
    n_starved = sum(1 for t in ours if t < 0.15)
    print(f"R{rnd.group(1):>4} {'W' if sw_white else 'B'} {result.group(1):>7} "
          f"plies={plies.group(1) if plies else '?':>4} "
          f"term={term.group(1) if term else 'mate/normal':<14} "
          f"our moves={len(ours):>3} min={min(ours):.3f}s "
          f"starved(<0.15s)={n_starved} "
          f"last5={['%.2f' % t for t in ours[-5:]]}")
