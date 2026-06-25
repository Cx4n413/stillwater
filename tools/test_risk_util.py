"""Definite unit test of the #1 distribution-native risk-utility readout logic.

Replicates the exact selection expression added to RustEngine._best_move and
verifies: (a) risk-seeking picks the higher-win-mass move among a value band,
(b) risk-averse picks the lower-loss-mass move, (c) a decisive tactic is a
singleton band and is NEVER overridden (the tactical-crater guard), (d) theta=0
is OFF. No oracle / GPU needed -- this isolates the new readout math.

scored tuple layout (from _scored_children after the #1 edit):
  (q, qt, evals, uci, var, dist, zeroing, W_our, D, L_our)   indices 0..9
"""


def risk_pick(scored, risk, risk_band):
    """Byte-for-byte the branch added to _best_move. Returns the chosen uci, or
    None when the branch does not fire (caller falls through to robustpick)."""
    if risk == 0.0:
        return None                      # OFF -> robustpick stands
    qmax = max(s[0] for s in scored)
    band = [s for s in scored if s[0] >= qmax - risk_band]
    if len(band) <= 1:
        return None                      # singleton band -> tactic untouched
    w_w = 1.0 + max(0.0, -risk)          # seeking up-weights wins
    w_l = 1.0 + max(0.0, risk)           # averse up-weights losses
    bp = max(band, key=lambda s: (w_w * s[7] - w_l * s[9], s[0], s[2]))
    return bp[3]


def mk(uci, q, w, d, l, evals=10):
    return (q, 0.0, evals, uci, 0.0, 0, 0, w, d, l)


def main():
    # Two near-equal-MEAN moves in the same value band (both q~0.05):
    #   SHARP: high win / high loss   W=.50 D=.05 L=.45
    #   SAFE : low  win / low  loss   W=.30 D=.45 L=.25
    sharp = mk("a1a2", 0.05, 0.50, 0.05, 0.45)
    safe = mk("b1b2", 0.05, 0.30, 0.45, 0.25)
    band = [sharp, safe]

    assert risk_pick(band, -0.9, 0.10) == "a1a2", "seeking must take the sharp/high-win move"
    assert risk_pick(band, +0.9, 0.10) == "b1b2", "averse must take the safe/low-loss move"
    assert risk_pick(band, 0.0, 0.10) is None, "theta=0 must be OFF (fall through)"

    # Decisive tactic: one move dominates on value -> singleton band -> the risk
    # utility must NOT override it (this is the load-bearing safety guard).
    tactic = mk("c1c2", 0.80, 0.85, 0.10, 0.05)
    quiet = mk("d1d2", 0.05, 0.30, 0.45, 0.25)
    assert risk_pick([tactic, quiet], -0.9, 0.10) is None, "decisive tactic must be a singleton band"
    assert risk_pick([tactic, quiet], +0.9, 0.10) is None, "decisive tactic must be a singleton band"

    # A risk-averse posture must never trade a clearly-better-MEAN move inside
    # the band for a worse-mean one purely on tails: the (util, q, evals) key
    # keeps q as the tie-breaker, and the band itself bounds the mean loss.
    near_best = mk("e1e2", 0.20, 0.55, 0.10, 0.35)   # best mean, sharp
    slightly = mk("f1f2", 0.12, 0.40, 0.40, 0.20)    # within 0.10 band, safe
    # averse strongly prefers low loss here (0.20 < 0.35), within the 0.10 band:
    assert risk_pick([near_best, slightly], +0.9, 0.10) == "f1f2"
    # but with a TIGHT band the safe move drops out -> best-mean move stands:
    assert risk_pick([near_best, slightly], +0.9, 0.05) is None

    print("ALL RISK-UTILITY UNIT TESTS PASSED")


if __name__ == "__main__":
    main()
