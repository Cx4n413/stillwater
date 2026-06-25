"""Train the oracle corrector: ridge regression on Distillery residuals.

The model is deliberately tiny — a linear map from cheap features to a value
correction, applied at node creation in the Rust core (clamped to ±0.15).
That is the right ambition for the corpus sizes this box generates; when the
corpus reaches millions of records, this script's job is taken over by real
net fine-tuning on cloud GPUs, and the pipeline upstream stays identical.

Run:  python tools/train_corrector.py        (writes corrector.npz at repo root)
Ship only if validation says it beats doing nothing.
"""

from __future__ import annotations

import os
import sys

import numpy as np

RIDGE = 1.0
MIN_EXAMPLES = 5000     # below this, a global corrector is noise — refuse


def main() -> int:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    argv = sys.argv[1:]
    in_name = argv[argv.index("--in") + 1] if "--in" in argv else "dataset.npz"
    out_path = (argv[argv.index("--out") + 1] if "--out" in argv
                else os.path.join(here, "corrector.npz"))
    data = np.load(os.path.join(here, "harvest", in_name))
    X, y, w, gid = data["X"], data["y"], data["w"], data["gid"]
    n = len(y)
    print(f"{n} examples, {X.shape[1]} features")

    # group split: last ~20% of source files become validation
    groups = np.unique(gid)
    val_groups = set(groups[int(len(groups) * 0.8):].tolist())
    va = np.isin(gid, list(val_groups))
    tr = ~va
    if tr.sum() < 100 or va.sum() < 50:
        print("not enough data for a meaningful split")
        return 1

    def fit(Xt, yt, wt):
        Xw = Xt * wt[:, None]
        A = Xt.T @ Xw + RIDGE * np.eye(Xt.shape[1], dtype=np.float64)
        b = Xw.T @ yt
        return np.linalg.solve(A, b)

    beta = fit(X[tr].astype(np.float64), y[tr].astype(np.float64),
               w[tr].astype(np.float64))
    pred = np.clip(X[va] @ beta, -0.15, 0.15)
    mae_zero = np.average(np.abs(y[va]), weights=w[va])
    mae_model = np.average(np.abs(y[va] - pred), weights=w[va])
    improve = 100 * (1 - mae_model / mae_zero)
    print(f"validation MAE: do-nothing {mae_zero:.4f} -> corrector {mae_model:.4f} "
          f"({improve:+.1f}%)")
    print("weights:", np.array2string(beta, precision=4))

    force = "--force" in sys.argv
    ship = (n >= MIN_EXAMPLES) and (improve > 1.0)
    out = out_path
    if ship or force:
        np.savez(out, beta=beta.astype(np.float64), version=data["version"])
        tag = "SHIPPED" if ship else "FORCE-SAVED (for A/B only; gate says NO-SHIP)"
        print(f"{tag} -> {out} (enable with UCI option Corrector=true)")
    reasons = []
    if n < MIN_EXAMPLES:
        reasons.append(f"corpus {n} < {MIN_EXAMPLES}")
    if improve <= 1.0:
        reasons.append(f"val improvement {improve:+.1f}% <= 1.0%")
    verdict = "SHIP" if ship else ("NO-SHIP (" + "; ".join(reasons) + ")")
    print(f"GATE VERDICT: {verdict}  [n={n}, improve={improve:+.1f}%]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
