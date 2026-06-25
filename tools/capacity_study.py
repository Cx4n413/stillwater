"""Offline capacity study: how well can we predict the SF-distill residual?

Decides (with evidence, no GPU, no engine changes) whether a HIGHER-CAPACITY
corrector is worth integrating into the engine. Target = SF_value - BT4_raw.
Compares, by held-out MAE vs do-nothing:
  * ridge-8      : the current linear corrector (8 features)         [info=low, cap=linear]
  * gbm-8        : gradient boosting on the SAME 8 features          [info=low, cap=nonlinear]
  * ridge-rich   : linear on ~30 cheap board features               [info=high, cap=linear]
  * gbm-rich     : gradient boosting on rich features               [info=high, cap=nonlinear]
  * mlp-rich     : small MLP on rich features                       [info=high, cap=nonlinear]
If rich/nonlinear models beat ridge-8 by a meaningful margin, a board-feature
corrector (applied in the Python oracle layer) is the next lever. If not, the
residual isn't cheaply feature-predictable -> needs a board-seeing net, or it's
search-specific noise and the linear corrector is the ceiling.

Run: python tools/capacity_study.py [harvest/sf_labels.jsonl]
"""

from __future__ import annotations

import glob
import json
import os
import sys

import chess
import numpy as np

PIECE_VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
             chess.ROOK: 5, chess.QUEEN: 9}
CENTER = [chess.D4, chess.E4, chess.D5, chess.E5]


def base8(board, raw_v, raw_mlh):
    us, them = board.turn, not board.turn
    mu = sum(v * len(board.pieces(p, us)) for p, v in PIECE_VAL.items())
    mt = sum(v * len(board.pieces(p, them)) for p, v in PIECE_VAL.items())
    pawns = len(board.pieces(chess.PAWN, us)) + len(board.pieces(chess.PAWN, them))
    pieces = chess.popcount(board.occupied)
    return [1.0, raw_v, raw_v * abs(raw_v), min(raw_mlh, 160.0) / 80.0,
            (mu + mt) / 78.0, (mu - mt) / 9.0, pawns / 16.0, pieces / 32.0]


def rich(board, raw_v, raw_wdl, raw_mlh):
    f = base8(board, raw_v, raw_mlh)
    us, them = board.turn, not board.turn
    # raw WDL components (rust-core harvest stores None -> use neutral)
    if not (isinstance(raw_wdl, (list, tuple)) and len(raw_wdl) == 3):
        raw_wdl = [0.0, 0.0, 0.0]
    f += [float(raw_wdl[0]), float(raw_wdl[1]), float(raw_wdl[2])]
    # per-type material diffs
    for p in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        f.append((len(board.pieces(p, us)) - len(board.pieces(p, them))) / 2.0)
    # bishop pair
    f.append(1.0 if len(board.pieces(chess.BISHOP, us)) >= 2 else 0.0)
    f.append(1.0 if len(board.pieces(chess.BISHOP, them)) >= 2 else 0.0)
    # stm mobility and (null-move) oppo mobility
    stm_mob = board.legal_moves.count()
    f.append(stm_mob / 40.0)
    opp_mob = 0
    if not board.is_check():
        board.push(chess.Move.null())
        opp_mob = board.legal_moves.count()
        board.pop()
    f.append(opp_mob / 40.0)
    f.append((stm_mob - opp_mob) / 40.0)
    # center attack pressure
    f.append(sum(len(board.attackers(us, s)) for s in CENTER) / 8.0)
    f.append(sum(len(board.attackers(them, s)) for s in CENTER) / 8.0)
    # king pawn shield (pawns adjacent to king)
    for color in (us, them):
        k = board.king(color)
        shield = 0
        if k is not None:
            for s in chess.SquareSet(chess.BB_KING_ATTACKS[k]):
                if board.piece_type_at(s) == chess.PAWN and board.color_at(s) == color:
                    shield += 1
        f.append(shield / 3.0)
    # passed pawns (cheap approx: no enemy pawn ahead on file or adjacent files)
    for color in (us, them):
        pp = 0
        for sq in board.pieces(chess.PAWN, color):
            file = chess.square_file(sq)
            rank = chess.square_rank(sq)
            blocked = False
            for df in (-1, 0, 1):
                ff = file + df
                if 0 <= ff <= 7:
                    for esq in board.pieces(chess.PAWN, not color):
                        if chess.square_file(esq) == ff:
                            er = chess.square_rank(esq)
                            if (color == chess.WHITE and er > rank) or \
                               (color == chess.BLACK and er < rank):
                                blocked = True
                                break
                if blocked:
                    break
            if not blocked:
                pp += 1
        f.append(pp / 4.0)
    f.append(1.0 if board.is_check() else 0.0)
    f.append(min(board.fullmove_number, 80) / 80.0)
    return f


def load(sf_path):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sf = {}
    for line in open(sf_path, encoding="utf-8"):
        try:
            r = json.loads(line)
            sf[r["fen"]] = r["sf_v"]
        except Exception:
            pass
    print(f"{len(sf)} SF labels")
    X8, XR, y = [], [], []
    files = [f for f in glob.glob(os.path.join(here, "harvest", "*.jsonl"))
             if "sf_labels" not in f]
    for path in files:
        for line in open(path, encoding="utf-8"):
            try:
                r = json.loads(line)
                if r.get("claim") or r.get("proof"):
                    continue
                fen = r["fen"]
                sv = sf.get(fen)
                if sv is None:
                    continue
                raw_v, raw_wdl, raw_mlh = r["raw"][0], r["raw"][1], r["raw"][2]
                board = chess.Board(fen)
                X8.append(base8(board, raw_v, raw_mlh))
                XR.append(rich(board, raw_v, raw_wdl, raw_mlh))
                y.append(sv - raw_v)
            except Exception:
                pass
    return (np.array(X8, np.float32), np.array(XR, np.float32),
            np.array(y, np.float32))


def main():
    sf_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "harvest", "sf_labels.jsonl")
    X8, XR, y = load(sf_path)
    n = len(y)
    print(f"{n} joined examples; base {X8.shape[1]} feats, rich {XR.shape[1]} feats")
    if n < 500:
        print("too few joined examples; wait for more harvest/SF data")
        return 1
    rng = np.random.RandomState(0x57111A7E)
    idx = rng.permutation(n)
    cut = int(n * 0.8)
    tr, va = idx[:cut], idx[cut:]
    mae0 = np.mean(np.abs(y[va]))
    print(f"\ndo-nothing val MAE: {mae0:.4f}\n")

    from sklearn.linear_model import Ridge
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.neural_network import MLPRegressor

    def ev(name, model, Xtr, Xva):
        model.fit(Xtr[tr], y[tr])
        pred = np.clip(model.predict(Xva[va]), -0.15, 0.15)
        mae = np.mean(np.abs(y[va] - pred))
        print(f"  {name:12s} val MAE {mae:.4f}  ({100*(1-mae/mae0):+.1f}% vs do-nothing)")
        return mae

    ev("ridge-8", Ridge(alpha=1.0), X8, X8)
    ev("gbm-8", GradientBoostingRegressor(n_estimators=300, max_depth=3,
                                          learning_rate=0.05), X8, X8)
    ev("ridge-rich", Ridge(alpha=1.0), XR, XR)
    ev("gbm-rich", GradientBoostingRegressor(n_estimators=400, max_depth=3,
                                             learning_rate=0.05), XR, XR)
    ev("mlp-rich", MLPRegressor(hidden_layer_sizes=(64, 32), max_iter=400,
                                early_stopping=True, alpha=1e-3), XR, XR)
    print("\nReadout: if rich/gbm/mlp beat ridge-8 by a clear margin, a board-"
          "feature corrector (Python oracle layer) is the next lever; if all "
          "~tie ridge-8, the residual isn't cheaply feature-predictable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
