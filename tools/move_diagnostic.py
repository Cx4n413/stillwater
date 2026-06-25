"""Play-relevant lever diagnostic: WHERE does STILLWATER lose Elo vs Stockfish?

For each position, score three moves against SF ground truth (centipawns):
  * SW   = STILLWATER's chosen move at a real think budget (search + BT4)
  * POL  = BT4's raw policy argmax (no search -- the prior alone)
  * SF   = Stockfish's best move (multipv top)
cp_cost(m) = cp(SF_best) - cp(m), both from the side-to-move POV.

ATTRIBUTION (the point):
  * cp_cost(SW) << cp_cost(POL)  -> search already fixes bad priors; POLICY is
                                    NOT the bottleneck (a policy net won't help).
  * cp_cost(SW) ~= cp_cost(POL)  -> search isn't improving move choice over the
                                    prior; policy-distill or search-retune is the lever.
  * cp_cost(SW) absolute size    -> how much move-quality headroom exists at all.

Run: python tools/move_diagnostic.py [n] [sw_movetime_s] [sf_depth]
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
    sc = info["score"].pov(turn)
    return sc.score(mate_score=2000)


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 800
    sw_mt = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
    sf_depth = int(sys.argv[3]) if len(sys.argv) > 3 else 16

    fens = [l.strip() for l in open(os.path.join(REPO, "games",
            "harvest_fens.txt"), encoding="utf-8") if l.strip()]
    random.shuffle(fens)
    fens = fens[:n]
    print(f"{len(fens)} positions | SW {sw_mt}s | SF depth {sf_depth}", flush=True)

    from stillwater.oracle import LeelaOracle
    oracle = LeelaOracle()

    sw = chess.engine.SimpleEngine.popen_uci(
        [sys.executable, "-u", "-m", "stillwater.uci"], cwd=REPO, timeout=180)
    legal = {o.name.lower() for o in sw.options.values()}
    sw.configure({k: v for k, v in {"RustCore": True, "Batch": 128,
                  "Refine": True, "DrawContempt": 10}.items() if k.lower() in legal})

    sf = chess.engine.SimpleEngine.popen_uci(SF, timeout=60)
    sf.configure({"Threads": 6, "Hash": 512})

    cc_sw, cc_pol = [], []
    agree_sw = agree_pol = 0
    search_helped = search_hurt = search_same = 0
    big_loss = 0
    t0 = time.time()
    done = 0
    for fen in fens:
        try:
            board = chess.Board(fen)
            if board.is_game_over() or board.legal_moves.count() < 2:
                continue
            pol = oracle.evaluate_one(board).policy
            if not pol:
                continue
            pol_move = max(pol, key=pol.get)
            pol_move = chess.Move.from_uci(pol_move) if isinstance(pol_move, str) else pol_move
            sw_move = sw.play(board, chess.engine.Limit(time=sw_mt)).move
            multi = sf.analyse(board, chess.engine.Limit(depth=sf_depth), multipv=5)
            sf_best = multi[0]["pv"][0]
            sf_best_cp = cp_of(multi[0], board.turn)
            sw_cp = cp_of(sf.analyse(board, chess.engine.Limit(depth=sf_depth),
                                     root_moves=[sw_move]), board.turn)
            pol_cp = cp_of(sf.analyse(board, chess.engine.Limit(depth=sf_depth),
                                      root_moves=[pol_move]), board.turn)
            csw = max(0, sf_best_cp - sw_cp)
            cpol = max(0, sf_best_cp - pol_cp)
            cc_sw.append(csw); cc_pol.append(cpol)
            agree_sw += (sw_move == sf_best)
            agree_pol += (pol_move == sf_best)
            if csw < cpol - 5: search_helped += 1
            elif csw > cpol + 5: search_hurt += 1
            else: search_same += 1
            big_loss += (csw > 80)
            done += 1
            if done % 50 == 0:
                import statistics as st
                print(f"  {done}/{len(fens)}  meanCC_sw={st.mean(cc_sw):.1f} "
                      f"meanCC_pol={st.mean(cc_pol):.1f}  ({time.time()-t0:.0f}s)",
                      flush=True)
        except Exception as e:
            print(f"  err: {e}", flush=True)
    sw.quit(); sf.quit()

    import statistics as st
    print("\n==== MOVE-QUALITY DIAGNOSTIC ====", flush=True)
    print(f"positions scored: {done}")
    print(f"mean cp_cost(SW move)         : {st.mean(cc_sw):6.1f}  median {st.median(cc_sw):.0f}")
    print(f"mean cp_cost(BT4 policy-top)  : {st.mean(cc_pol):6.1f}  median {st.median(cc_pol):.0f}")
    print(f"SW agrees with SF-best        : {100*agree_sw/done:.1f}%")
    print(f"BT4 policy-top == SF-best     : {100*agree_pol/done:.1f}%")
    print(f"search HELPED (cc_sw<cc_pol)  : {100*search_helped/done:.1f}%")
    print(f"search HURT   (cc_sw>cc_pol)  : {100*search_hurt/done:.1f}%")
    print(f"search ~same                  : {100*search_same/done:.1f}%")
    print(f"SW big blunders (cc>80cp)     : {100*big_loss/done:.1f}%")
    dsw, dpol = st.mean(cc_sw), st.mean(cc_pol)
    if dsw < dpol - 8:
        verdict = ("search already fixes priors; POLICY is NOT the bottleneck. "
                   "Lever = value/search-depth, not a policy net.")
    elif abs(dsw - dpol) <= 8:
        verdict = ("search barely improves on the raw prior; the policy effectively "
                   "drives play -> policy-distill OR search-retune is the lever.")
    else:
        verdict = "search is making moves WORSE than the prior -> search/value bug."
    print(f"\nVERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
