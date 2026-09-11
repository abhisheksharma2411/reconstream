"""E4 -- the idleness trap.

A merged-watermark join over a batch-posting source stalls: between batches the
bank emits nothing, its watermark stops, and because the operator takes the
minimum across inputs the whole job stops deciding.  The documented remedy is
an idleness timeout, which drops a quiet input from the minimum so the
watermark can advance again.

For reconciliation that remedy is the disease.  The quiet input is the one the
decision is about, and removing it from the minimum leaves the watermark
advancing at the ledger's rate -- so the join starts declaring that credits are
missing during the ordinary gap between bank batches.

The prediction is specific enough to be wrong: violations should appear once
the idleness timeout drops below the bank's posting period, and vanish above
it.  P1 posts the bank feed every 60 ticks, so the cliff should sit at 60.
"""

from __future__ import annotations

from _common import write

from reconstream.bootstrap import bootstrap, false_break_rate, inadmissible_rate, mean_exception_closure
from reconstream.calibrate import calibrate
from reconstream.checker import grade, run, summarise
from reconstream.contract import SourceModel
from reconstream.workload import build_workload
import reconstream.matchers as M

from finalitybench.faults import BANK_BATCH, FaultProfile

SEEDS = (1, 2, 3, 4, 5)
N_CASES = 200
GRID = list(range(10, 501, 10))
CHECK_BANK_BOUND = 80
IDLE_TIMEOUTS = (5, 10, 15, 20, 30, 40, 50, 60, 75, 90, 120, 180, 240)


def main() -> None:
    model = SourceModel(bound={"ledger": 2, "bank": CHECK_BANK_BOUND})
    calm = [build_workload(n_cases=N_CASES, seed=s, profile=FaultProfile.none()) for s in SEEDS]
    faulty = [build_workload(n_cases=N_CASES, seed=100 + s, profile=FaultProfile()) for s in SEEDS]

    # delta is calibrated once, with idleness disabled, so the sweep isolates
    # the idleness setting rather than confounding it with the watermark lag.
    base = calibrate("global_watermark", lambda p: M.GlobalWatermark(p), GRID, calm, model)
    delta = base.param or GRID[-1]

    out = {
        "config": {"seeds": SEEDS, "n_cases": N_CASES, "delta": delta,
                   "bank_batch_period": BANK_BATCH, "model": model.as_dict()},
        "baseline_no_idleness": {},
        "sweep": [],
    }

    for rname, workloads in (("calm", calm), ("faulty", faulty)):
        pooled = []
        for w in workloads:
            r = M.GlobalWatermark(delta)
            d = run(r, w.arrivals, horizon=w.horizon)
            pooled.extend(grade(r, w.arrivals, d, model, horizon=w.horizon))
        s = summarise(pooled)
        out["baseline_no_idleness"][rname] = {
            "inadmissible_rate": bootstrap(pooled, inadmissible_rate, seed=31).as_dict(),
            "false_break_rate": bootstrap(pooled, false_break_rate, seed=32).as_dict(),
            "mean_closure": mean_exception_closure(pooled),
            "undecided": s["undecided"],
        }

    for it in IDLE_TIMEOUTS:
        row = {"idle_timeout": it, "regimes": {}}
        for rname, workloads in (("calm", calm), ("faulty", faulty)):
            pooled = []
            for w in workloads:
                r = M.IdleWatermark(delta, it)
                d = run(r, w.arrivals, horizon=w.horizon)
                pooled.extend(grade(r, w.arrivals, d, model, horizon=w.horizon))
            s = summarise(pooled)
            row["regimes"][rname] = {
                "inadmissible_rate": bootstrap(pooled, inadmissible_rate, seed=33).as_dict(),
                "false_break_rate": bootstrap(pooled, false_break_rate, seed=34).as_dict(),
                "s1_premature_break": s["s1_premature_break"],
                "mean_closure": mean_exception_closure(pooled),
            }
        out["sweep"].append(row)

    write("e4_idleness.json", out)


if __name__ == "__main__":
    main()
