"""Build reconciliation workloads out of FinalityBench cases.

A workload is a set of cases replayed into one merged arrival stream, so that
obligations from different cases interleave the way they do in a real day's
traffic.  Interleaving is not cosmetic: the amount-matching baseline can only
mispair when two similar movements are in flight together, and a reconciler
that saw each case in isolation would never exhibit the ambiguity that makes
attribute matching unsound.

Cases are spread across the day by offsetting each case's event times, which
keeps P1's within-case structure exactly as P1 generated it while giving the
stream a realistic arrival profile.  Four of P1's nine archetypes are directly
reconciliation defects -- a settlement the processor never recorded, a
settlement delivered twice, a half-written ledger entry, and a processor view
that lags by three hundred ticks -- so the defect corpus is drawn from the
simulator rather than hand-written on top of it.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field

from ._p1 import ensure_p1
from .streams import Arrival, BANK_SRC, arrivals_for

ensure_p1()

from finalitybench.faults import FaultProfile, build_schedule  # noqa: E402
from finalitybench.world import (  # noqa: E402
    ARCHETYPES,
    build_log,
    make_case,
    sample_amount,
    sample_determination,
    schedule_seed_for,
)

#: Archetypes whose defining fault lands on the reconciliation path.  Kept
#: explicit so the defect corpus can be reported per class.
RECON_DEFECTS = ("lost_settlement", "duplicate_settlement", "partial_ledger", "stale_processor")

#: How far apart case start times are spread, in ticks.  One "day" of traffic.
DAY = 1440

#: Fraction of movements for which the bank genuinely never shows the money.
#: Without a positive class the benchmark is degenerate -- a reconciler that
#: never raises a break would be perfect -- so a controlled share of cases have
#: their bank-side evidence removed outright.  This is not a delivery fault: the
#: credit did not arrive, and the correct verdict is an exception.  Real
#: reconciliation break rates sit in the low single digits; 4% keeps the class
#: large enough to measure without making breaks the common case.
TRUE_BREAK_RATE = 0.04


@dataclass
class Workload:
    """One replayable stream plus the provenance needed to rebuild it."""

    arrivals: list[Arrival]
    horizon: int
    cases: list[dict]
    seed: int
    profile_label: str
    intensity: float
    true_break_rate: float = 0.0

    def fingerprint(self) -> str:
        """Content hash of the stream, so a results file names its own input."""
        h = hashlib.sha256()
        for a in self.arrivals:
            h.update(
                f"{a.source}|{a.at_t}|{a.event_t}|{a.seq}|{a.kind}|{a.case}|{a.ref}|{a.amount}|{a.copy}\n".encode()
            )
        return h.hexdigest()[:16]

    def stats(self) -> dict:
        kinds: dict[str, int] = {}
        for a in self.arrivals:
            kinds[a.kind] = kinds.get(a.kind, 0) + 1
        return {
            "arrivals": len(self.arrivals),
            "cases": len(self.cases),
            "horizon": self.horizon,
            "kinds": kinds,
            "true_breaks": sum(1 for c in self.cases if c.get("truly_broken")),
            "fingerprint": self.fingerprint(),
        }


def build_workload(
    *,
    n_cases: int,
    seed: int,
    profile: FaultProfile | None = None,
    duplicate_amounts: bool = True,
    true_break_rate: float = TRUE_BREAK_RATE,
) -> Workload:
    """Generate ``n_cases`` interleaved reconciliation cases.

    ``true_break_rate`` is the share of movements whose bank evidence is removed
    entirely, so that some exceptions are the right answer.  The removal is
    drawn from the workload seed before any fault is applied, which keeps the
    positive class identical across fault regimes -- otherwise a regime with
    more delivery loss would also have a different number of genuine breaks and
    the two effects could not be told apart.

    ``duplicate_amounts`` controls whether amounts are drawn from P1's eight
    round retail figures (the realistic choice, and the one under which
    attribute matching is ambiguous) or made unique per case.  Turning it off
    is how the experiments separate the ambiguity failure from the lateness
    failure, rather than reporting one number that mixes them.
    """
    profile = profile or FaultProfile()
    rng = random.Random(seed)
    arrivals: list[Arrival] = []
    cases: list[dict] = []
    horizon = 0

    for i in range(n_cases):
        archetype = ARCHETYPES[i % len(ARCHETYPES)]
        resolvable = archetype not in ("unresolvable",)
        amount = sample_amount(rng) if duplicate_amounts else 1000 + i * 7
        t_det = sample_determination(rng, resolvable=resolvable)
        case_seed = rng.randrange(1 << 30)
        case = make_case(
            task_id=f"w{seed}-{i:04d}",
            archetype=archetype,
            amount=amount,
            t_det=t_det,
            schedule_seed=case_seed,
        )
        truly_broken = rng.random() < true_break_rate
        log = build_log(case)
        schedule = build_schedule(log, profile, schedule_seed_for(case_seed, seed))
        offset = rng.randrange(0, DAY)
        for a in arrivals_for(log, schedule):
            if truly_broken and a.source == BANK_SRC:
                continue
            shifted = Arrival(
                source=a.source,
                at_t=a.at_t + offset,
                event_t=a.event_t + offset,
                seq=a.seq + i * 1000,
                kind=a.kind,
                case=a.case,
                ref=a.ref,
                amount=a.amount,
                copy=a.copy,
            )
            arrivals.append(shifted)
            horizon = max(horizon, shifted.at_t)
        cases.append(
            {
                "task_id": case.task_id,
                "archetype": archetype,
                "amount": amount,
                "offset": offset,
                "is_recon_defect": archetype in RECON_DEFECTS,
                "truly_broken": truly_broken,
            }
        )

    arrivals.sort(key=lambda a: (a.at_t, a.source, a.seq, a.copy))
    return Workload(
        arrivals=arrivals,
        horizon=horizon + 120,
        cases=cases,
        seed=seed,
        profile_label=profile.label(),
        intensity=profile.intensity,
        true_break_rate=true_break_rate,
    )
