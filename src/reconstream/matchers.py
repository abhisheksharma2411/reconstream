"""Reconcilers: four ways people build this, and the one the contract implies.

Each reconciler is an online consumer of the merged arrival stream.  It raises
an obligation when the ledger reports a movement, and must eventually say
whether the bank agrees.  None of them may look at the canonical log, and none
receives the source model unless it is the kind of reconciler that declares
one -- which is the whole difference between the last of them and the rest.

The baselines are not strawmen.  ``FixedTimeout`` is what an operations team
writes first; ``GlobalWatermark`` is the textbook Flink interval join;
``IdleWatermark`` is that same job after someone notices it stalls overnight
and reaches for the documented fix; ``AmountDate`` is how a reconciliation
product with no shared identifier has to work.  Three of the four are sound
under some configuration.  The question the experiments ask is what each has
to give up to get there.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .contract import Decision, Obligation, SourceModel, Verdict
from .streams import Arrival, BANK_SRC, LEDGER_SRC


class Reconciler:
    """Online reconciler interface.

    ``observe`` is called once per arrival in stream order; ``tick`` is called
    at every instant a decision could become due, whether or not anything
    arrived.  Separating them matters: a reconciler that only acts when data
    arrives cannot raise a break on a stream that has gone quiet, which is the
    failure mode idleness handling exists to fix.
    """

    name = "base"
    declares_model = False
    #: What a pairing is justified by. Identity pairings are stable on
    #: arrival; attribute pairings can be overturned by a later record.
    matches_on = "identity"

    def __init__(self) -> None:
        self.open: dict[str, Obligation] = {}
        self.decisions: dict[str, Decision] = {}
        self.retracted: set[str] = set()
        self.orphans = 0

    # -- helpers ----------------------------------------------------------
    def _raise(self, a: Arrival) -> None:
        oid = f"{a.case}:{a.ref}:{a.kind}"
        if oid in self.open or oid in self.decisions:
            return
        self.open[oid] = Obligation(
            oid=oid,
            case=a.case,
            ref=a.ref,
            kind=a.kind,
            amount=a.amount,
            event_t=a.event_t,
            raised_t=a.at_t,
        )

    def _settle(self, oid: str, verdict: Verdict, at_t: int, arr: Arrival | None = None) -> Decision | None:
        prior = self.decisions.get(oid)
        if prior is not None:
            if prior.verdict is not verdict:
                self.retracted.add(oid)
                self.decisions[oid] = Decision(oid, verdict, at_t,
                                               arr.seq if arr else None,
                                               arr.copy if arr else 0)
                return self.decisions[oid]
            return None
        d = Decision(oid, verdict, at_t, arr.seq if arr else None, arr.copy if arr else 0)
        self.decisions[oid] = d
        self.open.pop(oid, None)
        return d

    # -- interface --------------------------------------------------------
    def observe(self, a: Arrival) -> list[Decision]:
        raise NotImplementedError

    def tick(self, now: int) -> list[Decision]:
        return []

    def finish(self, now: int) -> list[Decision]:
        """Force a terminal verdict on anything still open.

        Anything decided here was undecided when the stream ended, which is an
        L1 failure; the checker counts them from the fact that the verdict
        instant equals the end of the stream.
        """
        out = []
        for oid in list(self.open):
            d = self._settle(oid, Verdict.EXCEPTION, now)
            if d:
                out.append(d)
        return out

    def config(self) -> dict:
        return {}


class TypedHorizon(Reconciler):
    """Ours.  One completeness horizon per source, from a declared bound.

    Matching is on identity, so a match is asserted the moment bank evidence
    arrives -- there is nothing a later arrival can do to make it wrong.  A
    break waits for the *bank's* horizon specifically, not for a horizon
    computed over both streams.  That asymmetry is the entire mechanism: the
    ledger's speed is irrelevant to whether the bank has finished talking.

    Duplicates are dropped by identity rather than matched again, which is what
    keeps S2 intact when the fault engine replays a delivery.
    """

    name = "typed_horizon"
    declares_model = True

    def __init__(self, model: SourceModel) -> None:
        super().__init__()
        self.model = model
        self.seen_bank: dict[tuple[str, str, str], Arrival] = {}

    def observe(self, a: Arrival) -> list[Decision]:
        out: list[Decision] = []
        if a.source == LEDGER_SRC:
            self._raise(a)
            key = (a.case, a.ref, a.kind)
            if key in self.seen_bank:
                oid = f"{a.case}:{a.ref}:{a.kind}"
                d = self._settle(oid, Verdict.MATCHED, a.at_t, self.seen_bank[key])
                if d:
                    out.append(d)
            return out
        key = a.identity
        if key in self.seen_bank:
            return out           # duplicate delivery: already accounted for
        self.seen_bank[key] = a
        oid = f"{a.case}:{a.ref}:{a.kind}"
        if oid in self.open:
            d = self._settle(oid, Verdict.MATCHED, a.at_t, a)
            if d:
                out.append(d)
        elif oid not in self.decisions:
            self.orphans += 1
        return out

    def tick(self, now: int) -> list[Decision]:
        out = []
        for oid, ob in list(self.open.items()):
            if now >= self.model.decidable_at(ob.event_t, BANK_SRC):
                d = self._settle(oid, Verdict.EXCEPTION, now)
                if d:
                    out.append(d)
        return out

    def config(self) -> dict:
        return {"model": self.model.as_dict()}


class FixedTimeout(Reconciler):
    """Raise a break when the counterpart has not arrived within ``timeout``
    ticks of the obligation being raised.

    The timeout is measured from when the *ledger* reported the movement,
    which is the only clock an operations team has to hand.  Its flaw is
    structural rather than a matter of tuning: the ledger's report time already
    carries the ledger's own lateness, so the same nominal timeout means
    different things for promptly and belatedly reported movements.
    """

    name = "fixed_timeout"

    def __init__(self, timeout: int) -> None:
        super().__init__()
        self.timeout = timeout
        self.seen_bank: dict[tuple[str, str, str], Arrival] = {}

    def observe(self, a: Arrival) -> list[Decision]:
        out: list[Decision] = []
        if a.source == LEDGER_SRC:
            self._raise(a)
            key = (a.case, a.ref, a.kind)
            if key in self.seen_bank:
                oid = f"{a.case}:{a.ref}:{a.kind}"
                d = self._settle(oid, Verdict.MATCHED, a.at_t, self.seen_bank[key])
                if d:
                    out.append(d)
            return out
        if a.identity in self.seen_bank:
            return out
        self.seen_bank[a.identity] = a
        oid = f"{a.case}:{a.ref}:{a.kind}"
        if oid in self.open:
            d = self._settle(oid, Verdict.MATCHED, a.at_t, a)
            if d:
                out.append(d)
        elif oid not in self.decisions:
            self.orphans += 1
        return out

    def tick(self, now: int) -> list[Decision]:
        out = []
        for oid, ob in list(self.open.items()):
            if now >= ob.raised_t + self.timeout:
                d = self._settle(oid, Verdict.EXCEPTION, now)
                if d:
                    out.append(d)
        return out

    def config(self) -> dict:
        return {"timeout": self.timeout}


class GlobalWatermark(Reconciler):
    """The textbook streaming join: one watermark over the merged input.

    Each source carries its own watermark, ``max event time seen - delta``, and
    the operator's watermark is the minimum across sources -- the standard rule,
    and the reason this configuration is usually sound.  What it is not is
    timely: the bank posts in batches, so between batches its watermark does
    not move, and the join holds every pending decision until the next batch
    regardless of how long ago the movement itself occurred.
    """

    name = "global_watermark"

    def __init__(self, delta: int) -> None:
        super().__init__()
        self.delta = delta
        self.src_max: dict[str, int] = {}
        self.seen_bank: dict[tuple[str, str, str], Arrival] = {}

    def _watermark(self) -> int:
        if len(self.src_max) < 2:
            return -(10**9)
        return min(self.src_max.values()) - self.delta

    def observe(self, a: Arrival) -> list[Decision]:
        out: list[Decision] = []
        self.src_max[a.source] = max(self.src_max.get(a.source, a.event_t), a.event_t)
        if a.source == LEDGER_SRC:
            self._raise(a)
            key = (a.case, a.ref, a.kind)
            if key in self.seen_bank:
                oid = f"{a.case}:{a.ref}:{a.kind}"
                d = self._settle(oid, Verdict.MATCHED, a.at_t, self.seen_bank[key])
                if d:
                    out.append(d)
        else:
            if a.identity in self.seen_bank:
                return self._sweep(a.at_t)
            self.seen_bank[a.identity] = a
            oid = f"{a.case}:{a.ref}:{a.kind}"
            if oid in self.open:
                d = self._settle(oid, Verdict.MATCHED, a.at_t, a)
                if d:
                    out.append(d)
            elif oid not in self.decisions:
                self.orphans += 1
        out.extend(self._sweep(a.at_t))
        return out

    def _sweep(self, now: int) -> list[Decision]:
        wm = self._watermark()
        out = []
        for oid, ob in list(self.open.items()):
            if ob.event_t < wm:
                d = self._settle(oid, Verdict.EXCEPTION, now)
                if d:
                    out.append(d)
        return out

    def tick(self, now: int) -> list[Decision]:
        return self._sweep(now)

    def config(self) -> dict:
        return {"delta": self.delta}


class IdleWatermark(GlobalWatermark):
    """The same job after someone fixes the stall with an idleness timeout.

    Flink's ``WatermarkStrategy.withIdleness`` exists because the minimum rule
    above lets one quiet input freeze the whole operator.  Marking a quiet
    source idle removes it from the minimum, and the watermark starts moving
    again.  For a reconciliation join the quiet source is the bank, between
    batches -- so the watermark then advances at the *ledger's* rate, and the
    join begins declaring breaks against evidence that has not had a chance to
    arrive.  The fix for the liveness problem is precisely what destroys S1.
    """

    name = "idle_watermark"

    def __init__(self, delta: int, idle_timeout: int) -> None:
        super().__init__(delta)
        self.idle_timeout = idle_timeout
        self.last_seen: dict[str, int] = {}
        self._now = 0

    def _watermark(self) -> int:
        active = {
            s: m
            for s, m in self.src_max.items()
            if self._now - self.last_seen.get(s, self._now) <= self.idle_timeout
        }
        if not active:
            return -(10**9)
        return min(active.values()) - self.delta

    def observe(self, a: Arrival) -> list[Decision]:
        self._now = a.at_t
        self.last_seen[a.source] = a.at_t
        return super().observe(a)

    def tick(self, now: int) -> list[Decision]:
        self._now = now
        return super().tick(now)

    def config(self) -> dict:
        return {"delta": self.delta, "idle_timeout": self.idle_timeout}


class AmountDate(Reconciler):
    """Business matching rules: pair on amount and proximity in time.

    No shared reference is used, because in the deployments this models there
    is not one -- a bank statement line carries a value date and a figure.  The
    reconciler pairs an obligation with any unconsumed bank record of equal
    amount whose event time is within ``tolerance``, preferring the closest.

    Its distinctive failure is not lateness but ambiguity.  Two movements of
    the same size close together are indistinguishable, so the first pairing
    made can be the wrong one, and it is only revealed as wrong when the real
    counterpart shows up with nothing left to pair to.
    """

    name = "amount_date"
    matches_on = "attributes"

    def __init__(self, tolerance: int, decide_after: int) -> None:
        super().__init__()
        self.tolerance = tolerance
        self.decide_after = decide_after
        self.pool: list[Arrival] = []
        self.consumed: set[tuple[int, int]] = set()

    def observe(self, a: Arrival) -> list[Decision]:
        out: list[Decision] = []
        if a.source == LEDGER_SRC:
            self._raise(a)
            oid = f"{a.case}:{a.ref}:{a.kind}"
            ob = self.open.get(oid)
            if ob is not None:
                cand = self._pick(ob)
                if cand is not None:
                    self.consumed.add((cand.seq, cand.copy))
                    d = self._settle(oid, Verdict.MATCHED, a.at_t, cand)
                    if d:
                        out.append(d)
            return out
        self.pool.append(a)
        for oid, ob in list(self.open.items()):
            cand = self._pick(ob)
            if cand is not None:
                self.consumed.add((cand.seq, cand.copy))
                d = self._settle(oid, Verdict.MATCHED, a.at_t, cand)
                if d:
                    out.append(d)
                break
        return out

    def _pick(self, ob: Obligation) -> Arrival | None:
        best: Arrival | None = None
        for c in self.pool:
            if (c.seq, c.copy) in self.consumed:
                continue
            if c.amount != ob.amount:
                continue
            if abs(c.event_t - ob.event_t) > self.tolerance:
                continue
            if best is None or abs(c.event_t - ob.event_t) < abs(best.event_t - ob.event_t):
                best = c
        return best

    def tick(self, now: int) -> list[Decision]:
        out = []
        for oid, ob in list(self.open.items()):
            if now >= ob.raised_t + self.decide_after:
                d = self._settle(oid, Verdict.EXCEPTION, now)
                if d:
                    out.append(d)
        return out

    def config(self) -> dict:
        return {"tolerance": self.tolerance, "decide_after": self.decide_after}
