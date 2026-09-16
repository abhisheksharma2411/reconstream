"""E10 -- how variable is the engine's nondeterminism, and does load explain it?

The paper reports an observation it withdrew. An early full run, made while
seven other experiments shared the machine, showed Flink disagreeing with
itself across repeats of an identical job at rates around a quarter to two
fifths of obligations. Re-run on an idle machine the same configuration gave
under one per cent, so the observation was reported as unreproduced and the
claim dropped from the abstract.

Withdrawing it was right on the evidence available and it left the wrong
impression, because "we could not reproduce it" reads as "it was probably
noise" when the candidate explanation was sitting in the sentence: the first
run was loaded and the second was not. Load is a variable, and a variable can
be controlled rather than apologised for.

So this varies load deliberately. It runs the determinism check under an idle
machine and under a synthetic CPU load of a stated size, and it runs each
condition several times, because the quantity being measured turns out to be a
random variable rather than a constant. Repeated measurements during
development ranged from under one per cent to over forty, and the highest one
came from an *idle* machine, so a single execution of this check -- including
the one the paper originally reported -- says very little.

Reporting the distribution is the point. If the two conditions separate, load
explains the instability. If they overlap, it does not, and the useful result
is the spread itself: a rate that moves by an order of magnitude between
executions is a rate no single run should be quoted for.

The load is deliberately crude -- busy loops on a stated number of cores -- so
that it is reproducible anywhere without a benchmark harness.
"""

from __future__ import annotations

import multiprocessing
import os
import time

from _common import write

from reconstream.flink import available, run_flink
from reconstream.workload import build_workload

from finalitybench.faults import FaultProfile

SEEDS = (1, 2)
N_CASES = 200
REPEATS = 4
CHECK_BANK_BOUND = 80
#: Busy-loop workers started for the loaded arm. Chosen to oversubscribe a
#: typical laptop without wedging it.
LOAD_WORKERS = max(4, (os.cpu_count() or 4))
#: How many times each condition is measured. The instability rate varies
#: between executions by more than it varies between conditions, so one
#: execution per condition would compare two draws from the same distribution
#: and call the difference an effect.
EXECUTIONS = 3


def _burn(stop) -> None:
    while not stop.is_set():
        pass


class Load:
    """A stated number of busy cores, or nothing at all."""

    def __init__(self, workers: int) -> None:
        self.workers = workers
        self._stop = multiprocessing.Event()
        self._procs: list = []

    def __enter__(self) -> "Load":
        for _ in range(self.workers):
            p = multiprocessing.Process(target=_burn, args=(self._stop,))
            p.start()
            self._procs.append(p)
        if self.workers:
            time.sleep(2)          # let the load actually arrive
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        for p in self._procs:
            p.join(timeout=10)
            if p.is_alive():
                p.terminate()


def measure(seed: int) -> dict:
    """Repeat one identical job and report how much its verdicts move."""
    w = build_workload(seed=seed, n_cases=N_CASES, profile=FaultProfile())
    reps = []
    for _ in range(REPEATS):
        fr = run_flink(w.arrivals, window=CHECK_BANK_BOUND, idle_timeout=60)
        reps.append({oid: d.verdict.value for oid, d in fr.decisions.items()})
    oids = sorted(set().union(*reps))
    unstable = [o for o in oids if len({r.get(o) for r in reps}) > 1]
    return {
        "seed": seed,
        "obligations": len(oids),
        "unstable": len(unstable),
        "unstable_rate": len(unstable) / len(oids) if oids else 0.0,
        "break_counts": [sum(1 for v in r.values() if v == "exception")
                         for r in reps],
    }


def main() -> None:
    if not available():
        write("e10_contention.json", {"status": "skipped",
                                      "reason": "docker or the pinned image is unavailable"})
        return

    arms: dict[str, list[dict]] = {"idle": [], "loaded": []}
    for label, workers in (("idle", 0), ("loaded", LOAD_WORKERS)):
        for execution in range(EXECUTIONS):
            with Load(workers):
                for seed in SEEDS:
                    row = measure(seed)
                    row["execution"] = execution
                    arms[label].append(row)

    def rates(label):
        return sorted(r["unstable_rate"] for r in arms[label])

    idle, loaded = rates("idle"), rates("loaded")
    overlap = not (max(idle) < min(loaded) or max(loaded) < min(idle))
    write("e10_contention.json", {
        "status": "ok",
        "config": {"seeds": list(SEEDS), "n_cases": N_CASES,
                   "repeats": REPEATS, "executions": EXECUTIONS,
                   "load_workers": LOAD_WORKERS, "cpus": os.cpu_count()},
        "arms": arms,
        "headline": {
            "measurements_per_condition": len(idle),
            "idle_rates": idle,
            "loaded_rates": loaded,
            "idle_min": min(idle), "idle_max": max(idle),
            "loaded_min": min(loaded), "loaded_max": max(loaded),
            "idle_mean": sum(idle) / len(idle),
            "loaded_mean": sum(loaded) / len(loaded),
            # The comparison the experiment exists for, and the spread that
            # makes it hard to make.
            "load_increases_instability": (sum(loaded) / len(loaded)
                                           > sum(idle) / len(idle)),
            "distributions_overlap": overlap,
            "spread_within_a_condition": max(idle) - min(idle),
            "gap_between_conditions": abs(sum(loaded) / len(loaded)
                                          - sum(idle) / len(idle)),
            "spread_exceeds_the_gap": (
                (max(idle) - min(idle))
                > abs(sum(loaded) / len(loaded) - sum(idle) / len(idle))),
            "note": ("the paper's withdrawn observation came from a loaded "
                     "machine and its replacement from an idle one, with one "
                     "execution each; this measures both conditions several "
                     "times so the spread can be compared against the gap"),
        },
    })


if __name__ == "__main__":
    main()
