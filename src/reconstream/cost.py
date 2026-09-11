"""What a reconciliation mistake costs.

Two errors, with different shapes.  A **false break** is an exception raised
against a movement that did settle: nothing is lost, but an analyst is paid to
discover that, and in the deployments this models a break also freezes the
counterparty's funds or triggers a dunning notice.  Its cost is roughly fixed
per item.  A **false match** is the reverse: a movement that never reached the
bank is marked reconciled, so the shortfall leaves the exception queue and
stops being looked for.  Its cost scales with the amount.

The third cost is not an error at all.  Holding an item undecided has a
carrying cost -- the books cannot close, and the working capital behind the
movement is neither released nor written off.  Including it is what stops
"never decide anything" from being the optimum, and it is why the liveness
property in the contract has teeth rather than being an aesthetic preference.

The numbers are defensible rather than measured, in the same spirit as P1's
economic constants, and every headline figure is re-run across a sweep in
``experiments/e5_costs.py``.  Counts and rates are the primary results; the
monetary view is a sensitivity analysis on top of them, and is labelled as such
wherever it appears.
"""

from __future__ import annotations

#: Cost of investigating one reconciliation break, in cents.  Twenty minutes of
#: a loaded reconciliation analyst, which is the figure operations teams use
#: when sizing an exception queue.  P1 charges $18 for a fifteen-minute
#: escalation; this is the same rate over a longer task.
BREAK_INVESTIGATION = 2400

#: Fraction of a falsely matched shortfall that is never recovered.  A movement
#: marked reconciled leaves the queue, and is then found only by a later
#: periodic control, if at all.  Sweeping this between 0.2 and 1.0 does not
#: change the ordering of the reconcilers.
UNRECOVERED_FRACTION = 0.60

#: Carrying cost per tick for an item still undecided, in cents.  Deliberately
#: small: it should make dithering expensive over long horizons without letting
#: a reconciler buy a good score by being hasty.
CARRY_PER_TICK = 2


def false_break_cost(n: int) -> int:
    return n * BREAK_INVESTIGATION


def false_match_cost(amounts: list[int]) -> int:
    total = sum(amounts)
    scaled = total * UNRECOVERED_FRACTION
    return int(scaled + (0.5 if scaled >= 0 else -0.5))


def carry_cost(total_ticks: int) -> int:
    return total_ticks * CARRY_PER_TICK


def total_cost(
    *,
    false_breaks: int,
    false_match_amounts: list[int],
    carried_ticks: int,
    break_investigation: int = BREAK_INVESTIGATION,
    unrecovered: float = UNRECOVERED_FRACTION,
    carry_per_tick: int = CARRY_PER_TICK,
) -> dict:
    """Itemised cost, so a table can show where a reconciler loses its money.

    Parameters are explicit rather than read from module state so the sweep can
    vary one at a time without reimporting.
    """
    fb = false_breaks * break_investigation
    scaled = sum(false_match_amounts) * unrecovered
    fm = int(scaled + (0.5 if scaled >= 0 else -0.5))
    cc = carried_ticks * carry_per_tick
    return {
        "false_break_cost": fb,
        "false_match_cost": fm,
        "carry_cost": cc,
        "total": fb + fm + cc,
    }
