# Leela Chess Zero (lc0) — Search Mathematics & Default Parameters Reference

**Target version:** lc0 **v0.32.1** (latest stable, released 2025-11-23). Also covers v0.31.x where defaults are unchanged.
**Source tree note:** As of v0.30+ the search was restructured. The classic MCTS engine now lives under **`src/search/classic/`** (`search.cc`, `params.cc`, `params.h`, `stoppers/`). Shared NN/backend options live in **`src/neural/shared_params.cc`**. Citations below use these paths.

All numeric defaults are the **shipped UCI defaults**. Flags marked *(Pro/hidden)* are not shown in default UCI option lists but exist.

---

## 1. PUCT Selection Formula

### 1.1 The score (`src/search/classic/search.cc`, `PickNodesToExtendTask` / edge scoring)

For each child edge `i` of a node with total child visits `N` (sum of children's visit counts), the selection score is:

```
score(i) = util(i) + P(i) * puct_mult / (1 + nstarted(i))
```

where:
- `puct_mult = cpuct * sqrt(max(N, 1))`   — note the `sqrt` is over the **sum of children visits** (`GetChildrenVisits()`), clamped to ≥1.
- `P(i)` = policy prior for the edge (post-softmax, see §3).
- `nstarted(i)` = child visits **including in-flight (virtual-loss) visits** — so the `1 + n` denominator is AlphaZero's `1 + N(s,a)`.
- `util(i)` = the child utility: child Q (with moves-left bonus folded in, §5) if visited, else FPU value (§2).

This is the standard PUCT: `U(s,a) = cpuct * P(s,a) * sqrt(ΣN_b) / (1 + N(s,a))`, with `Q + U` maximized.

### 1.2 cpuct grows with parent visits (`ComputeCpuct`, search.cc)

```cpp
inline float ComputeCpuct(const SearchParams& params, uint32_t N, bool is_root_node) {
  const float init = params.GetCpuct(is_root_node);
  const float k    = params.GetCpuctFactor(is_root_node);
  const float base = params.GetCpuctBase(is_root_node);
  return init + (k ? k * FastLog((N + base) / base) : 0.0f);
}
```

i.e.

```
cpuct(N) = cpuct_init + cpuct_factor * ln( (N + cpuct_base) / cpuct_base )
```

`N` here is the parent node's visit count. With `cpuct_factor = 0`, cpuct is constant. This is the DeepMind log-growth form.

### 1.3 Defaults (`src/search/classic/params.cc`)

| Flag | Default | Range |
|---|---|---|
| `--cpuct` (cpuct_init) | **1.745** | 0.0–100.0 |
| `--cpuct-base` | **38739.0** | 1.0–1e9 |
| `--cpuct-factor` | **3.894** | 0.0–1000.0 |

> Historical note: cpuct was a constant 3.4 (very old), then the AZ-style log-growth was added (cpuct_base = 19652, cpuct_factor = 2 per the AZ paper). Current tuned defaults are 1.745 / 38739 / 3.894.

### 1.4 Root-specific variants *(Pro/hidden; default to the same values as non-root)*

| Flag | Default |
|---|---|
| `--cpuct-at-root` | **1.745** |
| `--cpuct-base-at-root` | **38739.0** |
| `--cpuct-factor-at-root` | **3.894** |

`GetCpuct(is_root)` etc. simply return the `*-at-root` constant when `is_root_node` is true, else the normal one. By default the root behaves identically to interior nodes.

---

## 2. First Play Urgency (FPU)

### 2.1 Formula (`GetFpu`, search.cc)

```cpp
inline float GetFpu(const SearchParams& params, const Node* node,
                    bool is_root_node, float draw_score, float visited_pol) {
  const auto value = params.GetFpuValue(is_root_node);
  return params.GetFpuAbsolute(is_root_node)
             ? value
             : -node->GetQ(-draw_score) - value * std::sqrt(visited_pol);
}
```

So:
- **`reduction` strategy (default):**
  ```
  FPU = -Q_parent  -  fpu_value * sqrt(visited_pol)
  ```
  where `Q_parent = node->GetQ(-draw_score)` (parent's Q from the parent's perspective; negated because the child is evaluated from the opponent's side), and **`visited_pol`** is the **sum of policy priors `P` of children already visited at least once** (the "policy mass already explored"). The reduction term grows with `sqrt` of that explored mass, so the more of the policy mass has been examined, the more unvisited siblings are penalized.
- **`absolute` strategy:** `FPU = fpu_value` (a fixed eval for unvisited children, ignoring parent Q).

### 2.2 Defaults (params.cc)

| Flag | Default | Notes |
|---|---|---|
| `--fpu-strategy` | **`reduction`** | {`reduction`, `absolute`} |
| `--fpu-value` | **0.330** | range −100..100 |
| `--fpu-strategy-at-root` | **`same`** | {`reduction`,`absolute`,`same`} — `same` ⇒ use non-root strategy *(Pro/hidden)* |
| `--fpu-value-at-root` | **1.0** | only used if `fpu-strategy-at-root` ≠ `same` *(Pro/hidden)* |

Because `fpu-strategy-at-root = same` by default, the root uses the same `reduction` / `0.330` behavior as interior nodes. (The `fpu-value-at-root = 1.0` is only consulted if you explicitly set a root strategy; 1.0 in `reduction` means "discourage unvisited root moves a lot" — a self-play artifact, inert at default.)

---

## 3. Policy Handling

- **Policy softmax temperature** (`src/neural/shared_params.cc`):
  ```cpp
  options->Add<FloatOption>(kPolicySoftmaxTemp, 0.1f, 10.0f) = 1.359f;
  ```
  `--policy-softmax-temp` default **1.359** (shown rounded as 1.36 on docs). Logits are divided by this temperature before softmax: `P_i = softmax(logit_i / 1.359)`. Values >1 flatten the policy (more exploration); the tuned 1.359 slightly softens raw net policy.
- **Illegal-move masking:** only legal moves get edges in the tree; the softmax is computed over the legal move set only (illegal logits are never included), so priors over legal moves sum to 1.
- **Dirichlet noise — OFF by default (confirmed):**
  | Flag | Default |
  |---|---|
  | `--noise-epsilon` | **0.0** (no noise mixed into root priors) |
  | `--noise-alpha` | 0.3 (only used if epsilon > 0) |
  Match/analysis play uses **no** Dirichlet noise. Noise is a self-play-only training device.

---

## 4. Value Head → Q, Draw Score / Contempt, Backup

### 4.1 WDL → Q (`v = W − L`, confirmed)

The net emits a WDL distribution `(W, D, L)`. The scalar value is:

```
v (= WL) = W − L
```

Internally the node stores **WL** and **D** separately. Reconstruction used in the rescale code:
```cpp
auto w = (1 + v - d) / 2;   // W = (1 + (W−L) − D)/2
auto l = (1 - v - d) / 2;   // L = (1 − (W−L) − D)/2
```

### 4.2 Draw score / contempt at Q level

`Node::GetQ(draw_score)` returns:
```
Q = WL + draw_score * D
```
- `--draw-score` default **0.0** (range −1..1; from White's perspective). 0 ⇒ standard scoring; −1 ⇒ Armageddon (draw counts as a loss for the side that benefits from a draw).
- Note the sign convention in selection: parent Q for FPU is taken as `node->GetQ(-draw_score)` (perspective flip), the child as `GetQ(draw_score)`.

### 4.3 Backup — plain mean, NO depth discount (confirmed)

`DoBackupUpdateSingleNode` (search.cc):
```cpp
float v = node_to_process.eval->q;   // = W − L
float d = node_to_process.eval->d;
float m = node_to_process.eval->m;
for (Node *n = node, *p; n != root->GetParent(); n = p) {
  p = n->GetParent();
  n->FinalizeScoreUpdate(v, d, m, multivisit);   // accumulate
  v = -v;   // perspective flip per ply
  m++;      // moves-left grows by 1 per ply
}
```
`FinalizeScoreUpdate` accumulates a **running arithmetic mean** of the subtree evals (Q = Σv / N), exactly. There is **no depth/γ discount** anywhere — lc0 uses the undiscounted mean of leaf evaluations, with the value sign flipped each ply for side-to-move. The moves-left estimate `m` is incremented by 1 each ply going up.

---

## 5. Moves-Left Head (MLH)

### 5.1 Formula (`GetMUtility`, search.cc)

The M-bonus added to a child's utility before PUCT comparison:

```cpp
float GetMUtility(Node* child, float q) const {
  if (!enabled_ || !parent_within_threshold_) return 0.0f;
  const float child_m = child->GetM();
  float m = std::clamp(m_slope_ * (child_m - parent_m_), -m_cap_, m_cap_);
  m *= FastSign(-q);
  if (q_threshold_ > 0.0f && q_threshold_ < 1.0f) {
    q = std::max(0.0f, (std::abs(q) - q_threshold_)) / (1.0f - q_threshold_);
  }
  m *= a_constant_ + a_linear_ * std::abs(q) + a_square_ * q * q;
  return m;
}
```

In symbols, with `Δm = child_m − parent_m` (estimated change in remaining game length):

```
base   = clamp( moves_left_slope * Δm , −moves_left_max_effect , +moves_left_max_effect )
base  *= sign(−q)                       # winning (q>0): prefer SHORTER games; losing (q<0): prefer LONGER
qadj   = max(0, |q| − threshold) / (1 − threshold)     # only if 0 < threshold < 1
M_bonus = base * ( constant_factor + scaled_factor*|q'| + quadratic_factor*q'^2 )
```
(where `q'` is the threshold-rescaled q; `|q|` is used in the polynomial.)

### 5.2 When it kicks in (`parent_within_threshold_`)

`enabled_` requires the net to **have an MLH** output. The bonus is **0 unless `|Q_parent| ≥ moves-left-threshold`** — i.e. MLH only acts once the position is already clearly won or lost (default 0.8). Below threshold, the qadj rescale also drives the polynomial to use `q'=0`, leaving only the `constant_factor` term (which defaults to 0 ⇒ no effect).

### 5.3 Defaults (params.cc)

| Flag | Default | Maps to |
|---|---|---|
| `--moves-left-max-effect` | **0.0345** | `m_cap_` (max bonus magnitude) |
| `--moves-left-threshold` | **0.8** | `q_threshold_` |
| `--moves-left-slope` | **0.0027** | `m_slope_` |
| `--moves-left-constant-factor` | **0.0** | `a_constant_` |
| `--moves-left-scaled-factor` | **1.6521** | `a_linear_` (× \|q\|) |
| `--moves-left-quadratic-factor` | **−0.6521** | `a_square_` (× q²) |

Net effect: at default, the polynomial is `0 + 1.6521·|q| − 0.6521·q²`, so the bonus scales up with how decisive the position is (peaks near |q|→1), pushing the engine to convert won positions faster and drag out lost ones, capped at ±0.0345 of eval.

---

## 6. Virtual Loss, Batching, Collisions

### 6.1 Virtual loss / collision model (search.cc)

lc0 does **not** apply a fractional virtual-loss penalty to Q the way some MCTS engines do. Instead, during multi-threaded/batched descent the **in-flight visit count `nstarted` is incremented** as soon as a path is selected (it enters the `1 + nstarted` denominator and lowers that child's U), discouraging — but not forbidding — other collectors from re-picking it. When the same leaf is selected again while still pending, it is recorded as a **collision** (a multi-visit reservation) rather than re-evaluated:

```cpp
search_->shared_collisions_.emplace_back(node, multivisit);
```
A node is allowed to accumulate collision visits up to the per-batch caps below. On backup, collision reservations are cancelled via `CancelSharedCollisions()` (`CancelScoreUpdate`), so they never corrupt the running mean. The effect is "soft" virtual loss through the visit-count denominator plus explicit collision accounting.

### 6.2 Batching defaults (params.cc)

| Flag | Default | Range | Meaning |
|---|---|---|---|
| `--minibatch-size` | **0** | 0–1024 | 0 ⇒ use the **backend's preferred/optimal batch size** (e.g. cuda-fp16 backends suggest 256–1024). Otherwise the explicit cap on positions per NN eval. |
| `--max-collision-events` | **917** | 1–65536 | distinct collision events allowed while gathering one batch |
| `--max-collision-visits` | **80000** | 1–1e8 | total collision visits allowed per gather |
| `--max-out-of-order-evals-factor` | **2.4** | 0–100 | max OOO evals = `factor × max_batch_size` |
| `--out-of-order-eval` | **true** | — | terminal/cache-hit positions evaluated immediately during gather |
| `--max-concurrent-searchers` | **1** | 0–128 | gatherers active at once (0 = unlimited) |
| `--threads` | **0** | — | 0 ⇒ auto (typically 2 search threads for a single GPU backend) |
| `--nncache` | **2000000** | — | NN eval cache entries (`src/neural/shared_params.cc`) |

### 6.3 Strength vs minibatch size

Larger minibatches reduce strength slightly *at a fixed node count* (the help text says: "Larger batches may reduce strength a bit"). Reason: a larger batch forces more nodes to be selected from a less-updated tree (more collisions / staler statistics), so the search is less "on-policy" than fully sequential MCTS. The trade-off is throughput: larger batches give far higher nps on GPUs, so at fixed **wall-clock time** a bigger batch is usually a net win on a fast GPU. The per-node penalty matters mainly for fixed-nodes matches and weak/CPU backends.

---

## 7. Time Management

Default ("legacy"/smooth) time manager — `src/search/classic/stoppers/legacy.cc` + `stoppers/common.cc`.

### 7.1 Estimated remaining moves (log-logistic curve)

```
moves_to_go = midpoint * (1 + 2*(move/midpoint)^steepness)^(1/steepness) − move
```

### 7.2 Per-move allocation

1. `total = max(0, time_left + increment*(moves_to_go − 1) − move_overhead)`
2. `per_move = total / moves_to_go`
3. First move & opening bonus: `× (1 + first_move_bonus + book_ply_bonus*min(12, game_ply))`
4. `× slowmover`
5. Add carried-over "squandered"/saved time from smart pruning (`immediate-time-use` fraction).
6. Hard cap: `min(budget, time_left − move_overhead)`.

### 7.3 Defaults

| Flag | Default | File |
|---|---|---|
| `--move-overhead` (UCI `MoveOverheadMs`) | **200** ms | common |
| `--time-midpoint-move` (midpoint) | **51.5** | legacy |
| `--time-steepness` (steepness) | **7.0** | legacy |
| first-move-bonus | **1.8** | legacy |
| `--book-ply-bonus` | **0.25** | legacy |
| slowmover | **1.0** | legacy |
| `--immediate-time-use` | **1.00** | common (fraction of pruning-saved time rolled into next move) |
| `--smart-pruning-factor` | **1.33** | common (see §8) |
| `--nps-limit` | **0.0** (off) | params |
| `--ramlimit-mb` | **0** (off) | common |

---

## 8. Search Stopping / Smart Pruning

### 8.1 Early exit when best move cannot change (search.cc, in `PickNodesToExtendTask`)

A child is skipped from further visits when remaining playouts cannot let it catch the current best edge:
```cpp
if (cur_iters[idx] != current_best_edge_ &&
    EstimatedRemainingPlayouts() < best_node_n - cur_iters[idx].GetN()) {
  continue;   // hopeless this move — don't search it
}
```
When **no** other move can overtake the best on visits within the remaining time budget, the search stops early ("smart pruning"). `EstimatedRemainingPlayouts` is derived from elapsed nps × remaining time, scaled by `smart-pruning-factor` (factor >1 ⇒ prune more aggressively / stop sooner; <1 ⇒ keep searching laggards; 0 ⇒ disable).

### 8.2 Defaults (`stoppers/common.cc`)

| Flag | Default | Notes |
|---|---|---|
| `--smart-pruning-factor` | **1.33** (UCI mode); **0.00** in non-UCI/training modes | |
| `--smart-pruning-minimum-batches` | **0** | min batches before pruning may stop search |
| `--minimum-kldgain-per-node` | **0.0** (off) | KLD-gain stop (optional) |
| `--kldgain-average-interval` | **100** | |

The visit-based winner selection (most visits wins; ties broken by Q) plus smart pruning is the normal stop. There is no `Q`-vs-`Q` early stop by default beyond the visit-overtake logic.

---

## 9. Other Per-Node Strength Factors

### 9.1 Twofold repetition treated as draw in-tree (confirmed)

| Flag | Default |
|---|---|
| `--two-fold-draws` | **true** |

"Evaluates twofold repetitions **in the search tree** as draws." So inside the tree, a position repeating a second time (even though a real game needs threefold) is scored as an immediate draw terminal. This is a deliberate, strength-positive approximation (avoids wasting search re-deriving forced repetitions and helps it find/avoid perpetuals). Threefold/50-move at the actual game root are handled by real game rules.

### 9.2 Sticky endgames (confirmed)

| Flag | Default |
|---|---|
| `--sticky-endgames` | **true** |

When a proven terminal (mate / TB win-loss-draw) is found in the subtree, its exact eval is allowed to "stick" / propagate to the parent edge (overriding the noisy NN average), so the engine commits to proven results instead of letting them be diluted by the running mean. Improves endgame conversion.

### 9.3 Temperature = 0 at match play (confirmed)

| Flag | Default |
|---|---|
| `--temperature` | **0.0** ⇒ pick the best (most-visited) move deterministically |
| `--tempdecay-moves` | 0 |
| `--temp-cutoff-move` | 0 |
| `--temp-endgame` | 0.0 |
| `--temp-value-cutoff` | 100.0 |
| `--temp-visit-offset` | 0.0 |

All temperature randomization is off by default; move selection is deterministic (highest visit count, Q tiebreak).

### 9.4 WDL rescale / contempt (Elo-dependent value reshaping)

Introduced v0.30.0; default **inert** (raw WDL) in v0.31+/v0.32. Core transform (search.cc), reshaping the net's `(W,D,L)` using sharpness `s` and shift `mu`:

```cpp
auto w = (1 + v - d) / 2;
auto l = (1 - v - d) / 2;
auto a = FastLog(1 / l - 1);
auto b = FastLog(1 / w - 1);
auto s  = 2 / (a + b);          // current sharpness of the WDL
auto mu = (a - b) / (a + b);    // current location / eval offset
auto s_new  = s * wdl_rescale_ratio;                 // sharpen/soften
auto mu_new = mu + sign * s*s * wdl_rescale_diff;     // contempt shift (∝ s², Elo-derived)
auto w_new = FastLogistic((-1.0f + mu_new) / s_new);
auto l_new = FastLogistic((-1.0f - mu_new) / s_new);
v = w_new - l_new;                       // new WL
d = std::max(0.0f, 1.0f - w_new - l_new);
```
`sign` depends on contempt-mode vs side-to-move:
```cpp
auto sign = ((contempt_mode_ == ContemptMode::BLACK) == played_history_.IsBlackToMove()) ? 1.0f : -1.0f;
```
The user-facing parameters (`Contempt`, `WDLCalibrationElo`, `WDLDrawRate*`) are converted into the internal `wdl_rescale_ratio` (sharpness multiplier) and `wdl_rescale_diff` (Elo→shift, applied as `s²·diff`). The sharpness/eval relation comes from `s ≈ ( 2 / (ln(1/W − 1) + ln(1/L − 1)) )`.

User-facing defaults (params.cc), all **neutral by default**:

| Flag | Default | Effect at default |
|---|---|---|
| `--contempt` | `""` (empty) | no contempt |
| `--contempt-mode` | `play` | symmetric |
| `--contempt-max-value` | 420.0 *(Pro)* | cap on contempt Elo |
| `--wdl-calibration-elo` | **0.0** | 0 ⇒ keep raw WDL (no sharpen/soften) |
| `--wdl-draw-rate-target` | **0.0** | 0 ⇒ keep raw WDL (accepts 0 since v0.31.0-rc3, the new default) |
| `--wdl-draw-rate-reference` | 0.5 | net's nominal draw rate baseline |
| `--wdl-contempt-attenuation` | 1.0 *(Pro)* | scales contempt; recommended **0.5–0.6** for match play, 1.0 for realistic analysis |
| `--wdl-max-s` | 1.4 *(Pro)* | cap on sharpness s; raise for volatile positions |
| `--wdl-eval-objectivity` | 1.0 | how objective the reported cp eval is |
| `--wdl-book-exit-bias` | 0.65 *(Pro)* | |
| `--score-type` | `WDL_mu` | display: +1.00 ⇒ 50% win chance, comparable to Stockfish cp scale |

So **out of the box** lc0 reports raw network WDL with no contempt. For maximizing match score (e.g. vs weaker opponents or to reduce draws), the community recommendation is to set a positive `Contempt` Elo with `wdl-contempt-attenuation ≈ 0.5–0.6`.

---

## 10. Throughput (nps), Backends, and RTX 50-Series Support

### 10.1 BT4-class transformer net

"BT4" is the current top-tier **transformer** architecture (≈ 768-wide × 15 encoder blocks, 32 heads-class; the public `BT4-*` nets such as `BT4-spsa-1740` are used in TCEC/CCC). These nets are large (multi-GB on GPU) and much heavier per node than older 320×24 ResNets, so nps is correspondingly lower but each node is far stronger.

### 10.2 Typical nps (consumer Ada/Blackwell, BT4-class, batched)

Exact published BT4 nps tables on 4070/5070 are scarce; the following are representative community/order-of-magnitude figures (FP16, default-ish batch ~256–512). **Treat as ballpark — heavily dependent on net, batch, backend version, GPU clocks.**

| GPU | Backend | Approx BT4 nps |
|---|---|---|
| RTX 4070 (Ada) | `cuda-fp16` | ~12k–25k nps |
| RTX 4070 (Ada) | `onnx-trt` (TensorRT) | ~20k–40k nps (TRT usually fastest on Ada) |
| RTX 4070 | `onnx-dml` (DirectML) | ~8k–18k nps (typically slowest of the three) |
| RTX 5070 (Blackwell) | `cuda-fp16` / `onnx-trt` | higher than 4070 (Blackwell tensor cores, GDDR7); roughly ~1.5–2× the 4070 figures when TRT supports the arch |

General ordering on NVIDIA: **onnx-trt ≥ cuda-fp16 > onnx-dml** for transformer nets; FP16 (or lower) is essential — FP32 roughly halves throughput. Smaller/older nets (e.g. 320×24) run several times faster nps but are weaker per node.

### 10.3 RTX 50-series (Blackwell, sm_120) on Windows — which release/backend

- Latest stable **v0.32.1** (2025-11-23) Windows packages ship: CPU (`dnnl`, `openblas`), NVIDIA `cuda 11`/`cuda 12`/`cuDNN`, **`onnx-dml`**, and **`onnx-trt`**.
- The shipped CUDA binaries are built against **CUDA 12**; v0.32.0+ added the ability to **build with CUDA 13** in source (changelog: "Support for building with cuda 13"). CUDA 12.8/13 toolkits are what carry **sm_120 / Blackwell** device code.
- **For RTX 50-series (Blackwell) on Windows, the practical choices are:**
  1. **`onnx-trt`** (TensorRT) — recommended for best speed *if* your installed TensorRT/driver supports Blackwell (TRT 10.x with current drivers). v0.32's onnx-trt package includes an install script that fetches TensorRT.
  2. **`onnx-dml`** (DirectML) — the most hardware-agnostic Windows fallback; runs on any DX12 GPU including Blackwell without needing CUDA/TRT version matching. Use this if the CUDA/TRT builds don't yet have sm_120 kernels.
  3. The prebuilt **`cuda` (cuDNN/cuda 12)** zip may lack sm_120 cubins; it can still run via PTX-JIT if the driver's CUDA runtime is new enough (CUDA 12.8+/13), but if it errors on a 50-series card, fall back to `onnx-dml` or a CUDA-13-built binary.
- The changelog does **not** name "Blackwell / RTX 50 / sm_120" explicitly as of v0.32.1; support is implicit via CUDA 12.8+/13 builds and the onnx-trt/onnx-dml backends rather than an advertised feature.

---

## Quick Default Cheat-Sheet (v0.32.x)

```
cpuct=1.745  cpuct-base=38739  cpuct-factor=3.894   (root: identical)
fpu-strategy=reduction  fpu-value=0.330   (root: same)
policy-softmax-temp=1.359
draw-score=0.0   noise-epsilon=0.0 (no Dirichlet)   temperature=0.0
moves-left: max-effect=0.0345 threshold=0.8 slope=0.0027
            const=0.0 scaled=1.6521 quadratic=-0.6521
minibatch-size=0(=backend optimal)  max-collision-events=917  max-collision-visits=80000
max-out-of-order-evals-factor=2.4   max-concurrent-searchers=1   nncache=2000000
smart-pruning-factor=1.33  smart-pruning-minimum-batches=0
move-overhead=200ms  time-midpoint-move=51.5  time-steepness=7.0  immediate-time-use=1.0
two-fold-draws=true  sticky-endgames=true
contempt="" contempt-mode=play wdl-calibration-elo=0 wdl-draw-rate-target=0  (raw WDL)
score-type=WDL_mu
```

**Backup:** plain undiscounted running mean of leaf WL evals, sign-flipped per ply. No γ discount.
**Value:** `WL = W − L`; `Q = WL + draw_score·D`.
**Selection:** `argmax_a [ Q(a) (+M bonus) + cpuct(N)·P(a)·sqrt(ΣN)/(1+N(a)) ]`, `cpuct(N)=1.745 + 3.894·ln((N+38739)/38739)`.

### Source citations
- `src/search/classic/params.cc`, `params.h` — all search/eval/MLH/WDL/temperature defaults.
- `src/search/classic/search.cc` — `ComputeCpuct`, `GetFpu`, `GetMUtility`, PUCT edge score, `DoBackupUpdateSingleNode`, `CancelSharedCollisions`, WDL rescale transform.
- `src/search/classic/stoppers/common.cc`, `stoppers/legacy.cc` — smart-pruning & time-management defaults.
- `src/neural/shared_params.cc` — `policy-softmax-temp=1.359`, `nncache=2000000`, `history-fill=fen_only`.
- lc0 wiki "Lc0 options" / lczero.org flags & timemgr docs — cross-check of defaults.
- lczero.org blog "v0.30.0 WDL rescale/contempt" + PR #1791 — contempt/WDL semantics.
- GitHub releases + `changelog.txt` — v0.32.1 (2025-11-23) latest; CUDA 12/13 builds; onnx-trt/onnx-dml Windows packages.
```
