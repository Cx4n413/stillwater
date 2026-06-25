"""#90 step 2: build the ranking dataset from the Distillery harvest.

The ranking signal lives BETWEEN SIBLINGS: for each harvested parent position, the
search logged each candidate move's deep settled value (root perspective). We
train the new value head so its ordering of the children matches that settled
ordering -- the ORDERING, not the magnitude (the magnitude distill is the -26 Elo
graveyard). This script emits one GROUP per parent: the parent FEN + each move's
(uci, target=root-perspective settled value, evals, proof). The extraction step
then builds each child board (parent + move), encodes it, and runs the embedding
backbone; training compares net child-values against these targets per group.

Gates (clean ranking signal only): evidence >= MIN_EVID, >= 2 expanded moves,
the parent is not itself a proof/claim floored node (those have degenerate
values), and a spread gate so we keep groups where the search actually expresses
a preference. Dedupe parents by FEN, keeping the highest-evidence instance.

    python tools/build_rank_dataset.py            # active + archive harvest
"""
from __future__ import annotations
import json
import os
import sys

import chess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_EVID = 64          # self-distill evidence gate (matches build_dataset.py)
MIN_MOVES = 2          # need >=2 siblings to have an ordering
MIN_MOVE_EVALS = 2     # ignore singleton 1-eval children (pure noise tails)
OUT = os.path.join(REPO, "games", "rank_dataset.jsonl")


def harvest_files():
    hd = os.path.join(REPO, "harvest")
    files = []
    for f in os.listdir(hd):
        if f.startswith("2026") and f.endswith(".jsonl"):
            files.append(os.path.join(hd, f))
    for sub in ("archive_pre20260614", "archive_sfdistill_0614"):
        d = os.path.join(hd, sub)
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".jsonl"):
                    files.append(os.path.join(d, f))
    return files


def main():
    best = {}          # fen -> (evidence, record)  dedupe keeping highest evidence
    seen = bad = 0
    for path in harvest_files():
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                seen += 1
                try:
                    r = json.loads(line)
                except Exception:
                    bad += 1
                    continue
                fen = r.get("fen")
                ev = r.get("evidence", 0) or 0
                if not fen or ev < MIN_EVID:
                    continue
                if r.get("proof") or r.get("claim"):
                    continue
                moves = r.get("moves") or []
                if len(moves) < MIN_MOVES:
                    continue
                if fen not in best or ev > best[fen][0]:
                    best[fen] = (ev, r)

    groups = 0
    children = 0
    proofs = 0
    spreads = []
    with open(OUT, "w", encoding="utf-8") as out:
        for fen, (ev, r) in best.items():
            try:
                board = chess.Board(fen)
            except Exception:
                continue
            mv_out = []
            vals = []
            for m in r["moves"]:
                uci, target, mevals, mproof = m[0], float(m[1]), int(m[2]), int(m[3])
                if mevals < MIN_MOVE_EVALS and not mproof:
                    continue
                try:
                    mob = chess.Move.from_uci(uci)
                    if mob not in board.legal_moves:
                        continue
                except Exception:
                    continue
                mv_out.append([uci, round(target, 4), mevals, mproof])
                vals.append(target)
                if mproof:
                    proofs += 1
            if len(mv_out) < MIN_MOVES:
                continue
            spread = max(vals) - min(vals)
            spreads.append(spread)
            out.write(json.dumps({"fen": fen, "ev": ev, "moves": mv_out}) + "\n")
            groups += 1
            children += len(mv_out)

    spreads.sort()
    med = spreads[len(spreads) // 2] if spreads else 0.0
    print(f"scanned {seen} records ({bad} unparseable)")
    print(f"WROTE {groups} groups, {children} child positions -> {OUT}")
    print(f"  avg children/group: {children / max(1, groups):.1f}")
    print(f"  proof children: {proofs}")
    print(f"  sibling value-spread: median {med:.3f}, "
          f"p10 {spreads[len(spreads)//10]:.3f}, p90 {spreads[9*len(spreads)//10]:.3f}"
          if spreads else "  (no spreads)")


if __name__ == "__main__":
    main()
