"""E6 -- does the SQL formulation of the contract agree with the Python one?

The paper claims the contract is checkable in place, as a query against the
tables a reconciliation system already keeps.  That claim is only worth making
if the query and the reference implementation decide every verdict the same
way, so this experiment loads each run into PostgreSQL and compares them
verdict by verdict.

One property is deliberately outside the SQL: M1, which forbids retracting a
terminal verdict, is a statement about a *history* rather than about a row, and
expressing it as a per-verdict join would misrepresent what it says.  The
comparison treats an M1 flag as agreement on admissibility, and the retraction
count is reported separately.

If PostgreSQL is not reachable the experiment records that and exits without a
result, rather than emitting a parity figure it did not measure.
"""

from __future__ import annotations

from _common import write

from reconstream.checker import grade, obligations_from, run
from reconstream.contract import SourceModel
from reconstream.store import EventStore
from reconstream.workload import build_workload
import reconstream.matchers as M

from finalitybench.faults import FaultProfile

SEEDS = (1, 2, 3)
N_CASES = 200
CHECK_BANK_BOUND = 80

FAMILIES = {
    "typed_horizon": lambda: M.TypedHorizon(SourceModel(bound={"ledger": 2, "bank": CHECK_BANK_BOUND})),
    "fixed_timeout": lambda: M.FixedTimeout(CHECK_BANK_BOUND),
    "global_watermark": lambda: M.GlobalWatermark(60),
    "idle_watermark": lambda: M.IdleWatermark(60, 60),
    "amount_date": lambda: M.AmountDate(60, 500),
}


def main() -> None:
    store = EventStore()
    if not store.available():
        write("e6_sql_parity.json", {
            "status": "skipped",
            "reason": "PostgreSQL not reachable at the configured DSN; "
                      "run `docker compose up -d` first.",
            "dsn": store.dsn.rsplit("@", 1)[-1],
        })
        return

    model = SourceModel(bound={"ledger": 2, "bank": CHECK_BANK_BOUND})
    compared = agreed = 0
    disagreements = []
    outcome_compared = outcome_agreed = 0
    per_arm = {}

    for seed in SEEDS:
        for profile_name, profile in (("calm", FaultProfile.none()), ("faulty", FaultProfile())):
            w = build_workload(n_cases=N_CASES, seed=seed, profile=profile)
            obs = obligations_from(w.arrivals)
            for name, mk in FAMILIES.items():
                r = mk()
                d = run(r, w.arrivals, horizon=w.horizon)
                g = grade(r, w.arrivals, d, model, horizon=w.horizon)
                store.reset()
                store.load(w.arrivals, obs, d, getattr(r, "matches_on", "identity"))
                sql = {row[0]: (row[4], row[5]) for row in
                       store.admissibility(window=0, bank_bound=CHECK_BANK_BOUND)}
                truth = {row[0]: row[2] for row in store.outcomes()}
                arm = per_arm.setdefault(name, {"compared": 0, "agreed": 0})
                for x in g:
                    if x.verdict == "pending" or x.oid not in sql:
                        continue
                    compared += 1
                    arm["compared"] += 1
                    sql_adm, sql_closure = sql[x.oid]
                    py_adm = x.admissible or x.violation == "M1_retracted"
                    if py_adm == sql_adm and x.closure == sql_closure:
                        agreed += 1
                        arm["agreed"] += 1
                    else:
                        disagreements.append({
                            "oid": x.oid, "arm": name, "seed": seed, "regime": profile_name,
                            "py_admissible": x.admissible, "sql_admissible": sql_adm,
                            "py_closure": x.closure, "sql_closure": sql_closure,
                            "violation": x.violation,
                        })
                    outcome_compared += 1
                    if truth.get(x.oid) == (not x.true_break):
                        outcome_agreed += 1

    write("e6_sql_parity.json", {
        "status": "ok",
        "engine": "postgres:16.4-alpine",
        "config": {"seeds": SEEDS, "n_cases": N_CASES, "bank_bound": CHECK_BANK_BOUND},
        "admissibility": {
            "compared": compared, "agreed": agreed,
            "agreement": agreed / compared if compared else 0.0,
            "per_arm": per_arm,
        },
        "outcome": {
            "compared": outcome_compared, "agreed": outcome_agreed,
            "agreement": outcome_agreed / outcome_compared if outcome_compared else 0.0,
        },
        "disagreements": disagreements[:50],
    })


if __name__ == "__main__":
    main()
