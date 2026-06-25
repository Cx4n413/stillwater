"""Quantify the transposition-GRAPH advantage of the belief lattice over a
search TREE, at equal eval budget. STILLWATER keys beliefs by position (Zobrist
+ rule50 bucket + repetition salt), so a position reached by several move orders
is ONE node with several parents -- its evaluation is shared, where a tree would
recompute it on every path. core.graph_stats() exposes (nodes, parent_edges,
multi_parent_nodes, max_parents); the surplus edges over a tree's (nodes-1) is
exactly the reuse a tree lacks.

Reports, per position and pooled:
  - multi_parent_share = multi_parent_nodes / nodes   (how much of the lattice
    is genuinely graph-structured)
  - tree_edge_surplus  = parent_edges - (nodes-1)      (extra path-arrivals that
    landed on an already-known position -- evals a tree would have duplicated)
  - reuse_ratio        = parent_edges / max(1, nodes-1)  (>1 => sharing)

Run (base env): python tools/graph_advantage.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import chess  # noqa: E402

NODES = int(os.environ.get("GA_NODES", "8000"))

# Transposition density varies by position type. Openings/manoeuvring middle-
# games have many move-order transpositions; forcing tactical lines have few
# (each capture/check is near-unique). We expect reuse_ratio >> 1 for the former.
POSITIONS = [
    ("start (many move orders)", chess.STARTING_FEN),
    ("English/QGD transposition web",
     "rnbqkb1r/pp2pppp/3p1n2/2p5/2P5/2N2N2/PP1PPPPP/R1BQKB1R w KQkq - 0 4"),
    ("manoeuvring middlegame (closed)",
     "r1bq1rk1/pp1nbppp/2p1pn2/3p4/2PP4/2N1PN2/PPQ1BPPP/R1B2RK1 w - - 0 9"),
    ("forcing tactic (few transpositions)",
     "2rr3k/pp3pp1/1nnqbN1p/3pN3/2pP4/2P3Q1/PPB4P/R4RK1 w - - 0 1"),
    ("K+P endgame (move-order rich)",
     "8/p5k1/1p4p1/2p1p1p1/2P1P1P1/1P3PK1/P7/8 w - - 0 1"),
]


def main():
    from stillwater.oracle import LeelaOracle
    from stillwater.engine_rs import RustEngine
    oracle = LeelaOracle()
    print("provider:", oracle._sess.get_providers()[0], flush=True)
    eng = RustEngine(oracle=oracle, batch=128, refine=True)

    print(f"\n=== transposition-graph reuse @ {NODES} nodes/move ===\n",
          flush=True)
    rows = []
    for name, fen in POSITIONS:
        eng.new_game()
        eng.think(chess.Board(fen), node_budget=NODES)
        nodes, edges, multi, maxp, parented = eng.core.graph_stats()
        # honest denominator: nodes actually linked into the relaxation graph
        surplus = edges - parented          # extra parent links beyond a tree
        reuse = edges / max(1, parented)    # avg parents per linked node (>1 => graph)
        mshare = multi / max(1, parented)   # share of linked nodes that transpose
        rows.append((name, nodes, parented, edges, multi, maxp, surplus, reuse,
                     mshare))
        print(f"# {name}")
        print(f"  nodes={nodes}  linked={parented}  parent_edges={edges}  "
              f"multi_parent={multi} ({100*mshare:.1f}% of linked)  "
              f"max_parents={maxp}")
        print(f"  surplus_edges(vs tree)={surplus}  parents/linked={reuse:.3f} "
              f"(=1.0 would be a pure tree)", flush=True)

    n = len(rows)
    print("\n=== POOLED ===")
    print(f"mean multi_parent_share (of linked nodes): "
          f"{sum(r[8] for r in rows)/n*100:.1f}%")
    print(f"mean parents/linked (1.0 = tree, >1 = graph): "
          f"{sum(r[7] for r in rows)/n:.3f}")
    print(f"total surplus edges (positions a tree would re-evaluate): "
          f"{sum(r[6] for r in rows)}")
    print("\nREADING: among nodes linked into the relaxation graph, parents/"
          "linked > 1 means positions reached by multiple move orders are stored"
          " ONCE -- each surplus edge is an eval a tree duplicates per path. The"
          " forcing tactic is a near-pure tree (max_parents=1); move-order-rich "
          "phases (openings, K+P endgames) carry the real graph reuse.")


if __name__ == "__main__":
    sys.exit(main())
