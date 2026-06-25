"""Scope the #1 risk-utility effect SIZE before paying for a strength gauntlet.

For each real position: settle the lattice once (deployed config), then read out
the move TWICE on the identical settled lattice -- baseline (risk=0, robustpick)
vs risk-posture (risk=theta). Because the ONLY thing that differs between the two
readouts is self.risk, (move_base != move_risk) EXACTLY measures how often the
risk branch changes the move. This is a one-directional SCREEN, not an Elo proxy:
a readout that almost never changes the move cannot move Elo, so a low change-rate
rules the gauntlet OUT cheaply; a high change-rate authorizes (but does not prove)
it. Also reports the mean loss-mass reduction on changed moves (the mechanism's
bite): for risk-averse (theta>0) it should be >= 0 (averse picks lower-loss moves).

    python tools/scope_risk.py [theta=0.5] [n=150] [movetime=1.5]
"""

from __future__ import annotations

import os
import sys

# Match the deployed search constants so the settled lattice matches the live bot
# (these drive the SEARCH; the readout is toggled separately below).
for k, v in {
    "STILLWATER_CONVERT": "1", "STILLWATER_LCB_K": "0.0", "STILLWATER_FPU_RED": "0.22",
    "STILLWATER_ML_THRESH": "0.9", "STILLWATER_CPUCT_INIT": "2.045",
    "STILLWATER_CPUCT_FACTOR": "4.894", "STILLWATER_C_VAR": "0.2", "STILLWATER_PICK_K": "1.1",
}.items():
    os.environ.setdefault(k, v)
os.environ.pop("STILLWATER_RISK", None)        # readout toggled by hand below

# tools/ is sys.path[0] when run as a script -> add the repo root so the
# `stillwater` package (and the compiled stillwater_core) resolve from any cwd.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess

from stillwater.engine_rs import RustEngine, F_UCI, F_W


def _our_loss(core, uci):
    for c in core.root_children():
        if c[F_UCI] == uci:
            return c[F_W]          # our loss mass = child's win mass (F_W)
    return None


def main():
    theta = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 150
    mt = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fpath = os.path.join(here, "games", "harvest_fens.txt")
    with open(fpath) as f:
        fens = [ln.strip() for ln in f if ln.strip()]
    fens = fens[:n]

    eng = RustEngine(batch=128, refine=True, draw_contempt=0.10,
                     harvest_on=False, ledger_on=False)
    eng.risk_band = 0.10
    eng.risk_gate = "always"

    total = changed = 0
    lossred = []
    for i, fen in enumerate(fens):
        try:
            board = chess.Board(fen)
        except Exception:
            continue
        if board.is_game_over() or not list(board.legal_moves):
            continue
        try:
            eng.new_game()
            eng.risk = 0.0
            eng.think(board, movetime=mt)           # settle once
            mb = eng._best_move(board, 100)          # baseline readout
            eng.risk = theta
            ma = eng._best_move(board, 100)          # risk readout, same lattice
            eng.risk = 0.0
        except Exception as e:
            print(f"  [skip {i}] {e}")
            continue
        if mb is None or ma is None:
            continue
        total += 1
        if mb.uci() != ma.uci():
            changed += 1
            lb = _our_loss(eng.core, mb.uci())
            la = _our_loss(eng.core, ma.uci())
            if lb is not None and la is not None:
                lossred.append(lb - la)             # averse: expect >= 0
        if (i + 1) % 25 == 0:
            rate = 100.0 * changed / max(1, total)
            print(f"  {i+1}: changed {changed}/{total} ({rate:.1f}%)")

    rate = 100.0 * changed / max(1, total)
    mean_lr = sum(lossred) / len(lossred) if lossred else 0.0
    print("=" * 60)
    print(f"theta={theta}  band={eng.risk_band}  positions={total}")
    print(f"MOVE-CHANGE RATE: {changed}/{total} = {rate:.1f}%")
    print(f"mean loss-mass reduction on changed moves: {mean_lr:+.4f} "
          f"(n={len(lossred)}; >=0 confirms averse picks lower-loss moves)")
    print("SCREEN VERDICT: <2% change -> gauntlet NOT warranted (effect negligible); "
          ">~8% -> a real effect exists, size the gauntlet and RUN it.")


if __name__ == "__main__":
    main()
