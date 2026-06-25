"""Decompose the SW-vs-SF Elo gap into its mechanistic buckets.

The engine is eval-bound on BT4. This asks WHERE BT4's move-quality gap to
Stockfish lives, so the right lever can be chosen instead of guessed:

For each position (deep SF = ground truth):
  * policy recall@k : is SF's best move inside BT4's top-k policy moves?
      high recall  -> the right move is ON BT4's radar (a SELECTION problem)
      low  recall  -> BT4 is BLIND there (needs new candidates / a teacher)
  * cp-loss ladder (centipawns below SF's best, side-to-move POV):
      raw-policy    = BT4 policy argmax            (no search at all)
      top5-ceiling  = BEST of BT4's top-5 by SF eval (perfect selection,
                      candidate set limited to BT4's top-5 -- the most a
                      pure re-ranking / policy-distill could buy)
      (SW's own ~10cp from move_diagnostic is the search's actual result)
  Interpretation:
    top5-ceiling ~ 0      -> the move is there; SELECTION/policy-distill is the
                            lever and it can close most of the gap.
    top5-ceiling >> 0     -> even perfect re-ranking of BT4's candidates leaves
                            the gap -> the right move isn't a BT4 candidate
                            (blindness) OR no candidate is good enough (DEPTH)
                            -> needs a teacher-distill that adds moves, or a
                            cheap deep verifier (two-tier eval).

No SW engine needed -- this is a pure BT4-policy-vs-SF attribution (fast).
Run: python tools/gap_attribution.py [n] [sf_depth] [topN_for_ceiling]
"""

from __future__ import annotations

import os
import random
import sys
import time

import chess
import chess.engine

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
SF = (r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages"
      r"\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe"
      r"\stockfish\stockfish-windows-x86-64-avx2.exe")
random.seed(0x57111A7E)


def cp_of(info, turn):
    return info["score"].pov(turn).score(mate_score=2000)


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    depth = int(sys.argv[2]) if len(sys.argv) > 2 else 18
    topN = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    fens = [l.strip() for l in open(os.path.join(REPO, "games",
            "harvest_fens.txt"), encoding="utf-8") if l.strip()]
    random.shuffle(fens)
    fens = fens[:n]
    print(f"{len(fens)} positions | SF depth {depth} | ceiling over BT4 top-{topN}",
          flush=True)

    from stillwater.oracle import LeelaOracle
    oracle = LeelaOracle()
    sf = chess.engine.SimpleEngine.popen_uci(SF, timeout=60)
    sf.configure({"Threads": 6, "Hash": 512})

    K = [1, 3, 5, 10]
    recall = {k: 0 for k in K}
    cc_pol, cc_ceiling = [], []
    pol_in_top = 0          # SW-relevant: is BT4's #1 the SF best
    done = 0
    t0 = time.time()
    for fen in fens:
        try:
            board = chess.Board(fen)
            if board.is_game_over() or board.legal_moves.count() < 2:
                continue
            pol = oracle.evaluate_one(board).policy
            if not pol:
                continue
            # BT4 policy ranking (normalize keys to Move)
            ranked = sorted(pol.items(), key=lambda kv: -kv[1])
            ranked = [(m if isinstance(m, chess.Move)
                       else chess.Move.from_uci(m)) for m, _ in ranked]
            # SF ground truth
            best_info = sf.analyse(board, chess.engine.Limit(depth=depth))
            sf_best = best_info["pv"][0]
            sf_best_cp = cp_of(best_info, board.turn)
            # recall@k
            for k in K:
                if sf_best in ranked[:k]:
                    recall[k] += 1
            pol_in_top += (ranked[0] == sf_best)
            # raw-policy cp-loss
            pol_cp = cp_of(sf.analyse(board, chess.engine.Limit(depth=depth),
                                      root_moves=[ranked[0]]), board.turn)
            cc_pol.append(max(0, sf_best_cp - pol_cp))
            # top-N ceiling: best SF-cp achievable among BT4's top-N candidates
            cands = ranked[:topN]
            best_cand_cp = max(
                cp_of(sf.analyse(board, chess.engine.Limit(depth=depth),
                                 root_moves=[c]), board.turn) for c in cands)
            cc_ceiling.append(max(0, sf_best_cp - best_cand_cp))
            done += 1
            if done % 25 == 0:
                import statistics as st
                print(f"  {done}/{len(fens)}  recall@5={100*recall[5]/done:.0f}% "
                      f"polLoss={st.mean(cc_pol):.1f} ceilLoss={st.mean(cc_ceiling):.1f}"
                      f"  ({time.time()-t0:.0f}s)", flush=True)
        except Exception as e:
            print(f"  err: {e}", flush=True)
    sf.quit()

    import statistics as st
    print("\n==== GAP ATTRIBUTION ====", flush=True)
    print(f"positions: {done}")
    for k in K:
        print(f"  SF-best in BT4 top-{k:<2}: {100*recall[k]/done:5.1f}%")
    print(f"\n  raw-policy cp-loss      : {st.mean(cc_pol):6.1f}  median {st.median(cc_pol):.0f}")
    print(f"  top{topN}-ceiling cp-loss   : {st.mean(cc_ceiling):6.1f}  median {st.median(cc_ceiling):.0f}")
    print(f"  (SW search actual ~10cp from move_diagnostic; SF = 0)")
    rec5 = 100 * recall[5] / done
    ceil = st.mean(cc_ceiling)
    print("\nVERDICT:")
    if rec5 >= 88 and ceil <= 4:
        print("  The right move is on BT4's radar AND perfect re-ranking nearly")
        print("  closes the gap -> SELECTION is the lever; POLICY DISTILLATION")
        print("  (sharpen BT4's ordering toward SF) is high-leverage, low-risk.")
    elif rec5 < 78:
        print("  SF's move is often OUTSIDE BT4's top-5 -> BT4 is BLIND there ->")
        print("  distillation must ADD candidates, or a different eval is needed.")
    else:
        print("  Even perfect re-ranking of BT4's candidates leaves a large gap")
        print("  -> the bottleneck is DEPTH/eval-quality, not ordering -> a cheap")
        print("  deep verifier (two-tier eval) is the lever that adds new info.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
