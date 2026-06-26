"""Self-play game generator for the Aquifer -- the overnight data engine.

Direct engine (NO UCI/cutechess -> no time-flagging), deployed config + BT4 at
fixed nodes. Each game: a policy-SAMPLED opening (variety -> covers the band-tied
alternatives the Aquifer chooses among), then deterministic deployed play, with
aggressive value-adjudication so games end fast. Writes a PGN (both sides are the
engine) that tools/build_aquifer.py folds into the book.

Run several instances in parallel for GPU throughput; pass a distinct TAG each:
    python tools/selfplay.py A 1000
Stop with the task killer; PGNs are flushed per game so a kill never loses data.
"""
import os
import random
import sys

import chess
import chess.pgn

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

TAG = sys.argv[1] if len(sys.argv) > 1 else "0"
NODES = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
OPENING_PLIES = 8
OPENING_TEMP = 0.7
MAX_PLIES = 220
RESIGN_V, RESIGN_PLIES = 0.90, 6
DRAW_PLY, DRAW_V = 80, 0.10
OUT = os.path.join(REPO, "games", f"selfplay_{TAG}.pgn")
rng = random.Random(int.from_bytes(os.urandom(8), "little"))

from stillwater.oracle import LeelaOracle
from stillwater.engine_rs import RustEngine
oracle = LeelaOracle()
os.write(2, f"[selfplay {TAG}] provider {oracle._sess.get_providers()[0]} "
            f"nodes {NODES} -> {OUT}\n".encode())
eng = RustEngine(oracle=oracle, batch=128, refine=True, harvest_on=False,
                 ledger_on=False)


def sample_opening(board, plies):
    legalset = None
    for _ in range(plies):
        if board.is_game_over():
            break
        eng.new_game()
        eng.think(board, node_budget=1)          # 1 eval -> net policy at root
        moves = eng.core.root_moves()             # (uci, prior, expanded)
        legalset = {m.uci() for m in board.legal_moves}
        cand = [(m[0], max(1e-6, float(m[1]))) for m in moves
                if m[0] in legalset]
        if not cand:
            break
        ws = [p ** (1.0 / OPENING_TEMP) for _, p in cand]
        tot = sum(ws)
        r = rng.random() * tot
        acc, pick = 0.0, cand[-1][0]
        for (u, _), w in zip(cand, ws):
            acc += w
            if acc >= r:
                pick = u
                break
        board.push_uci(pick)


def play_game():
    board = chess.Board()
    sample_opening(board, OPENING_PLIES)
    eng.new_game()
    streak_side, streak = 0, 0
    while not board.is_game_over(claim_draw=True) and board.ply() < MAX_PLIES:
        mv, info = eng.think(board, node_budget=NODES)
        if mv is None:
            break
        stm_white = board.turn == chess.WHITE
        v = float(info.get("value", 0.0))
        white_v = v if stm_white else -v
        if mv not in board.legal_moves:
            break
        board.push(mv)
        if white_v > RESIGN_V:
            streak = streak + 1 if streak_side == 1 else 1
            streak_side = 1
        elif white_v < -RESIGN_V:
            streak = streak + 1 if streak_side == -1 else 1
            streak_side = -1
        else:
            streak_side, streak = 0, 0
        if streak >= RESIGN_PLIES:
            return ("1-0" if streak_side == 1 else "0-1"), board
        if board.ply() > DRAW_PLY and abs(white_v) < DRAW_V:
            return "1/2-1/2", board
    if board.is_game_over(claim_draw=True):
        return board.result(claim_draw=True), board
    return "1/2-1/2", board


n = 0
fh = open(OUT, "a", encoding="utf-8")
while True:
    try:
        result, board = play_game()
    except Exception as exc:
        os.write(2, f"[selfplay {TAG}] game error: {exc}\n".encode())
        continue
    g = chess.pgn.Game.from_board(board)
    g.headers["White"] = "STILLWATER-selfplay"
    g.headers["Black"] = "STILLWATER-selfplay"
    g.headers["Result"] = result
    fh.write(str(g) + "\n\n")
    fh.flush()
    n += 1
    if n % 20 == 0:
        os.write(2, f"[selfplay {TAG}] {n} games\n".encode())
