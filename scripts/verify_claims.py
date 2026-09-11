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
    e8 = load("e8_defects.json")
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
        c.append(("calm amount/date false match %", 22.82,
                  pct(calm["arms"]["amount_date"]["false_match_rate"]["point"])))
        fb = {k: pct(v["false_break_rate"]["point"]) for k, v in faulty["arms"].items()}
        c.append(("shifted min false break % (identity arms)", 11.80,
                  min(v for k, v in fb.items() if k != "amount_date")))
        c.append(("shifted max false break % (identity arms)", 14.84,
                  max(v for k, v in fb.items() if k != "amount_date")))
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
        c.append(("sweep fixed_timeout false break % at 0.5", 13.0,
                  pct(last["arms"]["fixed_timeout"]["false_break_rate"]["point"])))
        c.append(("sweep typed_horizon false break % at 0.5", 15.6,
                  pct(last["arms"]["typed_horizon"]["false_break_rate"]["point"])))
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
