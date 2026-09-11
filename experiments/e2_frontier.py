"""E2 -- the soundness/liveness frontier.

E1 compares reconcilers at one calibrated operating point each, which is what
an operator would deploy but is not a controlled comparison: two families
calibrated to the same rule can still land at different points on their own
curves.  Here each family's parameter is swept across the whole grid, giving a
curve in (false-break rate, exception closure delay).  Down and to the left is
better: fewer spurious breaks, raised sooner.

The question the curves answer is whether tracking a horizon per source buys
anything, or whether it is a more complicated way to express a timeout.  A
timeout measures from when the *ledger* spoke, and so inherits the ledger's own
lateness into a decision that is about the *bank*.  If that matters, it will
show up as a heavier tail at equal accuracy rather than as a better mean.
"""

from __future__ import annotations

from _common import write

from reconstream.bootstrap import (
    bootstrap,
    false_break_rate,
    mean_exception_closure,
    p99_exception_closure,
)
from reconstream.calibrate import evaluate
from reconstream.checker import grade, run, summarise
from reconstream.contract import SourceModel
from reconstream.workload import build_workload
import reconstream.matchers as M

from finalitybench.faults import FaultProfile

SEEDS = (1, 2, 3, 4, 5)
N_CASES = 200
GRID = list(range(20, 501, 20))
CHECK_BANK_BOUND = 80

FAMILIES = {
    "typed_horizon": lambda p: M.TypedHorizon(SourceModel(bound={"ledger": 2, "bank": p})),
    "fixed_timeout": lambda p: M.FixedTimeout(p),
    "global_watermark": lambda p: M.GlobalWatermark(p),
    "idle_watermark": lambda p: M.IdleWatermark(p, 60),
}


def curve(mk, workloads, model) -> list[dict]:
    pts = []
    for p in GRID:
        pooled = []
        for w in workloads:
            r = mk(p)
            d = run(r, w.arrivals, horizon=w.horizon)
            pooled.extend(grade(r, w.arrivals, d, model, horizon=w.horizon))
        s = summarise(pooled)
        pts.append(
            {
                "param": p,
                "false_break_rate": false_break_rate(pooled),
                "inadmissible_rate": s["inadmissible_rate"],
                "mean_closure": mean_exception_closure(pooled),
                "p99_closure": p99_exception_closure(pooled),
                "sd_closure": s["sd_closure"],
                "break_recall": s["break_recall"],
                "n_exceptions": s["n_exceptions"],
            }
        )
    return pts


def at_zero_false_breaks(pts: list[dict]) -> dict | None:
    """Cheapest point on a curve that raises no spurious break.

    This is the operating point a reconciliation team is actually asked for --
    "stop paging us about credits that turn up an hour later" -- so comparing
    families there is more honest than comparing at a shared parameter value,
    which means different things to different families.
    """
    clean = [p for p in pts if p["false_break_rate"] == 0.0]
    return min(clean, key=lambda p: p["mean_closure"]) if clean else None


def main() -> None:
    model = SourceModel(bound={"ledger": 2, "bank": CHECK_BANK_BOUND})
    out = {"config": {"seeds": SEEDS, "n_cases": N_CASES, "grid": GRID}, "regimes": {}}
    for rname, profile in (("calm", FaultProfile.none()), ("faulty", FaultProfile())):
        workloads = [build_workload(n_cases=N_CASES, seed=s, profile=profile) for s in SEEDS]
        rec = {"curves": {}, "at_zero_false_breaks": {}}
        for name, mk in FAMILIES.items():
            pts = curve(mk, workloads, model)
            rec["curves"][name] = pts
            best = at_zero_false_breaks(pts)
            rec["at_zero_false_breaks"][name] = best
            if best is not None:
                pooled = []
                for w in workloads:
                    r = mk(best["param"])
                    d = run(r, w.arrivals, horizon=w.horizon)
                    pooled.extend(grade(r, w.arrivals, d, model, horizon=w.horizon))
                rec["at_zero_false_breaks"][name] = {
                    **best,
                    "mean_closure_ci": bootstrap(pooled, mean_exception_closure, seed=11).as_dict(),
                    "p99_closure_ci": bootstrap(pooled, p99_exception_closure, seed=12).as_dict(),
                }
        out["regimes"][rname] = rec
    write("e2_frontier.json", out)


if __name__ == "__main__":
    main()
