"""Build the #1 policy-signal dataset from the deep harvest.

Per position: a compact board encoding, the SEARCH's visit-policy + settled
value (the expert-iteration targets), and BT4's RAW policy-top + value (the
baseline to beat). The signal question (answered by train_signal_net.py): can a
net trained on the search's policy predict the search's chosen move on held-out
positions BETTER than BT4's raw policy already does? If yes -> the search's
move-improvement is learnable -> #1 has legs. If no -> BT4 is the ceiling here.

Board encoding (18x8x8, absolute coords): 12 piece planes (6 white, 6 black) +
4 castling + side-to-move + en-passant file. Move index = from*64+to (4096;
underpromotions collapse to queen, negligible for the signal check).

Run (base env, uses the oracle for BT4 policy): python tools/extract_signal_data.py [limit]
"""
import glob, json, os, sys
import numpy as np
import chess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PT = [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING]


def encode(board):
    x = np.zeros((18, 8, 8), np.float32)
    for sq in chess.SQUARES:
        p = board.piece_at(sq)
        if p:
            plane = PT.index(p.piece_type) + (0 if p.color == chess.WHITE else 6)
            x[plane, chess.square_rank(sq), chess.square_file(sq)] = 1.0
    for i, cr in enumerate([board.has_kingside_castling_rights(chess.WHITE),
                            board.has_queenside_castling_rights(chess.WHITE),
                            board.has_kingside_castling_rights(chess.BLACK),
                            board.has_queenside_castling_rights(chess.BLACK)]):
        if cr:
            x[12 + i, :, :] = 1.0
    if board.turn == chess.WHITE:
        x[16, :, :] = 1.0
    if board.ep_square is not None:
        x[17, :, chess.square_file(board.ep_square)] = 1.0
    return x


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    files = [f for f in sorted(glob.glob(os.path.join(REPO, "harvest", "*.jsonl")))
             if "sf_labels" not in f and "dataset" not in f]
    recs = []
    for path in files:
        for line in open(path, encoding="utf-8"):
            try:
                r = json.loads(line)
                if r.get("claim") or r.get("proof") or r["evidence"] < 200:
                    continue
                if not r.get("moves") or len(r["moves"]) < 2:
                    continue
                recs.append(r)
            except Exception:
                pass
    if limit:
        recs = recs[:limit]
    print(f"{len(recs)} usable deep-harvest records", flush=True)

    boards = np.zeros((len(recs), 18, 8, 8), np.float16)
    spol = np.zeros((len(recs), 4096), np.float16)   # search visit policy
    mask = np.zeros((len(recs), 4096), bool)
    sval = np.zeros(len(recs), np.float32)            # search settled value
    sbest = np.zeros(len(recs), np.int32)             # search top move idx
    chess_boards = []
    for i, r in enumerate(recs):
        b = chess.Board(r["fen"])
        chess_boards.append(b)
        boards[i] = encode(b)
        sval[i] = r["settled"][0]
        tot = sum(m[2] for m in r["moves"]) or 1
        bestv = -1
        for uci, val, ev, pf in r["moves"]:
            mv = chess.Move.from_uci(uci)
            idx = mv.from_square * 64 + mv.to_square
            mask[i, idx] = True
            spol[i, idx] += ev / tot
            if ev > bestv:
                bestv = ev; sbest[i] = idx
        if (i + 1) % 2000 == 0:
            print(f"  encoded {i+1}/{len(recs)}", flush=True)

    # BT4 raw policy-top + value via the oracle (batched)
    print("computing BT4 raw policy via oracle...", flush=True)
    from stillwater.oracle import LeelaOracle
    o = LeelaOracle()
    print("provider:", o._sess.get_providers()[0], flush=True)
    bbest = np.zeros(len(recs), np.int32)
    bval = np.zeros(len(recs), np.float32)
    CH = 256
    for s in range(0, len(chess_boards), CH):
        chunk = chess_boards[s:s + CH]
        for k, ev in enumerate(o.evaluate(chunk)):
            pol = ev.policy
            if pol:
                bm = max(pol, key=pol.get)
                mv = bm if isinstance(bm, chess.Move) else chess.Move.from_uci(bm)
                bbest[s + k] = mv.from_square * 64 + mv.to_square
            bval[s + k] = ev.value
        if (s + CH) % 2560 == 0:
            print(f"  oracle {s+CH}/{len(chess_boards)}", flush=True)

    out = os.path.join(REPO, "harvest", "signal_dataset.npz")
    np.savez_compressed(out, boards=boards, spol=spol, mask=np.packbits(mask, axis=1),
                        sval=sval, sbest=sbest, bbest=bbest, bval=bval)
    agree = float(np.mean(sbest == bbest))
    print(f"\nsaved {out} ({len(recs)} positions)")
    print(f"search-top == BT4-policy-top: {100*agree:.1f}%  "
          f"(so the search changes the move in {100*(1-agree):.1f}% of positions)")
    print(f"value: BT4-raw vs search MAE {np.mean(np.abs(bval - sval)):.4f}")


if __name__ == "__main__":
    sys.exit(main())
