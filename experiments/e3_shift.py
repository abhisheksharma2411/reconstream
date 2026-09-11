"""E3 -- what happens when the lateness distribution moves.

Every arm in E1 was calibrated on calm traffic, and every arm was sound there.
This experiment keeps those calibrations and changes the world underneath them,
sweeping fault intensity from nothing up to the benchmark's default.

The measurement that matters is not that accuracy degrades -- of course it does.
It is *which* of the contract's two columns moves.  If the reconcilers were
deciding too early, the inadmissibility rate should climb.  If instead their
inputs stopped honouring the lateness bounds they were calibrated against, the
verdicts stay admissible and the source-model violations climb.  Those are
different faults with different owners, and an operator who cannot tell them
apart will retune a reconciler that was never the problem.
"""

from __future__ import annotations

from _common import write

from reconstream.bootstrap import bootstrap, false_break_rate, inadmissible_rate
from reconstream.calibrate import calibrate
from reconstream.checker import grade, model_respected, run, summarise
from reconstream.contract import SourceModel
from reconstream.workload import build_workload
import reconstream.matchers as M

from finalitybench.faults import FaultProfile

SEEDS = (1, 2, 3, 4, 5)
N_CASES = 200
GRID = list(range(10, 501, 10))
CHECK_BANK_BOUND = 80
INTENSITIES = (0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50)

FAMILIES = {
    "typed_horizon": lambda p: M.TypedHorizon(SourceModel(bound={"ledger": 2, "bank": p})),
    "fixed_timeout": lambda p: M.FixedTimeout(p),
    "global_watermark": lambda p: M.GlobalWatermark(p),
    "idle_watermark": lambda p: M.IdleWatermark(p, 60),
}


def main() -> None:
    model = SourceModel(bound={"ledger": 2, "bank": CHECK_BANK_BOUND})
    calm = [build_workload(n_cases=N_CASES, seed=s, profile=FaultProfile.none()) for s in SEEDS]
    cals = {n: calibrate(n, mk, GRID, calm, model) for n, mk in FAMILIES.items()}

    out = {
        "config": {"seeds": SEEDS, "n_cases": N_CASES, "intensities": INTENSITIES,
                   "model": model.as_dict()},
        "calibration": {k: v.as_dict() for k, v in cals.items()},
        "sweep": [],
    }

    for intensity in INTENSITIES:
        profile = FaultProfile.none() if intensity == 0.0 else FaultProfile(intensity=intensity)
        # Evaluation seeds are disjoint from the calibration seeds, so no arm is
        # scored on a stream it was tuned against.
        workloads = [build_workload(n_cases=N_CASES, seed=100 + s, profile=profile) for s in SEEDS]
        broken = {"ledger": 0, "bank": 0}
        for w in workloads:
            for k, v in model_respected(w.arrivals, model).items():
                broken[k] = broken.get(k, 0) + v
        total_arrivals = sum(len(w.arrivals) for w in workloads)
        row = {
            "intensity": intensity,
            "model_violations": broken,
            "model_violation_rate": sum(broken.values()) / total_arrivals,
            "arms": {},
        }
        for name, mk in FAMILIES.items():
            param = cals[name].param or GRID[-1]
            pooled, summaries = [], []
            for w in workloads:
                r = mk(param)
                d = run(r, w.arrivals, horizon=w.horizon)
                g = grade(r, w.arrivals, d, model, horizon=w.horizon)
                pooled.extend(g)
                summaries.append(summarise(g))
            row["arms"][name] = {
                "param": param,
                "false_break_rate": bootstrap(pooled, false_break_rate, seed=21).as_dict(),
                "inadmissible_rate": bootstrap(pooled, inadmissible_rate, seed=22).as_dict(),
                "attributable_to_model": sum(s["model_broken"] for s in summaries),
                "false_breaks": sum(s["false_breaks"] for s in summaries),
            }
        out["sweep"].append(row)

    write("e3_shift.json", out)


if __name__ == "__main__":
    main()
