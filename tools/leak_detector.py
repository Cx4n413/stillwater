"""Cheap conversion-leak detector: flag drawn games where we reached a big
material advantage (the class signature; SF autopsy only on flagged games)."""
import chess.pgn, io, sys, urllib.request
VALS = {chess.PAWN:1, chess.KNIGHT:3, chess.BISHOP:3, chess.ROOK:5, chess.QUEEN:9}
url = "https://lichess.org/api/games/user/stillwater_bot_2?max=60&moves=true"
pgn = urllib.request.urlopen(urllib.request.Request(url), timeout=30).read().decode()
flagged = []
for chunk in pgn.split("\n\n\n"):
    if "[Event" not in chunk: continue
    g = chess.pgn.read_game(io.StringIO(chunk))
    if g is None or g.headers.get("Result") != "1/2-1/2": continue
    me_white = "stillwater" in g.headers.get("White","").lower()
    board = g.board(); peak = 0
    for mv in g.mainline_moves():
        board.push(mv)
        d = sum(VALS[p]*(len(board.pieces(p,chess.WHITE))-len(board.pieces(p,chess.BLACK))) for p in VALS)
        mine = d if me_white else -d
        peak = max(peak, mine)
    if peak >= 5:
        flagged.append((g.headers.get("White"), g.headers.get("Black"), peak, g.headers.get("UTCTime")))
print(f"drawn-from-winning games (peak material >= +5): {len(flagged)}")
for w,b,p,t in flagged: print(f"  {w} vs {b} | peak +{p} | {t}")
