"""The contract's predicates, checked against hand-worked cases.

These are deliberately small and literal.  If the admissibility rule is ever
"improved" into something that no longer means what the paper says it means,
one of these should fail rather than the experiments quietly shifting.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from reconstream.contract import (
    Obligation,
    SourceModel,
    Verdict,
    closure_delay,
    exception_admissible,
    match_admissible,
)


@pytest.fixture
def model():
    return SourceModel(bound={"ledger": 2, "bank": 75}, settlement_window=0)


@pytest.fixture
def ob():
    return Obligation("o", "c", "r", "CAPTURE_SETTLED", 1000, event_t=100, raised_t=102)


def test_break_is_inadmissible_before_the_bank_horizon(model, ob):
    assert not exception_admissible(ob, 174, model)
    assert exception_admissible(ob, 175, model)


def test_break_admissibility_ignores_when_the_ledger_spoke(model):
    """Two obligations for the same movement, reported at different times.

    The bank's horizon is a property of the movement, not of how promptly the
    ledger mentioned it, so a late ledger report must not licence an earlier
    break.  A timeout measured from the ledger gets this wrong, which is the
    defect the typed horizon exists to avoid.
    """
    prompt = Obligation("a", "c", "r", "K", 1, event_t=100, raised_t=102)
    tardy = Obligation("b", "c", "r", "K", 1, event_t=100, raised_t=300)
    for at_t in (174, 175, 400):
        assert exception_admissible(prompt, at_t, model) == exception_admissible(tardy, at_t, model)


def test_identity_match_is_admissible_immediately(model, ob):
    assert match_admissible(ob, 0, model, identity_matched=True, rival_possible=False)


def test_attribute_match_must_wait_for_the_horizon(model, ob):
    assert not match_admissible(ob, 120, model, identity_matched=False, rival_possible=True)
    assert match_admissible(ob, 175, model, identity_matched=False, rival_possible=True)


def test_settlement_window_shifts_the_decision_point(ob):
    wide = SourceModel(bound={"ledger": 2, "bank": 75}, settlement_window=50)
    assert not exception_admissible(ob, 175, wide)
    assert exception_admissible(ob, 225, wide)


def test_closure_delay_is_signed(model, ob):
    assert closure_delay(ob, 175, model) == 0
    assert closure_delay(ob, 100, model) < 0
    assert closure_delay(ob, 200, model) > 0


def test_pending_is_the_only_non_terminal_verdict():
    assert not Verdict.PENDING.is_terminal
    assert Verdict.MATCHED.is_terminal and Verdict.EXCEPTION.is_terminal


def test_the_worked_timeline_matches_the_simulator():
    """The paragraph said the batch boundary falls at 1080. It falls at 1020.

    The range [1015, 1074] is right -- it is what the contract may assume
    without knowing where in the cycle the movement fell -- and the specific
    boundary was not. Both are asserted here so the distinction survives.
    """
    from reconstream._p1 import ensure_p1
    ensure_p1()
    from finalitybench.faults import BANK_BATCH, _bank_visible_at as visible

    assert visible(1000) == 1020
    delays = [visible(t) - t for t in range(BANK_BATCH)]
    assert min(delays) == 15
    assert max(delays) == 74
    # The declared bound has to cover the worst case and nothing less.
    assert SourceModel().lateness("bank") == max(delays) + 1
