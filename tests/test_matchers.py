"""Each reconciler does the specific thing the paper says it does."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from reconstream.checker import grade, run
from reconstream.contract import SourceModel, Verdict
from reconstream.streams import Arrival, BANK_SRC, LEDGER_SRC
import reconstream.matchers as M


def led(event_t, at_t, seq, case="c1", ref="r1", amount=500):
    return Arrival(LEDGER_SRC, at_t, event_t, seq, "CAPTURE_SETTLED", case, ref, amount)


def bnk(event_t, at_t, seq, case="c1", ref="r1", amount=500, copy=0):
    return Arrival(BANK_SRC, at_t, event_t, seq, "CAPTURE_SETTLED", case, ref, amount, copy)


MODEL = SourceModel(bound={"ledger": 2, "bank": 75})


def test_typed_horizon_matches_on_arrival_and_breaks_at_the_horizon():
    r = M.TypedHorizon(MODEL)
    d = run(r, [led(100, 102, 1), bnk(100, 140, 1)], horizon=400, tick_every=1)
    assert d["c1:r1:CAPTURE_SETTLED"].verdict is Verdict.MATCHED
    assert d["c1:r1:CAPTURE_SETTLED"].at_t == 140

    r = M.TypedHorizon(MODEL)
    d = run(r, [led(100, 102, 1)], horizon=400, tick_every=1)
    assert d["c1:r1:CAPTURE_SETTLED"].verdict is Verdict.EXCEPTION
    assert d["c1:r1:CAPTURE_SETTLED"].at_t == 175


def test_typed_horizon_ignores_a_duplicate_bank_record():
    """A replayed delivery is the same money, so it must not match twice."""
    r = M.TypedHorizon(MODEL)
    arrivals = [led(100, 102, 1), bnk(100, 140, 1), bnk(100, 150, 1, copy=1)]
    run(r, arrivals, horizon=400, tick_every=1)
    assert len(r.decisions) == 1
    assert r.orphans == 0


def test_fixed_timeout_inherits_the_ledger_lateness():
    """Identical movement, late ledger report -- the break comes later.

    This is the mechanism behind the heavier tail reported in E2, pinned down
    on two arrivals so that it cannot be confused with a sampling effect.
    """
    prompt = M.FixedTimeout(80)
    run(prompt, [led(100, 102, 1)], horizon=600, tick_every=1)
    tardy = M.FixedTimeout(80)
    run(tardy, [led(100, 300, 1)], horizon=600, tick_every=1)
    assert prompt.decisions["c1:r1:CAPTURE_SETTLED"].at_t == 182
    assert tardy.decisions["c1:r1:CAPTURE_SETTLED"].at_t == 380


def test_amount_date_can_pair_the_wrong_movement():
    """Two equal amounts in flight; attribute matching has nothing to separate
    them, so the first pairing made can be the wrong one."""
    r = M.AmountDate(tolerance=60, decide_after=400)
    arrivals = [
        led(100, 102, 1, case="cA", ref="rA", amount=500),
        led(110, 112, 2, case="cB", ref="rB", amount=500),
        bnk(110, 150, 2, case="cB", ref="rB", amount=500),
    ]
    run(r, arrivals, horizon=600, tick_every=1)
    g = {x.oid: x for x in grade(r, arrivals, r.decisions, MODEL, horizon=600)}
    # cA is paired with the record that belongs to cB.  That is both a
    # mispairing and -- since cA has no counterpart of its own -- a false match,
    # so the flag is checked rather than the error label.
    assert g["cA:rA:CAPTURE_SETTLED"].mispaired
    assert g["cA:rA:CAPTURE_SETTLED"].error == "false_match"
    assert g["cA:rA:CAPTURE_SETTLED"].violation == "S2_ambiguous_match"


def test_idle_watermark_advances_when_a_source_goes_quiet():
    """With the bank silent, idleness lets the watermark run on the ledger
    alone -- which is exactly how a premature break gets emitted."""
    arrivals = [led(100, 102, 1, case="cA", ref="rA"), led(500, 502, 2, case="cB", ref="rB")]
    horizon = 600
    patient = M.GlobalWatermark(10)
    run(patient, arrivals, horizon=horizon, tick_every=1)
    impatient = M.IdleWatermark(10, idle_timeout=5)
    run(impatient, arrivals, horizon=horizon, tick_every=1)
    # Both end up deciding, because the harness forces a verdict when the
    # stream ends.  The difference is *when*: the min-rule watermark never
    # advances on its own and only decides at the forced flush, while idleness
    # lets it decide during the run.
    assert all(d.at_t == horizon for d in patient.decisions.values())
    assert any(d.at_t < horizon for d in impatient.decisions.values())


def test_no_reconciler_leaves_an_obligation_open():
    """L1: every arm reaches a terminal verdict for every obligation."""
    arrivals = [led(100, 102, 1), led(200, 202, 2, case="c2", ref="r2")]
    for mk in (lambda: M.TypedHorizon(MODEL), lambda: M.FixedTimeout(80),
               lambda: M.GlobalWatermark(60), lambda: M.IdleWatermark(60, 60),
               lambda: M.AmountDate(60, 200)):
        r = mk()
        d = run(r, arrivals, horizon=900, tick_every=1)
        assert len(d) == 2, f"{r.name} left an obligation open"
        assert all(v.verdict.is_terminal for v in d.values())
