"""The event store, and the contract check expressed as SQL.

Most reconciliation already lives in a database.  The arrivals are rows, the
verdicts are rows, and an operator asking "should we have raised this break?"
is asking a question about rows.  So the contract is stated twice in this
project: once as the Python predicates in :mod:`contract`, and once as the
queries below.  They are meant to agree on every verdict, and
``experiments/e6_sql_parity.py`` checks that they do -- a claim that the
contract is checkable in place, rather than only inside this repository's
runtime, is worth nothing unless the two formulations are actually compared.

The SQL is deliberately plain.  No window functions, no recursive CTEs, nothing
that would tie it to PostgreSQL: the admissibility of a verdict is a join and a
comparison, and keeping it that way is part of the argument that the contract
is cheap enough to run continuously.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DSN = os.environ.get(
    "RECONSTREAM_DSN",
    "postgresql://reconstream:reconstream@localhost:55432/reconstream",
)

SCHEMA = """
DROP TABLE IF EXISTS arrivals, obligations, verdicts;

CREATE TABLE arrivals (
    id        bigserial PRIMARY KEY,
    source    text    NOT NULL,
    at_t      integer NOT NULL,
    event_t   integer NOT NULL,
    seq       integer NOT NULL,
    kind      text    NOT NULL,
    case_id   text    NOT NULL,
    ref       text    NOT NULL,
    amount    bigint  NOT NULL,
    copy      integer NOT NULL
);

CREATE TABLE obligations (
    oid       text PRIMARY KEY,
    case_id   text    NOT NULL,
    ref       text    NOT NULL,
    kind      text    NOT NULL,
    amount    bigint  NOT NULL,
    event_t   integer NOT NULL,
    raised_t  integer NOT NULL
);

CREATE TABLE verdicts (
    oid          text PRIMARY KEY REFERENCES obligations(oid),
    verdict      text    NOT NULL,
    at_t         integer NOT NULL,
    matched_seq  integer,
    matched_copy integer NOT NULL DEFAULT 0,
    matches_on   text    NOT NULL DEFAULT 'identity'
);

CREATE INDEX arrivals_ident ON arrivals (case_id, ref, kind, source);
CREATE INDEX arrivals_src_t ON arrivals (source, event_t);
"""

#: S1 and S2 in one pass.  ``decidable_at`` is the instant the bank's
#: completeness horizon reaches the last moment a counterpart could have
#: occurred; every safety property in the contract is a comparison against it.
ADMISSIBILITY_SQL = """
WITH decidable AS (
    SELECT o.oid,
           o.event_t + %(window)s + %(bank_bound)s AS decidable_at,
           o.amount
    FROM obligations o
),
paired AS (
    SELECT v.oid,
           v.verdict,
           v.at_t,
           v.matches_on,
           a.case_id IS NOT NULL
               AND a.case_id = split_part(v.oid, ':', 1)
               AND a.ref     = split_part(v.oid, ':', 2)
               AND a.kind    = split_part(v.oid, ':', 3) AS right_movement
    FROM verdicts v
    LEFT JOIN arrivals a
           ON a.seq = v.matched_seq AND a.copy = v.matched_copy
)
SELECT p.oid,
       p.verdict,
       p.at_t,
       d.decidable_at,
       CASE
           WHEN p.verdict = 'exception' THEN p.at_t >= d.decidable_at
           WHEN p.matches_on = 'identity' AND p.right_movement THEN true
           ELSE p.at_t >= d.decidable_at
       END AS admissible,
       p.at_t - d.decidable_at AS closure
FROM paired p
JOIN decidable d USING (oid)
ORDER BY p.oid;
"""

#: The outcome check.  Ground truth is "did the bank ever show this movement",
#: which is an existence test against the arrivals table and nothing more.
OUTCOME_SQL = """
SELECT v.oid,
       v.verdict,
       EXISTS (
           SELECT 1 FROM arrivals a
           WHERE a.source = 'bank'
             AND a.case_id = split_part(v.oid, ':', 1)
             AND a.ref     = split_part(v.oid, ':', 2)
             AND a.kind    = split_part(v.oid, ':', 3)
       ) AS bank_showed
FROM verdicts v
ORDER BY v.oid;
"""

#: Which sources broke the lateness bound they declared.  This is the query an
#: operator actually wants at 09:00: not "how many breaks" but "is the break
#: rate our doing or our counterparty's".
MODEL_VIOLATION_SQL = """
SELECT source,
       count(*) FILTER (WHERE at_t - event_t > bound) AS over_bound,
       count(*)                                       AS total,
       max(at_t - event_t)                            AS worst_lag
FROM (
    SELECT a.*, (%(bounds)s::jsonb ->> a.source)::int AS bound
    FROM arrivals a
) t
GROUP BY source
ORDER BY source;
"""


@dataclass
class EventStore:
    """Thin wrapper: create the schema, load a run, run the checks."""

    dsn: str = DSN

    def _connect(self):
        import psycopg

        return psycopg.connect(self.dsn)

    def reset(self) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(SCHEMA)
            conn.commit()

    def load(self, arrivals, obligations: dict, decisions: dict, matches_on: str) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            with cur.copy(
                "COPY arrivals (source, at_t, event_t, seq, kind, case_id, ref, amount, copy) FROM STDIN"
            ) as cp:
                for a in arrivals:
                    cp.write_row((a.source, a.at_t, a.event_t, a.seq, a.kind, a.case, a.ref, a.amount, a.copy))
            with cur.copy(
                "COPY obligations (oid, case_id, ref, kind, amount, event_t, raised_t) FROM STDIN"
            ) as cp:
                for oid, o in obligations.items():
                    cp.write_row((oid, o.case, o.ref, o.kind, o.amount, o.event_t, o.raised_t))
            with cur.copy(
                "COPY verdicts (oid, verdict, at_t, matched_seq, matched_copy, matches_on) FROM STDIN"
            ) as cp:
                for oid, d in decisions.items():
                    cp.write_row((oid, d.verdict.value, d.at_t, d.matched_seq, d.matched_copy, matches_on))
            conn.commit()

    def admissibility(self, *, window: int, bank_bound: int) -> list[tuple]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(ADMISSIBILITY_SQL, {"window": window, "bank_bound": bank_bound})
            return cur.fetchall()

    def outcomes(self) -> list[tuple]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(OUTCOME_SQL)
            return cur.fetchall()

    def model_violations(self, bounds: dict) -> list[tuple]:
        import json

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(MODEL_VIOLATION_SQL, {"bounds": json.dumps(bounds)})
            return cur.fetchall()

    def available(self) -> bool:
        try:
            with self._connect():
                return True
        except Exception:
            return False
