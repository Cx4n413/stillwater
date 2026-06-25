"""Train the Tier-2 value-recalibration curve g(raw_v) from SF-distillation data.

The capacity study showed the SF-vs-BT4 residual is a 1-D NONLINEAR function of
the net's raw value (gbm(raw_v) ~= +24% MAE vs +8% for the linear corrector).
This fits that curve and bakes it into a fine lookup table the Python oracle
applies at eval time: corrected_value = raw_v + clip(g(raw_v), +/-CLAMP).

No board features, no Rust change, no plane decoding -> the oracle already has
raw_v. Output: recal_lut.npz {grid, adj}. Runtime applies np.interp(raw_v,...).

Run: python tools/train_recal.py [harvest/sf_labels.jsonl]
"""

from __future__ import annotations

import os
import sys

import numpy as np

CLAMP = 0.15


def main() -> int:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sf_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        here, "harvest", "sf_labels.jsonl")
    sys.path.insert(0, os.path.join(here, "tools"))
    from capacity_study import load
    X8, _, y = load(sf_path)
    rawv = X8[:, 1].astype(np.float64)
    n = len(y)
    print(f"{n} examples")

    rng = np.random.RandomState(0x57111A7E)
    idx = rng.permutation(n)
    cut = int(n * 0.8)
    tr, va = idx[:cut], idx[cut:]

    from sklearn.ensemble import GradientBoostingRegressor
    gbm = GradientBoostingRegressor(n_estimators=300, max_depth=3,
                                    learning_rate=0.05)
    gbm.fit(rawv[tr].reshape(-1, 1), y[tr])

    mae0 = np.mean(np.abs(y[va]))
    pred_va = np.clip(gbm.predict(rawv[va].reshape(-1, 1)), -CLAMP, CLAMP)
    mae = np.mean(np.abs(y[va] - pred_va))
    print(f"held-out MAE: do-nothing {mae0:.4f} -> recal {mae:.4f} "
          f"({100*(1-mae/mae0):+.1f}%)")

    grid = np.linspace(-1.0, 1.0, 1001)
    adj = np.clip(gbm.predict(grid.reshape(-1, 1)), -CLAMP, CLAMP)
    out = os.path.join(here, "recal_lut.npz")
    np.savez(out, grid=grid.astype(np.float32), adj=adj.astype(np.float32),
             clamp=np.array([CLAMP], np.float32))
    print(f"saved -> {out}  (grid 1001 pts, |adj|<= {CLAMP})")
    # show the curve at a few anchor values
    for rv in (-0.9, -0.7, -0.3, 0.0, 0.2, 0.5, 0.7, 0.9):
        a = float(np.interp(rv, grid, adj))
        print(f"  raw_v {rv:+.2f} -> adj {a:+.4f}  (corrected {rv + a:+.3f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
