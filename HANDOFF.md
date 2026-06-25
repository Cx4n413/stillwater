# STILLWATER — Engineering Handoff (for an AI successor)

This document is written for another AI taking over the STILLWATER chess engine. It assumes a
strong reader: no concept is dumbed down. It covers (1) the model in depth, (2) the file map,
(3) the **complete** history of every trial/failure/step, (4) an exhaustive snapshot of the
current state, (5) the levers that remain, and (6) how to work on it without breaking things.

Two companion artifacts you must read:
- `README.md` — the original v0.1 architecture overview (still accurate on the paradigm).
- `ORACLE_NOTES.md` — the Lc0 ONNX oracle: encoding, policy index, cross-check methodology.
- The maintainer's persistent memory log: `C:\Users\nonna\.claude\projects\c--Users-nonna-Downloads\memory\stillwater-chess-engine.md`.
  This is the **chronological ground truth**; this handoff is the structured synthesis of it.

**The single most important operating principle**, learned the hard way and repeatedly:
> Only a **timed gauntlet** (or careful manual game analysis) tells the truth about strength.
> Every cheap proxy (WAC/STS solve-rate, move-agreement vs SF, recovery-on-a-biased-set,
> fixed-node parity vs Lc0, same-evaluator self-play) has at some point **lied** — said a change
> was good when it was neutral or bad in real play. Never ship on a proxy. Never trust a
> 10-game sample. Be honest; never explain away a bad result.

---

## 0. TL;DR of where it is

- STILLWATER is a **no-tree, position-keyed belief-lattice** chess engine. The "search tree" is
  replaced by a persistent lattice of positions (transpositions merge by construction) relaxed by
  prioritized **distributional minimax-MAX backups**; frontier leaves are chosen by a PUCT-style
  broker and evaluated by a **borrowed Lc0 transformer net (BT4)** on GPU.
- Measured strength: **~3432 CCRL 40/15 (1-CPU equivalent), 95% CI ~3352–3466.** It is **eval-quality
  bound**: the BT4 net is the ceiling. Our own repeated A/Bs show **2–3× more evals/s ≈ ~0 Elo** and
  every *search-reorganizer* change is neutral-to-negative in play (the "5-for-5 law", §3).
- Two kinds of changes have EVER helped: **constant tuning** (the +35-Elo STS vector) and **bug
  fixes** (time-management, claim-draw, value-conversion). Search-architecture reorganizers have not.
- It is **deployed live** on Lichess as `STILLWATER-bot` via `lichess-bot`, on the **DirectML**
  backend (a deliberate deploy choice, not a CUDA failure — §4.4). It auto-restarts on boot and
  self-heals via a watchdog.
- The only big remaining lever is a **better evaluator** (fine-tune/replace BT4) — a multi-day
  cloud-GPU project, since strength is eval-bound, not search-bound.

---

## 1. THE MODEL (architecture in depth)

### 1.1 The thesis: a belief lattice, not a game tree

Classical engines (AB or MCTS) build a **tree** rooted at the current position; transpositions are
either re-searched or patched with a hash table bolted onto a fundamentally tree-shaped search.
STILLWATER inverts this: the primary data structure is a **position-keyed lattice** (a DAG with
parent back-pointers). Each distinct position is one node, regardless of how many move-orders reach
it; transpositions **merge by construction**. After the opponent replies, the new root is already a
node in the lattice with its subtree intact — **re-rooting is a no-op** (no tree reuse heuristics).

Each node holds a **belief**: a (W, D, L) outcome distribution from the side-to-move's perspective.
`value = W − L`; `variance = (W + L) − (W − L)²`. Exact results (checkmate, stalemate, Syzygy,
proven mate) are the same datatype with **variance 0**.

### 1.2 Settling = search

The lattice is relaxed toward the fixed point of a **discounted distributional negamax** by
**prioritized sweeping** (a dirty queue). When a leaf is evaluated, its parents are enqueued; backups
propagate refutations toward the root. A refutation at the frontier reaches the root in **one
settling pass** (no re-search). Two critical properties of the backup operator:

- **Operator = MAX (minimax), not mean.** This is load-bearing. lc0 uses visit-weighted MEAN backups
  (sound only because tree-visit shares concentrate the mean toward the max). In a transposition
  *lattice*, a mean **dilutes** forced lines at every settle pass — empirically `R_MEANBACK` cratered
  WAC 97→56. Robustness must come from **evidence-gated MAX** (LCB), never averaging. (§3, parity.)
- **Per-ply discount γ = 0.997** makes the operator a **contraction** ⇒ repetition cycles damp toward
  draws *by theorem*, and shorter mates rank above longer ones. γ = 1.0 is used **only on zeroing
  edges** (captures/pawn pushes), which is sound because cycles can't cross a zeroing move
  (the contraction stays intact) and it is tactically positive.

`eff_value(value, mlh)` folds the moves-left head into the value so the engine prefers faster wins /
slower losses; an `ML_THRESH` gate (tuned to 0.9) controls when MLH urgency fires (our MAX-backup
won-position values sit ~0.7, so the gate had to be retuned up from lc0's 0.8 — see §3).

### 1.3 The Broker (frontier selection)

Selection is **PUCT-adjacent**: `cpuct · prior · √N/(1+n)` plus an uncertainty bonus, with proven
subtrees priced at zero (don't re-explore solved nodes). This is the one piece that is **not** a pure
belief-lattice quantity — it is borrowed MCTS machinery. An attempt to replace it with a
belief-native **VOI** rule (Value-of-Information, §3) was a measured **regression**: lc0's policy
prior carries real tactical move-ordering information that a value-only selection rule cannot recover
(the eval-bound thesis applies to the *selection* side too).

The loop is **serial**: `select_batch → infer (GPU) → integrate → settle`. Selection costs
single-digit ms in Rust, so an async pipeline gave only ~+15% and was dropped; the compiled core is
the throughput lever.

### 1.4 The Oracle (the evaluator — the ceiling)

`stillwater/oracle.py` wraps an **Lc0 ONNX transformer** run on GPU. The default net is
**BT4-1024x15x32h-policytune** (`nets/BT4-...-policytune.onnx`) — Lc0's strongest released net
(15 encoder layers × 1024 wide, 32 heads). It outputs **WDL + value + a 1858-entry policy + MLH
(moves-left head)**. Encoding is Lc0's `INPUT_CLASSICAL_112_PLANE` (8 history steps × 13 planes +
castling/halfmove/aux), bit-for-bit verified against lc0 v0.32.1 (worst |ΔP|≈0.003, |ΔV|≈0.0009).
The Rust core has a byte-identical port (`encoder.rs`, `policy.rs`).

**This net is the binding constraint on strength.** It is *borrowed*, not trained by us. See §3
(value-recal dead end, fast-net dead end) and §5 (the evaluator lever).

### 1.5 Proofs (exactness inside a probabilistic engine)

Three sources inject **variance-0** nodes that propagate rootward and end deliberation when they
reach the root:
- **Terminal rules**: checkmate, stalemate, insufficient material, 50-move, threefold.
- **Syzygy tablebases** (`stillwater/tablebase.py`, `core-rs` shakmaty-syzygy): ≤5-man positions
  probed instead of spending a GPU eval; KBNvK becomes an instant PROVEN WIN.
- **Proof bursts** (`core-rs/src/prover.rs`): when a belief saturates (|value|>0.92) but isn't a
  theorem, a bounded **checking-mate search** (attacker plays checks only, defender all legal) tries
  to promote it to a theorem. Sound by construction (checks-only is incomplete but never wrong);
  ~0 measured cost; SHIPPED ON.

**The 50-move validity envelope** is essential and subtle: a win/loss proof is only valid if the
50-move clock can actually reach the mate. `proof_trusted_at(node, headroom)` *demotes* a proof to
the draw it really is when the clock can't fund it. The lattice interior stays clock-naive and
self-corrects at the frontier and at decision sites (`_best_move`, the Court). Position keys are
**salted with a 50-move-counter bucket and a repetition flag** so that legality-relevant state
splits the lattice entry (and so proofs/ledgers transfer verbatim).

There is a whole **claim-draw correctness regime**: a threefold/50-move position is *claimable*, not
automatically drawn — the mover chooses. These are modeled as rep-salted nodes with a `claim_floor`
(value floored at `max(0, play-on)` for the mover). A recurring historical bug class
("the Ra8 free-draw") is the engine walking into a claimable repetition while ahead and the opponent
claiming. **Path-conditional** draws (SW's own descent walked a cycle assuming the opponent
cooperates) get the `path_cond` flag and an optional `VERIFY_DRAW` re-validation gate (§4).

### 1.6 Belief-learning layers (all in-game, no retraining)

- **Palimpsest** (`palimpsest.py`, `core-rs`): per `(pawn-structure × material × side)` context, a
  conjugate-Normal posterior over a value *correction*, updated in closed form from settled-vs-raw
  disagreements at well-evidenced nodes, then applied (shrunk by uncertainty) to every future eval in
  the same context — re-pricing positions search never visited. v0 is scalar-per-context.
- **Opponent model / "Effigy"** (`opponent.py`): one scalar `rho ∈ [0,1]` = P(opponent plays best).
  Learned mid-game from cheap observations (the lattice already evaluated the positions the opponent
  moved from). Drives the **Mirror** (opponent move distribution, `v_them`) and a **trap band**
  (exploit a fallible opponent). Starts at `rho=1` (confident) so behavior is unchanged vs strong
  opponents until the opponent proves fallible. Gated by `RHO_GATE`.
- **Lens** (in `search.py` / `_best_move`): a "liveliness" bonus on the draw component of WDL,
  `rho`-gated (only vs fallible opponents) — keeps winning chances alive against weaker play. It was a
  *regression* when ungated (§3) → it is gated on `gate_open = rho < RHO_GATE`.

### 1.7 The Root Court (stopping + time, as inference)

`court.py` maintains a posterior over **which root move is truly best** (each candidate's value
modeled `Normal(settled_value, variance/(1+evidence) + TAU2)`, sampled jointly, 1500 samples), and
**moves the instant `P(argmax is truly best)` clears a clock-derived bar**. There are no move-time
heuristics anywhere else. Bars: `EARLY_STOP_P=0.93` before the soft budget, `LATE_STOP_P=0.55` after
(keep thinking only if genuinely torn), `EXTEND_FACTOR=1.6` ceiling, plus a **throughput guard**
(before 0.5·soft only ≥0.985 confidence may stop, so a fast engine converts speed into depth instead
of idle banking). Budgets: `soft = clock/horizon + 0.8·inc` with `horizon = max(24, 64 − moves)`,
`hard = soft·(1.5 if rich else 1.2)` capped at `clock/12` — the cap is the **no-flag guarantee**.

### 1.8 Persistence and harvesting

- **Proof Ledger** (`ledger.py`): theorems persist across games in `.npz`, keyed by the salted
  position key (so they transfer verbatim). Fingerprinted by the key-salting scheme — discarded if
  the scheme changes. Seeds the lattice at game start (cap 250k deepest proofs).
- **Distillery** (`distillery.py`): one record per `think()` root — raw net impression vs settled
  verdict + per-root-move values (policy targets) + calibrated variance → `harvest/*.jsonl`. Zero
  hot-path cost. This is the data substrate for any future corrector/retrain.

### 1.9 The Rust/Python division of labor

The deployed engine is **`engine_rs.py`** driving the compiled **`stillwater_core`** pyo3 extension
(`core-rs/`). Rust owns everything **per-node**: movegen (shakmaty), the lattice, settling,
selection, plane encoding, Syzygy probes, palimpsest arithmetic, the prover. Python owns everything
**per-move / per-batch**: the DirectML oracle session, the Root Court, clock budgets, the Effigy,
the trap-band + Lens at the decision site, the panic floor, pondering, the Distillery, the Ledger.
`engine.py` is the **pure-Python reference** engine (same `think()` protocol, much slower) — kept for
parity testing; NOT deployed. UCI option `RustCore=true` selects the Rust path (the deploy).

### 1.10 The "Refine" package (lc0-aligned search semantics, bit-gated)

`core-rs` implements a set of lc0-derived search tweaks behind a `refine: u32` **bitmask** (UCI
`Refine`, env `STILLWATER_REFINE_MASK`; mask 0 = legacy bit-identical). Bits include
`R_TEMP|R_CPUCT|R_FPU|R_MLH|R_LCB|R_GAMMA|R_UFLIGHT|R_TWOFOLD|R_NOFLOOR|R_MEANBACK|R_COARSER50|
R_REPFORCE|R_FINER50|R_VISITREAD` plus a Python-side `0x200 = R_ROBUSTPICK` (LCB-based root readout).
The **shipped** mask is **`0xBFF`** (the parity-campaign composition). Notable findings encoded here
(see §3): `R_UFLIGHT` (lc0's in-flight U-denominator) **under-diversifies** our serial 128-leaf
batches and is the single biggest WAC drag in isolation but the *concentration king* in composition;
`R_MEANBACK` is poison (mean backup in a lattice); `R_TWOFOLD` as lc0 ships it reintroduces the
claim-draw bug and had to be restricted to in-descent twofolds only; `R_COARSER50` (one r50 bucket
below clock 64) stops periodic lattice "amnesia" in long grinds.

### 1.11 The deployed tuned constants (the +35-Elo vector)

Set as env vars in `stillwater_uci.bat` (remove the `set` lines to revert):
`STILLWATER_LCB_K=0.0, FPU_RED=0.22, ML_THRESH=0.9, CPUCT_INIT=2.045, CPUCT_FACTOR=4.894,
C_VAR=0.2, PICK_K=1.1`. Key insight: the engine plays **stronger with LESS search-pessimism**
(`lcb_k 0.3→0`) — the **opposite** of the failed "honest-max" experiment. Validated +34.9 ± 23.2 Elo
(LOS 99.8%, 150-game self-play vs default constants).

### 1.12 The deployed root readout

`_best_move` (in `engine_rs.py`): value-first **robust pick** (`R_ROBUSTPICK`, 0x200) — among root
moves whose **LCB** is within an evidence-shrinking band of the best, play the highest-LCB move
(a thinly-evaluated inflated value can't win the most expensive decision). A **trap band**
(`TRAP_MARGIN`) lets the value pick override the LCB pick only vs fallible opponents. On top of this
sit two **shipped** fixes and several **gated-off** experimental readouts (§4).

---

## 2. REPOSITORY MAP

Directory tree (top level):
```
ExperimentalChessEngine/
├── stillwater/      Python per-move engine layer (the brain's "slow" half)
├── core-rs/         Rust pyo3 extension `stillwater_core` (the "fast" half)
├── docs/            architecture references
├── games/           match PGNs, opening books, EPD suites, per-game analysis scripts, logs
├── harvest/         Distillery training data (.jsonl) + archives
├── nets/            Lc0 ONNX nets (BT4 default, t3, t1) + syzygy/ tablebases + trt_cache/
├── tests/           substrate tests on the GPU-free mock oracle
├── tests_oracle/    oracle + encoder cross-checks vs lc0 v0.32.1
├── tools/           ~60+ diagnostic / measurement / training / gauntlet scripts
├── play.py, stillwater_uci.bat, stillwater_*.bat   entry points / launchers
└── README.md, ORACLE_NOTES.md, HANDOFF.md (this file)
```
Deploy lives **outside** the repo: `C:\Users\nonna\Downloads\lichess-bot\`.

### 2.1 `stillwater/` (Python engine)
| File | Role |
|---|---|
| `engine_rs.py` | **THE DEPLOYED ENGINE.** Drives `stillwater_core`; owns the per-move loop, Court, oracle, Effigy, Lens, panic floor, pondering, Distillery, Ledger, the `_best_move` readout (incl. the conversion fix), `_should_stop`. |
| `engine.py` | Pure-Python reference engine (same protocol, slow); parity baseline only. |
| `core` (pyo3) | imported as `stillwater_core` from `core-rs`. |
| `lattice.py` | Position-keyed belief store + parent back-pointers + `position_key` (r50 bucket + rep salt). |
| `search.py` | Settling engine (dirty-queue relaxation) + Broker (PUCT selection) + the constants (`EPS_BASE, GAMMA, RHO_GATE, TRAP_MARGIN, DRAWISH, LENS_*`, `eff_value`, `proof_trusted_at`). |
| `oracle.py` | Lc0 ONNX evaluator; provider selection (TRT>CUDA>DML>CPU, filtered to installed); 112-plane encoding; `STILLWATER_RECAL` hook. |
| `beliefs.py` | (W,D,L) belief algebra; perspective flip. |
| `court.py` | Root Court: Bayesian stopping + time budgets; `VERIFY_DRAW` gate; `MIN_SPEND` floor. |
| `palimpsest.py` | In-game per-context value-correction posterior. |
| `opponent.py` | Effigy (`rho`) + Mirror opponent model. |
| `tablebase.py` | Syzygy proof oracle (≤5-man), 50-move-honest. |
| `distillery.py` | Harvest think() verdicts → `harvest/*.jsonl`. |
| `ledger.py` | Cross-game theorem persistence (.npz), scheme-fingerprinted. |
| `uci.py` | UCI front-end (`python -m stillwater.uci`); all UCI options; on a `think()` exception it prints `info string error` and falls back to `legal[0]` — a **latent footgun** (§4.6). |
| `mock_oracle.py` | Deterministic weak oracle (material+mobility) for GPU-free substrate tests. |

### 2.2 `core-rs/src/` (Rust core)
| File | Role |
|---|---|
| `lib.rs` | pyo3 module; exports `Core` (+ methods: `set_position/set_search/set_features/set_tunables/select_batch/integrate/root_info/root_children/prove_burst/stats/...`) and `position_key_of`. |
| `engine.rs` | Faithful port of `lattice.py`+`search.py`: Node struct (key, wdl, value, variance, evals, moves, priors, child_keys, parents, proof/proof_dist, claim_floor, path_cond, turn, v_them, context, mlh, epistemic), the dirty-queue SettlingEngine, the Broker, the Refine bitmask logic, the DrawContempt `draw_value`, the proof envelopes. ~the bulk of the core. |
| `encoder.rs` | Lc0 112-plane encoding (byte-identical to `oracle.py`). |
| `policy.rs` | Lc0 1858-entry policy index (byte-identical to lczero-training). |
| `keys.rs` | Salted Zobrist position keys (`position_key`, `_c` coarse r50, `_cf` finer). |
| `prover.rs` | Bounded checking-mate proof bursts. |
| `Cargo.toml` | pyo3 0.23, numpy, shakmaty(+syzygy), rustc-hash; LTO/codegen-units=1/panic=abort. |

**Build:** `cd core-rs && maturin develop --release` (installs `stillwater_core` into the active
Python env). The deploy env is `C:\Users\nonna\miniconda3` (has `onnxruntime-directml 1.23.0`).

### 2.3 Entry points / launchers
- `play.py` — terminal play (`--mock`, `--movetime`, `--black`).
- `stillwater_uci.bat` — **THE DEPLOY LAUNCHER** (config.yml points to it): tuned constants +
  `STILLWATER_CONVERT=1` + `STILLWATER_VERIFY_DRAW=256`, then `python -u -m stillwater.uci`.
- `stillwater_conv_on.bat` — A/B treatment copy (convert on) used in the convert gauntlet.
- `stillwater_candidate.bat`, `stillwater_c0/c10.bat`, `stillwater_vison/visoff.bat` — historical A/B
  arms (TRT, contempt, visit-readout). Treat as experiment scaffolding.

### 2.4 `docs/`
- `lc0_search_reference.md` — agent-compiled diff of our broker/backup vs lc0 v0.32.1 internals
  (cpuct constants, FPU, policy-softmax-temp, MLH cap, mean backup, in-flight U-denominator,
  two-fold-draws, sticky-endgames). Basis of the Refine package.
- `architecture_extensions.md` — paper-ready writeup of the epistemic/aleatoric split, VOI selection,
  graph-advantage quantification (the gated structural additions).

### 2.5 `tools/` (grouped — do not expect all to be current)
- **Gauntlet/match runners:** `run_gauntlet.py` (the big SF-ladder + bridge harness), `run_match.ps1`,
  `run_*_ab.cmd` (feature A/Bs: `run_convert_ab.cmd`, `run_convert_vs_weak.cmd`, `run_contempt_ab2.cmd`,
  `run_refine_validation.cmd`, …), `run_sf_gauntlet.cmd`, `run_parity_*.cmd`.
- **CCRL placement:** `fit_elo.py` (MLE Elo fit, pentanomial bootstrap CI, fixed classical-SF anchors),
  `ccrl_*.cmd` (preflight/calibrate/scout/concentrate/pinrungs).
- **Parity-vs-lc0 campaign:** `run_parity_match.cmd`, `diagnose_parity.py`, `probe_dossier.py`,
  `probe_anomaly.py`, `drift_mechanism.py`, `drift_policy_check.py`.
- **Corrector / distillation retrain:** `extract_fens.py`, `harvest_positions.py`, `build_dataset.py`,
  `train_corrector.py` (ridge), `train_recal.py` (GBM recal curve), `sf_label.py`, `capacity_study.py`,
  `overnight_pipeline.cmd`. (All gated/off; nothing shipped — value-recal was a dead end, §3.)
- **Tactical/defensive benches (proxies — use with skepticism):** `tactical_bench.py` (WAC/STS),
  `defense_bench.py` (parity-loss suite), `tune_constants.py`, `run_tact_sweep.ps1`.
- **Backend/throughput:** `bench_oracle.py`, `net_throughput.py`, `degradation_probe.py`
  (proved the CUDA leak), `conc_bench.py`/`conc_factor.py`, `backend_parity.py`.
- **Syzygy:** `fetch_syzygy345.ps1`.
- **THIS-SESSION diagnostics (conversion + time-use):** `diag_convert.py`, `diag_convert2.py`
  (play-out A/B on real FENs), `fetch_bot_games.py` (pull lichess drawn-won games), `analyze_ab.py`
  (won-then-drawn honesty check), `deploy_smoke.py` (pre-deploy sanity), `sim_timeuse.py`
  (GPU-free no-flag clock sim), `check_timeuse.py`, `_tbcheck.py` (python-chess syzygy probe check).
- **Misc analyzers:** `move_diagnostic.py`, `forensic_failures.py`, `gap_attribution.py`,
  `gap_depth_eval.py`, `graph_advantage.py`, `voi_characterize.py`, `encoder_planediff.py`,
  `leak_test.py`, `make_book.py`, `policy_index.py`.

### 2.6 `tests/` and `tests_oracle/`
- `tests/test_core.py` — substrate correctness on the mock oracle (mate-in-1/2, transposition merge,
  proof propagation, claim-floor, stalemate, Court stopping, palimpsest). **`RootCourt.budgets` is
  still a `@staticmethod` and `test_core.py` calls it statically — don't break that.**
- `tests/test_rs.py` — Rust↔Python parity. `tests/test_features.py` — feature ablations.
- `tests_oracle/{test_oracle,crosscheck_lc0,bench_oracle}.py` — oracle vs lc0 v0.32.1 + throughput.
- Note: `pytest` is **not installed** in the deploy env; run tests with the file's `__main__` or
  install pytest in a side env. Module import (`python -c "import stillwater.engine_rs"`) is the
  fast syntax check used throughout this session.

### 2.7 `nets/`, `games/`, `harvest/`
- `nets/`: `BT4-...-policytune.onnx` (default), `t3-...-distill.onnx`, `fallback.onnx` (t1) + their
  `.pb.gz` originals; `syzygy/` (**3-4-5 set, 291 files** — see the KQPPv caveat in §3/§4);
  `trt_cache/` (only used if `STILLWATER_TRT=1`).
- `games/`: PGN outputs + logs from every campaign; opening books `openings.pgn` (60 lines) and
  `gauntlet_book.pgn` (80 games); EPD suites `wac.epd`, `sts.epd`; many `g*.py` per-game forensic
  scripts (one-offs, safe to ignore unless replaying a specific game).
- `harvest/`: Distillery `.jsonl` + `archive_pre20260614/` + `archive_sfdistill_0614/` (SF-labeled).

### 2.8 Deploy (`C:\Users\nonna\Downloads\lichess-bot\`)
- `config.yml` — points `engine.name=stillwater_uci.bat`, `dir/working_dir=…\ExperimentalChessEngine`,
  protocol uci, ponder true; uci_options: `RustCore=true, Batch=128, Refine=true, DrawContempt=10`.
  **Holds the live Lichess token — never print it. Editing this file is gated behind explicit user
  sign-off.**
- `lichess-bot.py` — upstream lichess-bot bridge (spawns a fresh engine process per game).
- `start_stillwater_bot.ps1` — clean-slate launcher (kills stale bot+watchdog with self-clobber-safe
  filters, then starts both hidden).
- `watchdog.ps1` — every 120s checks process + lichess online status; relaunches if dead/wedged;
  rate-limited 1 restart / 10 min.
- Boot auto-restart: `shell:startup\StillwaterBot.vbs` runs `start_stillwater_bot.ps1` hidden at logon
  (a scheduled task needs admin; the Startup folder is the no-admin equivalent).

---

## 3. THE COMPLETE HISTORY (every trial, failure, and step)

Chronological. Format: **WHAT** → result → *why / lesson*. This is exhaustive; it is the most
valuable part of the handoff because most of these are **negative results that must not be retried.**

### 3.1 v0.1 baseline and the first rating
- Built the belief-lattice engine (Python) targeting 3000 Elo. First placement: **3191** (95% CI
  3118–3199) via a 184-game ML fit over an 11-tier SF ladder (`UCI_Elo 3100/3190` + node-capped SF +
  unthrottled) with a 60-line opening book + SF-vs-SF bridge matches (`fit_elo.py`).
  - *Pitfall discovered:* deterministic engine tiers **replay identical games** from startpos →
    **always use an opening book + dedupe** in fits. (Later: this 3191 and several "65%/55%" numbers
    turned out to be **small-sample over-estimates** — §3.7.)

### 3.2 The Rust rewrite (`core-rs`)
- Ported the whole core to a pyo3 extension. Three **parity bugs** found and fixed by cross-checking
  Rust output against Python on non-startpos/ep/short-history/long-shuffle regimes:
  1. **Encoder rep-scan** must be capped at 8 plies for net input (but claim/terminal detection keeps
     full history — that's rules, not input).
  2. **EP fixup dead code**: `encode_job` hardcoded `ep_square=None` so lc0's pre-history un-move
     fixup never ran (wrong planes for ~8 plies after an ep-bearing root) + a latent direction bug
     (must use the OLDEST-frame side-to-move, not the leaf's).
  3. **Vloss leak**: the dup-exhaust branch planted path-wide virtual loss that nothing decremented →
     phantom penalties accumulated on the BEST lines → search drifted off its PV.
  - Post-fix: **1533 evals/s**, all parity rechecks clean. *Lesson:* parity cross-checks must cover
    non-startpos regimes; in-flight penalties need explicit release accounting.

### 3.3 v0.2 architecture additions (June 11, all gated to reproduce old behavior)
- Proof certificates + 50-move validity envelope; **Syzygy as a proof oracle** (KBNvK instant proven
  win, 0 GPU evals vs floundering at +6679cp without); pondering (`go ponder`/`ponderhit`); and the
  belief-learning scaffolding. All default-off-equivalent unless data/tables present.

### 3.4 v0.4 (June 12): retrain pipeline, proof bursts, Thompson
- **Retraining pipeline** built end-to-end (`build_dataset.py` → `train_corrector.py`): ridge on
  Distillery residuals; **refuses to ship** unless corpus ≥5000 AND val-MAE beats do-nothing
  (on 1848 records it correctly declined at −5.6%).
- **Proof bursts** (`prover.rs`): SHIPPED ON (sound proofs can't hurt; value is field-side
  conversions, invisible to self-play which is ~81% rep-draws).
- **Root Thompson** (posterior-sample selection at root): validation 1-2-13 (46.9%) → **NO positive
  evidence → default FALSE**. *Lesson:* exploration changes need proof, not vibes.
- *Rule of the day:* **same-evaluator self-play at 60+1 is a saturated instrument (~80% draws)** —
  new SEARCH features need field-based or vs-SF instruments; only SOUND-proof features can ship on
  mechanism alone.

### 3.5 v0.5: the Refine package (June 12)
- Compiled a full diff of our search vs lc0 v0.32.1 (`docs/lc0_search_reference.md`). Implemented 8
  lc0-aligned changes behind the `refine` bitmask. **WAC-300 per-bit attribution** (legacy 284/300):
  `TEMP 287, CPUCT 285, FPU 281, MLH 284, LCB 282, GAMMA 287, UFLIGHT 274 (the culprit), TWOFOLD 284`;
  full `0xFF` package = **268 (−16 regression)**. Shipped composition `0xAB` = 285/300.
- *Lessons:* (1) lc0's in-flight U-denominator **under-diversifies** our serial 128-leaf batches —
  the evidence-damped Q-vloss is architecture-specific and **earned**, keep it. (2) lc0's
  two-fold-draws as shipped **reintroduces the claim-draw bug** (`test_claimable_rep_is_not_a_free_draw`
  caught it) → restricted to in-descent twofolds only. (3) γ=1.0 on zeroing edges is sound + positive.
  (4) **single-bit sweeps lie when bits interact** through the q0 floor (see §3.6).

### 3.6 The Parity Campaign (June 12) — closing the per-eval gap vs Lc0
- Instrument: fixed-node match vs lc0-cuda12 on the **same BT4 net** (identity proven via
  temp-invariant policy-rank agreement). Baseline (live 0xAB, b128): **14-0-10 lc0 (79.2% ≈ −230 Elo
  per eval).** Forensics (`diagnose_parity.py`) found: **DRIFT** (SW read −0.3 in SF −1.0..−1.8
  positions for dozens of plies) + outright calc errors. **Root cause proven live**: the `q0` raw-eval
  floor held the root at −0.24 while every expanded child read −0.99 — the engine was **structurally
  deaf to bad news.**
- Fixes (all bit-gated): **`R_NOFLOOR`** (backup aggregates expanded children only); **count-based LCB**
  argmax (wdl-variance LCB was a measured NO-OP — variance is aleatoric sharpness, not estimate error;
  `k/√(1+n)` is the epistemic proxy); Python **`R_ROBUSTPICK`** root pick; runtime tunables.
- Results: C1 (0x3BB) → 66.7%; C5 (0x3FF b32) → **62.5% ≈ −89**; final arm **57.3% lc0 = 8-1-39
  ≈ −51 ± 35 Elo (from −230), incl. SW's first win over lc0; 81% draws.** Shipped `0xBFF` + the tuned
  defaults; mask plumbing bug found (`set_refine(mask & 0xFF)` silently stripped bit `0x100` — always
  diff config outputs for identity).
- **Key receipts:** `R_MEANBACK` craters WAC 97→56 (**minimax-MAX is the correct operator for a
  lattice; robustness via evidence-gated MAX/LCB, never averaging**). `R_UFLIGHT` is −10 WAC solo but
  the concentration king in composition (PV child 60→240-795 of 768 evals). The "+3.56/+1.97 peaks
  we only drew" turned out to be **eval noise** (SF-truthed: never real edges) — the conversion-fix
  arm (ml_thresh .5) had **no effect** there. *Lesson:* at equal nodes + same evaluator the protocol
  asymptote is ~all-draws 50%; the residual gap is depth-bound endgame horizon + lc0 tuning tail.

### 3.7 The backend saga and the POISONED MEASUREMENT (June 12–13) — read carefully
- Swapped DirectML→CUDA (onnxruntime-gpu) for throughput; then a large-sample timed gauntlet showed
  SW at **~36% vs SF-3190L** and the maintainer (correctly, per the data at the time) concluded
  "it's just worse, testing done."
- **This verdict was WRONG.** `degradation_probe.py` proved the cause: the **ORT-1.26 CUDA EP grew
  GPU memory ~1GB/100k inferences** (default `kNextPowerOfTwo` arena) → saturated the 12GB card within
  a few games of a **reused-process** gauntlet (cutechess `restart=auto`) → cross-game accuracy fell
  95→86 linearly. **Lichess spawns a fresh process per game, so the leak never showed in deployment.**
  Fix: reverted to **`onnxruntime-directml 1.23.0`** (flat ~2.3GB); post-revert SW **consistently
  beats** SF-3190L. The early "65%" was REAL, wrecked by the leak. The CUDA EP arena is now mitigated
  in code (`arena_extend_strategy=kSameAsRequested` + bounded workspace).
- **Lesson (burned in):** a poisoned instrument produces a confident false negative. Do NOT re-derive
  "CUDA is broken" — it works; DirectML is a deploy *choice* (§4.4). And several historical
  "65%/55%/3191" numbers were small-sample over-estimates; the first large-sample measurement put true
  strength lower — which is why the CCRL placement (§3.9) is the number to trust.
- Same window: the **DrawContempt conversion fix** (gated, side-relative draw-contempt
  `core-rs draw_value`; `DRAW_DEAD .55 / DRAW_SAT .70` deadband; UCI `DrawContempt` centi-value) +
  the always-on **proven-mate shortest-proof pick**. A/B vs SF-3190L (DirectML, 60+1):
  **DrawContempt=10 → 7-0-9 (71.9%, ZERO losses)** vs an old 1-1-22 baseline → SHIP. Concurrency
  finding: per-game nps conc-1=1022 / conc-2=894 / conc-3=762 → placements run conc-2 with a ~1.15×
  SW clock compensation (node-limited anchors are contention-immune).

### 3.8 — (reserved; the parity/backend work above bleeds into the placement)

### 3.9 CCRL placement (June 14): the number to trust
- The SF18@N0-ladder method **saturated** (high-node SF18 self-play ≈100% draws, slope unmeasurable).
  Placement was redone by the **same-level classical-SF method**: fixed anchors = pre-NNUE SF
  (SF-DD 3210 / SF7 3303 / SF8 3362 / SF9 3425 / SF10 3447, one clock-norm), node-rungs float pinned
  by `ccrl_pinrungs`. Result: **SW = 3432 CCRL 40/15 (1-CPU), 95% CI 3352–3466** (`fit_elo.py`,
  pentanomial pair bootstrap over 183 games). It lands low-3400s mainly because the N192k rung pins
  high (SF18's NNUE eval is strong vs pre-NNUE anchors), not because SW moved.

### 3.10 Eval-quality is the ceiling (June 14) — three independent confirmations
- **Fast-net A/B** (`net_throughput.py`, identical search, only the net varies): throughput BT4 455 /
  t3 518 / **t1 727 evals/s**, but WAC@1s **BT4 90.7% / t3 85.7% / t1 69.3%** and the gap **widens**
  at shorter budgets. t1 got 1.65–1.93× more evals/position and still cratered. **Depth does NOT
  convert to strength; eval quality is the entire ceiling.** → keep BT4; do not chase a faster net.
- **Move-quality diagnostic** (`move_diagnostic.py`, 1000 pos, SW@2s vs SF d16): SW is a near-SF
  move-picker — **mean cp-loss 8.3 (median 1), 61% exact-move agreement**; search **helps** over raw
  BT4 policy (8.3 vs 15.8). Only 1.6% big blunders (>80cp, mostly endgame/already-losing). **The
  search is near its ceiling given BT4.**
- **Off-the-shelf-net dead end:** BT4-1024x15x32h is Lc0's strongest released net; nothing stronger to
  swap to (no BT5). GPU training *is* feasible on the RTX 5070 (Blackwell sm_120) via the cu128 torch
  wheel in an isolated venv `C:\Users\nonna\swtrain_venv` — but reproducing the BT4 transformer in
  torch is hard; a corrector/policy head is more tractable.

### 3.11 The +35-Elo tuning win and the honest-max failure (June 15)
- **SHIPPED +35 Elo:** the STS-tuned constants (§1.11), validated +34.9 ± 23.2 (LOS 99.8%, 150g).
- **Honest-max backup = NEGATIVE:** a winner's-curse-corrected backup (gated `honest_k`) **craters**
  tactics (WAC 90.7→85.7→78.3→75.7 across honest_k 0/.05/.10/.15). Chess `max` is **real signal**,
  not independent noise — penalizing it hurts, and the penalty compounds over depth. `honest_k=0`.
  Consistent with the tuning win: the engine wants **less** damping, not more.

### 3.12 Value-recalibration is a dead end (June 15 overnight) — decisive negative, 5 instruments
- Distilling Stockfish's value into BT4 (the big overnight bet) does NOT improve play at **any
  capacity**, despite large value-MAE gains. Tier-1 linear corrector: val-MAE +7.2% but WAC 90.3 vs
  90.7, match **−23 ± 42**. Self-distill **−26 ± 51**. Capacity study: the SF-residual is a strongly
  **nonlinear** function of `raw_v` alone (richer features add ~nothing); the miscalibration is a
  non-monotonic **S-wave** — BT4 **under-values clearly-winning** (raw_v~0.7 ⇒ +0.12, the quantified
  conversion bug) and over-values slight edges. Tier-2 nonlinear recal (`recal_lut.npz`, +24% MAE):
  match **−11.6 ± 17.4** (240g). **Conclusion: +24% value-MAE → ~−12 Elo.** *Mechanism:* the search
  constants are tuned around BT4's **native** value distribution; recalibrating the scale — even
  toward more accurate SF values — **detunes** the search, and the detune cost ≥ the better-value
  benefit. Value recal is monotonic-dominant so it barely changes move **ordering** (what play needs),
  only magnitudes. Forward (untried, ranked): **policy/ranking distillation** > joint recal+SPSA-retune
  > a board-seeing net fine-tune (needs cloud GPU).

### 3.13 Architectural extensions for the research paper (June 15, gated)
- Built `epistemic/aleatoric split` (reducible vs irreducible uncertainty as a propagated graph
  quantity), **VOI selection** (replace PUCT with `VOI(c)=epistemic·closeness`), and a
  **graph-advantage** quantifier (`graph_stats()`: transposition reuse e.g. 2.82× in a K+P endgame).
  Full writeup in `docs/architecture_extensions.md`. **VOI is NOT a strength win**: WAC-200 @1s
  **88.0% (on) vs 96.0% (off), −8 pts** — VOI scores expanded moves on belief alone (ignores BT4's
  policy) and its wider branching spreads a fixed budget too thin to drill the one winning line.
  The **eval-bound thesis applies to selection too**: BT4's policy carries tactical info a value-only
  rule can't recover. Soundness: VOI-off is bit-identical/PUCT-deterministic. Gated off.

### 3.14 The 5-FOR-5 LAW (June 16) — the most important meta-result
- The visit-distribution **structure-lever** readout (lc0-style: play the highest visit-share move
  among value-LCB-band candidates) passed **every** cheap proxy — Stage-1 signal strong (clean
  per-root-edge visits hit SF's move 40% where value-argmax got 2%), crater-check clean (WAC identical
  off/on), recovery +9/55 on a biased set — **and it STILL LOST in play** (A/B vison-vs-visoff
  45% = 1-5-34; the maintainer manually analyzed 15 games and found vison consistently *slightly less
  accurate*).
- **Now 5-for-5: every search REORGANIZER is ~0/negative in real play** — VOI (−8 WAC), honest-max
  (crater), `R_MEANBACK` (97→56), policy-tiebreak (sub-measurement), visit-readout (−Elo).
  **THE LAW:** *recovery on a biased "where-it-fails" set does NOT predict play; the engine is
  co-tuned around its value readout, so swapping the readout trades fixed cases for broken ones, net
  negative.* **Only TUNING and BUG FIXES have ever helped.** **Do not build more search-reorganizer
  levers expecting Elo.** (All such code is kept **gated default-off, byte-identical when off**.)

### 3.15 Deploy + rating discrepancy (June 18, earlier)
- The DrawContempt fix was **in** the 3432 placement (every `ccrl_*.cmd` sets `DrawContempt=10`) but
  had **never been shipped** to the live bot → the bot ran **below its own measured rating** for a
  long time. Fixed: added `DrawContempt: 10` to `config.yml` (with sign-off). Set up boot auto-restart
  + watchdog. **Process pitfall that burned hours:** process-management PowerShell commands
  **self-clobber** — a tool shell's own command line contains the filter strings (`lichess-bot.py`,
  `watchdog.ps1`), so `Stop-Process` matched and killed the tool's own shell ("exit 255, no output").
  Fixes: identify the bot by `Name='python.exe'` (excludes powershell shells); kill the watchdog with
  `-notlike '*-Command*'` (tool shells run via `-Command`, the real watchdog via `-File`) + `-ne $PID`;
  verify liveness via the **lichess status API**, not process matching.

### 3.16 THIS SESSION (June 18) — the conversion fix, the abort pitfall, the time-use negative
- **The reported symptom:** on Lichess, SW repeatedly **drew dead-won games by 3-fold** — up a whole
  queen it shuffled its king and let the opponent claim. `fetch_bot_games.py` confirmed **5 of the
  last 30 games were drawn while +5..+10 material** (vs opponents rated 2117–2784 — so not only weak
  bots; weak bots just expose it more because SW *reaches* won endgames more often).
- **Root cause:** in won endgames with no tablebase mate-distance and no short forcing mate, **BT4's
  value SATURATES** (every winning move reads ≈ equal) → no gradient toward mate → aimless king
  shuffle → 3-fold. DrawContempt can't fix this (it nudges off the exact rep but there's no converting
  gradient). Confirmed by `diag_convert2.py` play-outs.
- **A diagnostic detour worth remembering:** the first reproduction used a hand-made KQ+2P FEN that was
  **illegal** (black king in check with White to move). The Rust core correctly rejected it,
  `think()` threw, and `uci.py`'s fallback played `legal[0]` (a garbage king move) — a fake "shuffle".
  *Lesson:* verify test FENs are legal; and note the `legal[0]` footgun (§4.6).
- **The fix (`engine_rs.py`, gated `STILLWATER_CONVERT`, SHIPPED ON):** (#1) **Syzygy DTZ-optimal play**
  for ≤5-man (`_tb_best_move` via python-chess `chess.syzygy`: among WDL-verified win-keeping moves
  pick min |DTZ|, zeroing preferred; try/excepts → falls through). (#2) **endgame king-drive/progress
  readout** (`_progress`, ≤10-man, `qv>0.5`, value-banded 0.10 so a tactic's singleton band is
  untouched): play the move maximizing drive-enemy-king-to-edge + bring-our-king-up + confine +
  zeroing/check, hard-avoiding stalemate/insufficient-material.
- **Validation:** play-out on the **real drawn FENs** → all convert (CCI-9, Evil2Root, pawny_bot:
  DRAW→MATE; sseh-c 37→15 plies; KQK/Martuni held). 40-game self-play A/B convON-vs-convOFF =
  **3-3-34 (Elo 0, no regression)**; honesty check of the 34 draws = **ZERO clean won-games thrown**
  (the flagged ones were KBvK insufficient-material + a queens-on perpetual). A partial vs-SF-2600
  arm went **29-0-0** (zero draws) before being killed (see next). **This is a BUG FIX (conversion) —
  the class that helps — not a search reorganizer.**
- **python-chess Syzygy is flaky** for some materials: it threw `MissingTableError` on KQvK/KQPvK/
  KQPPvK but works on KRvK/KQvKPP (a key-normalization quirk, files are present). `_tb_best_move`
  try/excepts → falls through to #2, so the fix degrades gracefully.
- **GPU-CONTENTION ABORT PITFALL (operational):** running a cutechess gauntlet (2 SW engines) **while
  the live bot plays** = 3 STILLWATER engines timesharing one GPU → the bot couldn't produce its first
  move within Lichess's ~30s window → **Lichess auto-aborted games**. (Aborts don't cost rating but
  look broken and waste games.) **Lesson:** pause the live bot before GPU-heavy gauntlets, or run them
  when the machine is free. Clean kill without touching the live bot or the unrelated **pyrocast**
  python processes: `taskkill /F /T` on the orchestrating `cmd.exe` PID (filter `Name='cmd.exe'` +
  commandline match, exclude `$PID`) **and** on `cutechess-cli.exe` (gauntlet-only) — tree-based, so
  the live bot (separate process tree) survives; sweep any orphaned `stillwater_conv_on` bat separately.
- **TIME-USE INVESTIGATION = decisive negative.** Reported: "SW banks lots of time but never uses it."
  Built a spend-the-bank floor (`STILLWATER_TIMEUSE`: while `clock>8·soft`, force ≥0.6·soft on every
  non-forced/unproven move). **Proven safe** (`sim_timeuse.py`: 80-move replay × 5 TCs never flags,
  even spending the `clock/12` cap every move; ~2.5× time *if* it fires) but **INERT in play**,
  validated three ways (`check_timeuse.py` + a per-move `el/soft/floor/ev/proof` dbg). SW's moves are
  **binary**: (a) **proven** → snaps instantly (`ev≈29, proof=True`; the floor correctly never
  overrides a proof); (b) **exhausted** — simple positions where the lattice saturates and
  `select_batch` returns empty, so the think-loop breaks on empty-selection **before** `_should_stop`'s
  floor is consulted (`ev≈348`, e.g. post-queen-trade snapped at 0.4s); (c) **real work** → already
  thinks to the hard cap (`ev≈18–24k`, 18–30s, above the floor). **There is no "lazy confident snap
  with work left" to reclaim. The banked clock is a symptom of efficiency (solving/exhausting
  positions fast), not laziness.** Reverted clean. *Lesson:* before adding a "spend more time" lever,
  check WHY it banks — if it's proof/exhaustion (this engine), no floor helps; and the eval-bound
  finding says forcing more compute ≈ 0 Elo anyway.
- **VERIFY_DRAW — SHIPPED** (`STILLWATER_VERIFY_DRAW=256` in `stillwater_uci.bat`): re-validate a
  **path-conditional** draw proof with 256 fresh court-directed evals before snapping it, so SW
  doesn't instantly accept a repetition "draw" its own descent assumed when the position is winnable.
  Bounded by `VERIFY_DRAW_FRAC·soft` (0.25) → **cannot drain the clock → no flag risk**; unconditional
  draws + sound win/loss proofs are never delayed. The one "use the time where it helps" lever.
  Shipped on user sign-off (low-risk by construction); **not yet gauntlet-quantified** (it fires only
  in a narrow case, so no measurable-gain claim — offer a bot-paused gauntlet if a number is wanted).

---

## 4. CURRENT STATE (exhaustive snapshot)

### 4.1 Exactly what is deployed (the live config)
- **Launcher** `stillwater_uci.bat` (env): tuned `+35` constants (§1.11) **+ `STILLWATER_CONVERT=1`
  (conversion fix #1 DTZ + #2 progress) + `STILLWATER_VERIFY_DRAW=256`**, then
  `python -u -m stillwater.uci`.
- **`config.yml`**: `RustCore=true, Batch=128, Refine=true (→ mask 0xBFF), DrawContempt=10`, ponder
  true, draw/resign disabled, no online moves, Syzygy in-engine.
- **Backend:** **DirectML** (`onnxruntime-directml 1.23.0`), BT4 net, ~1.5k evals/s.
- **Gated OFF** (do not enable without a gauntlet): `STILLWATER_VOI`, `STILLWATER_VISIT_READOUT`,
  `pol_tiebreak`, `honest_k`, `STILLWATER_RECAL`, `Corrector`, `RootThompson`, `R_MEANBACK`,
  `STILLWATER_TIMEUSE` (reverted entirely), `STILLWATER_TRT` (works but see §4.4), `MIN_SPEND` (0).
- **Live process topology:** 1 × `lichess-bot.py`, 1 × `watchdog.ps1`, fresh engine per game.
  Auto-restart on boot via the Startup `.vbs`. Verified online during this session; recent completed
  games were wins.

### 4.2 Ratings (the honest picture)
- **CCRL 40/15 ≈ 3432 (1-CPU), CI ~3352–3466** — the number to cite.
- Historical/misleading numbers to NOT re-cite as current: the v0.1 "3191", the "65%/55% vs SF-3190L"
  small samples, and the "36% / just worse" (the **CUDA-leak-poisoned** measurement — §3.7).
- Lichess shows a **provisional ~2627** blitz/rapid rating — a *different scale* (and the recent abort
  episode was operational, not strength; aborts don't affect rating). Treat CCRL as the strength of
  record.

### 4.3 The binding constraint
**Eval quality (BT4), not search.** Established three independent ways (§3.10) plus the 5-for-5
selection-side law (§3.13–3.14): more evals/s ≈ 0 Elo, faster nets are worse, value-recal detunes,
search reorganizers don't translate. The search is a near-SF move-picker *given* BT4 (8.3cp mean loss).

### 4.4 Backend reality (why DirectML, not the 5070's CUDA/TRT)
- The 5070 **runs CUDA and TensorRT fine** (TRT ≈ lc0-class ~4800 evals/s ≈ 3× DirectML; the CUDA EP
  memory leak is fixed in `oracle.py` via the bounded arena). **Do not re-derive "CUDA is broken."**
- DirectML is deployed because: (a) the env has `onnxruntime-directml` installed (CUDA/TRT need
  `onnxruntime-gpu`, which **cannot coexist** with `-directml` — a pip swap, no code change;
  `oracle._default_providers` already prioritizes TRT>CUDA>DML>CPU filtered to installed); (b) DirectML
  is the **robust per-spawn** path — TRT doesn't register cleanly on this ORT-1.26/Windows pairing
  (`RegisterTensorRTPluginsAsCustomOps` fails → silent CUDA fallback; gated behind `STILLWATER_TRT`)
  and cold-builds BT4's engine (minutes, mitigated by `trt_cache`); (c) **crucially, 3× evals ≈ 0 Elo**
  (eval-bound), so the faster backend would not meaningfully strengthen rapid/classical play — only
  **blitz** is compute-ratio-bound. So DirectML costs ~no real strength.

### 4.5 What's gated off and WHY (the graveyard — don't resurrect without new evidence)
- VOI selection (−8 WAC), visit-distribution readout (lost in play 45%), policy-tiebreak readout
  (no measurable gain), honest-max backup (cratered tactics), `R_MEANBACK` (97→56 WAC),
  value recal / SF-distill corrector (−12 Elo), root Thompson (no evidence), `STILLWATER_TIMEUSE`
  (inert), fast nets (worse). **All are the 5-for-5 law in action: reorganizers/eval-rescalers don't
  translate to play here.**

### 4.6 Open issues / footguns
- **`uci.py` `legal[0]` fallback:** on any `think()` exception, the bridge plays the **first legal
  move** (garbage). Harmless on legal positions (real games don't throw), but worth hardening to a
  saner fallback (e.g., a shallow emergency search or the last PV move). Surfaced via the illegal-FEN
  detour (§3.16).
- **python-chess Syzygy flakiness** on KQ-family materials (§3.16) — the conversion fix tolerates it
  (falls through to #2), but a from-Rust DTZ path would be more robust if conversion is revisited.
- **Syzygy set:** 291 files (3-4-5). Some 5-man pawn-heavy tables behave oddly under python-chess;
  `tb_max_men=5` in the Core ctor. If extending to 6-7 man, fetch tables + raise the cap.
- **`pytest` not installed** in the deploy env (run tests via `__main__` or a side env).
- **Two engine paths** (`engine_rs.py` deployed, `engine.py` reference) — keep them parity-consistent
  if you touch shared semantics (the Court/should_stop logic is duplicated, by design, in both).

### 4.7 Standing constraints / boundaries (operational discipline)
- **Do NOT auto-deploy to the live Lichess bot without explicit sign-off.** Editing `config.yml` /
  restarting the bot is gated. (This session's deploys were each explicitly authorized.)
- **The Lichess token is in `config.yml` — never print it.**
- **Do NOT touch the unrelated `pyrocast` python processes** (`monitor_ignition_v10.py`, the
  `pyrocast_cuda` env) — they are the user's other project and share the machine.
- **Never run a GPU-heavy gauntlet while the live bot is playing** (§3.16 aborts). Pause the bot first.
- **Only timed gauntlets prove Elo.** Proxies mislead; 10-game samples mislead; be honest about
  results and never explain a bad number away.

---

## 5. THE LEVERS THAT REMAIN (ranked by expected value)

1. **A better evaluator (the only big one).** Strength is BT4-bound. Options, hardest-first:
   (a) **net fine-tune / from-scratch train** on a cloud GPU (the local 5070 can train via the cu128
   torch wheel, but reproducing the BT4 transformer is hard; a smaller native net or NNUE is more
   tractable — and remember t1/t3 were *worse*, so a new net must beat BT4, not merely run faster);
   (b) **policy/ranking distillation** (distill SF's *best move* into a policy-prior correction — the
   one distillation flavor untried, and it targets move *ordering* which value-recal can't touch — see
   §3.12 "forward"); (c) **joint value-recal + SPSA constant re-tune** (the recal benefit may only
   unlock if the search is re-tuned for the new value scale). All require the Distillery corpus +
   `swtrain_venv`.
2. **Blitz-specific backend swap to TRT** (`onnxruntime-gpu` + `STILLWATER_TRT=1`): the one regime
   where 3× evals could convert. Needs the registration/cold-build issues sorted + a bot-paused
   gauntlet. Likely neutral at rapid/classical.
3. **More constant tuning** (SPSA on the defense suite / STS) — largely tapped; the +35 vector is near
   a local optimum (lcb_k already at 0).
4. **Endgame conversion polish** beyond the current fix (6-7-man tablebases; a Rust-side DTZ readout;
   tuning `_progress` weights) — incremental.
5. **`VERIFY_DRAW` quantification / tuning** — confirm/expand the premature-draw guard with a gauntlet.
6. **The research-paper architecture story** is essentially complete: the belief-lattice paradigm +
   the negative results (search reorganizers don't translate; eval quality is the binding ceiling;
   graph-advantage quantified) are themselves a clean contribution (`docs/architecture_extensions.md`).

---

## 6. HOW TO WORK ON IT

### 6.1 Build / run / test
- Python env: `C:\Users\nonna\miniconda3\python.exe` (has `onnxruntime-directml`, `python-chess`,
  `numpy`, the compiled `stillwater_core`).
- Rebuild the Rust core after editing `core-rs/`: `cd core-rs && maturin develop --release`.
  **Pure-Python edits (engine_rs.py, court.py, oracle.py, …) need NO rebuild** — just restart the
  process. (This session's conversion fix, VERIFY_DRAW, and time-use work were all Python-only.)
- Fast syntax check: `python -c "import stillwater.engine_rs, stillwater.court"`.
- Play locally / smoke: `tools/deploy_smoke.py` (launches the deploy bat, confirms DirectML + a legal
  bestmove). `play.py --mock` for GPU-free.
- UCI: `python -m stillwater.uci` (or via `stillwater_uci.bat`).

### 6.2 Validating a change (the only trustworthy path)
- For a **conversion/endgame** change: `diag_convert2.py` (deterministic play-out A/B on the real
  drawn FENs) is a strong functional check; then a head-to-head or vs-weaker-SF gauntlet
  (`run_convert_ab.cmd` / `run_convert_vs_weak.cmd`) **with the bot paused**.
- For a **strength** change: a **timed gauntlet** (`run_gauntlet.py`, `run_sf_gauntlet.cmd`, or an A/B
  cmd) vs SF at an appropriate `UCI_Elo`, paired openings (`gauntlet_book.pgn`), DirectML, then
  `fit_elo.py` / `analyze_ab.py`. **Never** conclude from WAC/STS/move-agreement alone.
- cutechess-cli: `C:\Users\nonna\Downloads\ChessBotFableTest\tools\cutechess-1.3.1-win64\cutechess-cli.exe`.
  Stockfish: the WinGet install path used in `run_contempt_ab2.cmd`.
- **Pause the live bot** before any GPU gauntlet (kill its tree as in §3.16), run, then relaunch via
  `start_stillwater_bot.ps1`.

### 6.3 Deploying (only with sign-off)
- Enable a flag in `stillwater_uci.bat` (env) or a UCI option in `config.yml`, smoke-test
  (`deploy_smoke.py`), then `& C:\Users\nonna\Downloads\lichess-bot\start_stillwater_bot.ps1` to
  restart (clean-slate). Verify: 1 bot proc, 1 watchdog proc, and `online=true` via
  `https://lichess.org/api/users/status?ids=STILLWATER-bot`. Don't restart mid-game (check
  `playing` first).

### 6.4 The mindset that works here
- Default to **bug fixes and tuning**, not search re-architecture (the 5-for-5 law).
- Treat **eval quality** as the ceiling; frame strength work around the evaluator.
- **Falsify cheaply, then prove with a gauntlet.** Assume every proxy is lying until a timed match
  agrees. When a result is bad, say so plainly and find the mechanism — the two biggest wins of this
  project (the CUDA-leak unmasking and the conversion fix) came from *not* accepting a confident wrong
  conclusion.
