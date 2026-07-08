"""Mine every SW mistake across all games; classify king-safety vs other.

A mistake = our move concedes >=90cp (SF d13 before/after). Classification:
run the refutation PV (d15) after our move; if the opponent's punishment
involves checks on OUR king / captures in our king's zone early, or the eval
swing coincides with our king ring being attacked, tag KING-SAFETY.
"""
import chess.pgn, chess.engine, io, json, sys
SF = (r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages"
      r"\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe"
      r"\stockfish\stockfish-windows-x86-64-avx2.exe")
sf = chess.engine.SimpleEngine.popen_uci([SF]); sf.configure({"Threads": 2, "Hash": 512})
text = open("games/sb2_all.pgn", encoding="utf-8").read()
out = []
ngames = 0
for chunk in text.split("\n\n\n"):
    if "[Event" not in chunk: continue
    g = chess.pgn.read_game(io.StringIO(chunk))
    if g is None: continue
    ngames += 1
    me_white = "stillwater" in g.headers.get("White","").lower()
    board = g.board()
    for mv in g.mainline_moves():
        my_turn = board.turn == (chess.WHITE if me_white else chess.BLACK)
        if not my_turn or board.fullmove_number <= 8:
            board.push(mv); continue
        info = sf.analyse(board, chess.engine.Limit(depth=13))
        b4 = info["score"].pov(board.turn).score(mate_score=3000)
        best = info.get("pv", [None])[0]
        fen_before = board.fen()
        board.push(mv)
        info2 = sf.analyse(board, chess.engine.Limit(depth=13))
        aft = -info2["score"].pov(board.turn).score(mate_score=3000)
        if b4 is None or aft is None or b4 - aft < 90 or b4 < -300:
            continue
        # classify: examine the punishment PV
        pun = sf.analyse(board, chess.engine.Limit(depth=15))
        pv = pun.get("pv", [])[:8]
        b2 = board.copy()
        my_color = chess.WHITE if me_white else chess.BLACK
        checks = 0; king_zone_hits = 0
        for pmv in pv:
            ksq = b2.king(my_color)
            if b2.is_capture(pmv) and ksq is not None and chess.square_distance(pmv.to_square, ksq) <= 2 and b2.turn != my_color:
                king_zone_hits += 1
            b2.push(pmv)
            if b2.is_check() and b2.turn == my_color:
                checks += 1
        ks = checks >= 2 or king_zone_hits >= 2 or (checks >= 1 and king_zone_hits >= 1) or aft <= -900
        out.append({"fen": fen_before, "played": mv.uci(), "best": best.uci() if best else "?",
                    "b4": b4, "aft": aft, "checks": checks, "kz": king_zone_hits,
                    "king_safety": bool(ks),
                    "opp": g.headers.get("Black" if me_white else "White","?")})
sf.quit()
json.dump(out, open("games/mistakes.json","w"), indent=1)
n = len(out); k = sum(1 for m in out if m["king_safety"])
print(f"games {ngames} | mistakes(>=90cp): {n} | king-safety-tagged: {k} ({100*k/max(1,n):.0f}%)")
