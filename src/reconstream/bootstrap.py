"""Uncertainty for metrics computed over a stream that is not i.i.d.

A run grades one verdict per obligation, but obligations are not independent
draws.  Several arise from the same case, and a case is what the generator
sampled: its amount, its archetype and its fault draw are shared by every
obligation it produces.  Resampling obligations would treat those as separate
evidence and give intervals that are too narrow.

The unit here is therefore the **case**.  A replicate draws cases with
replacement and takes every obligation belonging to a drawn case, which keeps
the within-case correlation intact.  Seeds are pooled the same way: a case that
appears under three workload seeds contributes all three, because the three are
three views of one sampled case rather than three independent cases.

Comparisons between reconcilers use the same case resample for both arms.  The
arms faced identical streams, and a paired resample keeps that, which is what
makes a difference interval narrower than the gap between two marginal ones.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Sequence

DEFAULT_REPLICATES = 2000


@dataclass(frozen=True)
class Interval:
    """A point estimate with a percentile bootstrap interval."""

    point: float
    lo: float
    hi: float
    replicates: int

    def as_dict(self) -> dict:
        return {"point": self.point, "lo": self.lo, "hi": self.hi, "replicates": self.replicates}

    def __str__(self) -> str:
        return f"{self.point:.4g} [{self.lo:.4g}, {self.hi:.4g}]"


def case_of(oid: str) -> str:
    """The case an obligation belongs to.

    Obligation ids are ``case:ref:kind``; the case is the resampling unit.
    """
    return oid.split(":", 1)[0]


def _index_by_case(graded: Sequence) -> dict[str, list]:
    buckets: dict[str, list] = {}
    for g in graded:
        buckets.setdefault(case_of(g.oid), []).append(g)
    return buckets


def bootstrap(
    graded: Sequence,
    statistic: Callable[[Sequence], float],
    *,
    replicates: int = DEFAULT_REPLICATES,
    seed: int = 0,
    alpha: float = 0.05,
) -> Interval:
    """Percentile bootstrap over cases."""
    if not graded:
        return Interval(0.0, 0.0, 0.0, 0)
    buckets = _index_by_case(graded)
    keys = list(buckets)
    rng = random.Random(seed)
    point = statistic(list(graded))
    draws: list[float] = []
    for _ in range(replicates):
        sample: list = []
        for _ in range(len(keys)):
            sample.extend(buckets[keys[rng.randrange(len(keys))]])
        draws.append(statistic(sample))
    draws.sort()
    lo = draws[int((alpha / 2) * replicates)]
    hi = draws[min(replicates - 1, int((1 - alpha / 2) * replicates))]
    return Interval(point, lo, hi, replicates)


def paired_difference(
    a: Sequence,
    b: Sequence,
    statistic: Callable[[Sequence], float],
    *,
    replicates: int = DEFAULT_REPLICATES,
    seed: int = 0,
    alpha: float = 0.05,
) -> Interval:
    """Bootstrap of ``statistic(a) - statistic(b)`` on a shared case resample.

    Both arms must have been graded on the same stream, so that a drawn case
    contributes its obligations to both sides of the difference.  Cases present
    in only one arm are skipped rather than silently contributing a one-sided
    difference.
    """
    ba, bb = _index_by_case(a), _index_by_case(b)
    keys = [k for k in ba if k in bb]
    if not keys:
        return Interval(0.0, 0.0, 0.0, 0)
    rng = random.Random(seed)
    point = statistic(list(a)) - statistic(list(b))
    draws: list[float] = []
    for _ in range(replicates):
        sa: list = []
        sb: list = []
        for _ in range(len(keys)):
            k = keys[rng.randrange(len(keys))]
            sa.extend(ba[k])
            sb.extend(bb[k])
        draws.append(statistic(sa) - statistic(sb))
    draws.sort()
    lo = draws[int((alpha / 2) * replicates)]
    hi = draws[min(replicates - 1, int((1 - alpha / 2) * replicates))]
    return Interval(point, lo, hi, replicates)


# --- statistics the experiments resample -----------------------------------

def inadmissible_rate(graded: Sequence) -> float:
    return sum(1 for g in graded if not g.admissible) / len(graded) if graded else 0.0


def false_break_rate(graded: Sequence) -> float:
    return sum(1 for g in graded if g.error == "false_break") / len(graded) if graded else 0.0


def false_match_rate(graded: Sequence) -> float:
    n = len(graded)
    return sum(1 for g in graded if g.error in ("false_match", "mispaired")) / n if n else 0.0


def outcome_error_rate(graded: Sequence) -> float:
    n = len(graded)
    bad = sum(1 for g in graded if g.error)
    return bad / n if n else 0.0


def mean_exception_closure(graded: Sequence) -> float:
    xs = [g.closure for g in graded if g.verdict == "exception"]
    return sum(xs) / len(xs) if xs else 0.0


def p99_exception_closure(graded: Sequence) -> float:
    xs = sorted(g.closure for g in graded if g.verdict == "exception")
    return float(xs[min(len(xs) - 1, int(0.99 * len(xs)))]) if xs else 0.0


def false_break_fpr(graded: Sequence) -> float:
    """False breaks as a share of obligations the bank actually settled.

    Preferred over :func:`false_break_rate` for any comparison across fault
    regimes, whose genuine-break classes differ in size.
    """
    neg = [g for g in graded if not g.true_break]
    if not neg:
        return 0.0
    return sum(1 for g in neg if g.error == "false_break") / len(neg)


def break_recall(graded: Sequence) -> float:
    """Share of genuine breaks that were actually raised as exceptions.

    A reconciler that never decides scores zero here, which is what stops
    infinite caution from looking like soundness.
    """
    tb = [g for g in graded if g.true_break]
    if not tb:
        return 1.0
    return sum(1 for g in tb if g.verdict == "exception") / len(tb)


def model_violation_rate(graded: Sequence) -> float:
    return sum(1 for g in graded if g.model_broken) / len(graded) if graded else 0.0
