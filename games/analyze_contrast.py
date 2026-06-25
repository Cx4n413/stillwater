import sys, chess, chess.pgn, chess.engine

SF = r"C:\Users\nonna\AppData\Local\Microsoft\WinGet\Packages\Stockfish.Stockfish_Microsoft.Winget.Source_8wekyb3d8bbwe\stockfish\stockfish-windows-x86-64-avx2.exe"
DEPTH = 27

def score_white_cp(info_score, board_turn_white_to_move):
    # info_score is POV of side to move (PovScore). Convert to White POV in cp, capped.
    s = info_score.white()
    if s.is_mate():
        m = s.mate()
        return (100000 - abs(m)*100) * (1 if m > 0 else -1)
    return s.score()

def fmt(cp):
    if abs(cp) >= 90000:
        sign = '+' if cp > 0 else '-'
        return f"{sign}M~"
    return f"{cp/100:+.2f}"

def main(pgn_path, sw_is_white_label):
    with open(pgn_path) as f:
        game = chess.pgn.read_game(f)
    white = game.headers["White"]
    black = game.headers["Black"]
    result = game.headers["Result"]
    sw_white = (white == "SW")
    print(f"# {pgn_path}  White={white} Black={black} Result={result}  SW_is_white={sw_white}")

    eng = chess.engine.SimpleEngine.popen_uci(SF)
    eng.configure({"Threads": 6, "Hash": 2048})

    board = game.board()
    # eval before any move (start) from White POV
    rows = []
    node = game
    # We evaluate the position AFTER each move.
    moves = list(game.mainline_moves())
    # baseline eval of start position
    info = eng.analyse(board, chess.engine.Limit(depth=DEPTH))
    prev_white_cp = score_white_cp(info["score"], board.turn == chess.WHITE)

    sw_cploss = []  # (ply, movestr, sw_eval_reported, sf_white_cp_after, cploss_sw_pov)
    comments = list(game.mainline())  # nodes

    ply = 0
    for node in game.mainline():
        mv = node.move
        mover_is_white = board.turn == chess.WHITE
        san = board.san(mv)
        board.push(mv)
        info = eng.analyse(board, chess.engine.Limit(depth=DEPTH))
        white_cp_after = score_white_cp(info["score"], board.turn == chess.WHITE)
        # CP loss for the mover: from mover POV, eval before (mover pov) - eval after (mover pov)
        before_mover = prev_white_cp if mover_is_white else -prev_white_cp
        after_mover = white_cp_after if mover_is_white else -white_cp_after
        cploss = before_mover - after_mover  # positive = mover lost ground
        mover_is_sw = (mover_is_white == sw_white)
        ply += 1
        movenum = (ply + 1)//2
        tag = "SW" if mover_is_sw else "OP"
        comment = node.comment.strip()
        # capture reported eval (first token)
        rep = comment.split()[0] if comment else ""
        marker = ""
        if mover_is_sw and cploss >= 60:
            marker = "  <== SW LOSS"
            sw_cploss.append((ply, movenum, mover_is_white, san, rep, white_cp_after, cploss, comment))
        print(f"{ply:3d} {movenum:3d}.{'' if mover_is_white else '..'} {tag} {san:8s} sfW={fmt(white_cp_after):>8s} cploss={cploss:6d} rep={rep:10s} {comment}{marker}")
        prev_white_cp = white_cp_after

    eng.quit()
    print("\n## SW moves with cploss>=60 (sorted):")
    for r in sorted(sw_cploss, key=lambda x: -x[6]):
        ply, movenum, isw, san, rep, wcp, cploss, comment = r
        print(f"  ply{ply} {movenum}.{'' if isw else '..'}{san}  cploss={cploss}  SWreported={rep}  sfWhiteAfter={fmt(wcp)}  full={comment}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
