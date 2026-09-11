"""Turn a FinalityBench case into the two evidence streams a reconciler sees.

Reconciliation is an argument between systems that learned the same facts at
different times.  P1 already models that: one canonical log, and a fault engine
that derives a per-system delivery stream from it.  This module does nothing
but re-present those deliveries as *arrivals* on named evidence sources, which
is the vocabulary the correctness contract is written in.

Two sources are in play.  The **ledger** is what the business believes it is
owed: it sees a settlement two ticks after the money moves.  The **bank** is
where the money actually lands: it posts in batches, so the same fact can take
anywhere from fifteen to seventy-five ticks to appear even with no faults at
all.  That gap is not an artifact of the simulation.  It is the reason
reconciliation is hard, and it is why a single watermark over the merged stream
cannot be both sound and timely.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from ._p1 import ensure_p1

ensure_p1()

from finalitybench.events import (  # noqa: E402
    CHARGEBACK,
    CAPTURE_SETTLED,
    Event,
    PAYOUT,
    REFUND_SETTLED,
)
from finalitybench.faults import BANK, LEDGER, Schedule  # noqa: E402

#: The sources the reconciler consumes.  Named separately from P1's "systems"
#: because a source is an *evidence channel*, and two systems could in
#: principle publish onto one channel.
LEDGER_SRC = "ledger"
BANK_SRC = "bank"
SOURCES = (LEDGER_SRC, BANK_SRC)

_SYSTEM_OF = {LEDGER_SRC: LEDGER, BANK_SRC: BANK}

#: Event kinds that create a reconcilable money movement.  An obligation is
#: raised for each of these seen on the ledger; the bank is expected to show
#: the same movement.
RECONCILABLE = (CAPTURE_SETTLED, REFUND_SETTLED, CHARGEBACK, PAYOUT)


@dataclass(frozen=True, slots=True)
class Arrival:
    """One evidence record landing on one source at one instant.

    ``event_t`` is when the money moved; ``at_t`` is when this source could
    first have told anyone about it.  Every temporal property in the contract
    is a statement relating those two numbers, so they are never collapsed.
    """

    source: str
    at_t: int
    event_t: int
    seq: int
    kind: str
    case: str
    ref: str
    amount: int
    copy: int = 0

    @property
    def is_duplicate(self) -> bool:
        return self.copy > 0

    @property
    def identity(self) -> tuple[str, str, str]:
        """Operation identity in the sense of T8: what makes two records the
        same money movement rather than two movements that look alike."""
        return (self.case, self.ref, self.kind)

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "at_t": self.at_t,
            "event_t": self.event_t,
            "seq": self.seq,
            "kind": self.kind,
            "case": self.case,
            "ref": self.ref,
            "amount": self.amount,
            "copy": self.copy,
        }


def arrivals_for(log, schedule: Schedule) -> list[Arrival]:
    """Project a P1 schedule onto the ledger and bank evidence streams.

    Ordering is by arrival instant, with ``seq`` and ``copy`` breaking ties so
    the stream is a deterministic function of the schedule.  A reconciler that
    behaved differently on two orderings of the same instant would make every
    measurement below irreproducible.
    """
    by_seq: dict[int, Event] = {ev.seq: ev for ev in log}
    out: list[Arrival] = []
    for source, system in _SYSTEM_OF.items():
        for d in schedule.for_system(system):
            ev = by_seq.get(d.event_seq)
            if ev is None or ev.kind not in RECONCILABLE:
                continue
            out.append(
                Arrival(
                    source=source,
                    at_t=d.at_t,
                    event_t=ev.t,
                    seq=ev.seq,
                    kind=ev.kind,
                    case=ev.case,
                    ref=ev.ref,
                    amount=int(ev.amount),
                    copy=d.copy,
                )
            )
    out.sort(key=lambda a: (a.at_t, a.source, a.seq, a.copy))
    return out


def canonical_movements(log) -> list[Event]:
    """The money movements that truly happened, in canonical order.

    This is the oracle's view.  No matcher is allowed to consult it; the
    checker uses it only to score outcomes after the fact.
    """
    return [ev for ev in log if ev.kind in RECONCILABLE]


def stream_stats(arrivals: list[Arrival]) -> dict:
    """Lag summary per source -- the empirical counterpart of the source model."""
    stats: dict[str, dict] = {}
    for src in SOURCES:
        lags = [a.at_t - a.event_t for a in arrivals if a.source == src]
        if not lags:
            stats[src] = {"n": 0}
            continue
        lags.sort()
        stats[src] = {
            "n": len(lags),
            "min": lags[0],
            "median": lags[len(lags) // 2],
            "p99": lags[min(len(lags) - 1, int(0.99 * len(lags)))],
            "max": lags[-1],
        }
    return stats
