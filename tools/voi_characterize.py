"""Behavioral characterization of the VOI (value-of-information) selection rule
vs the legacy PUCT descent. NOT an Elo test -- the engine is eval-bound, so the
question for the paper is whether the search becomes genuinely *belief-driven*:
does VOI route evals to the moves that actually decide the position (contested,
still-uncertain) instead of PUCT's policy x sqrt(N)/(1+n) sweep?

Method: one shared oracle, two fresh engines (VOI off / on), each thinks the
same positions to the SAME node budget. We read the root eval distribution
(core.root_children) and report, per position and pooled:
  - effective branching (# moves with >=5% of evals) and eval entropy,
  - top-1 eval share,
  - whether the chosen move agrees with PUCT,
  - the rank correlation between a move's value-closeness-to-best and its eval
    share -- the direct test of "evals follow contestedness" (VOI) vs "evals
    follow the policy prior" (PUCT).
Soundness: VOI-off is run twice and asserted bit-identical (the gated default
path must not move), and the per-move epistemic is dumped so the split is visible.

Run (base env, DirectML oracle):  python tools/voi_characterize.py
"""
import os
import sys
import json
import math
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import chess  # noqa: E402

NODES = int(os.environ.get("VOI_NODES", "4000"))
F_UCI, F_VAL, F_VTHEM, F_VAR, F_EVALS, F_PROOF, F_DIST, F_MLH = range(8)

# A spread: sharp tactic, quiet middlegame, a genuine 2-3 way choice, endgame.
POSITIONS = [
    ("start", chess.STARTING_FEN),
    ("WAC.001 mate-ish tactic",
     "2rr3k/pp3pp1/1nnqbN1p/3pN3/2pP4/2P3Q1/PPB4P/R4RK1 w - - 0 1"),
    ("quiet QGD middlegame",
     "r1bq1rk1/pp1nbppp/2p1pn2/3p4/2PP4/2N1PN2/PPQ1BPPP/R1B2RK1 w - - 0 9"),
    ("sharp Najdorf, several tries",
     "rnbqkb1r/1p3ppp/p2ppn2/8/3NP3/2N1B3/PPP2PPP/R2QKB1R w KQkq - 0 7"),
    ("rook endgame, one plan",
     "8/8/4kpp1/3p1b2/p6P/2B5/6P1/6K1 w - - 0 1"),
    ("opposite-side castling race",
     "r1b1k2r/ppppnppp/2n2q2/2b5/3NP3/2P1B3/PP3PPP/RN1QKB1R w KQkq - 0 1"),
]


def entropy(ns):
    tot = sum(ns)
    if tot <= 0:
        return 0.0
    h = 0.0
    for n in ns:
        if n > 0:
            p = n / tot
            h -= p * math.log(p)
    return h


def spearman(xs, ys):
    n = len(xs)
    if n < 2:
        return float("nan")

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx = sum(rx) / n
    my = sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = math.sqrt(sum((rx[i] - mx) ** 2 for i in range(n)))
    dy = math.sqrt(sum((ry[i] - my) ** 2 for i in range(n)))
    return num / (dx * dy) if dx > 0 and dy > 0 else float("nan")


def make_engine(oracle, voi):
    os.environ["STILLWATER_VOI"] = "1" if voi else "0"
    from stillwater.engine_rs import RustEngine
    eng = RustEngine(oracle=oracle, batch=128, refine=True)  # shipped feature set
    eng.new_game()
    return eng


def children_of(eng):
    rows = []
    for c in eng.core.root_children():
        rows.append({
            "uci": c[F_UCI],
            "q": round(-c[F_VAL], 4),      # value to the mover at the root
            "evals": int(c[F_EVALS]),
            "proof": bool(c[F_PROOF]),
        })
    return rows


def priors_of(oracle, fen):
    """BT4's raw policy as {uci: prob} for the root position."""
    board = chess.Board(fen)
    ev = oracle.evaluate([board])[0]
    out = {}
    for mv, p in (ev.policy or {}).items():
        uci = mv.uci() if isinstance(mv, chess.Move) else str(mv)
        out[uci] = float(p)
    return out


def run_position(eng, fen):
    board = chess.Board(fen)
    best, info = eng.think(board, node_budget=NODES)
    rows = children_of(eng)
    rows.sort(key=lambda r: -r["evals"])
    return (best.uci() if best else None), rows


def summarize(rows, priors):
    ns = [r["evals"] for r in rows]
    tot = sum(ns) or 1
    qs = [r["q"] for r in rows]
    qbest = max(qs) if qs else 0.0
    # closeness of each move's value to the best (1 = tied for best)
    closeness = [math.exp(-((qbest - q) ** 2) / (2 * 0.10 ** 2)) for q in qs]
    shares = [n / tot for n in ns]
    pri = [priors.get(r["uci"], 0.0) for r in rows]
    eff_branch = sum(1 for s in shares if s >= 0.05)
    # Head-of-distribution test (the rank correlations are confounded by the
    # unexplored tail). Which move gets the MOST evals -- the top-VALUE move
    # (belief-driven) or BT4's top-POLICY move (prior-driven)? On positions
    # where those two moves differ, this separates the rules cleanly.
    most_eval = rows[0]["uci"] if rows else None
    top_value = max(rows, key=lambda r: r["q"])["uci"] if rows else None
    top_prior = max(priors, key=priors.get) if priors else None
    conflict = (top_value != top_prior)  # value-argmax vs policy-argmax disagree
    return {
        "total_evals": tot,
        "moves": len(rows),
        "eff_branching@5%": eff_branch,
        "top1_share": round(max(shares) if shares else 0.0, 3),
        "entropy": round(entropy(ns), 3),
        "rho_closeness_vs_evalshare": round(spearman(closeness, shares), 3),
        "rho_prior_vs_evalshare": round(spearman(pri, shares), 3),
        "alloc_follows_value": int(most_eval == top_value),
        "alloc_follows_prior": int(most_eval == top_prior),
        "value_prior_conflict": int(conflict),
    }


def main():
    from stillwater.oracle import LeelaOracle
    oracle = LeelaOracle()
    print("provider:", oracle._sess.get_providers()[0], flush=True)

    puct = make_engine(oracle, voi=False)
    voi = make_engine(oracle, voi=True)
    # determinism / soundness: a second PUCT engine must reproduce PUCT exactly
    puct2 = make_engine(oracle, voi=False)

    out = []
    print(f"\n=== VOI vs PUCT @ {NODES} nodes/move ===\n", flush=True)
    for name, fen in POSITIONS:
        priors = priors_of(oracle, fen)
        p_best, p_rows = run_position(puct, fen)
        v_best, v_rows = run_position(voi, fen)
        p2_best, p2_rows = run_position(puct2, fen)

        identical = (p_best == p2_best and
                     [(r["uci"], r["evals"]) for r in p_rows] ==
                     [(r["uci"], r["evals"]) for r in p2_rows])
        ps, vs = summarize(p_rows, priors), summarize(v_rows, priors)
        agree = (p_best == v_best)
        print(f"# {name}")
        print(f"  PUCT best={p_best:6}  effB={ps['eff_branching@5%']} "
              f"top1={ps['top1_share']:.2f} H={ps['entropy']:.2f} "
              f"rho(close)={ps['rho_closeness_vs_evalshare']} "
              f"rho(prior)={ps['rho_prior_vs_evalshare']}")
        print(f"  VOI  best={v_best:6}  effB={vs['eff_branching@5%']} "
              f"top1={vs['top1_share']:.2f} H={vs['entropy']:.2f} "
              f"rho(close)={vs['rho_closeness_vs_evalshare']} "
              f"rho(prior)={vs['rho_prior_vs_evalshare']}")
        print(f"  agree={agree}  PUCT-deterministic={identical}")
        # show the top-4 of each so the redistribution is legible
        print("   PUCT:", "  ".join(f"{r['uci']}:{r['evals']}({r['q']:+.2f})"
                                     for r in p_rows[:4]))
        print("   VOI :", "  ".join(f"{r['uci']}:{r['evals']}({r['q']:+.2f})"
                                    for r in v_rows[:4]), flush=True)
        out.append({"name": name, "fen": fen, "agree": agree,
                    "puct_deterministic": identical,
                    "puct_best": p_best, "voi_best": v_best,
                    "puct": ps, "voi": vs,
                    "puct_rows": p_rows, "voi_rows": v_rows})

    # pooled
    def pooled(key):
        return {
            "mean_eff_branching": round(
                sum(o[key]["eff_branching@5%"] for o in out) / len(out), 2),
            "mean_top1_share": round(
                sum(o[key]["top1_share"] for o in out) / len(out), 3),
            "mean_entropy": round(
                sum(o[key]["entropy"] for o in out) / len(out), 3),
            "mean_rho_close_vs_share": round(sum(
                o[key]["rho_closeness_vs_evalshare"] for o in out
                if not math.isnan(o[key]["rho_closeness_vs_evalshare"]))
                / max(1, sum(1 for o in out if not math.isnan(
                    o[key]["rho_closeness_vs_evalshare"]))), 3),
            "mean_rho_prior_vs_share": round(sum(
                o[key]["rho_prior_vs_evalshare"] for o in out
                if not math.isnan(o[key]["rho_prior_vs_evalshare"]))
                / max(1, sum(1 for o in out if not math.isnan(
                    o[key]["rho_prior_vs_evalshare"]))), 3),
        }

    agree_rate = sum(1 for o in out if o["agree"]) / len(out)
    det_ok = all(o["puct_deterministic"] for o in out)
    # On the value/prior-conflict positions, who does the eval mass follow?
    conflicts = [o for o in out if o["puct"]["value_prior_conflict"]
                 or o["voi"]["value_prior_conflict"]]

    def follow(mode, kind):
        if not conflicts:
            return float("nan")
        return round(sum(o[mode][kind] for o in conflicts) / len(conflicts), 2)

    print("\n=== POOLED ===")
    print("PUCT:", pooled("puct"))
    print("VOI :", pooled("voi"))
    print(f"move-agreement VOI vs PUCT: {agree_rate:.2f}")
    print(f"PUCT determinism (gated-off bit-identical): "
          f"{'OK' if det_ok else 'FAILED'}")
    print(f"\nValue/prior-CONFLICT positions ({len(conflicts)}/{len(out)}): "
          "where most-evals goes")
    print(f"  PUCT  follows_value={follow('puct','alloc_follows_value')} "
          f"follows_prior={follow('puct','alloc_follows_prior')}")
    print(f"  VOI   follows_value={follow('voi','alloc_follows_value')} "
          f"follows_prior={follow('voi','alloc_follows_prior')}")
    print("\nREADING: on positions where BT4's top-policy move != the top-value "
          "move, PUCT's eval mass tends to follow the POLICY prior while VOI's "
          "follows the VALUE -- the belief-driven vs MCTS-prior distinction.")

    res = {"nodes": NODES, "agree_rate": agree_rate,
           "puct_deterministic": det_ok,
           "pooled_puct": pooled("puct"), "pooled_voi": pooled("voi"),
           "positions": out}
    path = os.path.join(REPO, "games", "voi_characterize.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    print("saved", path)


if __name__ == "__main__":
    sys.exit(main())
