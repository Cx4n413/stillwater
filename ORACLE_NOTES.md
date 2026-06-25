# STILLWATER GPU Oracle — Notes

`stillwater/oracle.py` evaluates batches of `chess.Board` on the GPU
(RTX 5070, DirectML) using a pretrained Lc0 network exported to ONNX.

```python
from stillwater.oracle import LeelaOracle, OracleEval
oracle = LeelaOracle()            # newest .onnx in <repo>/nets/ -> BT4
oracle.warmup()                   # optional: pre-compile DML graphs
evals = oracle.evaluate(boards)   # list[chess.Board] -> list[OracleEval]
```

`OracleEval` is a NamedTuple: `wdl=(win,draw,loss)` (side-to-move
perspective, sums to 1), `value = win - loss`, `policy = {chess.Move:
prior}` over legal moves only (sums to 1; empty dict for mate/stalemate).

## Networks (in `nets/`)

| file | net | class |
|---|---|---|
| `BT4-1024x15x32h-policytune.onnx` (default) | BT4-1024x15x32h-swa-6147500-policytune-332 | Strongest released Lc0 net family (big-transformer, 15 encoders x 1024, 32 heads). Top-tier / superhuman; far above the 3000-Elo requirement. |
| `t3-512x15x16h-distill.onnx` | t3-512x15x16h-distill-swa-2767500 | Strong distilled transformer; ~1.7x faster than BT4, somewhat weaker. |
| `fallback.onnx` | t1-256x10-distilled-swa-2432500 | Small distilled transformer; ~2.7x faster than BT4. Still a very strong eval (it matched lc0 in all cross-checks); use if throughput matters more than strength. |

Source: https://storage.lczero.org/files/networks-contrib/ (original
`.pb.gz` files kept alongside the ONNX exports). Converter: lc0 v0.32.1
(`tools/lc0/`, windows-onnx-dml build from GitHub LeelaChessZero/lc0
releases — used only for `leela2onnx` and as a cross-check engine).

Conversion command (same for all, fp16):

```
tools\lc0\lc0.exe leela2onnx --input=nets\<net>.pb.gz --output=nets\<name>.onnx --onnx-data-type=f16
```

Head selection used the converter defaults: `--value-head=winner`,
`--policy-head=vanilla`. BT4/t3 are multihead nets; `q`/`st` value heads and
`optimistic`/`soft` policy heads are available via those flags if the engine
ever wants to experiment.

## ONNX interface

* Input: `/input/planes`, `[batch, 112, 8, 8]`, `tensor(float16)`
  (dynamic batch). Lc0 `INPUT_CLASSICAL_112_PLANE` encoding (all three nets
  use this format — verified with `lc0 describenet`).
* Outputs: `/output/policy` `[batch, 1858]` raw logits;
  `/output/wdl` `[batch, 3]` **already softmaxed in-graph**;
  `/output/mlh` `[batch, 1]` moves-left (unused by the oracle).

The oracle discovers outputs by width (1858 = policy, 3 = wdl), so renamed
exports also work. WDL rows are renormalized (fp16 rows can sum to ~0.9988);
they are only treated as logits if they cannot be probabilities.

## Encoding details (verified against lc0 v0.32.1 encoder.cc + empirically)

* 8 history steps x 13 planes (our P,N,B,R,Q,K, their P,N,B,R,Q,K,
  repetition), newest first; then aux planes 104..111: we-O-O-O, we-O-O,
  they-O-O-O, they-O-O, black-to-move, rule-50 count (raw, constant plane),
  zeros, ones.
* Black to move: every bitboard is flipped vertically (bswap64) and colors
  swapped; "our" pieces are always the side to move, in all history steps.
* History comes from `board.move_stack` (walked via `pop()`); pass boards
  that carry their game history for full strength. Missing history follows
  lc0 `FillEmptyHistory::FEN_ONLY`: zeros if the root is the standard
  startpos, otherwise the oldest position is repeated (with lc0's
  en-passant "un-move" fix-up applied to the synthesized frames).
* Repetition planes: a step is flagged if its transposition key occurred
  earlier in the game within its 50-move window (the walk continues past 8
  plies until the halfmove clock hits 0, so flags are exact; null moves in
  the stack are handled).
* Policy index: the canonical 1858-entry table is generated
  programmatically in `oracle.py` and is byte-identical to
  `lczero-training/tf/policy_index.py` (vendored at `tools/policy_index.py`).
  Conventions (all empirically confirmed against lc0 verbose move stats,
  which print the NN index per move):
  * Castling is indexed as **king-takes-rook**: white O-O = `e1h1` = index
    103 (lc0 internal convention), not `e1g1`. The oracle translates
    python-chess castling moves accordingly.
  * Knight promotions use the **bare** move string (no suffix); q/r/b
    promotions use the suffixed entries.
  * When black is to move, move from/to squares are rank-mirrored before
    lookup.
  * Softmax is taken over legal-move logits only.

## Cross-check vs lc0 itself (`tests_oracle/crosscheck_lc0.py`)

lc0 v0.32.1 (onnx-cpu backend, fp32, `PolicyTemperature=1.0`,
`ContemptMode=disable`) vs the oracle (DirectML fp16) on the same t1 net,
comparing every legal move's prior and the root value over 9 positions
(startpos, black-to-move, 6-ply history, bare-FEN castling, en passant from
FEN, twofold repetition, promotion race, KQR-vs-K):

```
worst |dP| = 0.0032, worst |dV| = 0.0009   -> CROSSCHECK PASSED
```

Note: lc0's *bundled* onnxruntime.dll crashes with DML on this machine
("DmlGraphFusionHelper... parameter is incorrect"), so the cross-check uses
its onnx-cpu backend. Our python onnxruntime-directml 1.23.0 works fine.

## Sanity tests (`tests_oracle/test_oracle.py`) — 9/9 pass on BT4

* startpos: top-4 = d4, Nf3, c4, g3; e4/d4/Nf3/c4 mass 0.51; wdl
  (0.19, 0.64, 0.17), value +0.025.
* mirror test (4 asymmetric positions): |dV| <= 0.0053, top moves map to
  their mirrors.
* hanging queen (Nf3xh4 available): P(Nxh4) = 0.97, top move; value +0.997.
* KQR vs K: value +1.0000.
* black after 1.e4: top replies e5/c6/c5/Nc6, sane mass 0.955.
* castling present in policy (white O-O 13%, black O-O likewise).
* mate/stalemate boards: empty policy, no crash.
* batch-vs-single consistency: max |dV| 0.0008.
* twofold repetition raises the draw probability vs startpos.

## Benchmark (end-to-end `evaluate()`, includes encoding; RTX 5070 12GB,
driver 591.86, onnxruntime-directml 1.23.0, fp16)

| net | b=32 | b=64 | b=128 | b=256 | b=512 |
|---|---|---|---|---|---|
| BT4 (default) | 1378 | 1618 | **1665** | 1623 | 1419 |
| t3-512x15x16h | 1957 | 2453 | 2814 | 2744 | 2691 |
| t1-256x10 (fallback) | 2863 | 3604 | 3836 | 4439 | 4155 |

evals/s; sweet spot batch 128-256. Encoding costs ~0.10-0.12 ms/board
(single CPU thread, well under the 0.5 ms budget; ~16-20% of BT4 wall time).
BT4 exceeds the 1500 evals/s target, so the fallback is optional — pass
`LeelaOracle(onnx_path="nets/fallback.onnx")` to trade strength for ~2.7x
throughput.

## Quirks / things the engine author must know

1. **DirectML JIT-compiles per input shape.** The oracle pads batches to
   power-of-two buckets (capped at `batch_max`) so at most ~log2(batch_max)
   shapes are ever compiled. The first call at each bucket takes seconds for
   BT4; call `oracle.warmup()` once at startup to hide this.
2. A few shape-handling nodes run on the CPU EP (onnxruntime assigns them
   there by design); `session.get_providers()` reports
   `['DmlExecutionProvider', 'CPUExecutionProvider']`. Outputs match the
   pure-CPU fp32 run within ~1e-3, so nothing meaningful falls back.
3. Auto-discovery picks the newest `.onnx` in `nets/`, skipping files named
   `*fallback*`/`*test*` unless nothing else exists. Dropping a new export
   into `nets/` changes the default — pass an explicit path if that matters.
4. fp16 noise: identical positions evaluated under different batch sizes can
   differ by ~1e-3 in value/priors. Don't expect bit-exact reproducibility
   across batch shapes.
5. Terminal positions (mate/stalemate) return `policy={}` and a *network*
   wdl/value that is not meaningful — the search must score terminals
   itself.
6. `evaluate()` never mutates the boards (it works on copies), and boards
   may freely contain null moves in their stacks.
7. The oracle is not thread-safe per instance (onnxruntime sessions are, but
   keep one instance per search thread or serialize calls for simplicity).
