"""Run a reconciler over a stream and grade it on two separate axes.

The distinction this module exists to enforce: **admissibility** is whether a
verdict was permitted by the contract at the instant it was emitted, and
**outcome** is whether it turned out to be right.  Neither implies the other.

A reconciler can be inadmissible and lucky.  Raising a break the moment a
credit is overdue is not permitted -- the bank may simply not have posted yet --
but on a stream where nothing was ever late it will be right every time.  That
reconciler has not solved the problem; it has been handed a benign input, and
its accuracy is a property of the input rather than of itself.  The gap between
the two axes is what the distribution-shift experiment converts into real
money.

A reconciler can also be admissible and wrong, which the checker reports
separately and does not count against it.  That happens when a source breaks
its declared lateness bound.  The contract is relative to a source model; an
input that violates the model has broken the interface, and blaming the
reconciler would make the contract unfalsifiable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .contract import (
    Decision,
    L1_UNDECIDED,
    M1_RETRACTED,
    Obligation,
    S1_PREMATURE_BREAK,
    S2_AMBIGUOUS_MATCH,
    S2_PREMATURE_MATCH,
    SourceModel,
    Verdict,
    closure_delay,
    exception_admissible,
    match_admissible,
)
from .streams import Arrival, BANK_SRC, LEDGER_SRC


@dataclass
class Graded:
    """One verdict, with everything needed to explain why it scored as it did."""

    oid: str
    verdict: str
    at_t: int
    admissible: bool
    violation: str = ""
    correct: bool = True
    error: str = ""
    #: The bank never showed this movement, so an exception is the right call.
    true_break: bool = False
    #: The pairing pointed at a different movement's record.  Recorded
    #: separately from ``error`` because an obligation with no counterpart at
    #: all is scored as a false match, and that would otherwise hide the fact
    #: that the reconciler also grabbed someone else's money.
    mispaired: bool = False
    amount: int = 0
    closure: int = 0
    model_broken: bool = False

    def as_dict(self) -> dict:
        return {
            "oid": self.oid,
            "verdict": self.verdict,
            "at_t": self.at_t,
            "admissible": self.admissible,
            "violation": self.violation,
            "correct": self.correct,
            "error": self.error,
            "true_break": self.true_break,
            "mispaired": self.mispaired,
            "amount": self.amount,
            "closure": self.closure,
            "model_broken": self.model_broken,
        }


def run(reconciler, arrivals: list[Arrival], *, horizon: int, tick_every: int = 5):
    """Drive a reconciler over the stream, interleaving arrivals and ticks.

    Ticks are what let a reconciler act on the *absence* of data.  Without
    them the only reconciler that could ever raise a break is one that happens
    to receive an unrelated arrival at the right moment, which would make the
    comparison a measurement of traffic rather than of policy.  ``tick_every``
    is the reconciler's polling granularity and is held equal across all arms.
    """
    i = 0
    now = 0
    n = len(arrivals)
    while now <= horizon:
        while i < n and arrivals[i].at_t <= now:
            reconciler.observe(arrivals[i])
            i += 1
        reconciler.tick(now)
        now += tick_every
    while i < n:
        reconciler.observe(arrivals[i])
        i += 1
    reconciler.tick(horizon)
    reconciler.finish(horizon)
    return reconciler.decisions


def obligations_from(arrivals: list[Arrival]) -> dict[str, Obligation]:
    """Every obligation the ledger actually raised, as the reconciler saw it."""
    out: dict[str, Obligation] = {}
    for a in arrivals:
        if a.source != LEDGER_SRC:
            continue
        oid = f"{a.case}:{a.ref}:{a.kind}"
        if oid in out:
            continue
        out[oid] = Obligation(
            oid=oid,
            case=a.case,
            ref=a.ref,
            kind=a.kind,
            amount=a.amount,
            event_t=a.event_t,
            raised_t=a.at_t,
        )
    return out


def bank_truth(arrivals: list[Arrival]) -> dict[str, Arrival]:
    """Whether the bank ever showed each movement, over the whole stream.

    The oracle.  A reconciler never sees this; the checker uses it only to
    decide, after the fact, whether a verdict was right.
    """
    out: dict[str, Arrival] = {}
    for a in arrivals:
        if a.source != BANK_SRC:
            continue
        oid = f"{a.case}:{a.ref}:{a.kind}"
        if oid not in out or a.at_t < out[oid].at_t:
            out[oid] = a
    return out


def model_respected(arrivals: list[Arrival], model: SourceModel) -> dict[str, int]:
    """Count arrivals that exceeded their source's declared lateness bound."""
    broken = {s: 0 for s in model.bound}
    for a in arrivals:
        if a.at_t - a.event_t > model.bound.get(a.source, 10**9):
            broken[a.source] = broken.get(a.source, 0) + 1
    return broken


def grade(
    reconciler,
    arrivals: list[Arrival],
    decisions: dict[str, Decision],
    model: SourceModel,
    *,
    horizon: int,
) -> list[Graded]:
    """Score every terminal verdict on admissibility and on outcome."""
    obs = obligations_from(arrivals)
    truth = bank_truth(arrivals)
    # A pairing always points at a bank record, and the ledger and bank
    # deliveries of one canonical event share a sequence number, so the lookup
    # is restricted to the bank side rather than keyed on (seq, copy) alone.
    by_key: dict[tuple[int, int], Arrival] = {
        (a.seq, a.copy): a for a in arrivals if a.source == BANK_SRC
    }
    late = {
        (a.seq, a.copy)
        for a in arrivals
        if a.at_t - a.event_t > model.bound.get(a.source, 10**9)
    }
    identity_based = getattr(reconciler, "matches_on", "identity") == "identity"

    graded: list[Graded] = []
    for oid, ob in obs.items():
        d = decisions.get(oid)
        if d is None:
            graded.append(
                Graded(oid, "pending", horizon, admissible=False, violation=L1_UNDECIDED,
                       correct=False, error="undecided", amount=ob.amount,
                       closure=closure_delay(ob, horizon, model),
                       true_break=truth.get(oid) is None)
            )
            continue

        truth_arr = truth.get(oid)
        g = Graded(oid, d.verdict.value, d.at_t, admissible=True,
                   amount=ob.amount, closure=closure_delay(ob, d.at_t, model),
                   true_break=truth_arr is None)

        if d.verdict is Verdict.EXCEPTION:
            if not exception_admissible(ob, d.at_t, model):
                g.admissible = False
                g.violation = S1_PREMATURE_BREAK
            if truth_arr is not None:
                g.correct = False
                g.error = "false_break"
                g.model_broken = (truth_arr.seq, truth_arr.copy) in late
            if d.at_t >= horizon:
                g.violation = g.violation or L1_UNDECIDED
        else:
            paired = by_key.get((d.matched_seq, d.matched_copy)) if d.matched_seq is not None else None
            right_movement = paired is not None and paired.identity == ob.identity
            rival = not identity_based
            g.mispaired = paired is not None and not right_movement
            if not match_admissible(ob, d.at_t, model,
                                    identity_matched=right_movement and identity_based,
                                    rival_possible=rival):
                g.admissible = False
                g.violation = S2_AMBIGUOUS_MATCH if rival else S2_PREMATURE_MATCH
            if truth_arr is None:
                g.correct = False
                g.error = "false_match"
            elif not right_movement:
                g.correct = False
                g.error = "mispaired"
        graded.append(g)

    retracted = getattr(reconciler, "retracted", set())
    for g in graded:
        if g.oid in retracted and not g.violation:
            g.violation = M1_RETRACTED
            g.admissible = False
    return graded


def summarise(graded: list[Graded]) -> dict:
    """Aggregate one run into the numbers the tables are built from."""
    n = len(graded)
    if n == 0:
        return {"n": 0}
    terminal = [g for g in graded if g.verdict != "pending"]
    inadmissible = [g for g in graded if not g.admissible]
    false_breaks = [g for g in graded if g.error == "false_break"]
    false_matches = [g for g in graded if g.error in ("false_match", "mispaired")]
    undecided = [g for g in graded if g.verdict == "pending"]
    # Liveness is about how long a *break* takes to surface.  Matches close as
    # soon as the evidence lands, which is earlier than the decision point and
    # would drag the mean below zero if pooled -- making a reconciler look
    # timely for the one verdict whose timeliness was never in question.
    ex_closures = sorted(g.closure for g in terminal if g.verdict == "exception")
    match_closures = sorted(g.closure for g in terminal if g.verdict == "matched")
    carried = sum(max(0, g.closure) for g in terminal) + sum(max(0, g.closure) for g in undecided)

    def _pct(xs, q):
        return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else 0

    def _mean(xs):
        return sum(xs) / len(xs) if xs else 0.0
    return {
        "n": n,
        "terminal": len(terminal),
        "undecided": len(undecided),
        "inadmissible": len(inadmissible),
        "inadmissible_rate": len(inadmissible) / n,
        "s1_premature_break": sum(1 for g in inadmissible if g.violation == S1_PREMATURE_BREAK),
        "s2_violations": sum(
            1 for g in inadmissible if g.violation in (S2_PREMATURE_MATCH, S2_AMBIGUOUS_MATCH)
        ),
        "false_breaks": len(false_breaks),
        "false_break_rate": len(false_breaks) / n,
        "false_matches": len(false_matches),
        "mispaired": sum(1 for g in graded if g.mispaired),
        "false_match_rate": len(false_matches) / n,
        "false_match_amounts": [g.amount for g in false_matches],
        "outcome_error_rate": (len(false_breaks) + len(false_matches)) / n,
        "n_exceptions": len(ex_closures),
        "mean_closure": _mean(ex_closures),
        "p50_closure": _pct(ex_closures, 0.50),
        "p99_closure": _pct(ex_closures, 0.99),
        "max_closure": max(ex_closures) if ex_closures else 0,
        "sd_closure": (
            (sum((x - _mean(ex_closures)) ** 2 for x in ex_closures) / len(ex_closures)) ** 0.5
            if ex_closures else 0.0
        ),
        "mean_match_closure": _mean(match_closures),
        "carried_ticks": carried,
        "m1_retracted": sum(1 for g in graded if g.violation == M1_RETRACTED),
        "true_breaks": sum(1 for g in graded if g.true_break),
        "breaks_detected": sum(1 for g in graded if g.true_break and g.verdict == "exception"),
        "break_recall": (
            sum(1 for g in graded if g.true_break and g.verdict == "exception")
            / sum(1 for g in graded if g.true_break)
            if any(g.true_break for g in graded) else 1.0
        ),
        "mean_detection_delay": _mean(
            [g.closure for g in graded if g.true_break and g.verdict == "exception"]
        ),
        "model_broken": sum(1 for g in graded if g.model_broken),
    }
