"""Forensic dissection of WHERE/WHY STILLWATER loses move quality vs Stockfish.

The move diagnostic showed SW is a near-SF picker on average (8.3cp), with the
Elo leak concentrated in (a) a ~1.6%% big-blunder tail (>80cp) and (b) ~9.7%%
"search HURT" cases (SW's searched move worse than BT4's raw prior). This finds
the COMMON CAUSE: for every problem position it records phase, material context
(winning/equal/losing per SF), and move-type features, then aggregates so the
dominant pattern (e.g. endgame pawn-pushes, conversion of winning positions,
noise-amplified quiet moves) is visible -> that pattern defines the fix.

Saves problem positions to games/forensic_failures.jsonl and prints aggregates.
Run: python tools/forensic_failures.py [n] [sw_movetime_s] [sf_depth]
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
random.seed(0xBEEF)
NPM = {chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


def cp_of(info, turn):
    return info["score"].pov(turn).score(mate_score=2000)


def phase(board):
    npm = sum(v * (len(board.pieces(p, True)) + len(board.pieces(p, False)))
              for p, v in NPM.items())
    pieces = chess.popcount(board.occupied)
    if pieces <= 12 or npm <= 16:
        return "endgame"
    if board.fullmove_number <= 12:
        return "opening"
    return "middlegame"


def move_feats(board, mv, pre=""):
    pc = board.piece_at(mv.from_square)
    ptype = chess.piece_name(pc.piece_type) if pc else "?"
    return {
        pre + "piece": ptype,
        pre + "capture": board.is_capture(mv),
        pre + "pawn_push": pc is not None and pc.piece_type == chess.PAWN
        and not board.is_capture(mv),
        pre + "promo": mv.promotion is not None,
        pre + "to_rank": chess.square_rank(mv.to_square),
    }


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    sw_mt = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
    sf_depth = int(sys.argv[3]) if len(sys.argv) > 3 else 16
    fens = [l.strip() for l in open(os.path.join(REPO, "games",
            "harvest_fens.txt"), encoding="utf-8") if l.strip()]
    random.shuffle(fens); fens = fens[:n]
    print(f"{len(fens)} positions | SW {sw_mt}s | SF d{sf_depth}", flush=True)

    from stillwater.oracle import LeelaOracle
    oracle = LeelaOracle()
    sw = chess.engine.SimpleEngine.popen_uci(
        [sys.executable, "-u", "-m", "stillwater.uci"], cwd=REPO, timeout=180)
    legal = {o.name.lower() for o in sw.options.values()}
    sw.configure({k: v for k, v in {"RustCore": True, "Batch": 128,
                  "Refine": True, "DrawContempt": 10}.items() if k.lower() in legal})
    sf = chess.engine.SimpleEngine.popen_uci(SF, timeout=60)
    sf.configure({"Threads": 6, "Hash": 512})

    out = open(os.path.join(REPO, "games", "forensic_failures.jsonl"), "w",
               encoding="utf-8")
    blunder_phase, blunder_mtype, blunder_ctx = Counter(), Counter(), Counter()
    hurt_phase, hurt_mtype, hurt_ctx = Counter(), Counter(), Counter()
    n_blunder = n_hurt = done = 0
    t0 = time.time()
    for fen in fens:
        try:
            board = chess.Board(fen)
            if board.is_game_over() or board.legal_moves.count() < 2:
                continue
            pol = oracle.evaluate_one(board).policy
            if not pol:
                continue
            pol_move = max(pol, key=pol.get)
            if isinstance(pol_move, str):
                pol_move = chess.Move.from_uci(pol_move)
            sw_move = sw.play(board, chess.engine.Limit(time=sw_mt)).move
            multi = sf.analyse(board, chess.engine.Limit(depth=sf_depth), multipv=3)
            sf_best, sf_best_cp = multi[0]["pv"][0], cp_of(multi[0], board.turn)
            sw_cp = cp_of(sf.analyse(board, chess.engine.Limit(depth=sf_depth),
                          root_moves=[sw_move]), board.turn)
            pol_cp = cp_of(sf.analyse(board, chess.engine.Limit(depth=sf_depth),
                           root_moves=[pol_move]), board.turn)
            csw, cpol = max(0, sf_best_cp - sw_cp), max(0, sf_best_cp - pol_cp)
            done += 1
            ph = phase(board)
            ctx = ("winning" if sf_best_cp > 150 else
                   "losing" if sf_best_cp < -150 else "equalish")
            mf = move_feats(board, sw_move)
            mtype = ("capture" if mf["capture"] else
                     "pawn_push" if mf["pawn_push"] else
                     mf["piece"])
            is_blunder = csw > 80
            is_hurt = csw > cpol + 30
            if is_blunder or is_hurt:
                rec = {"fen": fen, "phase": ph, "ctx": ctx,
                       "sw": sw_move.uci(), "sf_best": sf_best.uci(),
                       "pol": pol_move.uci(), "cc_sw": csw, "cc_pol": cpol,
                       "blunder": is_blunder, "hurt": is_hurt,
                       "mtype": mtype, "fullmove": board.fullmove_number,
                       **mf}
                out.write(json.dumps(rec, separators=(",", ":")) + "\n")
                out.flush()
            if is_blunder:
                n_blunder += 1
                blunder_phase[ph] += 1; blunder_mtype[mtype] += 1; blunder_ctx[ctx] += 1
            if is_hurt:
                n_hurt += 1
                hurt_phase[ph] += 1; hurt_mtype[mtype] += 1; hurt_ctx[ctx] += 1
            if done % 100 == 0:
                print(f"  {done}  blunders={n_blunder} hurt={n_hurt} "
                      f"({time.time()-t0:.0f}s)", flush=True)
        except Exception as e:
            print(f"  err: {e}", flush=True)
    sw.quit(); sf.quit(); out.close()

    def show(name, c):
        print(f"  {name}: " + ", ".join(f"{k}={v}" for k, v in c.most_common()))
    print(f"\n==== FORENSICS: {done} scored | blunders(>80cp)={n_blunder} "
          f"({100*n_blunder/max(1,done):.1f}%) | search-hurt(>+30cp)={n_hurt} "
          f"({100*n_hurt/max(1,done):.1f}%) ====", flush=True)
    print(" BLUNDERS:")
    show("phase", blunder_phase); show("ctx", blunder_ctx); show("move-type", blunder_mtype)
    print(" SEARCH-HURT:")
    show("phase", hurt_phase); show("ctx", hurt_ctx); show("move-type", hurt_mtype)
    print("\n-> dominant pattern defines the fix; details in games/forensic_failures.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
