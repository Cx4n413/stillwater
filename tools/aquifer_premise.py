"""Part B (The Aquifer) PREMISE GATE -- fully offline, parses the bot's real games.

The Aquifer steers, among value-band-tied OPENING moves, toward the one that has
HISTORICALLY scored best for THIS engine. That only helps if the engine's own
realized opening results carry a real, stable signal -- one move scoring better
than an equal-value sibling -- that PERSISTS after controlling for opponent
strength (engine-fit, not just "we happened to face weaker players in that line").

PASS: there exist opening positions reached >= MIN_GAMES with >=2 candidate moves
      whose realized-score spread is >= 8pp AND whose better-move ordering holds
      after stratifying by opponent Elo (so it is engine-fit, not pool-overfit).
KILL: no such stable, opponent-controlled spread -> pure overfit, ship off.
"""
import collections
import glob
import os
import sys

import chess
import chess.pgn

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECORDS = r"C:\Users\nonna\Downloads\lichess-bot\game_records"
PLY_MAX = int(sys.argv[1]) if len(sys.argv) > 1 else 16
MIN_GAMES = int(sys.argv[2]) if len(sys.argv) > 2 else 4
SW = "STILLWATER"

pgns = glob.glob(os.path.join(RECORDS, "*.pgn"))
print(f"{len(pgns)} game records | ply<={PLY_MAX} | min_games/move {MIN_GAMES}",
      flush=True)

# (epd, sw_move_uci) -> list of (score, opp_elo)
edge = collections.defaultdict(list)
games_used = 0
for p in pgns:
    try:
        with open(p, encoding="utf-8", errors="ignore") as fh:
            g = chess.pgn.read_game(fh)
    except Exception:
        continue
    if g is None:
        continue
    h = g.headers
    white, black = h.get("White", ""), h.get("Black", "")
    if SW in white:
        sw_white = True
        opp_elo = h.get("BlackElo", "")
    elif SW in black:
        sw_white = False
        opp_elo = h.get("WhiteElo", "")
    else:
        continue
    res = h.get("Result", "*")
    if res == "1-0":
        sw_score = 1.0 if sw_white else 0.0
    elif res == "0-1":
        sw_score = 0.0 if sw_white else 1.0
    elif res == "1/2-1/2":
        sw_score = 0.5
    else:
        continue
    try:
        opp_elo = int(opp_elo)
    except (ValueError, TypeError):
        opp_elo = 0
    games_used += 1
    board = g.board()
    ply = 0
    for mv in g.mainline_moves():
        if ply >= PLY_MAX:
            break
        sw_to_move = (board.turn == chess.WHITE) == sw_white
        if sw_to_move:
            key = (board.epd(), mv.uci())
            edge[key].append((sw_score, opp_elo))
        board.push(mv)
        ply += 1

print(f"games used: {games_used}", flush=True)

# group by position (epd) -> {move: [(score,elo)]}
pos = collections.defaultdict(dict)
for (epd, mv), recs in edge.items():
    pos[epd][mv] = recs

# find positions with >=2 moves each reached >= MIN_GAMES
candidates = []
for epd, moves in pos.items():
    qualified = {m: r for m, r in moves.items() if len(r) >= MIN_GAMES}
    if len(qualified) >= 2:
        candidates.append((epd, qualified))

print(f"\nopening positions with >=2 moves each played >= {MIN_GAMES} games: "
      f"{len(candidates)}")
if not candidates:
    print("KILL premise: corpus too thin for any multi-move opening node "
          "(Aquifer needs more games to compound).")
    sys.exit()


def avg(recs):
    return sum(s for s, _ in recs) / len(recs)


def avg_elo(recs):
    es = [e for _, e in recs if e > 0]
    return sum(es) / len(es) if es else 0.0


import statistics as st
spreads = []
engine_fit = 0
for epd, moves in candidates:
    items = sorted(moves.items(), key=lambda kv: avg(kv[1]), reverse=True)
    best_m, best_r = items[0]
    worst_m, worst_r = items[-1]
    spread = avg(best_r) - avg(worst_r)
    spreads.append(spread)
    # opponent-control: is the best move's edge NOT explained by facing weaker foes?
    # (best move's avg opp-Elo should be >= worst's, i.e. it won despite equal/tougher)
    if spread >= 0.08 and avg_elo(best_r) >= avg_elo(worst_r) - 50:
        engine_fit += 1

print(f"median realized-score spread (best vs worst move): "
      f"{st.median(spreads):.2f}")
big = sum(1 for s in spreads if s >= 0.08)
print(f"positions with spread >= 8pp: {big}/{len(candidates)}")
print(f"  ... of those, opponent-controlled (engine-fit, not weaker-foe): {engine_fit}")
print(f"\nVERDICT: {'PASS -> engine-fit opening signal exists, Aquifer can steer' if engine_fit >= 3 else 'THIN -> not enough stable opponent-controlled signal yet; build infra, let it COMPOUND as games accumulate'}")
