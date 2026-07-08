"""UCI front-end. Run:  python -m stillwater.uci

The lattice persists across moves of a game (position-keyed: re-rooting after
the opponent replies is free), and the palimpsest's lessons persist with it.
`ucinewgame` drains the pond. Set option UseMock=true (or env STILLWATER_MOCK=1)
to run on the GPU-free mock oracle for plumbing tests.
"""

from __future__ import annotations

import os
import sys
import threading
import time

import chess

from . import __version__
from .engine import Engine


def _print(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


class UciServer:
    def __init__(self):
        self.engine: Engine | None = None
        self.board = chess.Board()
        self.options = {
            "Batch": int(os.environ.get("STILLWATER_BATCH", "128")),
            "Palimpsest": True,
            "UseMock": bool(int(os.environ.get("STILLWATER_MOCK", "0"))),
            "NetPath": "",
            "SyzygyPath": os.environ.get("STILLWATER_SYZYGY", ""),
            "OpponentModel": not bool(int(os.environ.get("STILLWATER_NO_OPP", "0"))),
            "Lens": not bool(int(os.environ.get("STILLWATER_NO_LENS", "0"))),
            # True only under arbiters that auto-adjudicate threefold/50-move
            # (cutechess). Lichess and human play use claim semantics.
            "StrictDraws": bool(int(os.environ.get("STILLWATER_STRICT_DRAWS", "0"))),
            "Harvest": not bool(int(os.environ.get("STILLWATER_NO_HARVEST", "0"))),
            "Ledger": not bool(int(os.environ.get("STILLWATER_NO_LEDGER", "0"))),
            # The compiled core (Rust lattice/settling/broker/encoder).
            # Falls back to the Python engine if the module is missing.
            "RustCore": not bool(int(os.environ.get("STILLWATER_NO_RUST", "0"))),
            "ProofBursts": True,    # sound theorems, field-targeted
            "RootThompson": False,  # exploration change: no positive evidence yet
            "Corrector": False,   # flip after train_corrector.py ships weights
            # The Refine package: lc0-aligned selection/backup semantics
            # (softmax temp, FPU, cpuct schedule, MLH gating, LCB backup,
            # zeroing-edge gamma, in-flight U, twofold pins). Default off
            # until validated vs the SF ladder + previous version.
            "Refine": bool(int(os.environ.get("STILLWATER_REFINE", "0"))),
            # Gated draw contempt (centi-value; 10 -> 0.10). Fight when winning,
            # draw when equal. Default 0 (off/legacy) until the timed SF
            # gauntlet clears the ship gate (no loss% increase vs 0).
            "DrawContempt": int(os.environ.get("STILLWATER_DRAW_CONTEMPT_CENTI", "0")),
        }
        self.search_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.ponder_hit_event = threading.Event()
        self._our_side: bool | None = None   # side we last searched for
        self._build_lock = threading.Lock()  # one engine build at a time
        if not UciServer._COLD_BOOK:         # entry-path-proof (also in main)
            UciServer._init_cold_book()

    # ----------------------------------------------------------------- engine

    def _make_engine(self) -> Engine:
        if self.options["UseMock"]:
            from .mock_oracle import MockOracle
            oracle = MockOracle()
        else:
            from .oracle import LeelaOracle
            path = self.options["NetPath"] or None
            # batch_max = the configured Batch so warmup builds only the buckets
            # the engine actually feeds (<=Batch). Avoids the slow/VRAM-heavy
            # 256-bucket TRT build that the deployment never uses (Batch=128).
            oracle = LeelaOracle(onnx_path=path, batch_max=int(self.options["Batch"]))
            if hasattr(oracle, "warmup"):
                oracle.warmup()
        kwargs = dict(oracle=oracle, batch=self.options["Batch"],
                      palimpsest_on=self.options["Palimpsest"],
                      syzygy_path=self.options["SyzygyPath"] or None,
                      opponent_model_on=self.options["OpponentModel"],
                      lens_on=self.options["Lens"],
                      strict_draws=self.options["StrictDraws"],
                      harvest_on=self.options["Harvest"],
                      ledger_on=self.options["Ledger"])
        if self.options["RustCore"]:
            try:
                from .engine_rs import RustEngine
                kwargs.update(proof_bursts=self.options["ProofBursts"],
                              root_thompson=self.options["RootThompson"],
                              corrector_on=self.options["Corrector"],
                              refine=self.options["Refine"],
                              draw_contempt=self.options["DrawContempt"] / 100.0)
                _print("info string compiled core active")
                return RustEngine(**kwargs)
            except ImportError:
                _print("info string compiled core unavailable; python engine")
        return Engine(**kwargs)

    def _ensure_engine(self) -> Engine:
        # Options-snapshot validation (2026-07-08): a build started before the
        # host's setoptions arrive must NOT win the race and leave a stale
        # default-options engine playing the game. If options changed while
        # _make_engine ran, discard the result and rebuild.
        while True:
            with self._build_lock:
                if self.engine is not None:
                    return self.engine
                snapshot = dict(self.options)
                eng = self._make_engine()
                if self.options == snapshot:
                    self.engine = eng
                    return eng
                try:
                    eng.shutdown()
                except Exception:
                    pass

    def _build_in_background(self) -> None:
        """Build the engine (incl. the oracle: _make_engine constructs and
        warms it -- the 10-15s CUDA/DML session on BT4) off the UCI thread.
        Anchored on `isready` (all setoptions have arrived by then; a build
        that races an options change is discarded by _ensure_engine). GUI
        hosts spawn a fresh engine process per game and opponents abort
        after ~15-30s of first-move silence, so _go bridges a still-cold
        engine with an instant book reply instead of blocking."""
        threading.Thread(target=self._ensure_engine, daemon=True).start()

    # ----------------------------------------------------------------- search

    @staticmethod
    def _cold_book_key(board: chess.Board) -> str:
        return " ".join(board.fen().split()[:2])

    # Instant first-move replies for when `go` arrives while the oracle is
    # still warming (opponents abort after ~15-30s of first-move silence;
    # one mainline book move costs ~nothing and caps our response under 3s).
    _COLD_BOOK: dict[str, str] = {}

    @classmethod
    def _init_cold_book(cls) -> None:
        start = chess.Board()
        cls._COLD_BOOK[cls._cold_book_key(start)] = "d2d4"
        for first, reply in [("e2e4", "e7e5"), ("d2d4", "g8f6"),
                             ("c2c4", "e7e5"), ("g1f3", "d7d5"),
                             ("g2g3", "d7d5"), ("b2b3", "e7e5"),
                             ("e2e3", "d7d5"), ("b1c3", "d7d5"),
                             ("f2f4", "d7d5"), ("d2d3", "d7d5")]:
            b = chess.Board()
            b.push_uci(first)
            cls._COLD_BOOK[cls._cold_book_key(b)] = reply

    def _go(self, args: list[str]) -> None:
        params: dict[str, float] = {}
        i = 0
        while i < len(args):
            tok = args[i]
            if tok in ("wtime", "btime", "winc", "binc", "movetime", "nodes",
                       "depth", "movestogo"):
                try:
                    params[tok] = float(args[i + 1])
                except (IndexError, ValueError):
                    pass
                i += 2
            elif tok == "infinite":
                params["infinite"] = 1.0
                i += 1
            elif tok == "ponder":
                params["ponder"] = 1.0
                i += 1
            else:
                i += 1
        pondering = "ponder" in params
        # COLD-START GUARD: if the engine is still building (first move of a
        # fresh process; the oracle session is the 10-15s cost), never make
        # the opponent wait past its abort window. Grace-wait 2.5s; still
        # cold -> instant book reply; off-book -> pay the wait (rare: the
        # book covers ply 0-1 and the build finishes during the opponent's
        # reply).
        if self.engine is None and not pondering:
            t0 = time.monotonic()
            while self.engine is None and time.monotonic() - t0 < 2.5:
                time.sleep(0.05)
            if self.engine is None:
                bk = self._COLD_BOOK.get(self._cold_book_key(self.board))
                if bk is not None and chess.Move.from_uci(bk) in self.board.legal_moves:
                    _print("info string cold-start book reply (engine warming)")
                    _print(f"bestmove {bk}")
                    return
        # FIRST-MOVE THINK CAP: opponents abort on move-one silence (~15-30s),
        # and with a full clock the court happily thinks 15-25s on ply 0/1 --
        # theory moves that a 3.5s search plays equally well. Applies to both
        # the clock path and lichess-bot's explicit first-move movetime.
        if self.board.ply() <= 1 and not pondering and "nodes" not in params \
                and "infinite" not in params:
            params["movetime"] = min(params.get("movetime", 3500.0), 3500.0)
        engine = self._ensure_engine()
        board = self.board.copy()
        # On a normal go after the opponent's reply, their move is on the
        # board; on `go ponder` the last move is only our PREDICTION of their
        # reply, so the Effigy must not see it (ponderhit confirms it instead).
        if (not pondering and self._our_side is not None
                and board.turn == self._our_side):
            self._feed_effigy(board)
        self._our_side = board.turn
        self.stop_event.clear()
        self.ponder_hit_event.clear()

        def info_cb(info: dict) -> None:
            self._emit_info(info)

        def run() -> None:
            kw = dict(stop_event=self.stop_event, info_cb=info_cb)
            force_nodes = os.environ.get("STILLWATER_FORCE_NODES", "")
            if force_nodes and not pondering:
                # Clock-free FIXED-NODES mode for clean gauntlets: ignore wtime/btime
                # entirely and always search exactly N nodes/move -> ZERO time
                # forfeits (the tc-based flagging that contaminates timed A/Bs).
                # Pair with tc=inf in cutechess so there is no clock to lose on.
                kw["node_budget"] = int(force_nodes)
            elif pondering:
                # Settle on the opponent's clock; the clock for our reply is
                # carried so 'ponderhit' starts it without a re-parse.
                kw["ponder"] = True
                kw["ponder_hit_event"] = self.ponder_hit_event
                kw.update(
                    wtime=params.get("wtime", 60000) / 1000.0,
                    btime=params.get("btime", 60000) / 1000.0,
                    winc=params.get("winc", 0) / 1000.0,
                    binc=params.get("binc", 0) / 1000.0,
                )
            elif "infinite" in params:
                kw["movetime"] = 86400.0
            elif "movetime" in params:
                kw["movetime"] = params["movetime"] / 1000.0
            elif "nodes" in params:
                kw["node_budget"] = int(params["nodes"])
            else:
                kw.update(
                    wtime=params.get("wtime", 60000) / 1000.0,
                    btime=params.get("btime", 60000) / 1000.0,
                    winc=params.get("winc", 0) / 1000.0,
                    binc=params.get("binc", 0) / 1000.0,
                )
            try:
                move, info = engine.think(board, **kw)
            except Exception as exc:  # never leave the GUI hanging
                _print(f"info string error {type(exc).__name__}: {exc}")
                if os.environ.get("STILLWATER_DBG"):
                    import sys as _s, traceback as _tb
                    _tb.print_exc(file=_s.stderr)
                    _s.stderr.flush()
                move, info = None, {}
            if move is None:
                legal = list(board.legal_moves)
                move = legal[0] if legal else None
            self._emit_info(info)
            # Offer the predicted reply so the GUI can ponder for us in turn.
            pv = info.get("pv", []) if isinstance(info, dict) else []
            ponder_sfx = f" ponder {pv[1].uci()}" if len(pv) >= 2 else ""
            _print(f"bestmove {move.uci() if move else '0000'}{ponder_sfx}")

        self.search_thread = threading.Thread(target=run, daemon=True)
        self.search_thread.start()

    def _emit_info(self, info: dict) -> None:
        if not info or "cp" not in info:
            return
        if (info.get("proof") and abs(info.get("value", 0)) > 0.5
                and info.get("proof_dist")):
            plies = max(1, int(info["proof_dist"]))   # exact, from the proof
            mate = (plies + 1) // 2
            score = f"mate {mate if info['value'] > 0 else -mate}"
        else:
            score = f"cp {info['cp']}"
        pv = " ".join(m.uci() for m in info.get("pv", []))
        # pv must precede "string": per the UCI spec everything after "string"
        # is opaque text, and parsers (python-chess/lichess-bot) drop it.
        _print(
            f"info depth {max(1, len(info.get('pv', [])))} "
            f"nodes {info.get('evals', 0)} nps {info.get('nps', 0)} "
            f"time {int(1000 * info.get('time', 0))} "
            f"score {score} hashfull {min(999, info.get('lattice', 0) // 2500)}"
            + (f" pv {pv}" if pv else "")
            + f" string pbest {info.get('p_best', 0):.2f} "
            f"rho {info.get('rho', 1.0):.2f} tb {info.get('tb_hits', 0)} "
            f"lessons {info.get('lessons', 0)}"
        )

    # ------------------------------------------------------------------- loop

    def run(self) -> None:
        for raw in sys.stdin:
            line = raw.strip().lstrip("﻿")
            if not line:
                continue
            cmd, *rest = line.split()
            if cmd == "uci":
                _print(f"id name STILLWATER {__version__}")
                _print("id author the settling engine")
                _print("option name Batch type spin default 128 min 8 max 1024")
                _print("option name Palimpsest type check default true")
                _print("option name UseMock type check default false")
                _print("option name NetPath type string default <empty>")
                _print("option name SyzygyPath type string default <empty>")
                _print("option name Ponder type check default false")
                _print("option name OpponentModel type check default true")
                _print("option name Lens type check default true")
                _print("option name StrictDraws type check default false")
                _print("option name Harvest type check default true")
                _print("option name Ledger type check default true")
                _print("option name RustCore type check default true")
                _print("option name ProofBursts type check default true")
                _print("option name RootThompson type check default false")
                _print("option name Corrector type check default false")
                _print("option name Refine type check default false")
                _print("option name DrawContempt type spin default 0 min 0 max 40")
                _print("uciok")
                # NOTE: deliberately NO build here -- hosts send setoptions
                # right after uciok, and a default-options build would either
                # win the race stale or be discarded (13s of wasted VRAM
                # churn). isready is the anchor.
            elif cmd == "isready":
                # Never block the GUI on the oracle load: build in the
                # background and reply immediately; _go bridges a cold
                # engine with the cold-book instant reply.
                if self.engine is None:
                    self._build_in_background()
                _print("readyok")
            elif cmd == "setoption":
                self._setoption(rest)
            elif cmd == "ucinewgame":
                if self.engine is not None:
                    self.engine.new_game()
            elif cmd == "position":
                self._position(rest)
            elif cmd == "go":
                self._go(rest)
            elif cmd == "ponderhit":
                # The opponent really played the predicted move: confirm it to
                # the Effigy, then let the pondering search convert to a timed one.
                self._feed_effigy(self.board)
                self.ponder_hit_event.set()
            elif cmd == "stop":
                self.stop_event.set()
                if self.search_thread is not None:
                    self.search_thread.join(timeout=10.0)
            elif cmd == "quit":
                self.stop_event.set()
                searching = False
                if self.search_thread is not None and self.search_thread.is_alive():
                    self.search_thread.join(timeout=30.0)  # let bestmove flush
                    searching = self.search_thread.is_alive()
                if self.engine is not None and not searching:
                    self.engine.shutdown()   # bank theorems + flush harvest
                break

    def _setoption(self, rest: list[str]) -> None:
        try:
            ni = rest.index("name") + 1
            vi = rest.index("value")
            name = " ".join(rest[ni:vi])
            val = " ".join(rest[vi + 1:])
        except ValueError:
            return
        if name in ("Batch", "DrawContempt"):
            new = int(val)
        elif name in ("Palimpsest", "UseMock", "OpponentModel", "Lens",
                      "StrictDraws", "Harvest", "Ledger", "RustCore",
                      "ProofBursts", "RootThompson", "Corrector", "Refine"):
            new = val.lower() in ("true", "1", "on")
        elif name in ("NetPath", "SyzygyPath"):
            new = val
        else:
            return  # Ponder etc.: always supported, nothing to configure
        if self.options.get(name) != new:
            self.options[name] = new
            self.engine = None  # rebuild lazily with the new options
            # NO build here: hosts send several setoptions in a burst, and a
            # build started mid-burst races the rest (stale until the snapshot
            # check discards it -- wasted 10-15s of session churn). The next
            # isready (or _go) anchors the rebuild with final options.

    def _position(self, rest: list[str]) -> None:
        if not rest:
            return
        if rest[0] == "startpos":
            board = chess.Board()
            moves = rest[2:] if len(rest) > 1 and rest[1] == "moves" else []
        elif rest[0] == "fen":
            try:
                mi = rest.index("moves")
                fen, moves = " ".join(rest[1:mi]), rest[mi + 1:]
            except ValueError:
                fen, moves = " ".join(rest[1:]), []
            board = chess.Board(fen)
        else:
            return
        for u in moves:
            board.push(chess.Move.from_uci(u))
        self.board = board

    def _feed_effigy(self, board: chess.Board) -> None:
        """The last move on this board was the opponent's actual move: free
        evidence on their strength. Called only for moves really played (a
        normal `go`, or `ponderhit` confirming the prediction) — never for the
        predicted move a GUI appends before `go ponder`."""
        if self.engine is None or not board.move_stack:
            return
        try:
            before = board.copy()
            last = before.pop()
            self.engine.note_opponent_move(before, last)
        except Exception:
            pass


def main() -> None:
    UciServer._init_cold_book()
    UciServer().run()


if __name__ == "__main__":
    main()
