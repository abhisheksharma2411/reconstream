"""Choose each reconciler's parameter the way an operator would.

Nobody deploys a reconciliation job with a tuning constant picked from the
regime it will be judged on.  What actually happens is that the job is tested
against a stretch of ordinary traffic, the constant is lowered until breaks
start appearing that turn out to be spurious, and it is left there.  This
module does exactly that, and the experiments use its output rather than
hand-chosen numbers, so no arm gets an advantage the field would not give it.

The selection rule is the smallest parameter that is both sound and accurate on
the calibration regime -- zero contract violations and zero false breaks --
because smaller means faster, and an operator has no reason to wait longer than
the evidence requires.  Two consequences are deliberate.  A family whose
structure makes it unsound at every parameter fails to calibrate and is
reported as such rather than being handed its least-bad setting.  And a family
that is sound only at a large parameter pays for it in closure delay, which is
the trade the frontier experiment then maps out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from .checker import grade, run
from .contract import SourceModel


@dataclass(frozen=True)
class Calibration:
    """The chosen parameter and the evidence it was chosen on."""

    family: str
    param: int | None
    false_break_rate: float
    inadmissible_rate: float
    converged: bool

    def as_dict(self) -> dict:
        return {
            "family": self.family,
            "param": self.param,
            "false_break_rate": self.false_break_rate,
            "inadmissible_rate": self.inadmissible_rate,
            "converged": self.converged,
        }


def evaluate(make, workloads: Sequence, model: SourceModel) -> tuple[float, float, list]:
    """Pooled false-break and inadmissibility rates over a set of workloads."""
    pooled: list = []
    for w in workloads:
        r = make()
        d = run(r, w.arrivals, horizon=w.horizon)
        pooled.extend(grade(r, w.arrivals, d, model, horizon=w.horizon))
    n = len(pooled) or 1
    fb = sum(1 for g in pooled if g.error == "false_break") / n
    inadm = sum(1 for g in pooled if not g.admissible) / n
    return fb, inadm, pooled


def calibrate(
    family: str,
    make: Callable[[int], object],
    params: Sequence[int],
    workloads: Sequence,
    model: SourceModel,
) -> Calibration:
    """Smallest parameter that is sound and accurate on ``workloads``.

    ``params`` must be ascending.  If none qualifies the calibration is
    reported as not converged, carrying the rates of the largest parameter
    tried, and the caller decides what to do about it.
    """
    last = (1.0, 1.0)
    for p in params:
        fb, inadm, _ = evaluate(lambda p=p: make(p), workloads, model)
        last = (fb, inadm)
        if fb == 0.0 and inadm == 0.0:
            return Calibration(family, p, fb, inadm, True)
    return Calibration(family, None, last[0], last[1], False)
