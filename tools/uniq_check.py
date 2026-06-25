"""Per-opponent game-uniqueness check (guards the Elo fit against
deterministic tiers replaying the same game N times).
Run: python tools/uniq_check.py [pgn ...]
"""

import hashlib
import re
import sys

paths = sys.argv[1:] or ["games/gauntlet.pgn"]
seqs = {}
for p in paths:
    txt = open(p, encoding="utf-8", errors="replace").read()
    for g in txt.split("[Event ")[1:]:
        names = re.findall(r'\[(?:White|Black) "([^"]+)"\]', g)
        opp = next((n for n in names if n != "STILLWATER"), "?")
        parts = g.split("\n\n", 1)
        body = parts[1] if len(parts) > 1 else ""
        moves = re.sub(r"\{[^}]*\}", "", body)
        h = hashlib.md5(" ".join(moves.split()[:40]).encode()).hexdigest()[:8]
        seqs.setdefault(opp, []).append(h)
for opp, hs in sorted(seqs.items()):
    print(f"{opp:<12} games={len(hs):>3}  unique-first-20-moves={len(set(hs)):>3}")
