"""E7 -- the same contract, checked against a real stream processor.

Everything up to here grades reconcilers written for this paper.  This
experiment grades Apache Flink.  The job is an ordinary LEFT interval join --
the shape the pattern is normally built as -- and its verdicts go through the
same checker as every other arm, with the decision instant recovered from the
watermark the engine reported at emission.

Three things are measured.  Whether the engine's own verdicts satisfy S1.
Whether the simulated ``global_watermark`` arm is a faithful model of it, which
is what licenses the timing results in E2 that were produced from the model.
And what the idleness timeout does to the engine, as opposed to what it does to
the model -- the prediction in E4 was made about Flink, so it should be tested
on Flink.

If Docker or the pinned image is unavailable the experiment records that and
stops, rather than reporting numbers from the model as though the engine had
produced them.
"""

from __future__ import annotations

from _common import write

from reconstream.checker import grade, obligations_from, run, summarise
from reconstream.contract import SourceModel
from reconstream.flink import available, run_flink
from reconstream.workload import build_workload
import reconstream.matchers as M

from finalitybench.faults import FaultProfile

SEEDS = (1, 2)
N_CASES = 200
REPEATS = 4
CHECK_BANK_BOUND = 80
WINDOWS = (80, 160, 320)
IDLE_TIMEOUTS = (None, 10, 60, 240)


class _FlinkArm:
    """Adapter so the engine's verdict log can go through the same grader."""

    matches_on = "identity"

    def __init__(self, decisions):
        self.decisions = decisions
        self.retracted: set[str] = set()


def main() -> None:
    if not available():
        write("e7_flink.json", {
            "status": "skipped",
            "reason": "Docker unavailable or flink:1.20-scala_2.12-java17 not pulled; "
                      "run `make flink-image` first.",
        })
        return

    model = SourceModel(bound={"ledger": 2, "bank": CHECK_BANK_BOUND})
    out: dict = {
        "status": "ok",
        "engine": "apache/flink 1.20 (scala_2.12-java17), SQL interval join",
        "config": {"seeds": SEEDS, "n_cases": N_CASES, "bank_bound": CHECK_BANK_BOUND,
                   "windows": WINDOWS, "idle_timeouts": [str(i) for i in IDLE_TIMEOUTS]},
        "runs": [],
        "model_fidelity": [],
        "determinism": [],
    }

    for seed in SEEDS:
        w = build_workload(n_cases=N_CASES, seed=seed, profile=FaultProfile())
        obs = obligations_from(w.arrivals)

        for window in WINDOWS:
            for idle in IDLE_TIMEOUTS:
                fr = run_flink(w.arrivals, window=window, idle_timeout=idle)
                g = grade(_FlinkArm(fr.decisions), w.arrivals, fr.decisions, model, horizon=w.horizon)
                s = summarise(g)
                out["runs"].append({
                    "seed": seed, **fr.as_dict(),
                    "inadmissible_rate": s["inadmissible_rate"],
                    "s1_premature_break": s["s1_premature_break"],
                    "false_break_rate": s["false_break_rate"],
                    "false_breaks": s["false_breaks"],
                    "break_recall": s["break_recall"],
                    "mean_closure": s["mean_closure"],
                    "p99_closure": s["p99_closure"],
                    "n": s["n"],
                })

        # Determinism: the same job, the same input, run again.  Two
        # filesystem sources are read concurrently, so the order in which their
        # records interleave -- and therefore how far the watermark has advanced
        # when each obligation is considered -- is not fixed by the input alone.
        reps = []
        for _ in range(REPEATS):
            fr = run_flink(w.arrivals, window=CHECK_BANK_BOUND, idle_timeout=60)
            reps.append({oid: d.verdict.value for oid, d in fr.decisions.items()})
        oids = sorted(set().union(*reps))
        unstable = [o for o in oids if len({r.get(o) for r in reps}) > 1]
        out["determinism"].append({
            "seed": seed,
            "repeats": REPEATS,
            "obligations": len(oids),
            "unstable": len(unstable),
            "unstable_rate": len(unstable) / len(oids) if oids else 0.0,
            "break_counts": [sum(1 for v in r.values() if v == "exception") for r in reps],
        })

        # Fidelity: does the simulated arm partition the obligations the same
        # way the engine does, at the setting that corresponds to it?
        fr = run_flink(w.arrivals, window=CHECK_BANK_BOUND, idle_timeout=None)
        sim = M.GlobalWatermark(60)
        sim_d = run(sim, w.arrivals, horizon=w.horizon)
        common = set(fr.decisions) & set(sim_d)
        agree = sum(1 for o in common if fr.decisions[o].verdict is sim_d[o].verdict)
        out["model_fidelity"].append({
            "seed": seed,
            "common": len(common),
            "agree": agree,
            "agreement": agree / len(common) if common else 0.0,
            "only_engine": len(set(fr.decisions) - set(sim_d)),
            "only_model": len(set(sim_d) - set(fr.decisions)),
        })

    write("e7_flink.json", out)


if __name__ == "__main__":
    main()
