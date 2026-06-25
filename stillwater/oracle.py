"""STILLWATER GPU evaluation oracle.

Loads a pretrained Lc0 chess network (converted to ONNX with ``lc0 leela2onnx``)
and evaluates batches of ``chess.Board`` positions on the GPU through
onnxruntime-directml (provider ``DmlExecutionProvider``).

Usage::

    from stillwater.oracle import LeelaOracle, OracleEval

    oracle = LeelaOracle()                  # auto-discovers newest .onnx in <repo>/nets/
    evals = oracle.evaluate([board, ...])   # -> list[OracleEval]
    evals[0].wdl     # (win, draw, loss) from the side to move's perspective
    evals[0].value   # win - loss, in [-1, 1], side to move's perspective
    evals[0].policy  # {chess.Move: prior}, over legal moves only, sums to 1.0

Notes for engine authors
------------------------
* Everything is from the SIDE-TO-MOVE perspective (value > 0 means the side to
  move is better), for both white and black to move.
* The network uses up to 8 plies of history taken from ``board.move_stack``.
  Pass boards that carry their game history (i.e. boards you reached via
  ``push()``) for maximum strength; bare FEN boards still work (lc0's standard
  "fill empty history" rule is applied).
* The DirectML execution provider JIT-compiles the fused graph once per input
  shape.  Batches are therefore padded up to power-of-two bucket sizes (capped
  at ``batch_max``) so at most ~log2(batch_max) compilations ever happen.  The
  first call at each bucket size is slow (up to a few seconds for a large
  net); call :meth:`LeelaOracle.warmup` once at startup to pre-compile.
* Boards with no legal moves (checkmate/stalemate) return an empty policy
  dict; ``wdl``/``value`` are still produced by the net but are meaningless
  for terminal nodes -- the search should score terminals itself.

Input encoding implemented here is lc0's INPUT_CLASSICAL_112_PLANE, verified
against lc0 v0.32.1 (src/neural/encoder.cc) and cross-checked move-by-move
against lc0's own output (see tests_oracle/crosscheck_lc0.py).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

import chess
import numpy as np
import onnxruntime as ort

# onnxruntime-gpu ships its CUDA/cuDNN/TensorRT DLLs as bundled nvidia-*-cu12
# pip wheels that are NOT on Windows' default DLL search path. Without this,
# the CUDA/TensorRT EPs silently fall back to CPU (18 evals/s). preload_dlls()
# (ORT 1.22+) loads them; the add_dll_directory loop is the belt-and-braces
# fallback for older ORT. Harmless under onnxruntime-directml (no nvidia dir).
def _load_gpu_dlls() -> None:
    try:
        import glob
        nvbase = os.path.join(os.path.dirname(ort.__file__), "..", "nvidia")
        for d in glob.glob(os.path.join(nvbase, "*", "bin")):
            try:
                os.add_dll_directory(os.path.abspath(d))
            except OSError:
                pass
        # TensorRT EP: the nvinfer DLLs ship in the tensorrt_libs wheel, a
        # sibling of onnxruntime/. Without this on the DLL search path,
        # RegisterTensorRTPluginsAsCustomOps fails and the TRT EP silently falls
        # back to CUDA (the June-12 failure). Add it so STILLWATER_TRT works.
        trtlib = os.path.join(os.path.dirname(ort.__file__), "..", "tensorrt_libs")
        if os.path.isdir(trtlib):
            trtlib = os.path.abspath(trtlib)
            try:
                os.add_dll_directory(trtlib)
            except OSError:
                pass
            # ORT's RegisterTensorRTPluginsAsCustomOps loads nvinfer via PATH
            # (NOT the add_dll_directory list), so prepend it to PATH too --
            # this is what actually makes the TRT EP register.
            os.environ["PATH"] = trtlib + os.pathsep + os.environ.get("PATH", "")
        if hasattr(ort, "preload_dlls"):
            ort.preload_dlls()
    except Exception:
        pass  # CPU/DML installs have nothing to preload


_load_gpu_dlls()

__all__ = ["OracleEval", "LeelaOracle"]

_ALL = 0xFFFF_FFFF_FFFF_FFFF  # full 8x8 plane bitmask


class OracleEval(NamedTuple):
    """Result of a single position evaluation (side-to-move perspective)."""

    wdl: Tuple[float, float, float]  # (win, draw, loss), sums to 1
    value: float                     # win - loss, in [-1, 1]
    policy: Dict[chess.Move, float]  # legal move -> prior prob, sums to 1
    mlh: float = 60.0                # predicted moves left in the game


# --------------------------------------------------------------------------
# Lc0 policy index (1858 entries).
#
# Generated programmatically; verified byte-identical to the canonical table
# in lczero-training/tf/policy_index.py (vendored at tools/policy_index.py)
# and to kMoveStrs in lc0 src/neural/encoder.cc.
#
# Layout: for every from-square (a1..h8), all queen-ray and knight
# destinations sorted by destination square index; then the 66 q/r/b
# underpromotion strings.  Knight promotions use the bare move string (no
# suffix).  Castling is indexed by the KING-takes-ROOK string (e.g. white O-O
# = "e1h1" = index 103); verified empirically against lc0 verbose move stats.
# --------------------------------------------------------------------------
def _gen_policy_index() -> List[str]:
    files = "abcdefgh"
    out: List[str] = []
    for fsq in range(64):
        fr, ff = divmod(fsq, 8)
        dests = set()
        for dr, df in ((0, 1), (0, -1), (1, 0), (-1, 0),
                       (1, 1), (1, -1), (-1, 1), (-1, -1)):
            r, f = fr + dr, ff + df
            while 0 <= r < 8 and 0 <= f < 8:
                dests.add(r * 8 + f)
                r += dr
                f += df
        for dr, df in ((1, 2), (2, 1), (2, -1), (1, -2),
                       (-1, -2), (-2, -1), (-2, 1), (-1, 2)):
            r, f = fr + dr, ff + df
            if 0 <= r < 8 and 0 <= f < 8:
                dests.add(r * 8 + f)
        frm = files[ff] + str(fr + 1)
        for t in sorted(dests):
            tr, tf = divmod(t, 8)
            out.append(frm + files[tf] + str(tr + 1))
    for ff in range(8):
        for tf in (ff - 1, ff, ff + 1):
            if 0 <= tf < 8:
                for p in "qrb":
                    out.append(files[ff] + "7" + files[tf] + "8" + p)
    assert len(out) == 1858
    return out


POLICY_INDEX: List[str] = _gen_policy_index()

_PROMO_CHAR = {chess.QUEEN: "q", chess.ROOK: "r", chess.BISHOP: "b"}


def _build_move_lut() -> Dict[Tuple[int, int, Optional[int]], int]:
    """(from_sq, to_sq, promo piece type or None) -> policy index.

    Squares are in the white-to-move (unflipped) frame.  Knight promotions
    map through the bare from-to entry, so their key uses promo=None.
    """
    lut: Dict[Tuple[int, int, Optional[int]], int] = {}
    rev = {v: k for k, v in _PROMO_CHAR.items()}
    for i, s in enumerate(POLICY_INDEX):
        frm = chess.parse_square(s[0:2])
        to = chess.parse_square(s[2:4])
        promo = rev[s[4]] if len(s) == 5 else None
        lut[(frm, to, promo)] = i
    return lut


_MOVE_LUT = _build_move_lut()


def _is_startpos(b: chess.Board) -> bool:
    return (b.board_fen() == chess.STARTING_BOARD_FEN
            and b.turn == chess.WHITE
            and b.castling_rights == chess.BB_CORNERS
            and b.ep_square is None)


def _default_nets_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "nets"


def _discover_onnx(nets_dir: Optional[Path] = None) -> str:
    nets_dir = nets_dir or _default_nets_dir()
    cands = sorted(nets_dir.glob("*.onnx"), key=lambda p: p.stat().st_mtime,
                   reverse=True)
    if not cands:
        raise FileNotFoundError(
            f"No .onnx network found in {nets_dir}. Convert one with "
            "tools/lc0/lc0.exe leela2onnx --input=<net.pb.gz> "
            "--output=nets/<name>.onnx --onnx-data-type=f16")
    preferred = [c for c in cands
                 if not any(t in c.name.lower() for t in ("fallback", "test"))]
    return str((preferred or cands)[0])


class LeelaOracle:
    """Batched GPU evaluator for Lc0 ONNX networks (DirectML).

    Parameters
    ----------
    onnx_path:
        Path to a network exported by ``lc0 leela2onnx``.  ``None`` picks the
        newest ``.onnx`` in ``<repo>/nets/`` (files named ``*fallback*`` or
        ``*test*`` are only used if nothing else exists).
    batch_max:
        Largest batch sent to the GPU in one call; longer board lists are
        evaluated in chunks of this size.
    providers:
        Override onnxruntime providers.  Default: DmlExecutionProvider with
        CPUExecutionProvider fallback.
    pad_batches:
        Pad batches to power-of-two bucket sizes to bound the number of
        DirectML graph compilations (recommended; see module docstring).
    """

    def __init__(self, onnx_path: Optional[str] = None, batch_max: int = 256,
                 providers: Optional[Sequence[str]] = None,
                 pad_batches: bool = True):
        if batch_max < 1:
            raise ValueError("batch_max must be >= 1")
        self.batch_max = int(batch_max)
        self.pad_batches = bool(pad_batches)
        # #90: when the value head is active, default to the embedding-exposing
        # backbone (it carries the /value/reshape features the head consumes).
        if onnx_path is None and os.environ.get("STILLWATER_VHEAD", "") not in ("", "0"):
            _h = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            _emb = os.path.join(_h, "nets", "BT4-embed.onnx")
            if os.path.exists(_emb):
                onnx_path = _emb
        self.onnx_path = onnx_path if onnx_path is not None else _discover_onnx()
        if providers is None:
            providers = self._default_providers()
        so = ort.SessionOptions()
        so.log_severity_level = 3  # silence "nodes assigned to CPU" warning
        self._sess = ort.InferenceSession(str(self.onnx_path), sess_options=so,
                                          providers=list(providers))
        active = self._sess.get_providers()
        os.write(2, f"[oracle] execution provider: {active[0]}\n"
                    .encode())
        inp = self._sess.get_inputs()[0]
        self._in_name = inp.name
        self._in_dtype = np.float16 if "float16" in inp.type else np.float32
        if list(inp.shape[1:]) != [112, 8, 8]:
            raise ValueError(f"Unexpected input shape {inp.shape}; expected "
                             "[batch, 112, 8, 8] (lc0 classical input)")
        out_policy = out_wdl = out_mlh = None
        for o in self._sess.get_outputs():
            if o.shape and o.shape[-1] == 1858:
                out_policy = o.name
            elif o.shape and o.shape[-1] == 3:
                out_wdl = o.name
            elif o.shape and o.shape[-1] == 1:
                out_mlh = o.name  # moves-left head: the conversion compass
        if out_policy is None or out_wdl is None:
            raise ValueError(
                f"Model {self.onnx_path} lacks a 1858-wide policy or 3-wide "
                "WDL output; convert with lc0 leela2onnx (WDL nets only)")
        self._has_mlh = out_mlh is not None
        self._fetch = [out_policy, out_wdl] + ([out_mlh] if out_mlh else [])
        # Tier-2: SF-distilled nonlinear value recalibration (gated, default off).
        # corrected_value = raw_v + interp(raw_v, lut); applied in infer_planes by
        # redistributing W/L around fixed draw mass. Env-gated for per-engine A/B.
        self._recal = None
        if os.environ.get("STILLWATER_RECAL") == "1":
            try:
                _here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                _z = np.load(os.path.join(_here, "recal_lut.npz"))
                self._recal = (_z["grid"].astype(np.float32),
                               _z["adj"].astype(np.float32))
                os.write(2, b"[oracle] value recalibration ENABLED\n")
            except Exception as _e:
                os.write(2, f"[oracle] recal load failed: {_e}\n".encode())
                self._recal = None
        # #90: max-backup-native value head (gated STILLWATER_VHEAD=<npz>|1). A
        # small MLP on the value features (/value/reshape) replaces the value
        # (W-L) with one re-ranked toward the search's settled ordering; the draw
        # mass D is kept native, so only the value/ordering changes -- the
        # co-tuned constants are not detuned by a magnitude rescale. Requires a
        # model exposing those features (nets/BT4-embed.onnx). Off => byte-identical.
        self._vhead = None
        self._feat_idx = None
        _vh = os.environ.get("STILLWATER_VHEAD", "")
        if _vh and _vh != "0":
            try:
                _here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                _path = _vh if _vh.lower().endswith(".npz") else os.path.join(
                    _here, "nets", "value_head_v1.npz")
                _z = np.load(_path)
                self._vhead = (_z["l1_w"].astype(np.float32), _z["l1_b"].astype(np.float32),
                               _z["l2_w"].astype(np.float32), _z["l2_b"].astype(np.float32))
                _w = int(_z["d_in"])
                _feat = next((o.name for o in self._sess.get_outputs()
                              if o.shape and o.shape[-1] == _w), None)
                if _feat is None:
                    raise ValueError(f"model lacks the {_w}-wide value-feature output; "
                                     "use nets/BT4-embed.onnx")
                self._feat_idx = len(self._fetch)
                self._fetch = self._fetch + [_feat]
                os.write(2, f"[oracle] value-head ACTIVE ({_path})\n".encode())
            except Exception as _e:
                os.write(2, f"[oracle] value-head load failed: {_e}\n".encode())
                self._vhead = None
                self._feat_idx = None

    def _default_providers(self):
        """Prioritized provider list, filtered to what's installed.

        TensorRT > CUDA > DirectML > CPU. The same code runs under either an
        onnxruntime-gpu install (TRT/CUDA available) or onnxruntime-directml
        (only DML available) — so a backend rollback needs no code change.
        TensorRT caches its built engine to disk: the lichess bridge spawns a
        fresh engine per game, and without the cache every spawn would rebuild
        BT4's engine (minutes). fp16 is forced on the GPU EPs (the net is fp16).
        """
        avail = set(ort.get_available_providers())
        out = []
        # TensorRT EP is the highest-ceiling path (lc0-class throughput) but
        # the pip TRT libs don't register cleanly with ORT 1.26 on Windows
        # (RegisterTensorRTPluginsAsCustomOps fails -> silent CUDA fallback).
        # Gated OFF by default so the bot doesn't pay a failed-registration
        # penalty every spawn; STILLWATER_TRT=1 re-enables for experiments
        # once the TRT/ORT version pairing is sorted.
        if (os.environ.get("STILLWATER_TRT") == "1"
                and "TensorrtExecutionProvider" in avail):
            cache = os.path.join(os.path.dirname(str(self.onnx_path)),
                                 "trt_cache")
            os.makedirs(cache, exist_ok=True)
            out.append(("TensorrtExecutionProvider", {
                "trt_fp16_enable": True,
                "trt_engine_cache_enable": True,
                "trt_engine_cache_path": cache,
                "trt_timing_cache_enable": True,
            }))
        if "CUDAExecutionProvider" in avail:
            if os.environ.get("STILLWATER_CUDA_FAST") == "1":
                # FAST path: default CUDA EP options ~2x the throughput of the
                # memory-bounded config below (2316 vs 1078 evals/s on the 5070),
                # but the default arena leaks ~1GB/100k inferences -> saturates a
                # 12GB card mid-match. ONLY use with cutechess restart=on (fresh
                # process per game resets the leak). For fast gauntlets, NOT the bot.
                out.append("CUDAExecutionProvider")
            else:
                # arena_extend_strategy=kSameAsRequested + bounded workspace:
                # ORT 1.26's CUDA EP grew GPU memory ~1GB/100k inferences with the
                # default kNextPowerOfTwo arena (saturated the 12GB card within a
                # few games of a match -> stalls + cross-game decay). Allocate
                # exactly what's requested and don't let cuDNN grab max workspace.
                out.append(("CUDAExecutionProvider", {
                    "cudnn_conv_algo_search": "HEURISTIC",
                    "arena_extend_strategy": "kSameAsRequested",
                    "cudnn_conv_use_max_workspace": "0",
                    "do_copy_in_default_stream": "1",
                }))
        if "DmlExecutionProvider" in avail:
            out.append("DmlExecutionProvider")
        out.append("CPUExecutionProvider")
        return out

    # ------------------------------------------------------------------ API

    def evaluate(self, boards: List[chess.Board]) -> List[OracleEval]:
        """Evaluate a list of boards; returns one OracleEval per board."""
        results: List[OracleEval] = []
        for i in range(0, len(boards), self.batch_max):
            chunk = boards[i:i + self.batch_max]
            policy, wdl, mlh = self._infer(self._encode_batch(chunk))
            for k, board in enumerate(chunk):
                results.append(self._decode(
                    board, policy[k], wdl[k],
                    mlh[k] if mlh is not None else None))
        return results

    def evaluate_one(self, board: chess.Board) -> OracleEval:
        return self.evaluate([board])[0]

    def infer_planes(self, planes: np.ndarray, n: int):
        """Run the net on pre-encoded [n, 112*64] float32 planes (the Rust
        core encodes; this is the GPU-only slice of evaluate). Returns
        (policy [n,1858] f32, wdl [n,3] f32, mlh [n] f32)."""
        out_p = []
        out_w = []
        out_m = []
        x_all = planes.reshape(n, 112, 8, 8).astype(self._in_dtype)
        for i in range(0, n, self.batch_max):
            chunk = x_all[i:i + self.batch_max]
            policy, wdl, mlh = self._infer(chunk)
            out_p.append(policy)
            out_w.append(wdl)
            out_m.append(mlh.reshape(len(chunk)) if mlh is not None
                         else np.full(len(chunk), 60.0, dtype=np.float32))
        wdl_all = np.concatenate(out_w).astype(np.float32)
        # Same guard as _decode's looks_prob: leela2onnx nets emit in-graph
        # softmax, but a net exporting raw logits must not silently corrupt
        # every value downstream — softmax any row that cannot be a
        # probability vector.
        sums = wdl_all.sum(axis=1)
        bad = (wdl_all.min(axis=1) < -1e-3) | (sums < 0.5) | (sums > 1.5)
        if bad.any():
            rows = wdl_all[bad]
            e = np.exp(rows - rows.max(axis=1, keepdims=True))
            wdl_all[bad] = e / e.sum(axis=1, keepdims=True)
        if self._recal is not None:
            grid, adj_lut = self._recal
            rv = wdl_all[:, 0] - wdl_all[:, 2]
            a = np.interp(rv, grid, adj_lut).astype(np.float32)
            d = wdl_all[:, 1]
            span = np.maximum(1.0 - d, 1e-6).astype(np.float32)
            corr = np.clip(rv + a, -span, span)
            wdl_all[:, 0] = (span + corr) / 2.0
            wdl_all[:, 2] = (span - corr) / 2.0
        return (np.ascontiguousarray(np.concatenate(out_p), dtype=np.float32),
                np.ascontiguousarray(wdl_all, dtype=np.float32),
                np.ascontiguousarray(np.maximum(
                    0.0, np.concatenate(out_m)), dtype=np.float32))

    def warmup(self) -> None:
        """Pre-compile the DML graph for every batch bucket size."""
        sizes = {1}
        b = 1
        while b < self.batch_max:
            b = min(b * 2, self.batch_max)
            sizes.add(b)
        for n in sorted(sizes):
            x = np.zeros((n, 112, 8, 8), dtype=self._in_dtype)
            self._sess.run(self._fetch, {self._in_name: x})

    @property
    def providers(self) -> List[str]:
        """Providers actually in use (first one executes the bulk)."""
        return self._sess.get_providers()

    # ------------------------------------------------------------- internals

    def _infer(self, x: np.ndarray):
        n = x.shape[0]
        if self.pad_batches:
            bucket = 1
            while bucket < n:
                bucket *= 2
            bucket = min(max(bucket, n), max(self.batch_max, n))
            if bucket > n:
                pad = np.zeros((bucket - n,) + x.shape[1:], dtype=x.dtype)
                x = np.concatenate([x, pad], axis=0)
        outs = self._sess.run(self._fetch, {self._in_name: x})
        policy = np.asarray(outs[0], dtype=np.float32)[:n]
        wdl = np.asarray(outs[1], dtype=np.float32)[:n]
        mlh = (np.asarray(outs[2], dtype=np.float32)[:n]
               if self._has_mlh else None)
        if self._vhead is not None:
            feats = np.asarray(outs[self._feat_idx], dtype=np.float32)[:n]
            wdl = self._apply_vhead(feats, wdl)
        return policy, wdl, mlh

    def _apply_vhead(self, feats: np.ndarray, wdl: np.ndarray) -> np.ndarray:
        """#90: replace the value (W-L) with the trained head's value, KEEPING the
        native draw mass D. feats = /value/reshape; wdl = BT4's WDL. Only the
        value/ordering changes; D is untouched."""
        w = wdl.astype(np.float32, copy=True)
        s = w.sum(axis=1)
        bad = (w.min(axis=1) < -1e-3) | (s < 0.5) | (s > 1.5)
        if bad.any():                       # guard nets that emit raw logits
            e = np.exp(w[bad] - w[bad].max(axis=1, keepdims=True))
            w[bad] = e / e.sum(axis=1, keepdims=True)
        l1w, l1b, l2w, l2b = self._vhead
        h = feats @ l1w.T + l1b
        h = h * np.tanh(np.logaddexp(0.0, h))            # mish
        v = np.tanh(h @ l2w.T + l2b).reshape(-1)         # new value in [-1,1]
        d = w[:, 1]
        span = np.maximum(1.0 - d, 1e-6)
        corr = np.clip(v, -span, span)
        w[:, 0] = (span + corr) / 2.0
        w[:, 2] = (span - corr) / 2.0
        return w

    def _encode_batch(self, boards: Sequence[chess.Board]) -> np.ndarray:
        """Encode boards as lc0 INPUT_CLASSICAL_112_PLANE, shape [N,112,8,8].

        Plane layout (after the final side-to-move flip):
          0..103   8 history steps x 13 planes, newest first.  Per step:
                   our P,N,B,R,Q,K, their P,N,B,R,Q,K, repetition (all-ones
                   if this position occurred before within the 50-move
                   window).  "Our" = current side to move, in all steps.
          104..107 we can O-O-O / we can O-O / they can O-O-O / they can O-O
          108      all ones if black is to move
          109      rule-50 half-move counter (raw count, constant plane)
          110      all zeros
          111      all ones
        When black is to move every bitboard is flipped vertically (ranks
        mirrored) and colors swapped, so the side to move always plays "up".
        Missing history: repeat the oldest known position (with lc0's
        en-passant un-move fix-up), or all-zeros if the game starts from the
        standard initial position (lc0 FillEmptyHistory::FEN_ONLY).
        """
        n_boards = len(boards)
        masks = np.zeros((n_boards, 112), dtype=np.uint64)
        rule50 = np.zeros(n_boards, dtype=np.float32)

        for n, board in enumerate(boards):
            stm = board.turn
            b = board.copy()

            frames: List[Tuple[int, ...]] = []  # 12 piece bitboards per step
            keys: List = []                     # transposition keys, newest first
            clocks: List[int] = []              # halfmove clocks, newest first
            root_exhausted = False
            while True:
                keys.append(b._transposition_key())
                clocks.append(b.halfmove_clock)
                if len(frames) < 8:
                    us = b.occupied_co[stm]
                    them = b.occupied_co[not stm]
                    frames.append((
                        b.pawns & us, b.knights & us, b.bishops & us,
                        b.rooks & us, b.queens & us, b.kings & us,
                        b.pawns & them, b.knights & them, b.bishops & them,
                        b.rooks & them, b.queens & them, b.kings & them))
                if not b.move_stack:
                    root_exhausted = True
                    break
                if len(frames) >= 8 and b.halfmove_clock == 0:
                    break  # irreversible boundary: older positions can't repeat
                b.pop()

            # Repetition flags: position i (plies back) repeats if the same
            # transposition key occurs earlier in the game within its 50-move
            # window (window length = its halfmove clock).
            n_frames = len(frames)
            n_keys = len(keys)
            rep = [False] * n_frames
            for i in range(n_frames):
                ki = keys[i]
                limit = min(n_keys - 1, i + clocks[i])
                for j in range(i + 1, limit + 1):  # key includes side to move
                    if keys[j] == ki:
                        rep[i] = True
                        break

            row = masks[n]
            for i in range(n_frames):
                base = 13 * i
                f = frames[i]
                for p in range(12):
                    row[base + p] = f[p]
                if rep[i]:
                    row[base + 12] = _ALL

            # Fill missing history (ran out of move_stack before 8 steps).
            if n_frames < 8 and root_exhausted and not _is_startpos(b):
                fill = list(frames[-1])
                if b.ep_square is not None:
                    # lc0 quirk: un-make the implied double pawn push in the
                    # synthesized pre-history frames.
                    ep = b.ep_square
                    if b.turn == chess.WHITE:   # black just double-pushed
                        mover, cur, orig = chess.BLACK, ep - 8, ep + 8
                    else:                       # white just double-pushed
                        mover, cur, orig = chess.WHITE, ep + 8, ep - 8
                    pi = 0 if mover == stm else 6
                    fill[pi] = (fill[pi] & ~(1 << cur)) | (1 << orig)
                fill_rep = _ALL if rep[n_frames - 1] else 0
                for i in range(n_frames, 8):
                    base = 13 * i
                    for p in range(12):
                        row[base + p] = fill[p]
                    row[base + 12] = fill_rep

            if board.has_queenside_castling_rights(stm):
                row[104] = _ALL
            if board.has_kingside_castling_rights(stm):
                row[105] = _ALL
            if board.has_queenside_castling_rights(not stm):
                row[106] = _ALL
            if board.has_kingside_castling_rights(not stm):
                row[107] = _ALL
            if stm == chess.BLACK:
                row[108] = _ALL
                # Mirror ranks of all square-encoded planes (bswap64).
                masks[n, :104] = masks[n, :104].byteswap()
            rule50[n] = board.halfmove_clock
            row[111] = _ALL

        # uint64 planes -> [N,112,8,8] floats.  Little-endian byte k of each
        # mask is rank k (a-file = bit 0), so a plain unpack yields
        # [rank][file] with rank 1 at row 0, as lc0 expects.
        byts = masks.view(np.uint8).reshape(n_boards, 112, 8)
        bits = np.unpackbits(byts, axis=2, bitorder="little")
        x = bits.reshape(n_boards, 112, 8, 8).astype(self._in_dtype)
        x[:, 109] = rule50.astype(self._in_dtype)[:, None, None]
        return x

    def _decode(self, board: chess.Board, policy_logits: np.ndarray,
                wdl_raw: np.ndarray,
                mlh_raw: Optional[np.ndarray] = None) -> OracleEval:
        mlh = (max(0.0, float(mlh_raw.reshape(-1)[0]))
               if mlh_raw is not None else 60.0)
        w, d, l = (float(v) for v in wdl_raw)
        s = w + d + l
        # lc0 leela2onnx emits an in-graph softmax, so (w,d,l) are already
        # probabilities (sum ~1 up to fp16 rounding) and only need
        # renormalizing.  Only treat them as raw logits (and softmax) if they
        # cannot possibly be probabilities.
        looks_prob = (min(w, d, l) >= -1e-3 and max(w, d, l) <= 1.001
                      and 0.5 <= s <= 1.5)
        if not looks_prob:
            e = np.exp(wdl_raw - wdl_raw.max())
            e /= e.sum()
            w, d, l = (float(v) for v in e)
        elif s > 0:
            w, d, l = w / s, d / s, l / s

        moves = list(board.legal_moves)
        if not moves:
            return OracleEval(wdl=(w, d, l), value=w - l, policy={}, mlh=mlh)

        flip = board.turn == chess.BLACK
        idxs = np.empty(len(moves), dtype=np.int64)
        for k, m in enumerate(moves):
            frm, to = m.from_square, m.to_square
            if board.is_castling(m) and not board.chess960:
                # lc0 indexes castling as king-takes-rook (e.g. e1h1).
                to = chess.square(
                    7 if chess.square_file(to) > chess.square_file(frm) else 0,
                    chess.square_rank(frm))
            if flip:
                frm ^= 56
                to ^= 56
            promo = m.promotion
            if promo == chess.KNIGHT:  # knight promo = bare move string
                promo = None
            idxs[k] = _MOVE_LUT[(frm, to, promo)]

        sel = policy_logits[idxs]
        sel = sel - sel.max()
        e = np.exp(sel)
        e /= e.sum()
        return OracleEval(wdl=(w, d, l), value=w - l,
                          policy=dict(zip(moves, e.tolist())), mlh=mlh)
