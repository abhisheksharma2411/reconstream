"""The temporal correctness contract for streaming reconciliation.

A reconciler watches two evidence streams and must say, for each expected
money movement, whether it happened.  The question this module answers is not
"did it get the answer right" but the prior one: **was it entitled to answer
yet**.  Those come apart.  A reconciler that declares a break the instant a
bank credit is overdue will be right most of the time, because most credits are
not late -- and will be wrong in exactly the cases that cost money.

The contract is stated against a *source model*: a declared bound on how late
each source may be.  Everything below is relative to that declaration.  A
reconciler cannot be sound in the abstract; it can only be sound with respect
to an assumption about its inputs, and the discipline the contract imposes is
that the assumption has to be written down.

Four properties.  The first two are safety, the third liveness, the fourth
rules out taking the verdict back.

``S1`` no premature break
    An exception may be raised only when no admissible continuation of the
    streams could still supply a counterpart.

``S2`` no premature match
    A match may be asserted only when no admissible continuation could make
    that pairing wrong.

``L1`` decisiveness
    Every obligation reaches a terminal verdict within a bounded delay after
    its settlement window closes.

``M1`` stability
    A terminal verdict is never retracted.

S1 and L1 pull against each other, and the size of that gap is set by the
slowest source the decision depends on.  A reconciler that tracks one horizon
for all sources pays the slowest source's latency on every decision, or gives
up S1.  That trade is the subject of the paper.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .streams import BANK_SRC, LEDGER_SRC


class Verdict(str, Enum):
    """What a reconciler can say about an obligation at a given instant."""

    PENDING = "pending"
    MATCHED = "matched"
    EXCEPTION = "exception"

    @property
    def is_terminal(self) -> bool:
        return self is not Verdict.PENDING


#: Why a verdict was not admissible.  Kept as strings rather than a second enum
#: so that results files stay readable without the code that wrote them.
S1_PREMATURE_BREAK = "S1_premature_break"
S2_PREMATURE_MATCH = "S2_premature_match"
S2_AMBIGUOUS_MATCH = "S2_ambiguous_match"
L1_UNDECIDED = "L1_undecided"
M1_RETRACTED = "M1_retracted"


@dataclass(frozen=True, slots=True)
class SourceModel:
    """Declared lateness bounds: how far behind each source may run.

    ``bound[source]`` is the maximum admissible gap between the instant a fact
    became true and the instant that source could first report it.  A source
    that exceeds its bound has broken the assumption, not the contract -- the
    checker reports those separately, because a reconciler cannot be blamed for
    an input that violated its declared interface.

    The default numbers are P1's own delivery model, read off the simulator
    rather than guessed: the ledger trails by a fixed two ticks, and the bank
    posts on a sixty-tick cycle no sooner than fifteen ticks after the money
    moved, so a fact can wait seventy-five ticks for a fault-free batch.
    """

    bound: dict[str, int] = field(
        default_factory=lambda: {LEDGER_SRC: 2, BANK_SRC: 75}
    )
    #: How long after the money moved a counterpart may still legitimately
    #: appear.  Distinct from lateness: lateness is about *reporting* delay,
    #: the window is about how long the business allows the movement itself to
    #: take.  Conflating the two is one of the defects the corpus records.
    settlement_window: int = 0

    def lateness(self, source: str) -> int:
        return self.bound[source]

    def horizon(self, source: str, now: int) -> int:
        """Event-time completeness frontier for one source.

        Every event of this source with event time at or below the horizon has
        arrived by ``now``, if it was ever going to.  This is a watermark, but
        one per source and derived from a declared bound rather than inferred
        from whatever happens to have been seen.
        """
        return now - self.bound[source]

    def decidable_at(self, event_t: int, source: str) -> int:
        """First instant at which absence of evidence from ``source`` is
        informative about a movement that occurred at ``event_t``."""
        return event_t + self.settlement_window + self.bound[source]

    def as_dict(self) -> dict:
        return {"bound": dict(self.bound), "settlement_window": self.settlement_window}


@dataclass(frozen=True, slots=True)
class Obligation:
    """A money movement the ledger believes happened, awaiting bank evidence.

    Identity follows T8's notion of operation identity: two records describe
    the same movement when they agree on case, reference and kind.  Amount is
    carried for the amount-matching baselines but is deliberately not part of
    identity, because two distinct refunds for the same price are two refunds.
    """

    oid: str
    case: str
    ref: str
    kind: str
    amount: int
    event_t: int
    #: When the ledger learned of it -- the earliest a reconciler could have
    #: raised the obligation at all.
    raised_t: int

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.case, self.ref, self.kind)


@dataclass(frozen=True, slots=True)
class Decision:
    """One terminal verdict, with the instant it was emitted."""

    oid: str
    verdict: Verdict
    at_t: int
    #: Arrival the reconciler paired the obligation with, if it matched.
    matched_seq: int | None = None
    matched_copy: int = 0

    def as_dict(self) -> dict:
        return {
            "oid": self.oid,
            "verdict": self.verdict.value,
            "at_t": self.at_t,
            "matched_seq": self.matched_seq,
            "matched_copy": self.matched_copy,
        }


def exception_admissible(ob: Obligation, at_t: int, model: SourceModel) -> bool:
    """S1.  May a break be raised for ``ob`` at ``at_t``?

    Only once the bank's completeness frontier has passed the last instant at
    which a counterpart could have occurred.  Before that, silence from the
    bank carries no information: the credit may have happened and simply not
    been posted yet.
    """
    return at_t >= model.decidable_at(ob.event_t, BANK_SRC)


def match_admissible(
    ob: Obligation,
    at_t: int,
    model: SourceModel,
    *,
    identity_matched: bool,
    rival_possible: bool,
) -> bool:
    """S2.  May a match be asserted for ``ob`` at ``at_t``?

    Two quite different situations are folded into one predicate, and keeping
    them apart is the point of the two keyword arguments.

    When the pairing was made on *identity*, the match is stable the moment the
    evidence arrives: nothing that can arrive later makes this record describe
    a different movement.  Identity matching is admissible immediately, and
    that is the strongest argument for it.

    When the pairing was made on *attributes* -- amount and date, the way most
    deployed reconcilers work -- a later arrival can turn out to be the real
    counterpart, leaving the earlier pairing wrong.  Such a match is admissible
    only once no rival can still appear, which puts it under the same horizon
    as a break.  Attribute matching therefore buys nothing in timeliness and
    costs correctness, which is the case against leading with matching rules.
    """
    if identity_matched and not rival_possible:
        return True
    return at_t >= model.decidable_at(ob.event_t, BANK_SRC)


def closure_delay(ob: Obligation, at_t: int, model: SourceModel) -> int:
    """L1.  Ticks between the earliest sound decision point and the verdict.

    Negative values are the interesting ones: they are decisions taken before
    the contract allowed, and their magnitude is how much soundness was traded
    away for timeliness.
    """
    return at_t - model.decidable_at(ob.event_t, BANK_SRC)
