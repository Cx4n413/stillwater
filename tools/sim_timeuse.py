"""GPU-free proof that the TIMEUSE spend-the-bank floor never flags + shows how
much more time it uses. Replays court.budgets() over an 80-move game under three
spend policies and tracks the clock. The floor (0.6*soft) sits below soft below
the clock/12 hard cap, so the MAX per-move spend is unchanged from baseline; the
'maxhard' policy (spend the cap every move) is the true worst case."""

def budgets(clock, inc, moves_played):
    horizon = max(24.0, 64.0 - moves_played)
    soft = clock / horizon + 0.8 * inc
    rich = clock > 8.0 * soft
    hard = soft * (1.5 if rich else 1.2)
    hard = min(hard, clock / 12.0)
    margin = max(0.08, clock * 0.04)
    soft = min(soft, max(0.05, clock - margin))
    hard = min(hard, max(0.05, clock - margin))
    return soft, max(soft, hard), rich

def sim(base, inc, policy, moves=80):
    clock = float(base); spent = 0.0; minclock = clock; flagged = False
    for m in range(moves):
        soft, hard, rich = budgets(clock, inc, m)
        if policy == "snap":           # current banking behavior: stop fast
            spend = min(0.15 * soft, hard)
        elif policy == "timeuse":      # spend 0.6*soft floor while rich
            spend = min(0.6 * soft if rich else 0.15 * soft, hard)
        else:                          # maxhard: worst case, spend the cap
            spend = hard
        if spend >= clock:             # would flag
            flagged = True; spend = max(0.0, clock - 0.05)
        clock -= spend; spent += spend
        clock += inc                   # increment after the move
        minclock = min(minclock, clock)
    return spent, minclock, flagged

for base, inc in [(60, 1), (180, 2), (300, 3), (120, 1), (60, 0)]:
    print(f"\n=== TC {base}+{inc} (80 moves) ===")
    for pol in ("snap", "timeuse", "maxhard"):
        spent, mn, fl = sim(base, inc, pol)
        print(f"  {pol:8} total_spent={spent:7.1f}s  min_clock={mn:6.1f}s  "
              f"FLAGGED={fl}")
