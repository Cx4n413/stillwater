"""Pull STILLWATER-bot's recent lichess games and find the drawn-won ones:
result, opponent + rating, SW color, final material balance, termination, and
whether the finish was a 3-fold. Confirms the 'draws won games vs weaker bots'
report and extracts real positions ~N plies before the end for analysis.
"""
import io, sys, urllib.request
import chess, chess.pgn

USER = "STILLWATER-bot"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 25
VAL = {chess.PAWN:1, chess.KNIGHT:3, chess.BISHOP:3, chess.ROOK:5, chess.QUEEN:9, chess.KING:0}

url = f"https://lichess.org/api/games/user/{USER}?max={N}&moves=true&tags=true&clocks=false"
req = urllib.request.Request(url, headers={"User-Agent":"stillwater-diag", "Accept":"application/x-chess-pgn"})
pgn = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
stream = io.StringIO(pgn)

def material(board, color):
    s = 0
    for sq, pc in board.piece_map().items():
        s += VAL[pc.piece_type] * (1 if pc.color == color else -1)
    return s

games = 0; draws = 0; drawn_won = []
res_count = {}
while True:
    g = chess.pgn.read_game(stream)
    if g is None: break
    games += 1
    w, bl = g.headers.get("White",""), g.headers.get("Black","")
    res = g.headers.get("Result","*")
    term = g.headers.get("Termination","")
    sw_white = (w == USER)
    sw_color = chess.WHITE if sw_white else chess.BLACK
    opp = bl if sw_white else w
    opp_elo = g.headers.get("BlackElo","?") if sw_white else g.headers.get("WhiteElo","?")
    # play to final position
    board = g.board(); plies = 0; last_positions = []
    for mv in g.mainline_moves():
        board.push(mv); plies += 1
    res_count[res] = res_count.get(res, 0) + 1
    # SW result
    sw_pts = 0.5 if res == "1/2-1/2" else (1.0 if (res=="1-0")==sw_white else 0.0)
    mat = material(board, sw_color)
    if res == "1/2-1/2":
        draws += 1
        if mat >= 3:   # SW was up >=3 pts of material in a draw
            # get position 14 plies before the end (the won-but-shuffling phase)
            b2 = g.board(); mv_list = list(g.mainline_moves())
            for mv in mv_list[:max(0, len(mv_list)-14)]: b2.push(mv)
            drawn_won.append((opp, opp_elo, sw_white, mat, plies, term, b2.fen(),
                              " ".join(m.uci() for m in mv_list[-14:])))

print(f"games fetched: {games} | results {res_count} | draws {draws} | "
      f"DRAWN-WHILE-UP-MATERIAL: {len(drawn_won)}")
print("\nDRAWN WON GAMES (opp, oppElo, SWwhite, SW_material_adv, plies, term):")
for opp, elo, sww, mat, plies, term, fen, lastmoves in drawn_won:
    print(f"  vs {opp} ({elo}) SWwhite={sww} +{mat} mat, {plies} plies, {term}")
    print(f"    pos -14: {fen}")
    print(f"    last14 : {lastmoves}")
