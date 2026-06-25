"""Sanity tests for stillwater.oracle (runs on the auto-discovered net).

Run from the repo root:
    python tests_oracle/test_oracle.py        # plain runner
    python -m pytest tests_oracle/test_oracle.py -v   # if pytest installed
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import chess  # noqa: E402

from stillwater.oracle import LeelaOracle, OracleEval  # noqa: E402

_ORACLE = None


def get_oracle():
    global _ORACLE
    if _ORACLE is None:
        _ORACLE = LeelaOracle()
        print(f"[oracle] net      : {_ORACLE.onnx_path}")
        print(f"[oracle] providers: {_ORACLE.providers}")
    return _ORACLE


def top_moves(ev, k=4):
    return [m for m, _ in
            sorted(ev.policy.items(), key=lambda kv: -kv[1])[:k]]


def test_startpos():
    ev = get_oracle().evaluate([chess.Board()])[0]
    w, d, l = ev.wdl
    assert abs(w + d + l - 1.0) < 1e-3, f"wdl not normalized: {ev.wdl}"
    assert abs(sum(ev.policy.values()) - 1.0) < 1e-5, "policy not normalized"
    assert len(ev.policy) == 20
    mains = [chess.Move.from_uci(u)
             for u in ("e2e4", "d2d4", "g1f3", "c2c4")]
    mass = sum(ev.policy[m] for m in mains)
    tops = top_moves(ev, 4)
    print(f"[startpos] top4={[m.uci() for m in tops]} mainline mass={mass:.3f}"
          f" wdl=({w:.3f},{d:.3f},{l:.3f}) value={ev.value:+.4f}")
    assert tops[0] in mains, f"odd top move {tops[0]}"
    assert mass > 0.5, f"main openings carry too little mass: {mass:.3f}"
    assert w > l, "white should not be worse at startpos"
    assert abs(ev.value) < 0.5, f"startpos value implausible: {ev.value}"


def test_mirror():
    """eval(position) ~ eval(color-flipped mirror), stm perspective kept."""
    fens = [
        "r1bq1rk1/ppp2ppp/2np1n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 7",
        "r2qkb1r/pp2nppp/3p4/2pNN1B1/2BnP3/3P4/PPP2PPP/R2bK2R w KQkq - 1 10",
        "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
        "2kr3r/pp1n1ppp/2p1p3/q7/1b1P1B2/2N2Q1P/PPP2PP1/2KR3R w - - 4 13",
    ]
    o = get_oracle()
    for fen in fens:
        b = chess.Board(fen)
        m = b.mirror()  # vertical flip + color swap + turn/castling swap
        ev_b, ev_m = o.evaluate([b, m])
        dv = abs(ev_b.value - ev_m.value)
        top_b = top_moves(ev_b, 1)[0]
        top_m = top_moves(ev_m, 1)[0]
        mirrored_top = chess.Move(
            chess.square_mirror(top_b.from_square),
            chess.square_mirror(top_b.to_square), top_b.promotion)
        print(f"[mirror] |dV|={dv:.4f} top {top_b.uci()} -> {top_m.uci()} "
              f"({fen.split()[1]} to move)")
        assert dv < 0.05, f"mirror value mismatch {dv:.4f} for {fen}"
        assert top_m == mirrored_top, (
            f"mirror top-move mismatch: {top_b.uci()} vs {top_m.uci()}")


def test_hanging_queen():
    # Black queen on h4 is en prise to the f3 knight; Nxh4 must be top move.
    b = chess.Board(
        "rnb1kbnr/pppppppp/8/8/7q/5N2/PPPPPPPP/RNBQKB1R w KQkq - 2 3")
    ev = get_oracle().evaluate([b])[0]
    top = top_moves(ev, 1)[0]
    p = ev.policy[chess.Move.from_uci("f3h4")]
    print(f"[tactics] Nxh4 prob={p:.3f}, top={top.uci()}, "
          f"value={ev.value:+.3f}")
    assert top == chess.Move.from_uci("f3h4"), f"missed hanging queen: {top}"


def test_winning_position():
    # K+Q+R vs K, side to move winning -> value > 0.8
    ev = get_oracle().evaluate([chess.Board("4k3/8/8/8/8/8/8/RQ2K3 w - - 0 1")])[0]
    print(f"[winning] KQR vs K value={ev.value:+.4f} wdl={ev.wdl}")
    assert ev.value > 0.8, f"KQR vs K should be winning: {ev.value}"


def test_black_to_move():
    b = chess.Board()
    b.push_uci("e2e4")
    ev = get_oracle().evaluate([b])[0]
    sane = {chess.Move.from_uci(u)
            for u in ("e7e5", "c7c5", "e7e6", "c7c6", "d7d5", "g8f6", "d7d6")}
    tops = top_moves(ev, 4)
    mass = sum(p for m, p in ev.policy.items() if m in sane)
    print(f"[black] after 1.e4 top4={[m.uci() for m in tops]} "
          f"sane mass={mass:.3f} value={ev.value:+.4f}")
    assert tops[0] in sane, f"odd reply to 1.e4: {tops[0]}"
    assert mass > 0.5
    # black is slightly worse after 1.e4 but within a quarter pawn or so
    assert -0.4 < ev.value < 0.2


def test_castling_in_policy():
    b = chess.Board(
        "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
    ev = get_oracle().evaluate([b])[0]
    oo = chess.Move.from_uci("e1g1")
    assert oo in ev.policy, "O-O missing from policy dict"
    print(f"[castle] white O-O prob={ev.policy[oo]:.3f} "
          f"(rank {top_moves(ev, len(ev.policy)).index(oo) + 1} "
          f"of {len(ev.policy)})")
    assert ev.policy[oo] > 0.005
    # ... and for black after castling becomes legal
    b2 = chess.Board(
        "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R b KQkq - 5 5")
    ev2 = get_oracle().evaluate([b2])[0]
    oo8 = chess.Move.from_uci("e8g8")
    assert oo8 in ev2.policy and ev2.policy[oo8] > 0.005


def test_no_legal_moves():
    mate = chess.Board(  # fool's mate, white is checkmated
        "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3")
    stale = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")  # stalemate
    evs = get_oracle().evaluate([mate, stale])
    for ev in evs:
        assert isinstance(ev, OracleEval)
        assert ev.policy == {}
    print(f"[terminal] mate value={evs[0].value:+.3f}, "
          f"stalemate value={evs[1].value:+.3f} (both empty policy, ok)")


def test_batch_consistency():
    """Same board evaluated alone and inside a batch must agree closely."""
    o = get_oracle()
    boards = []
    b = chess.Board()
    for u in ("e2e4", "c7c5", "g1f3", "d7d6", "d2d4", "c5d4", "f3d4", "g8f6"):
        b.push_uci(u)
        boards.append(b.copy())
    batch = o.evaluate(boards)
    singles = [o.evaluate([x])[0] for x in boards]
    for ev_b, ev_s in zip(batch, singles):
        assert abs(ev_b.value - ev_s.value) < 0.02
        for m in ev_b.policy:
            assert abs(ev_b.policy[m] - ev_s.policy[m]) < 0.01
    print(f"[batch] batch-vs-single max value diff = "
          f"{max(abs(a.value - b.value) for a, b in zip(batch, singles)):.5f}")


def test_history_matters():
    """Boards passed with move history must encode it (smoke check only)."""
    o = get_oracle()
    b = chess.Board()
    for u in ("g1f3", "g8f6", "f3g1", "f6g8", "g1f3", "g8f6", "f3g1", "f6g8"):
        b.push_uci(u)
    ev_hist = o.evaluate([b])[0]          # twofold repetition encoded
    ev_bare = o.evaluate([chess.Board()])[0]
    print(f"[history] startpos value={ev_bare.value:+.4f}, after knight "
          f"shuffle repetition value={ev_hist.value:+.4f}")
    # with a repetition on the board the net should smell the draw
    assert ev_hist.wdl[1] >= ev_bare.wdl[1] - 0.05


ALL_TESTS = [
    test_startpos, test_mirror, test_hanging_queen, test_winning_position,
    test_black_to_move, test_castling_in_policy, test_no_legal_moves,
    test_batch_consistency, test_history_matters,
]

if __name__ == "__main__":
    failed = []
    for t in ALL_TESTS:
        try:
            t()
            print(f"PASS {t.__name__}\n")
        except AssertionError as e:
            failed.append(t.__name__)
            print(f"FAIL {t.__name__}: {e}\n")
    print(f"{len(ALL_TESTS) - len(failed)}/{len(ALL_TESTS)} tests passed"
          + (f"; FAILED: {failed}" if failed else ""))
    sys.exit(1 if failed else 0)
