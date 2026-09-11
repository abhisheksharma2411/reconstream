-- Reconciliation as the textbook Flink interval join.
--
-- The ledger side raises an obligation; the bank side supplies the counterpart.
-- A LEFT interval join emits a null-padded row when the watermark passes the
-- upper bound of the interval with no match found, which is exactly a
-- reconciliation break. This is the shape of job the pattern is usually built
-- as, written the way the documentation writes it.

SET 'execution.runtime-mode' = 'BATCH';
SET 'parallelism.default' = '1';

CREATE TABLE ledger (
    at_t      BIGINT,
    event_t   BIGINT,
    seq       BIGINT,
    kind      STRING,
    case_id   STRING,
    opref     STRING,
    amount    BIGINT,
    copy_n    INT,
    ts AS TO_TIMESTAMP_LTZ(event_t * 1000, 3),
    WATERMARK FOR ts AS ts - INTERVAL '0' SECOND
) WITH (
    'connector' = 'filesystem',
    'path' = 'file:///data/ledger.csv',
    'format' = 'csv',
    'csv.ignore-parse-errors' = 'false'
);

CREATE TABLE bank (
    at_t      BIGINT,
    event_t   BIGINT,
    seq       BIGINT,
    kind      STRING,
    case_id   STRING,
    opref     STRING,
    amount    BIGINT,
    copy_n    INT,
    ts AS TO_TIMESTAMP_LTZ(event_t * 1000, 3),
    WATERMARK FOR ts AS ts - INTERVAL '0' SECOND
) WITH (
    'connector' = 'filesystem',
    'path' = 'file:///data/bank.csv',
    'format' = 'csv',
    'csv.ignore-parse-errors' = 'false'
);

CREATE TABLE verdicts_out (
    oid       STRING,
    verdict   STRING,
    bank_seq  BIGINT
) WITH (
    'connector' = 'filesystem',
    'path' = 'file:///data/out',
    'format' = 'csv'
);

INSERT INTO verdicts_out
SELECT
    l.case_id || ':' || l.opref || ':' || l.kind AS oid,
    CASE WHEN b.seq IS NULL THEN 'exception' ELSE 'matched' END AS verdict,
    b.seq
FROM ledger l
LEFT JOIN bank b
  ON  l.case_id = b.case_id
  AND l.opref     = b.opref
  AND l.kind    = b.kind
  AND b.ts BETWEEN l.ts - INTERVAL '1' SECOND AND l.ts + INTERVAL '__WINDOW__' SECOND;
