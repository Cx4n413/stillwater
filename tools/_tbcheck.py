import chess, chess.syzygy
tb = chess.syzygy.open_tablebase("nets/syzygy")
for fen in ["8/8/8/3k4/8/8/8/3QK3 w - - 0 1",          # KQ vs K (3-man)
            "8/8/8/4k3/8/8/8/R3K3 w - - 0 1",          # KR vs K (3-man)
            "8/8/8/3k4/8/4P3/8/3QK3 w - - 0 1",        # KQP vs K (4-man)
            "8/8/8/3k4/8/2P1P3/8/3QK3 w - - 0 1",      # KQ+2P vs K (5-man)
            "3k4/8/5P2/8/8/1P2K3/8/5q2 b - - 4 72"]:   # real sseh-c pos (KQ vs KPP)
    b = chess.Board(fen)
    try:
        w = tb.probe_wdl(b)
    except Exception as ex:
        print("\nFEN:", fen, "| PROBE FAILED:", type(ex).__name__, ex)
        continue
    print("\nFEN:", fen, "| wdl(stm):", w)
    best=None; bk=None
    for m in b.legal_moves:
        z=b.is_zeroing(m); b.push(m)
        try:
            cm=b.is_checkmate(); ow=tb.probe_wdl(b); od=tb.probe_dtz(b)
        except Exception:
            b.pop(); continue
        b.pop()
        if cm: best=m; break
        if ow is None or ow>=0: continue
        k=(0 if z else 1, abs(od) if od is not None else 999)
        if bk is None or k<bk: bk=k; best=m
    print("  DTZ-best converting move:", b.san(best) if best else None, "key", bk)
tb.close()
