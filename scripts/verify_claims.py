"""Check every number in the paper against the results files.

The failure mode this exists to prevent is a stale figure surviving a re-run:
a number is written into the text, the experiment changes, and nothing
complains.  Each entry below names a claim, the value the paper states, and
where that value is supposed to come from.  Run it after every experiment
re-run and before every release.

Usage:  python scripts/verify_claims.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
PAPER = ROOT / "paper" / "reconstream.tex"


def load(name: str) -> dict | None:
    path = RESULTS / name
    return json.loads(path.read_text()) if path.exists() else None


def pct(x: float) -> float:
    return round(100 * x, 2)


def build_claims() -> list[tuple[str, object, object]]:
    """(description, stated in paper, computed from results)."""
    e1, e2, e3 = load("e1_main.json"), load("e2_frontier.json"), load("e3_shift.json")
    e4, e5, e6 = load("e4_idleness.json"), load("e5_costs.json"), load("e6_sql_parity.json")
    e9 = load("e9_worked_instance.json")
    e8 = load("e8_defects.json")
    e10 = load("e10_contention.json")
    c: list[tuple[str, object, object]] = []

    if e1:
        calm, faulty = e1["regimes"]["calm"], e1["regimes"]["faulty"]
        c.append(("obligations, calm", 885, calm["arms"]["typed_horizon"]["n"]))
        c.append(("obligations, shifted", 593, faulty["arms"]["typed_horizon"]["n"]))
        c.append(("arrivals, calm", 1733, sum(w["arrivals"] for w in calm["workloads"])))
        c.append(("arrivals, shifted", 1684, sum(w["arrivals"] for w in faulty["workloads"])))
        c.append(("true breaks, calm", 45, sum(w["true_breaks"] for w in calm["workloads"])))
        c.append(("true breaks, shifted", 45, sum(w["true_breaks"] for w in faulty["workloads"])))
        c.append(("bank bound violations, shifted", 240, faulty["model_violations"]["bank"]))
        c.append(("ledger bound violations, shifted", 413, faulty["model_violations"]["ledger"]))
        c.append(("amount/date calibrates", False, e1["calibration"]["amount_date"]["converged"]))
        for arm, mean, p99 in (("typed_horizon", 2.1, 4), ("fixed_timeout", 3.8, 6),
                               ("global_watermark", 32.7, 223), ("idle_watermark", 29.9, 201)):
            a = calm["arms"][arm]
            c.append((f"calm {arm} mean closure", mean, round(a["mean_closure"]["point"], 1)))
            c.append((f"calm {arm} p99 closure", p99, round(a["p99_closure"]["point"])))
            c.append((f"calm {arm} contract violations", 0.0, pct(a["inadmissible_rate"]["point"])))
        c.append(("calm amount/date violations %", 94.46,
                  pct(calm["arms"]["amount_date"]["inadmissible_rate"]["point"])))
        c.append(("calm amount/date FPR %", 2.12,
                  pct(calm["arms"]["amount_date"]["false_break_fpr"]["point"])))
        c.append(("shifted amount/date FPR %", 8.36,
                  pct(faulty["arms"]["amount_date"]["false_break_fpr"]["point"])))
        c.append(("calm amount/date false match %", 22.82,
                  pct(calm["arms"]["amount_date"]["false_match_rate"]["point"])))
        fb = {k: pct(v["false_break_fpr"]["point"]) for k, v in faulty["arms"].items()}
        c.append(("shifted min false-break FPR % (identity arms)", 18.28,
                  min(v for k, v in fb.items() if k != "amount_date")))
        c.append(("shifted max false-break FPR % (identity arms)", 22.98,
                  max(v for k, v in fb.items() if k != "amount_date")))
        for arm, fpr, exc in (("typed_horizon", 22.98, 298), ("fixed_timeout", 20.89, 290),
                              ("global_watermark", 18.28, 280), ("idle_watermark", 18.80, 282)):
            a = faulty["arms"][arm]
            c.append((f"shifted {arm} FPR %", fpr, pct(a["false_break_fpr"]["point"])))
            c.append((f"shifted {arm} exceptions", exc, a["n_exceptions"]))
        c.append(("calm settled obligations", 848, calm["arms"]["typed_horizon"]["negatives"]))
        c.append(("shifted settled obligations", 383, faulty["arms"]["typed_horizon"]["negatives"]))
        c.append(("calm graded true breaks", 37, calm["arms"]["typed_horizon"]["true_breaks"]))
        c.append(("shifted graded true breaks", 210, faulty["arms"]["typed_horizon"]["true_breaks"]))
        c.append(("calm exceptions per arm", 37, calm["arms"]["typed_horizon"]["n_exceptions"]))
        inadm = {k: pct(v["inadmissible_rate"]["point"]) for k, v in faulty["arms"].items()}
        c.append(("shifted max contract violation % (identity arms)", 1.01,
                  max(v for k, v in inadm.items() if k != "amount_date")))

    if e2:
        z = e2["regimes"]["faulty"]["at_zero_false_breaks"]
        for arm, mean, p99, sd in (("typed_horizon", 221.6, 224, 5.0),
                                   ("idle_watermark", 245.8, 392, 40.4),
                                   ("fixed_timeout", 253.8, 446, 60.8),
                                   ("global_watermark", 264.9, 554, 69.8)):
            c.append((f"zero-fb {arm} mean", mean, round(z[arm]["mean_closure_ci"]["point"], 1)))
            c.append((f"zero-fb {arm} p99", p99, round(z[arm]["p99_closure_ci"]["point"])))
            c.append((f"zero-fb {arm} sd", sd, round(z[arm]["sd_closure"], 1)))
        gain = 100 * (z["fixed_timeout"]["mean_closure"] - z["typed_horizon"]["mean_closure"]) \
            / z["fixed_timeout"]["mean_closure"]
        c.append(("typed vs fixed closure improvement %", 12.7, round(gain, 1)))

    if e3:
        last = e3["sweep"][-1]
        c.append(("max bound-violation rate in sweep %", 57.9, pct(last["model_violation_rate"])))
        c.append(("sweep fixed_timeout FPR % at 0.5", 25.64,
                  pct(last["arms"]["fixed_timeout"]["false_break_fpr"]["point"])))
        c.append(("sweep typed_horizon FPR % at 0.5", 30.77,
                  pct(last["arms"]["typed_horizon"]["false_break_fpr"]["point"])))
        worst = max(pct(r["arms"][a]["inadmissible_rate"]["point"])
                    for r in e3["sweep"] for a in r["arms"])
        c.append(("max contract violation % across whole sweep", 1.11, worst))
        no_idle = max(pct(r["arms"][a]["inadmissible_rate"]["point"])
                      for r in e3["sweep"] for a in r["arms"] if a != "idle_watermark")
        c.append(("max contract violation % excluding idleness", 0.43, no_idle))

    if e4:
        c.append(("bank posting period", 60, e4["config"]["bank_batch_period"]))
        c.append(("no-idleness calm violations %", 0.0,
                  pct(e4["baseline_no_idleness"]["calm"]["inadmissible_rate"]["point"])))
        by = {r["idle_timeout"]: r["regimes"]["calm"]["inadmissible_rate"] for r in e4["sweep"]}
        c.append(("idle=5 calm violations %", 5.42, pct(by[5]["point"])))
        c.append(("idle=5 calm CI lo", 3.94, pct(by[5]["lo"])))
        c.append(("idle=5 calm CI hi", 6.92, pct(by[5]["hi"])))
        c.append(("idle=30 calm violations %", 0.45, pct(by[30]["point"])))
        c.append(("idle=50 calm violations %", 0.11, pct(by[50]["point"])))
        c.append(("idle=60 calm violations %", 0.0, pct(by[60]["point"])))
        above = [pct(v["point"]) for k, v in by.items() if k >= 60]
        c.append(("all idle>=period calm violations zero", True, all(x == 0.0 for x in above)))
        fb5 = [r for r in e4["sweep"] if r["idle_timeout"] == 5][0]
        c.append(("idle=5 calm false breaks %", 3.05,
                  pct(fb5["regimes"]["calm"]["false_break_rate"]["point"])))

    if e5:
        c.append(("cost grid points per regime", 125, e5["sweeps"]["calm"]["n_points"]))
        c.append(("calm: typed cheapest count", 125, e5["sweeps"]["calm"]["cheapest_counts"]["typed_horizon"]))
        c.append(("shifted: typed cheapest count", 30, e5["sweeps"]["faulty"]["cheapest_counts"]["typed_horizon"]))
        c.append(("shifted: watermark cheapest count", 75,
                  e5["sweeps"]["faulty"]["cheapest_counts"]["global_watermark"]))
        c.append(("shifted: fixed cheapest count", 20,
                  e5["sweeps"]["faulty"]["cheapest_counts"]["fixed_timeout"]))

    if e6:
        c.append(("SQL parity verdicts compared", 4395, e6["admissibility"]["compared"]))
        c.append(("SQL parity agreement", 1.0, e6["admissibility"]["agreement"]))
        c.append(("SQL parity disagreements", 0, len(e6["disagreements"])))

    e7 = load("e7_flink.json")
    if e7 and e7.get("status") == "ok":
        by = {}
        for r in e7["runs"]:
            by.setdefault((r["window"], str(r["idle_timeout"])), []).append(r)
        def avg(key, field):
            rs = by[key]
            return sum(x[field] for x in rs) / len(rs)
        # The idleness timeout is inert on a bounded file source, so the table
        # collapses it and each row averages the eight runs of one window.
        # Pinning a single (window, idleness) cell would pin a draw: E10 shows
        # the engine's own spread is larger than the differences between cells.
        def win(w, field):
            rs = [r for r in e7["runs"] if r["window"] == w]
            return sum(x[field] for x in rs) / len(rs)
        def winrange(w):
            rs = [pct(r["inadmissible_rate"]) for r in e7["runs"] if r["window"] == w]
            return min(rs), max(rs)
        c.append(("flink win80 violations %", 14.91, pct(win(80, "inadmissible_rate"))))
        c.append(("flink win160 violations %", 18.18, pct(win(160, "inadmissible_rate"))))
        c.append(("flink win320 violations %", 20.09, pct(win(320, "inadmissible_rate"))))
        c.append(("flink win80 range", (14.78, 15.04), winrange(80)))
        c.append(("flink win160 range", (14.16, 20.87), winrange(160)))
        c.append(("flink win320 range", (16.52, 23.01), winrange(320)))
        c.append(("flink win80 false-break %", 18.28, pct(win(80, "false_break_rate"))))
        c.append(("flink win160 false-break %", 16.00, pct(win(160, "false_break_rate"))))
        c.append(("flink win320 false-break %", 14.80, pct(win(320, "false_break_rate"))))
        worst = max(pct(r["inadmissible_rate"]) for r in e7["runs"])
        best = min(pct(r["inadmissible_rate"]) for r in e7["runs"])
        c.append(("flink min violation % over single runs", 14.16, best))
        c.append(("flink max violation % over single runs", 23.01, worst))
        wm = [pct(win(w, "inadmissible_rate")) for w in (80, 160, 320)]
        c.append(("flink min per-window mean violation %", 14.91, min(wm)))
        c.append(("flink max per-window mean violation %", 20.09, max(wm)))
        c.append(("flink violation rate rises with the window", True, wm == sorted(wm)))
        # Windows 80 and 320 are identical across the four inert idleness
        # settings within a seed; window 160 seed 1 is not. That asymmetry is
        # the engine's nondeterminism, and the paper says so.
        def spread_within_seed(w, s):
            rs = [pct(r["inadmissible_rate"]) for r in e7["runs"]
                  if r["window"] == w and r["seed"] == s]
            return max(rs) - min(rs)
        # WHICH cell moves is not stable between runs -- an earlier execution
        # had window 160 seed 1 varying and window 320 flat, this one has the
        # reverse -- so the claims are about the shape: window 80 flat, and
        # exactly one seed moving at each of the other two windows.
        c.append(("flink win80 is idleness-invariant on both seeds", True,
                  spread_within_seed(80, 1) == 0 and spread_within_seed(80, 2) == 0))
        for w, spread in ((160, 1.77), (320, 0.87)):
            moving = [s for s in (1, 2) if spread_within_seed(w, s) > 0]
            c.append((f"flink win{w}: exactly one seed moves across inert settings",
                      1, len(moving)))
            c.append((f"flink win{w} spread on the moving seed, points", spread,
                      spread_within_seed(w, moving[0]) if moving else 0.0))
        # Determinism on an idle machine. The loaded-machine observation in the
        # paper is explicitly labelled unreproduced and is not checked here,
        # because there is no results file that reproduces it -- which is the
        # point of saying so in the text.
        # The engine is not deterministic on seed 1, so what is asserted here
        # is the shape of the instability, not the exact obligation count. An
        # earlier version pinned the break counts and the fidelity to one
        # draw, and a re-run that changed no code failed the suite.
        det = {f["seed"]: f for f in e7["determinism"]}
        c.append(("flink seed1 is unstable across repeats", True,
                  det[1]["unstable"] > 0))
        # E10 measured this rate six times per condition and found 0-25.22%.
        # A bound is the only assertion that survives a re-run; the shipped
        # run happens to sit near the top of that band, which the paper notes.
        e10_band = load("e10_contention.json")
        top = max(e10_band["headline"]["idle_rates"] + e10_band["headline"]["loaded_rates"]) \
            if e10_band and e10_band.get("status") == "ok" else 1.0
        c.append(("flink seed1 instability lies in E10's measured band", True,
                  0.0 <= det[1]["unstable_rate"] <= max(top, 0.05) + 1e-9))
        c.append(("flink seed2 is stable across repeats", 0.0,
                  pct(det[2]["unstable_rate"])))
        c.append(("flink seed2 break counts (idle)", [58, 58, 58, 58],
                  det[2]["break_counts"]))
        c.append(("flink seed1 break counts vary", True,
                  len(set(det[1]["break_counts"])) > 1))
        fid = {f["seed"]: f for f in e7["model_fidelity"]}
        # Whether fidelity is a single value or a range depends on whether the
        # engine was stable on that run, so only the band is asserted.
        c.append(("flink fidelity seed1 stays near three quarters", True,
                  0.70 <= fid[1]["agreement_min"] <= fid[1]["agreement_max"] <= 0.80))
        c.append(("flink fidelity seed1 mean %", 77.0, pct(fid[1]["agreement_mean"])))
        c.append(("flink fidelity seed2 %", 78.8, pct(fid[2]["agreement_mean"])))
        c.append(("flink fidelity seed2 is stable", True,
                  fid[2]["stable_across_repeats"]))
        dups = [r["duplicate_match_rows"] for r in e7["runs"]]
        c.append(("flink min duplicate match rows", 15, min(dups)))
        c.append(("flink max duplicate match rows", 44, max(dups)))

    if e10 and e10.get("status") == "ok":
        # E10 measures a distribution, so what is asserted is the shape of it:
        # the range of each arm, and that the gap between the conditions is
        # small next to the spread inside one. Pinning individual rates here
        # would be the same mistake the experiment exists to document.
        h = e10["headline"]
        idle, loaded = sorted(h["idle_rates"]), sorted(h["loaded_rates"])
        c.append(("e10 measurements per condition", 6, h["measurements_per_condition"]))
        c.append(("e10 load workers", 12, e10["config"]["load_workers"]))
        c.append(("e10 idle arm low end %", 0.0, pct(min(idle))))
        c.append(("e10 idle arm high end %", 11.30, pct(max(idle))))
        c.append(("e10 loaded arm low end %", 0.0, pct(min(loaded))))
        c.append(("e10 loaded arm high end %", 7.83, pct(max(loaded))))
        c.append(("e10 gap between condition means, points", 0.43,
                  pct(h["gap_between_conditions"])))
        c.append(("e10 distributions overlap", True, h["distributions_overlap"]))
        c.append(("e10 spread exceeds the gap", True, h["spread_exceeds_the_gap"]))
        c.append(("e10 idle high end beats every loaded reading", 6,
                  sum(1 for x in loaded if x < max(idle))))
        c.append(("e10 gap is an order of magnitude under the spread", True,
                  h["gap_between_conditions"] * 10 < (max(idle) - min(idle))))

    if e8:
        ff = e8["fault_families"]
        c.append(("delay bound violations", 462, sum(ff["delay"]["model_violations"].values())))
        c.append(("duplicate bound violations", 430, sum(ff["duplicate"]["model_violations"].values())))
        c.append(("delay typed false break %", 22.9,
                  pct(ff["delay"]["arms"]["typed_horizon"]["false_break_rate"])))
        c.append(("duplicate typed false break %", 0.0,
                  pct(ff["duplicate"]["arms"]["typed_horizon"]["false_break_rate"])))
        c.append(("duplicate amount/date false match %", 36.4,
                  pct(ff["duplicate"]["arms"]["amount_date"]["false_match_rate"])))
        for fam in ("reorder", "partial_commit", "stale_read"):
            base = ff["none"]["arms"]["typed_horizon"]["false_break_rate"]
            c.append((f"{fam} identical to fault-free",
                      round(pct(base), 1), round(pct(ff[fam]["arms"]["typed_horizon"]["false_break_rate"]), 1)))
    if e9:
        t, o = e9["timeline"], e9["timeouts"]
        c.append(("the movement settles at", 1000, t["settles_at"]))
        c.append(("the ledger publishes at", 1002, t["ledger_publishes_at"]))
        c.append(("earliest the credit can appear", 1015, t["earliest_credit"]))
        c.append(("latest the credit can appear", 1074, t["latest_credit"]))
        c.append(("where it actually posts", 1020, t["actual_posting_instant"]))
        c.append(("decidable at", 1075, t["decidable_at"]))
        c.append(("a prompt timeout fires at", 1082,
                  o["prompt_publication_fires_at"]))
        c.append(("a late timeout fires at", 1280,
                  o["late_publication_fires_at"]))
        c.append(("ticks after the decision became sound", 205,
                  o["late_timeout_after_decidable"]))
        c.append(("ticks between the two timeouts", 198,
                  o["gap_between_the_two"]))

    return c


def main() -> int:
    claims = build_claims()
    if not claims:
        print("no results files found; run the experiments first")
        return 1

    bad = []
    for desc, stated, computed in claims:
        if isinstance(stated, float) and isinstance(computed, (int, float)):
            ok = abs(float(stated) - float(computed)) <= 0.051
        else:
            ok = stated == computed
        if not ok:
            bad.append((desc, stated, computed))

    print(f"checked {len(claims)} numeric claims against results/")
    for desc, stated, computed in bad:
        print(f"  MISMATCH  {desc}: paper says {stated!r}, results give {computed!r}")

    # Anything left over from a template should never reach a release.
    text = PAPER.read_text() if PAPER.exists() else ""
    leftovers = [m for m in re.findall(r"[A-Z\\_]*PLACEHOLDER[A-Z\\_]*", text)
                 if m.replace("\\", "") != "ZENODO_DOI_PLACEHOLDER"]
    if leftovers:
        print(f"  LEFTOVER placeholders in paper: {sorted(set(leftovers))}")

    if not bad and not leftovers:
        print("all claims verified")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
