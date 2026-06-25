"""THE FORK EXPERIMENT (v2, hardened by two adversarial reviews): of STILLWATER's
residual move-losses, what fraction is DEPTH-findable vs SEARCH-STRUCTURE vs
EVAL-QUALITY? This picks the architectural lever; nothing in the record measures it.

Three references, classified on SW's RAW argmax-VALUE readout (NOT the deployed
LCB+trap pick -- review P0.1: the LCB pick rule would mislabel selection effects
as search-structure; we record the deployed pick separately to size that):
  * SW at a fixed-NODE ladder (in-process RustEngine -> core.root_children gives
    the backed-up per-move value, invisible over UCI). new_game() per rung +
    ledger/harvest OFF so rungs are independent and reproducible (review P2.7).
  * lc0 on the SAME BT4 at a NODE LADDER (review P0.2: a single low lc0 budget
    inflates eval_quality; eval_quality requires lc0 to miss M at its TOP rung).
  * Stockfish SINGLE-THREADED (deterministic), deep, with NEAR-TIE exclusion
    (review P1.5: 6-thread SF nondeterminism corrupts the decisive filter and the
    M identity on near-ties).

Buckets (M = SF's best move):
  correct_always   : SW raw-pick == M at every rung (no loss).
  depth_findable   : SW raw-pick wrong at LOW rung, == M at TOP rung (nodes fixed it)  -> THROUGHPUT lever.
  depth_unstable   : SW found M at some middle rung then lost it                        -> BACKUP/fixed-point STABILITY lever.
  search_structure : SW never raw-picks M, but lc0-on-BT4 plays M at some rung          -> HYBRID-SELECTION lever (extract like lc0).
  eval_quality     : neither SW nor lc0-on-BT4 ever plays M (only SF does)              -> EVAL teacher / two-tier / retrain.

cp-loss is a SCREEN, not Elo (the project's recurring trap). A bucket authorizes a
BUILD; only a timed gauntlet proves Elo. Report DISTRIBUTIONS + the decisive subset.

Run (oracle MUST be DirectML -- asserted; CUDA leak degrades late positions):
  python tools/gap_depth_eval.py [n] [sw_rungs] [lc0_rungs] [sf_depth] [out.json]
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from collections import Counter

import chess
import chess.engine

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
SF = (r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages"
      r"\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe"
      r"\stockfish\stockfish-windows-x86-64-avx2.exe")
LC0 = r"C:\Users\nonna\Downloads\lc0\cuda12\lc0.exe"
BT4 = os.path.join(REPO, "nets",
                   "BT4-1024x15x32h-swa-6147500-policytune-332.pb.gz")
F_UCI, F_VAL, F_EVALS = 0, 1, 4
random.seed(0x57111A7E)
DECISIVE = 25      # cp; loss below this is noise (review P1.5: margin > SF noise)
NEAR_TIE = 15      # cp; if SF top1-top2 gap < this, M is ambiguous -> skip position


def cp_of(info, turn):
    return info["score"].pov(turn).score(mate_score=2000)


def sw_value_map(eng):
    """uci -> (q_mover, evals); q = -val (child-POV negated to mover-POV)."""
    out = {}
    for c in eng.core.root_children():
        out[c[F_UCI]] = (-float(c[F_VAL]), int(c[F_EVALS]))
    return out


def raw_argmax(vmap):
    """SW's raw argmax-VALUE pick among expanded children (the thesis readout)."""
    if not vmap:
        return None
    return max(vmap.items(), key=lambda kv: kv[1][0])[0]


def phase_of(board):
    n = chess.popcount(board.occupied)
    return "opening" if n >= 26 else "endgame" if n <= 12 else "middlegame"


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    sw_rungs = ([int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2
                else [768, 4000, 16000, 40000])
    lc0_rungs = ([int(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3
                 else [20000, 100000])
    sf_depth = int(sys.argv[4]) if len(sys.argv) > 4 else 20
    out_path = (sys.argv[5] if len(sys.argv) > 5
                else os.path.join(REPO, "games", "gap_depth_eval.json"))
    sf_shallow = 10

    fens = [l.strip() for l in open(os.path.join(REPO, "games",
            "harvest_fens.txt"), encoding="utf-8") if l.strip()]
    fens = list(dict.fromkeys(fens))
    random.shuffle(fens)
    fens = fens[:n]
    print(f"{len(fens)} pos | SW {sw_rungs} | lc0 {lc0_rungs} (residual only) | "
          f"SF d{sf_depth} 1-thread | decisive>={DECISIVE} near-tie-excl<{NEAR_TIE}",
          flush=True)

    from stillwater.oracle import LeelaOracle
    from stillwater.engine_rs import RustEngine
    oracle = LeelaOracle()
    prov = oracle._sess.get_providers()[0]
    print("SW oracle provider:", prov, flush=True)
    assert prov in ("TensorrtExecutionProvider", "CUDAExecutionProvider"), (
        f"oracle on {prov} -- want a GPU provider (TRT or CUDA) for a large run, "
        f"not DirectML/CPU.")
    sw = RustEngine(oracle=oracle, batch=128, refine=True,
                    harvest_on=False, ledger_on=False)

    lc0 = chess.engine.SimpleEngine.popen_uci([LC0], timeout=120)
    lc0.configure({"WeightsFile": BT4})
    sf = chess.engine.SimpleEngine.popen_uci(SF, timeout=60)
    sf.configure({"Threads": 1, "Hash": 512})   # single-thread = deterministic

    recs = []
    skipped_tie = 0
    t0 = time.time()
    for fi, fen in enumerate(fens):
        try:
            board = chess.Board(fen)
            if board.is_game_over() or board.legal_moves.count() < 2:
                continue
            turn = board.turn

            # --- SF reference: M + near-tie guard + cp lookup from multipv
            multi = sf.analyse(board, chess.engine.Limit(depth=sf_depth), multipv=5)
            M = multi[0]["pv"][0]
            cp_M = cp_of(multi[0], turn)
            if len(multi) >= 2 and (cp_M - cp_of(multi[1], turn)) < NEAR_TIE:
                skipped_tie += 1
                continue                          # M ambiguous -> not a clean target
            cp_lookup = {info["pv"][0].uci(): cp_of(info, turn) for info in multi}

            def sf_cp(uci):
                if uci in cp_lookup:
                    return cp_lookup[uci]
                return cp_of(sf.analyse(board, chess.engine.Limit(depth=sf_depth),
                                        root_moves=[chess.Move.from_uci(uci)]), turn)

            Mu = M.uci()

            # --- SW ladder, classify on RAW argmax-value (not the LCB pick)
            ladder = []
            for r in sw_rungs:
                sw.new_game()
                best, info = sw.think(board, node_budget=r)
                vmap = sw_value_map(sw)
                ev = (info or {}).get("evals") or sum(v[1] for v in vmap.values())
                ladder.append({
                    "rung": r, "realized_evals": int(ev),
                    "raw_pick": raw_argmax(vmap),
                    "deployed_pick": best.uci() if best else None,
                    "q_M": vmap.get(Mu, (None, 0))[0],
                })
            raw_picks = [x["raw_pick"] for x in ladder]
            S_raw_top, S_raw_low = raw_picks[-1], raw_picks[0]
            deployed_top = ladder[-1]["deployed_pick"]

            # --- cp screen (decisive?) from SW's top raw pick
            cp_Sraw = sf_cp(S_raw_top) if S_raw_top else cp_M
            loss = max(0, cp_M - cp_Sraw)
            decisive = loss >= DECISIVE

            # --- classify on RAW pick. lc0 (the expensive 20-100k-node probe)
            # runs ONLY when it is the discriminator: a DECISIVE loss where SW
            # never raw-picked M at any rung (the search_structure-vs-eval_quality
            # fork). depth_findable / depth_unstable are decided by SW's ladder
            # alone; non-decisive misses are excluded from the fork.
            lc0_picks, lc0_found, M_sf10 = None, None, None
            if S_raw_top == Mu:
                bucket = "depth_findable" if S_raw_low != Mu else "correct_always"
            elif Mu in raw_picks:
                bucket = "depth_unstable"          # found M mid-ladder, drifted off it
            elif not decisive:
                bucket = "minor_miss"              # SW != M but <DECISIVE cp: ignore
            else:
                lc0_picks = []                     # the fork: run lc0-on-BT4
                for r in lc0_rungs:
                    mv = lc0.play(board, chess.engine.Limit(nodes=r)).move
                    lc0_picks.append(mv.uci() if mv else None)
                lc0_found = Mu in lc0_picks
                if lc0_found:
                    bucket = "search_structure"    # lc0-on-BT4 finds it, SW never does
                else:
                    bucket = "eval_quality"        # neither BT4-search finds it
                    M_sf10 = sf.analyse(board, chess.engine.Limit(
                        depth=sf_shallow))["pv"][0].uci()

            qMs = [x["q_M"] for x in ladder if x["q_M"] is not None]
            q_M_trend = (qMs[-1] - qMs[0]) if len(qMs) >= 2 else None

            recs.append({
                "fen": fen, "phase": phase_of(board), "M": Mu, "cp_M": cp_M,
                "S_raw_top": S_raw_top, "S_raw_low": S_raw_low,
                "deployed_top": deployed_top,
                "raw_vs_deployed_differ": (S_raw_top != deployed_top),
                "loss": loss, "decisive": decisive,
                "lc0_picks": lc0_picks, "lc0_found": lc0_found,
                "sf10_eq_M": (M_sf10 == Mu) if M_sf10 else None,
                "bucket": bucket, "q_M_trend": q_M_trend, "ladder": ladder,
            })
            if len(recs) % 10 == 0:
                dec = [r for r in recs if r["decisive"]]
                bc = Counter(r["bucket"] for r in dec)
                print(f"  {len(recs)}/{len(fens)} (tie-skip {skipped_tie}) "
                      f"decisive={len(dec)} {dict(bc)} ({time.time()-t0:.0f}s)",
                      flush=True)
                with open(out_path, "w", encoding="utf-8") as f:   # checkpoint
                    json.dump({"sw_rungs": sw_rungs, "lc0_rungs": lc0_rungs,
                               "sf_depth": sf_depth, "skipped_tie": skipped_tie,
                               "records": recs}, f)
        except Exception as e:
            print(f"  err @{fi}: {e}", flush=True)

    sw.shutdown(); lc0.quit(); sf.quit()
    report(recs, skipped_tie, sw_rungs, lc0_rungs)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"sw_rungs": sw_rungs, "lc0_rungs": lc0_rungs,
                   "sf_depth": sf_depth, "skipped_tie": skipped_tie,
                   "records": recs}, f, indent=1)
    print(f"\nsaved {out_path}")
    return 0


def report(recs, skipped_tie, sw_rungs, lc0_rungs):
    import statistics as st
    dec = [r for r in recs if r["decisive"]]
    residual = [r for r in dec if r["bucket"] in
                ("search_structure", "eval_quality", "depth_unstable")]
    print("\n==== DEPTH vs SEARCH-STRUCTURE vs EVAL-QUALITY ====")
    print(f"scored {len(recs)} | near-tie skipped {skipped_tie} | "
          f"decisive losses (>={DECISIVE}cp) {len(dec)}")
    if recs:
        print(f"mean loss {st.mean([r['loss'] for r in recs]):.1f} "
              f"median {st.median([r['loss'] for r in recs]):.0f} (means are a "
              f"screen, not Elo)")
    print(f"\nbuckets (ALL scored): {dict(Counter(r['bucket'] for r in recs))}")
    print(f"buckets (DECISIVE):    {dict(Counter(r['bucket'] for r in dec))}")
    if residual:
        print(f"\nDECISIVE RESIDUAL (SW raw-pick != M), N={len(residual)} -- the lever fork:")
        rc = Counter(r["bucket"] for r in residual)
        for b in ("search_structure", "eval_quality", "depth_unstable"):
            sub = [r for r in residual if r["bucket"] == b]
            frac = 100 * len(sub) / len(residual)
            rising = sum(1 for r in sub if (r["q_M_trend"] or 0) > 0.02)
            lever = {"search_structure": "HYBRID-SELECTION (extract like lc0)",
                     "eval_quality": "EVAL teacher / two-tier / retrain",
                     "depth_unstable": "BACKUP STABILITY (non-monotone fixed pt)"}[b]
            print(f"  {b:16} {len(sub):3} ({frac:4.0f}%)  q_M-rising@top {rising}/{len(sub)}"
                  f"  -> {lever}")
        eq = [r for r in residual if r["bucket"] == "eval_quality"]
        if eq:
            caught = sum(1 for r in eq if r["sf10_eq_M"])
            print(f"  two-tier probe: cheap SF-d10 ranks M best in {caught}/{len(eq)}"
                  f" eval_quality positions (decorrelation -> verifier-addressable)")
        # BLOCKING CHECK (review P3.9): if many residuals still rising at top rung,
        # the top SW rung is too low and depth-findable cases are mislabeled.
        rising_all = sum(1 for r in residual if (r["q_M_trend"] or 0) > 0.02)
        if rising_all > 0.20 * len(residual):
            print(f"  !! WARNING: {rising_all}/{len(residual)} residuals still RISING "
                  f"at top rung {sw_rungs[-1]} -> raise the top rung before trusting "
                  f"the structure/eval split (latent depth contaminates it).")
    # depth-findable + selection inefficiency
    flips = [r for r in recs if r["bucket"] == "depth_findable"]
    print(f"\ndepth_findable (wrong@low, M@top): {len(flips)}/{len(recs)} "
          f"-> THROUGHPUT lever signal")
    diff = [r for r in dec if r["raw_vs_deployed_differ"]]
    print(f"selection inefficiency: raw-argmax != deployed-LCB pick on "
          f"{len(diff)}/{len(dec)} decisive positions")
    # phase breakdown of the residual
    if residual:
        ph = Counter((r["phase"], r["bucket"]) for r in residual)
        print(f"\nresidual by phase: {dict(ph)}")
    print("\nREMINDER: lever-SELECTION screen, not Elo. A bucket authorizes a "
          "BUILD; only a timed gauntlet proves strength.")


if __name__ == "__main__":
    sys.exit(main())
