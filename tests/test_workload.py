"""Properties the generated streams must have for the results to mean anything."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from reconstream.checker import model_respected, obligations_from
from reconstream.contract import SourceModel
from reconstream.streams import BANK_SRC, LEDGER_SRC, stream_stats
from reconstream.workload import build_workload

from finalitybench.faults import BANK_BATCH, BANK_LAG, FaultProfile


def test_workload_is_a_pure_function_of_its_inputs():
    a = build_workload(n_cases=60, seed=5, profile=FaultProfile.none())
    b = build_workload(n_cases=60, seed=5, profile=FaultProfile.none())
    assert a.fingerprint() == b.fingerprint()
    assert build_workload(n_cases=60, seed=6, profile=FaultProfile.none()).fingerprint() != a.fingerprint()


def test_arrivals_are_ordered_by_instant():
    w = build_workload(n_cases=60, seed=5)
    keys = [(a.at_t, a.source, a.seq, a.copy) for a in w.arrivals]
    assert keys == sorted(keys)


def test_nothing_is_reported_before_it_happened():
    """A source cannot tell you about a fact before the fact exists."""
    w = build_workload(n_cases=120, seed=5)
    assert all(a.at_t >= a.event_t for a in w.arrivals)


def test_fault_free_bank_lag_stays_inside_the_declared_bound():
    """The default source model claims the bank is at most 75 ticks behind.

    That number is read off P1's batching constants rather than guessed, so if
    the simulator's batching ever changes this should fail rather than the
    contract silently becoming wrong.
    """
    w = build_workload(n_cases=200, seed=5, profile=FaultProfile.none())
    stats = stream_stats(w.arrivals)
    assert stats[BANK_SRC]["max"] <= BANK_BATCH + BANK_LAG
    assert model_respected(w.arrivals, SourceModel())[BANK_SRC] == 0


def test_faults_do_break_the_declared_bound():
    """The shifted regime must actually shift, or E3 measures nothing."""
    w = build_workload(n_cases=200, seed=5, profile=FaultProfile())
    assert sum(model_respected(w.arrivals, SourceModel()).values()) > 0


def test_injected_breaks_are_regime_independent():
    """The *injected* positive class does not move with the fault profile."""
    calm = build_workload(n_cases=200, seed=5, profile=FaultProfile.none())
    faulty = build_workload(n_cases=200, seed=5, profile=FaultProfile())
    calm_breaks = {c["task_id"] for c in calm.cases if c["truly_broken"]}
    faulty_breaks = {c["task_id"] for c in faulty.cases if c["truly_broken"]}
    assert calm_breaks == faulty_breaks
    assert calm_breaks


def test_delivery_loss_creates_further_genuine_breaks():
    """The *graded* positive class does move, and only the loss family moves it.

    Injection guarantees a positive class exists in every regime; it does not
    hold the class constant, because dropping a bank delivery is itself a
    genuine break. Any comparison of break rates across regimes therefore has
    to divide by the negatives rather than by every obligation, which is what
    ``false_break_fpr`` does. This test exists so that the distinction cannot
    be quietly lost again.
    """
    from reconstream.checker import bank_truth, obligations_from

    def graded_breaks(profile):
        w = build_workload(n_cases=200, seed=5, profile=profile)
        obs, truth = obligations_from(w.arrivals), bank_truth(w.arrivals)
        return sum(1 for o in obs if o not in truth)

    calm = graded_breaks(FaultProfile.none())
    loss_only = graded_breaks(FaultProfile(families=frozenset({"loss"}), intensity=0.30))
    delay_only = graded_breaks(FaultProfile(families=frozenset({"delay"}), intensity=0.30))
    assert loss_only > calm
    assert delay_only == calm


def test_a_true_break_has_no_bank_evidence():
    w = build_workload(n_cases=200, seed=5, profile=FaultProfile.none())
    broken = {c["task_id"] for c in w.cases if c["truly_broken"]}
    bank_cases = {a.case for a in w.arrivals if a.source == BANK_SRC}
    assert not (broken & bank_cases)


def test_every_obligation_comes_from_the_ledger():
    w = build_workload(n_cases=120, seed=5)
    obs = obligations_from(w.arrivals)
    ledger_ids = {f"{a.case}:{a.ref}:{a.kind}" for a in w.arrivals if a.source == LEDGER_SRC}
    assert set(obs) == ledger_ids
