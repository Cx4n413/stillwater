"""The Distillery: harvest the engine's considered verdicts as training data.

Every think() manufactures something no self-play pipeline gets cheaply: the
same position evaluated twice — once by the neural net's instant first
impression (raw), once by minutes of settled search (the verdict) — plus
settled values for every root move (policy targets) and a calibrated variance.
AlphaZero-style training needs whole games for one noisy label; here every
move of every game yields a clean labelled record as a byproduct.

v1 harvests the root of each think only: it is the deepest-settled, most
evidence-rich position in the lattice, the board is in hand (keys are not
invertible), and one record per move costs nothing on the hot path. The full
per-node harvest arrives with the compiled core.

Records are JSON lines in <repo>/harvest/, one file per process. Nothing in
here influences play — pure write-path.
"""

from __future__ import annotations

import json
import os
import time


class Distillery:
    MIN_EVIDENCE = 32          # don't record roots the search barely touched
    FLUSH_EVERY = 20           # buffer writes: disk latency (AV scans, slow
                               # disks) must never sit between search end and
                               # the bestmove going out; a crash loses at most
                               # a handful of records

    def __init__(self, enabled: bool = True, out_dir: str | None = None):
        self.enabled = enabled
        self.records = 0
        self._buf: list[str] = []
        self._fh = None
        if not enabled:
            return
        if out_dir is None:
            here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            out_dir = os.path.join(here, "harvest")
        try:
            os.makedirs(out_dir, exist_ok=True)
            name = time.strftime("%Y%m%d") + f"_{os.getpid()}.jsonl"
            self._fh = open(os.path.join(out_dir, name), "a", encoding="utf-8")
        except Exception:
            self.enabled = False   # harvesting must never break a game

    def harvest_root(self, board, root, lattice, best_move, info) -> None:
        """One record: the net's first impression vs the settled verdict."""
        if not self.enabled or self._fh is None:
            return
        if root.evals < self.MIN_EVIDENCE and not root.proof:
            return
        try:
            children = []
            for i, ck in enumerate(root.child_keys):
                child = lattice.get(ck)
                if child is None:
                    continue
                children.append([root.moves[i].uci(),
                                 round(-child.value, 4),   # our perspective
                                 child.evals,
                                 1 if child.proof else 0])
            rec = {
                "fen": board.fen(),
                "raw": [round(root.raw_value, 4),
                        [round(x, 4) for x in root.raw_wdl],
                        round(root.raw_mlh, 1)],
                "settled": [round(root.value, 4),
                            [round(x, 4) for x in root.wdl],
                            round(root.variance, 4),
                            round(root.mlh, 1)],
                "evidence": root.evals,
                "proof": 1 if root.proof else 0,
                "claim": 1 if root.claim_floor else 0,
                "best": best_move.uci() if best_move else None,
                "rho": round(info.get("rho", 1.0), 3),
                "moves": children,
            }
            self._buf.append(json.dumps(rec, separators=(",", ":")) + "\n")
            self.records += 1
            if len(self._buf) >= self.FLUSH_EVERY:
                self._flush()
        except Exception:
            pass                  # never let bookkeeping touch the game

    def harvest_raw(self, rec: dict) -> None:
        """Record a pre-built root record (the Rust-core path)."""
        if not self.enabled or self._fh is None:
            return
        try:
            self._buf.append(json.dumps(rec, separators=(",", ":")) + "\n")
            self.records += 1
            if len(self._buf) >= self.FLUSH_EVERY:
                self._flush()
        except Exception:
            pass

    def _flush(self) -> None:
        if self._fh is not None and self._buf:
            self._fh.write("".join(self._buf))
            self._fh.flush()
            self._buf.clear()

    def close(self) -> None:
        try:
            self._flush()
            if self._fh is not None:
                self._fh.close()
        except Exception:
            pass
