# STILLWATER

STILLWATER is a chess engine with **no game tree**. There is no alpha-beta,
no depth-first iterative deepening, no MCTS rollouts, no visit counts, no
PUCT descent-and-backup. Instead, it uses a lattice (like a "pond", hence the name) of "beliefs" (W/L/D, certainty, best moves)about positions it has seen (so no position is counted twice), and when new evaluations flow in, the whole thing settles toward a new, more informed equilibrium (the "water goes still"). The benefits of my architecture are that it can play blitz and even bullet at around the same level as rapid due to it's near-perfectly efficient time control (it relies on the evaluation stagnating as the move clock).

I can't be bothered to write a description of all of its parts at the moment. I posted a slightly more detailed version of its contents as well as answered a lot of questions about the model [here](https://www.reddit.com/r/ComputerChess/comments/1uqyjqj/an_entirely_new_kind_of_chess_engine_with_no_tree/)

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
