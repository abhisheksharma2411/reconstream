"""E1 -- the main table.

Every reconciler is calibrated on calm traffic and then run unchanged on both
regimes, which is the only comparison an operator could actually reproduce.
Results are reported on two axes that the checker keeps apart: whether a
verdict was *permitted* at the instant it was emitted, and whether it turned
out to be *right*.  The gap between those two columns is the finding.
"""

from __future__ import annotations

from _common import write

from reconstream.bootstrap import (
    bootstrap,
    break_recall,
    false_break_fpr,
    false_break_rate,
    false_match_rate,
    inadmissible_rate,
    mean_exception_closure,
    p99_exception_closure,
)
from reconstream.calibrate import calibrate
from reconstream.checker import grade, model_respected, run, summarise
from reconstream.contract import SourceModel
from reconstream.cost import total_cost
from reconstream.workload import build_workload
import reconstream.matchers as M

from finalitybench.faults import FaultProfile

SEEDS = (1, 2, 3, 4, 5)
N_CASES = 200
GRID = list(range(10, 501, 10))

#: The bound the checker holds every arm to.  Calibrated on calm traffic by the
#: same procedure the arms use, so the contract is not judged against a bound
#: chosen with knowledge of the faulty regime.
CHECK_BANK_BOUND = 80

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
    faulty = [build_workload(n_cases=N_CASES, seed=s, profile=FaultProfile()) for s in SEEDS]

    cals = {name: calibrate(name, mk, GRID, calm, model) for name, mk in FAMILIES.items()}
    out: dict = {
        "config": {
            "seeds": SEEDS, "n_cases": N_CASES, "grid": [GRID[0], GRID[-1], GRID[1] - GRID[0]],
            "model": model.as_dict(),
        },
        "calibration": {k: v.as_dict() for k, v in cals.items()},
        "regimes": {},
    }

    for rname, workloads in (("calm", calm), ("faulty", faulty)):
        broken = {"ledger": 0, "bank": 0}
        for w in workloads:
            for k, v in model_respected(w.arrivals, model).items():
                broken[k] = broken.get(k, 0) + v
        rec: dict = {
            "workloads": [w.stats() for w in workloads],
            "model_violations": broken,
            "arms": {},
        }
        for name, mk in FAMILIES.items():
            cal = cals[name]
            # A family that never calibrates is still evaluated, at the largest
            # parameter tried, and its non-convergence is carried in the record.
            param = cal.param if cal.param is not None else GRID[-1]
            pooled, summaries = [], []
            for w in workloads:
                r = mk(param)
                d = run(r, w.arrivals, horizon=w.horizon)
                g = grade(r, w.arrivals, d, model, horizon=w.horizon)
                pooled.extend(g)
                summaries.append(summarise(g))
            rec["arms"][name] = {
                "param": param,
                "calibrated": cal.converged,
                "n": len(pooled),
                "inadmissible_rate": bootstrap(pooled, inadmissible_rate, seed=1).as_dict(),
                "false_break_rate": bootstrap(pooled, false_break_rate, seed=2).as_dict(),
                "false_break_fpr": bootstrap(pooled, false_break_fpr, seed=7).as_dict(),
                "n_exceptions": sum(s["n_exceptions"] for s in summaries),
                "negatives": sum(s["negatives"] for s in summaries),
                "true_breaks": sum(s["true_breaks"] for s in summaries),
                "false_match_rate": bootstrap(pooled, false_match_rate, seed=3).as_dict(),
                "break_recall": bootstrap(pooled, break_recall, seed=6).as_dict(),
                "mean_closure": bootstrap(pooled, mean_exception_closure, seed=4).as_dict(),
                "p99_closure": bootstrap(pooled, p99_exception_closure, seed=5).as_dict(),
                "cost": total_cost(
                    false_breaks=sum(s["false_breaks"] for s in summaries),
                    false_match_amounts=[a for s in summaries for a in s["false_match_amounts"]],
                    carried_ticks=sum(s["carried_ticks"] for s in summaries),
                ),
                "per_seed": summaries,
            }
        out["regimes"][rname] = rec

    write("e1_main.json", out)


if __name__ == "__main__":
    main()
