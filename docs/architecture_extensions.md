# STILLWATER — Architectural Extensions (research notes)

These notes document three structural additions to the belief-lattice engine,
implemented in the Rust core (`core-rs/src/engine.rs`) and validated by
behavioral characterization rather than Elo. They are written for the paper:
each is motivated by a gap in the v0 design, specified precisely, and reported
honestly including a failed first attempt and the limits of what was measured.

All three are **gated**: with the gate off the default search path is
**bit-identical** to the prior build (verified — see Soundness). Nothing here
changes shipped play until deliberately enabled.

---

## 0. The gap they close

The README's own *Honest status* names it:

> the search is GPU-batched best-first over the lattice; **selection is
> prior/uncertainty-guided (PUCT-adjacent by design** — the genuinely new
> pricing signal … requires the training pipeline).

So the thesis — *"one persistent position-keyed lattice of beliefs, relaxed to
its fixed point"* **is** the search — was true for the **backup** (prioritized
graph relaxation, minimax-max, per-ply contraction, proofs as variance-zero
pinned beliefs) but **not for the selection**. The broker still scored frontier
leaves with PUCT: `cpuct · prior · √N / (1+n)`. That is MCTS machinery bolted
onto a graph. A belief-lattice search should decide *what to evaluate next* from
the **beliefs** — specifically from where uncertainty, if resolved, would most
change the decision — not from a visit-count exploration bonus.

Extensions 1–2 build that. Extension 3 quantifies the one structural advantage
the lattice already had over a tree but never measured: transposition reuse.

---

## 1. Epistemic / aleatoric uncertainty split (+ graph propagation)

**Idea.** A node's value uncertainty has two components that the v0 lattice
conflated into one `variance` field:

- **Aleatoric** — the position's *intrinsic* sharpness. Search cannot remove it.
  Already present as `wdl_variance(w,d,l) = (w+l) − (w−l)²`. A position that is
  genuinely 50/50 stays uncertain no matter how deep you look.
- **Epistemic** — *reducible-by-search* uncertainty. A fresh leaf's value rests
  on a single net glance; expanding it and relaxing the subtree drives this
  toward zero. This is the quantity a value-of-information rule must reason
  about, and it did not exist.

**Implementation.** A new `Node.epistemic: f64`.
- Fresh leaf → `EPI0 = 1.0` (maximal; value rests on one glance).
- Proven node (mate / TB / pinned) → `0.0` (certain).
- Propagated in `backup()` for every internal node:

  ```
  epistemic(node) = EPI_DECAY · epistemic(winning child)        ── inherited
                  + Σ_{sibling s} closeness(v_s, v_best) · epistemic(s)   ── ambiguity
                  + (1 − visited_policy_mass) · EPI0 · closeness(fpu, v_best)
  ```
  with `EPI_DECAY = 0.75`, `closeness(a,b) = exp(−(a−b)² / 2·VOI_TAU²)`,
  `VOI_TAU = 0.10` (value units).

  The first term is the residual uncertainty of the line we believe is best,
  contracted one ply (each resolved level of search shrinks it). The second is
  **argmax ambiguity** — uncertainty about *which* child is best, summed over
  siblings whose value is close enough to contend, weighted by how uncertain
  *they* are. The third treats unexplored policy mass sitting near the best
  value as live uncertainty (a move we have not looked at might be best).

This makes uncertainty a **propagated graph quantity**, like value and proof
status — not a per-node constant. A deep, settled, one-sided subtree reports low
epistemic; a shallow or genuinely contested one reports high.

---

## 2. Value-of-information selection — the belief-driven broker

**Idea.** Replace the PUCT descent with: *expand the child whose resolution most
reduces this node's decision uncertainty.* A child is worth evaluating to the
extent that (a) it is still uncertain (high epistemic — there is something to
learn) **and** (b) it could plausibly overturn the current best (its value is
close to the leader). Confidently-worse moves and already-settled leaders both
score low.

```
VOI(child) = epistemic(child) · closeness(v_child, v_best)        (expanded)
VOI(child) = EPI0 · closeness(v_best, v_best) · policy_prior       (unexpanded)
```

selected by argmax, with an in-flight-count divisor so a GPU batch spreads
across contenders instead of piling onto one. Unexpanded children enter at the
node's current value as an optimistic prior (so exploration is *policy-ordered*
— BT4 still picks which unseen move to look at first — but not *policy-driven*
thereafter).

### 2a. The first attempt failed — and the failure is informative

v1 scaled the closeness kernel by the children's *own* combined epistemic:
`closeness = exp(−gap² / 2(σ²_best + σ²_child))`. The intent was "near in units
of uncertainty." The effect was pathological: while everything is fresh
(σ ≈ EPI0 = 1), the denominator is ≈ 4, so a **hung-piece** move (gap ≈ 1.0)
still scores `exp(−0.25) ≈ 0.78`. The kernel could not distinguish a good move
from a blunder, and since VOI then reduced to "expand whatever is most
uncertain," the search degenerated to **breadth-first expansion of losing
moves**. The characterization caught it red-handed — in a won rook endgame the
search split its evals four ways across `c3d2 / c3b4 / c3a5 / c3e1`, every one a
way to drop the bishop (all ≈ −0.98).

> **Finding for the paper:** a value-of-information rule whose relevance kernel
> is scaled by the candidates' own uncertainty is unstable in the
> high-uncertainty regime — it rewards uncertainty without anchoring on value
> and collapses to undirected breadth. The relevance scale must be *fixed*.

### 2b. The fix

v2 uses a **fixed decision-relevance scale** `VOI_TAU = 0.10` in the closeness
denominator. Now a hung piece (gap ≈ 1.0) scores `exp(−50) ≈ 0` and is abandoned
immediately; only moves whose value sits within ~`TAU` of the best stay live,
and among those the **most epistemically uncertain** is resolved first.

### 2c. Behavioral characterization (`tools/voi_characterize.py`)

Equal node budget (4000/move), one shared oracle, fresh engines. The question is
**not** strength (the engine is eval-bound, §4) but whether the search became
genuinely belief-driven.

| position | PUCT alloc | VOI alloc |
|---|---|---|
| WAC tactic (decisive) | g3g6 50% | g3g6 **61%** — commits *harder* |
| won rook endgame | g1f2 58% | g1f2 57% — agrees, abandons losers |
| quiet QGD (several ≈) | f1d1 44%, concentrated | spreads b2b3/h2h3/f1d1 ≈ 0.10 |
| opposite-castling race | **f1c4 83%** (policy favorite) | **f1b5/f1c4 split**, prefers f1b5 |

Pooled: VOI mean effective-branching 4.67 vs PUCT 3.17; mean top-1 share 0.41 vs
0.51. So VOI is **position-adaptive**: it concentrates *harder* than PUCT when
the eval signal is decisive, and distributes across genuine contenders when
several moves are near-equal.

The decisive metric is the **value/prior-conflict** test. On the 5/6 positions
where BT4's top-*policy* move differs from the top-*value* move, where does the
eval mass go?

|   | follows the **value** | follows the **policy prior** |
|---|---|---|
| **PUCT** | 0.6 | **0.8** |
| **VOI** | 0.6 | **0.0** |

PUCT routes its compute to BT4's policy favorite 80% of the time — it is
**prior-driven**. VOI routes it there **0%** of the time; it follows the value —
it is **belief-driven**. The opposite-castling position is the concrete witness:
PUCT spends 83% on `f1c4` because the policy loves it; VOI splits `f1b5/f1c4`
because their *values* are tied (+0.04 vs +0.02) and ends up preferring the
higher-value `f1b5`.

> *(The naive rank-correlations `ρ(closeness, share)` and `ρ(prior, share)` do
> **not** separate the two rules — both ≈ 0.7–0.8 — because Spearman over all
> legal moves is dominated by the long tail of unexplored moves with share ≈
> prior ≈ closeness ≈ 0. The signal lives in the head of the distribution; the
> conflict-position metric isolates it. This confound is worth stating in the
> paper as a methodological note.)*

### 2d. The cost of decoupling — VOI loses tactical solve-rate (the key tradeoff)

WAC-200 solve-rate at 1 s/move, same positions, only `STILLWATER_VOI` flipped:

| | solve rate | avg nodes |
|---|---|---|
| PUCT (VOI off) | **96.0%** (192/200) | 647 |
| VOI (on) | **88.0%** (176/200) | 662 |

A consistent **−8 points** (the gap is steady across the run, on identical
positions — not leak noise). This is **not** a crater — honest-max, by contrast,
fell to 75.7% — but it is a real, on-thesis cost, and it is the most important
single finding here:

> **Decoupling selection from the policy prior discards information.** BT4's
> policy is a strong *tactical* move-orderer (the net was trained to see tactics),
> and PUCT consumes it directly via `prior · U`. VOI, by scoring *expanded*
> children on belief alone (`prior_w = 1`), throws that ordering away once a move
> is expanded — and its higher effective branching (4.67 vs 3.17) then spreads
> the fixed time-budget too thin to drill the one deep winning line. On sharp
> tactics the policy prior *is* the signal, and a pure value-of-information rule
> that ignores it searches broad where it should search deep.

This is the eval-bound thesis once more, now on the *selection* side: just as
more search ≈ 0 Elo because BT4's *value* is the ceiling, pure belief-driven
selection costs tactics because BT4's *policy* carries real information a
value-only rule cannot recover. It also points cleanly at the fix (future work,
§3¾ and below): the practical rule is a **hybrid** that keeps a policy-prior
term on expanded moves — VOI for *which contested move to resolve*, policy for
*how much tactical benefit of the doubt a line still deserves* — or the learned
trajectory head, which would encode the tactical signal the hand-crafted
`epistemic` lacks.

---

## 3. The transposition-graph advantage, quantified (`tools/graph_advantage.py`)

The lattice keys beliefs by position (Zobrist + rule50 bucket + repetition
salt), so a position reached by several move orders is **one** node with several
parents — evaluated once where a tree recomputes it per path. This was a design
claim never measured. `core.graph_stats()` now exposes it. Among nodes linked
into the relaxation graph (8000 evals/move):

| position type | multi-parent share | max parents | parents/linked |
|---|---|---|---|
| forcing tactic | **0.0%** | **1** | **1.000** (a pure tree) |
| closed middlegame | 8.3% | 4 | 1.091 |
| QGD/English web | 12.7% | 4 | 1.141 |
| start | 14.6% | 4 | 1.166 |
| K+P endgame | **73.5%** | **9** | **2.820** |

The result is exactly what theory predicts and is its own control: forcing
tactical lines have **no** transpositions and the graph degenerates to a pure
tree (1.000×, max 1 parent); move-order-rich phases carry the reuse, peaking in
pawn endgames where the lattice stores positions **once** that a tree would
re-evaluate ~2.8× on average (some reached 9 distinct ways). Pooled mean reuse
1.44×; 10,264 surplus parent-edges across the suite are evaluations a tree
would have duplicated. This is the eval-efficiency the graph structure buys —
free, and largest exactly where chess move-order convergence is greatest.

---

## 3½. Relation to the full design — VOI is the trajectory head, hand-built

The project pitch's endgame for selection is an **effort-conditioned trajectory
head**: a learned output emitting *quantiles of what further search will
conclude* about a position, used to price which leaf to buy next. That is, in
the language of decision theory, a **learned value-of-information** — it predicts
how much, and in which direction, more search would move a belief.

The VOI rule here is that same object **built by hand instead of learned**:
`epistemic` is a closed-form stand-in for "how much would further search move
this value" (the spread the trajectory head would predict), and the closeness
kernel is the "would that movement change the decision" gate. So Extension 2 is
not a detour from the design — it is the design's selection vision realized
without the training pipeline, and it demonstrates the vision is *coherent and
implementable*: a belief-lattice can be driven end-to-end by value-of-
information rather than by borrowed PUCT. When the trajectory head is later
trained, it drops into exactly this slot, replacing the hand-crafted `epistemic`
+ `closeness` with learned quantiles — the selection plumbing (two-pass scan,
in-flight damping, policy-ordered exploration of unexpanded moves) is unchanged.

## 3¾. The natural next unification — epistemic-aware stopping

The Root Court already stops on `P(argmax is truly best)`, sampling each move's
posterior with `std = √(variance/(1+evals) + τ²)` — a *local, count-based*
epistemic proxy. The propagated `epistemic` field is a strictly better posterior
width for that same test: it carries argmax-ambiguity from deep in the subtree,
not just the local visit count, so a root move that looks settled locally but
sits above an unresolved deep fork reports the wide posterior it deserves.

The unification (designed, **not built here** — it adds an uncalibrated term to
the engine's most delicately-tuned component and stopping quality can only be
judged by timed gauntlets, which are saturated): blend the propagated epistemic
into `RootCourt.p_best`,
`std = √(variance/(1+evals) + k·epistemic² + τ²)`, gated under `voi_on` so the
default Court is byte-identical. Then **one** uncertainty model drives both
*where to look* (VOI selection) and *when to stop* (the Court) — the clean
Bayesian closure the paper should make, with `k` set by an SPSA/grid pass against
a timed instrument before it is trusted. `core.graph_stats` and the per-child
plumbing this would need (expose `epistemic` as a 13th field on
`root_children`, append-only so the existing `F_*` indices are untouched) are
the only mechanical prerequisites.

---

## 4. Soundness and honest limitations

**Soundness.** Every extension is gated (`set_voi`, `STILLWATER_VOI=1`;
epistemic maintained only when VOI is on; `graph_stats` is read-only). With VOI
off, two independently-constructed engines produce **bit-identical** root eval
distributions on every test position (`PUCT-deterministic=True` throughout) —
the default path is provably unperturbed. The epistemic field and VOI branch are
dead code unless enabled.

**Limitations, stated plainly:**

1. **VOI is not, as-is, a strength improvement — and that is reported, not
   hidden.** At a fixed 1 s budget it solves 8 points fewer WAC tactics than
   PUCT (§2d). The contribution is the *paradigm* (selection driven by value-of-
   information on a belief lattice, demonstrably belief- rather than policy-
   driven) and the *characterization of its tradeoff* (it discards the policy
   prior's tactical signal), not a "we beat PUCT" claim — which would in any case
   be suspect given the engine is **eval-bound** (more/better-directed search ≈
   0 Elo against the same net; the 2.3× ≈ 3.4× ≈ 0 finding). A timed
   VOI-on-vs-off game gauntlet would quantify the full-game cost; the WAC result
   already says the honest headline is "coherent and belief-driven, but pays for
   ignoring the policy — the hybrid is the practical rule."
2. **Small position sample** (6 for VOI, 5 for the graph study) — enough to
   establish the qualitative behavior and the conflict-position separation, not
   to put error bars on the pooled means.
3. **`VOI_TAU`, `EPI_DECAY`, `EPI0` are untuned** first-principles constants.
   The v1→v2 episode shows the rule is sensitive to the *form* of the relevance
   kernel (fixed vs uncertainty-scaled); it is presumably also sensitive to
   `TAU`'s magnitude, which has not been swept.
4. **Parent backrefs are recorded only for nodes linked into the relaxation
   graph** (~35% of created nodes at these budgets; the rest are glanced-but-
   unlinked leaves). The graph-advantage numbers use the linked count as the
   honest denominator, so they describe the *relaxed* subgraph, not every node
   the oracle ever touched.

## 5. Reproduce

```
# behavioral characterization: VOI vs PUCT, equal nodes, one oracle
python tools/voi_characterize.py            # → games/voi_characterize.json

# transposition-graph reuse vs a tree
python tools/graph_advantage.py

# enable the belief-driven broker in normal play (UCI / matches)
set STILLWATER_VOI=1
```

Implementation: `core-rs/src/engine.rs` (`Node.epistemic`, `backup()`
propagation, the `voi_on` branch in `score_moves`, `graph_stats`); pyo3 bindings
in `core-rs/src/lib.rs`; env wiring in `stillwater/engine_rs.py`.
