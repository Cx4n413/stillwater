# The +164 gap: a measured decomposition (no-tree-scaling branch)

**Question:** can a no-tree belief-lattice be made to "scale with compute like a
tree," closing the measured +164 Elo gap between lc0 (MCTS) and STILLWATER on the
*same* BT4 net?

**Short answer:** the move-quality part of the gap is **small (+3pp at matched
compute), structural, and tree-specific** — it resists every no-tree backup/readout
lever, and it is *not* a scaling deficit (lc0 doesn't scale these positions either;
it wins them by tree structure at all node counts). A large part of the headline
+164 is **throughput** (the original measurement throttled SW on DirectML), which
the CUDA backend recovers. The pure "no-tree that scales like a tree" goal rests on
a premise the data does not support.

## What was measured (all at the deployed config, CUDA, matched nodes)

### 1. No internal lattice signal separates the best move from its drifting rival
On the depth_unstable ("drift") positions — the 62% bucket — the lattice's three
internal signals all AGREE with each other and all fail to recover SF-best M:

| signal | recovers M on drift |
|---|---|
| value-argmax | 74% |
| visit-argmax | 70% (visits concentrate, share 0.53, but on the SAME move as value) |
| value-geometry (PV singularity) | no asymmetry: pv_margin ≈ 0 for both M and the overtaker |

→ There is **no state-level discriminator**. (This is why SMAB was killed by its
premise gate before any build, and why confback / verify-deepen / anti-drift / IVR
all washed: they all read off the same selection that concentrates on the value-leader.)

### 2. The backup rule is not the lever
On the same drift positions:

| backup | recovers M |
|---|---|
| MAX (deployed) | 74% |
| MEAN (R_MEANBACK) | **64% — worse** |
| lc0 (mean over a PUCT-concentrated tree) | **85%** |

→ lc0's 85% is **above both** lattice endpoints. The whole annealed-blend family
(confback, SMAB, LEASB) interpolates between 74% and 64% — both below lc0. lc0's
edge is averaging *plus* concentration on the best line, a property of the **tree
structure**, which the shared-node DAG cannot represent.

### 3. lc0's advantage is structural, not scaling
lc0 on the drift positions: 4k→85%, 16k→85%, 40k→83% (**flat**). MCTS doesn't
"think longer to find M" here — it gets them by structure at all node counts. So
"scale with compute like a tree" mis-frames the prize.

### 4. The real gap, sized directly (lc0-vs-lattice, not lattice-vs-SF)
120 clear-best positions, matched 16k nodes:
- **AGREE 91%**, DISAGREE 9%.
- Overall SF-best recovery: **lattice 90%, lc0 93% (+3pp)**.
- On the 11 disagreements: lc0 plays M 55%, lattice 18%, neither 27% (net-limited).
- Decisive disagreements: 6 → lc0 right 3, lattice right 1.

→ At matched compute the lattice is a **strong engine ~3pp behind lc0**, with the
gap concentrated on ~9% hard positions where lc0's tree wins ~3×. At 3400+ Elo a
+3pp move-quality edge, compounded over games, is consistent with a large Elo gap.

## Why no *pure* no-tree lever closes it
Every readout/backup statistic (value, mean, max, visits, edge-Q, singularity)
feeds off the lattice's **selection**, which concentrates compute on the current
value-leader. On the drift positions that leader is the *wrong* move, so every
statistic inherits the same wrong concentration — a circular trap. lc0 escapes it
because a **tree gives each position a path-separated rollout-mean** that favors M
from low node counts, before concentration sets in. "No-tree" is precisely the
choice that gives up that path-separation — so the residual gap is, to first order,
*inherent to the no-tree premise*, not a tunable.

## Recommendations (tiered, honest)
1. **Deploy the CUDA backend** (built, `sw-gpu-venv`). This recovers the throughput
   slice of the +164 — the single largest *recoverable* chunk — with no model or
   search change. No-regret. (Gated behind your sign-off since it touches the live
   bot.)
2. **Finish the anti-drift gauntlet** properly (targets the 62% drift bucket; the
   manual read was mildly positive; it never got a clean number). Small, real.
3. **Accept the structural residual** (~3pp, tree-specific) as near the no-tree
   paradigm ceiling — OR —
4. **Go hybrid** if you want the residual: no-tree lattice by default, invoke a
   small selective tree search on the ~9% hard/sharp "disagreement" positions where
   lc0's structure wins. This directly targets the measured gap but compromises the
   pure no-tree premise. It is the only path the data supports for the residual.

## Reusable artifacts added this branch
- `core-rs` `pv_child_gaps` — read-only PV introspection (per-ply best/2nd child q).
- `tools/smab_premise.py`, `visit_premise.py`, `meanback_test.py`,
  `mcts_compare.py`, `lc0_vs_lattice.py` — the premise gates and lc0 comparisons above.
