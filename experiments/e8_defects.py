"""E8 -- which fault causes which contract violation.

A break rate is not actionable on its own.  What an operator needs is the map
from a property that failed to the thing in the pipeline that failed it, and
that map is what this experiment builds: each of P1's delivery-fault families
is enabled on its own, at a fixed intensity, and the resulting violations are
attributed to it.

The second half is the defect corpus.  Four of P1's nine case archetypes are
reconciliation defects by construction -- a settlement the processor never
recorded, one delivered twice, a half-written ledger entry, and a processor
view that lags far behind -- so a corpus of labelled defects comes out of the
generator rather than being annotated by hand.  Each entry records the
archetype, the property it breaks, and which reconcilers it breaks, and that
triple is checkable by re-running the row rather than taken on trust.
"""

from __future__ import annotations

from _common import write

from reconstream.calibrate import calibrate
from reconstream.checker import grade, model_respected, run, summarise
from reconstream.contract import SourceModel
from reconstream.workload import RECON_DEFECTS, build_workload
import reconstream.matchers as M

from finalitybench.faults import PROFILE_FAMILIES, FaultProfile

SEEDS = (1, 2, 3, 4, 5)
N_CASES = 200
GRID = list(range(10, 501, 10))
CHECK_BANK_BOUND = 80
INTENSITY = 0.30

FAMILIES = {
    "typed_horizon": lambda p: M.TypedHorizon(SourceModel(bound={"ledger": 2, "bank": p})),
    "fixed_timeout": lambda p: M.FixedTimeout(p),
    "global_watermark": lambda p: M.GlobalWatermark(p),
    "idle_watermark": lambda p: M.IdleWatermark(p, 60),
    "amount_date": lambda p: M.AmountDate(60, p),
}


def main() -> None:
    model = SourceModel(bound={"ledger": 2, "bank": CHECK_BANK_BOUND})
    calm = [build_workload(n_cases=N_CASES, seed=s, profile=FaultProfile.none()) for s in SEEDS]
    cals = {n: calibrate(n, mk, GRID, calm, model) for n, mk in FAMILIES.items()}

    out: dict = {
        "config": {"seeds": SEEDS, "n_cases": N_CASES, "intensity": INTENSITY,
                   "model": model.as_dict(), "recon_defect_archetypes": list(RECON_DEFECTS)},
        "calibration": {k: v.as_dict() for k, v in cals.items()},
        "fault_families": {},
        "defect_corpus": {},
    }

    # --- one fault family at a time ---------------------------------------
    arms = ["none", *sorted(PROFILE_FAMILIES)]
    for fam in arms:
        profile = FaultProfile.none() if fam == "none" else FaultProfile.only(fam)
        if fam != "none":
            profile = FaultProfile(families=profile.families, intensity=INTENSITY)
        workloads = [build_workload(n_cases=N_CASES, seed=200 + s, profile=profile) for s in SEEDS]
        broken = {"ledger": 0, "bank": 0}
        for w in workloads:
            for k, v in model_respected(w.arrivals, model).items():
                broken[k] = broken.get(k, 0) + v
        rec = {"model_violations": broken, "arms": {}}
        for name, mk in FAMILIES.items():
            param = cals[name].param or GRID[-1]
            pooled = []
            for w in workloads:
                r = mk(param)
                d = run(r, w.arrivals, horizon=w.horizon)
                pooled.extend(grade(r, w.arrivals, d, model, horizon=w.horizon))
            s = summarise(pooled)
            rec["arms"][name] = {
                "inadmissible_rate": s["inadmissible_rate"],
                "s1_premature_break": s["s1_premature_break"],
                "s2_violations": s["s2_violations"],
                "m1_retracted": s["m1_retracted"],
                "false_break_rate": s["false_break_rate"],
                "false_match_rate": s["false_match_rate"],
                "break_recall": s["break_recall"],
            }
        out["fault_families"][fam] = rec

    # --- the defect corpus -------------------------------------------------
    workloads = [build_workload(n_cases=N_CASES, seed=300 + s, profile=FaultProfile(intensity=INTENSITY))
                 for s in SEEDS]
    by_arch: dict[str, dict] = {}
    for name, mk in FAMILIES.items():
        param = cals[name].param or GRID[-1]
        for w in workloads:
            arch_of = {c["task_id"]: c["archetype"] for c in w.cases}
            r = mk(param)
            d = run(r, w.arrivals, horizon=w.horizon)
            for g in grade(r, w.arrivals, d, model, horizon=w.horizon):
                arch = arch_of.get(g.oid.split(":", 1)[0], "unknown")
                slot = by_arch.setdefault(arch, {
                    "is_recon_defect": arch in RECON_DEFECTS,
                    "obligations": 0,
                    "per_arm": {},
                })
                arm = slot["per_arm"].setdefault(
                    name, {"n": 0, "inadmissible": 0, "false_break": 0, "false_match": 0,
                           "s1": 0, "s2": 0}
                )
                arm["n"] += 1
                if not g.admissible:
                    arm["inadmissible"] += 1
                if g.violation == "S1_premature_break":
                    arm["s1"] += 1
                if g.violation in ("S2_premature_match", "S2_ambiguous_match"):
                    arm["s2"] += 1
                if g.error == "false_break":
                    arm["false_break"] += 1
                if g.error in ("false_match", "mispaired"):
                    arm["false_match"] += 1
    for arch, slot in by_arch.items():
        slot["obligations"] = max(a["n"] for a in slot["per_arm"].values())
        slot["breaks_property"] = sorted({
            prop
            for arm in slot["per_arm"].values()
            for prop, hit in (("S1", arm["s1"]), ("S2", arm["s2"])) if hit
        })
        slot["affected_arms"] = sorted(
            n for n, a in slot["per_arm"].items() if a["inadmissible"] or a["false_break"] or a["false_match"]
        )
    out["defect_corpus"] = by_arch

    write("e8_defects.json", out)


if __name__ == "__main__":
    main()
