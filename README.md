# STILLWATER

*The engine that thinks by letting the water settle.*

STILLWATER is a chess engine with **no game tree**. There is no alpha-beta,
no depth-first iterative deepening, no MCTS rollouts, no visit counts, no
PUCT descent-and-backup. Instead:

> A neural guess, a lesson learned mid-move, and a machine-checked result are
> the same object at three precisions — a belief with variance, a belief whose
> variance is being updated, and a belief with variance zero. One persistent
> position-keyed lattice of beliefs, relaxed to its fixed point by prioritized
> backward induction, **is** the search, the transposition table, the learner,
> and the proof store simultaneously.

## Architecture

| Component | File | What it does |
|---|---|---|
| **The Lattice** | `stillwater/lattice.py` | Position-keyed belief store with parent back-pointers. Transpositions merge by construction; the table survives between moves, so re-rooting after the opponent replies is a no-op. Keys are salted with fifty-move-counter buckets and a repetition flag so legality-relevant state splits the entry. |
| **The Settling Engine** | `stillwater/search.py` | Prioritized dirty-queue relaxation: any node whose belief moves gets re-backed-up and its parents enqueued, so a refutation discovered at the frontier reaches the root in one pass. The per-ply discount makes the backup a contraction — repetition cycles damp toward draws by theorem, and nearer mates outrank farther ones for free. |
| **The Broker** | `stillwater/search.py` | Decides which frontier leaves to buy next: settled value + prior-weighted exploration + uncertainty bonus; proven subtrees price at zero. (v0 stand-in for the trajectory-head pricing of the full design.) |
| **The Oracle** | `stillwater/oracle.py` | A strong pretrained Lc0 network running on the GPU (DirectML), emitting a *distribution* (W/D/L) per position, not a scalar. The full design replaces this with a self-trained net plus the effort-conditioned trajectory head. |
| **The Palimpsest** | `stillwater/palimpsest.py` | The evaluator rewrites itself during the move: per pawn-structure × material context, a conjugate Normal posterior over an eval correction, updated in closed form from settled-search-vs-raw-eval disagreements, applied to every future evaluation in that context — re-pricing positions the search never visited. |
| **The Root Court** | `stillwater/court.py` | Stopping as inference: maintains P(current argmax is truly best) by joint posterior sampling and moves when it clears a clock-derived bar. Recaptures snap in milliseconds; critical decisions absorb banked time. No move-time heuristics exist anywhere. |
| **Proofs** | woven through | Checkmates, stalemates, path-repetitions, and the fifty-move rule enter the lattice as **pinned, variance-zero beliefs**; proof status propagates rootward through the ordinary dirty queue (a proven losing reply proves the parent won, regardless of unexplored siblings). A proven win at the root ends deliberation instantly. |

The full design (see the project pitch) adds the effort-conditioned
trajectory head — quantiles of *what further search will conclude* — the
512-d feature-space Palimpsest, GPU retrograde slice solving, and fortress
certificates. This v0 is the substrate those bolt onto.

## Run it

```
# play in the terminal (engine thinks ~10s/move)
python play.py
python play.py --black --movetime 20

# as a UCI engine (Arena, BanksiaGUI, cutechess, ...)
python -m stillwater.uci

# core tests, no GPU needed
python tests/test_core.py
```

Requires: Python 3.11+, `python-chess`, `numpy`, `onnxruntime-directml`,
and a converted network in `nets/` (see `ORACLE_NOTES.md`).

## Honest status

- v0.1: substrate + pretrained Oracle. The search is GPU-batched best-first
  over the lattice; selection is prior/uncertainty-guided (PUCT-adjacent by
  design — the genuinely new pricing signal, the trajectory head, requires
  the training pipeline).
- Target strength on an RTX 5070 + Ryzen 5700X: 3000+ Elo verified against
  calibrated Stockfish; far below full Stockfish on the same box, which is
  expected and honest for a from-scratch paradigm (see pitch, "Honest risks").
