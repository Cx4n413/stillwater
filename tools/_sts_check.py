import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.tune_constants import load_sts, PARAMS, BASE
full = load_sts(os.path.join(os.path.dirname(__file__), "..", "games", "sts.epd"), 1)
sub = load_sts(os.path.join(os.path.dirname(__file__), "..", "games", "sts.epd"), 7)
print("full:", len(full), "subset:", len(sub))
print("max-points full:", sum(max(p.values()) for _, p in full))
b, pmap = full[0]
print("pos0:", b.fen()[:28], "pmap:", pmap)
print("params:", [p[0] for p in PARAMS])
print("baseline vector:", BASE)
