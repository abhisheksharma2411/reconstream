"""E5 -- does the conclusion survive the cost constants?

The monetary figures in this paper rest on three numbers that were argued for
rather than measured: what it costs to investigate a break, how much of a
falsely-matched shortfall is never recovered, and what carrying an undecided
item costs per tick.  A conclusion that only holds at one setting of those is
not a conclusion about reconciliation, it is a conclusion about the constants.

So each is swept over an order of magnitude and the ordering of the arms is
recorded at every point.  What is reported in the paper is the fraction of the
grid on which the ordering is unchanged, not a single dollar figure.
"""

from __future__ import annotations

import itertools

from _common import write

from reconstream.calibrate import calibrate
from reconstream.checker import grade, run, summarise
from reconstream.contract import SourceModel
from reconstream.cost import total_cost
from reconstream.workload import build_workload
import reconstream.matchers as M

from finalitybench.faults import FaultProfile

SEEDS = (1, 2, 3, 4, 5)
N_CASES = 200
GRID = list(range(10, 501, 10))
CHECK_BANK_BOUND = 80

INVESTIGATION = (600, 1200, 2400, 4800, 9600)
UNRECOVERED = (0.2, 0.4, 0.6, 0.8, 1.0)
CARRY = (0, 1, 2, 5, 10)

FAMILIES = {
    "typed_horizon": lambda p: M.TypedHorizon(SourceModel(bound={"ledger": 2, "bank": p})),
    "fixed_timeout": lambda p: M.FixedTimeout(p),
    "global_watermark": lambda p: M.GlobalWatermark(p),
    "idle_watermark": lambda p: M.IdleWatermark(p, 60),
    "amount_date": lambda p: M.AmountDate(60, p),
}


def main() -> None:
    model = SourceModel(bound={"ledger": 2, "bank": CHECK_BANK_BOUND})
    calm = [build_workload(n_cases=N_CASES, seed=s, profile=FaultProfile.none()) for s in SEEDS]
    faulty = [build_workload(n_cases=N_CASES, seed=100 + s, profile=FaultProfile()) for s in SEEDS]
    cals = {n: calibrate(n, mk, GRID, calm, model) for n, mk in FAMILIES.items()}

    tallies: dict[str, dict] = {}
    for rname, workloads in (("calm", calm), ("faulty", faulty)):
        per_arm = {}
        for name, mk in FAMILIES.items():
            param = cals[name].param or GRID[-1]
            summaries = []
            for w in workloads:
                r = mk(param)
                d = run(r, w.arrivals, horizon=w.horizon)
                summaries.append(summarise(grade(r, w.arrivals, d, model, horizon=w.horizon)))
            per_arm[name] = {
                "false_breaks": sum(s["false_breaks"] for s in summaries),
                "false_match_amounts": [a for s in summaries for a in s["false_match_amounts"]],
                "carried_ticks": sum(s["carried_ticks"] for s in summaries),
                "param": param,
            }
        tallies[rname] = per_arm

    out = {
        "config": {"seeds": SEEDS, "n_cases": N_CASES, "model": model.as_dict(),
                   "investigation": INVESTIGATION, "unrecovered": UNRECOVERED, "carry": CARRY},
        "calibration": {k: v.as_dict() for k, v in cals.items()},
        "tallies": tallies,
        "sweeps": {},
    }

    for rname, per_arm in tallies.items():
        points = []
        for inv, unrec, carry in itertools.product(INVESTIGATION, UNRECOVERED, CARRY):
            costs = {
                name: total_cost(
                    false_breaks=t["false_breaks"],
                    false_match_amounts=t["false_match_amounts"],
                    carried_ticks=t["carried_ticks"],
                    break_investigation=inv,
                    unrecovered=unrec,
                    carry_per_tick=carry,
                )["total"]
                for name, t in per_arm.items()
            }
            points.append({
                "investigation": inv, "unrecovered": unrec, "carry": carry,
                "costs": costs,
                "cheapest": min(costs, key=costs.get),
                "order": sorted(costs, key=costs.get),
            })
        baseline = points[0]["order"]
        out["sweeps"][rname] = {
            "points": points,
            "n_points": len(points),
            "cheapest_counts": {
                n: sum(1 for p in points if p["cheapest"] == n) for n in per_arm
            },
            "order_stable_fraction": sum(1 for p in points if p["order"] == baseline) / len(points),
            "baseline_order": baseline,
        }

    write("e5_costs.json", out)


if __name__ == "__main__":
    main()
