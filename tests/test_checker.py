"""The checker's two axes stay independent, and its bookkeeping adds up."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reconstream.bootstrap import bootstrap, false_break_rate, paired_difference
from reconstream.checker import grade, run, summarise
from reconstream.contract import SourceModel
from reconstream.workload import build_workload
import reconstream.matchers as M

from finalitybench.faults import FaultProfile

MODEL = SourceModel(bound={"ledger": 2, "bank": 80})


def _run(mk, w):
    r = mk()
    d = run(r, w.arrivals, horizon=w.horizon)
    return grade(r, w.arrivals, d, MODEL, horizon=w.horizon)


def test_a_contract_following_reconciler_never_violates_s1():
    """The central soundness claim, on both regimes.

    The typed horizon decides exactly at the declared bound, so no verdict of
    its should ever be premature with respect to that same bound -- whatever
    the input does.
    """
    for profile in (FaultProfile.none(), FaultProfile()):
        for seed in (1, 2, 3):
            w = build_workload(n_cases=150, seed=seed, profile=profile)
            g = _run(lambda: M.TypedHorizon(MODEL), w)
            premature = [x for x in g if x.violation == "S1_premature_break"]
            assert not premature, f"{len(premature)} premature breaks at seed {seed}"


def test_admissibility_and_correctness_are_different_columns():
    """Under shift the arms stay admissible while their accuracy falls.

    If this ever stopped holding, the paper's main claim -- that the two can be
    told apart -- would be false, so it is asserted rather than described.
    """
    w = build_workload(n_cases=200, seed=11, profile=FaultProfile())
    g = _run(lambda: M.FixedTimeout(80), w)
    s = summarise(g)
    assert s["inadmissible_rate"] == 0.0
    assert s["false_break_rate"] > 0.05
    assert s["model_broken"] > 0


def test_calm_traffic_leaves_a_calibrated_arm_clean():
    w = build_workload(n_cases=200, seed=11, profile=FaultProfile.none())
    s = summarise(_run(lambda: M.TypedHorizon(MODEL), w))
    assert s["inadmissible_rate"] == 0.0
    assert s["false_break_rate"] == 0.0
    assert s["break_recall"] == 1.0


def test_counts_are_consistent():
    w = build_workload(n_cases=150, seed=3, profile=FaultProfile())
    s = summarise(_run(lambda: M.GlobalWatermark(60), w))
    assert s["terminal"] + s["undecided"] == s["n"]
    assert s["breaks_detected"] <= s["true_breaks"] <= s["n"]
    assert 0.0 <= s["inadmissible_rate"] <= 1.0


def test_bootstrap_interval_brackets_its_point_estimate():
    w = build_workload(n_cases=200, seed=3, profile=FaultProfile())
    g = _run(lambda: M.FixedTimeout(80), w)
    ci = bootstrap(g, false_break_rate, replicates=300, seed=1)
    assert ci.lo <= ci.point <= ci.hi


def test_paired_difference_is_tighter_than_independent_intervals():
    """Both arms saw the same stream, so the paired resample should exploit it."""
    w = build_workload(n_cases=200, seed=3, profile=FaultProfile())
    a = _run(lambda: M.TypedHorizon(MODEL), w)
    b = _run(lambda: M.FixedTimeout(80), w)
    d = paired_difference(a, b, false_break_rate, replicates=400, seed=2)
    ia = bootstrap(a, false_break_rate, replicates=400, seed=2)
    ib = bootstrap(b, false_break_rate, replicates=400, seed=2)
    assert (d.hi - d.lo) <= (ia.hi - ia.lo) + (ib.hi - ib.lo)
