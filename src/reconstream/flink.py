"""Run the reconciliation join on Apache Flink and grade what it actually did.

The simulated watermark reconcilers in :mod:`matchers` are a model of what a
stream processor does.  A model is an argument, not evidence, so the same
workloads are replayed through a real Flink SQL interval join and the engine's
own verdicts are graded by the same checker.

Recovering *when* Flink decided is the part that needs care.  A null-padded row
from a LEFT interval join is emitted when the watermark passes the upper bound
of the interval, so the job selects ``CURRENT_WATERMARK`` alongside each row,
which gives the decision instant in event time.  Converting that to the
wall-clock instant the contract is written in is a lookup: the watermark, with
a zero-lateness strategy, reaches value ``W`` at the moment the first record
with event time ``W`` arrives, so the decision instant is that record's arrival
time.  Rows carrying the end-of-input watermark are flush artefacts of a
bounded source rather than decisions the engine reached on its own, and are
recorded separately instead of being scored as timely verdicts.
"""

from __future__ import annotations

import csv
import glob
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .contract import Decision, Verdict
from .streams import Arrival, BANK_SRC, LEDGER_SRC

IMAGE = "flink:1.20-scala_2.12-java17"
JOB_TEMPLATE = Path(__file__).resolve().parents[2] / "docker" / "flink" / "job.sql"


def available() -> bool:
    """Is Docker running and the pinned Flink image present locally?"""
    try:
        out = subprocess.run(
            ["docker", "images", "-q", IMAGE], capture_output=True, text=True, timeout=30
        )
        return out.returncode == 0 and bool(out.stdout.strip())
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


@dataclass
class FlinkRun:
    """What the engine emitted, and how much of it was a flush artefact."""

    decisions: dict[str, Decision]
    rows: int
    duplicate_match_rows: int
    flushed: int
    window: int
    idle_timeout: int | None
    runtime_mode: str

    def as_dict(self) -> dict:
        return {
            "verdicts": len(self.decisions),
            "rows": self.rows,
            "duplicate_match_rows": self.duplicate_match_rows,
            "flushed": self.flushed,
            "window": self.window,
            "idle_timeout": self.idle_timeout,
            "runtime_mode": self.runtime_mode,
        }


def _write_inputs(arrivals: list[Arrival], workdir: Path) -> None:
    for src, name in ((LEDGER_SRC, "ledger"), (BANK_SRC, "bank")):
        rows = [a for a in arrivals if a.source == src]
        with (workdir / f"{name}.csv").open("w", newline="") as fh:
            w = csv.writer(fh)
            for a in rows:
                w.writerow([a.at_t, a.event_t, a.seq, a.kind, a.case, a.ref, a.amount, a.copy])


def _render_job(window: int, idle_timeout: int | None, runtime_mode: str) -> str:
    sql = JOB_TEMPLATE.read_text().replace("__WINDOW__", str(window))
    sql = sql.replace("'execution.runtime-mode' = 'BATCH'", f"'execution.runtime-mode' = '{runtime_mode}'")
    sql = sql.replace(
        "CREATE TABLE verdicts_out (\n    oid       STRING,\n    verdict   STRING,\n    bank_seq  BIGINT\n)",
        "CREATE TABLE verdicts_out (\n    oid       STRING,\n    verdict   STRING,\n"
        "    bank_seq  BIGINT,\n    wm_at_emit BIGINT\n)",
    )
    sql = sql.replace(
        "    CASE WHEN b.seq IS NULL THEN 'exception' ELSE 'matched' END AS verdict,\n    b.seq",
        "    CASE WHEN b.seq IS NULL THEN 'exception' ELSE 'matched' END AS verdict,\n    b.seq,\n"
        "    CAST(EXTRACT(EPOCH FROM CURRENT_WATERMARK(l.ts)) AS BIGINT) AS wm_at_emit",
    )
    if idle_timeout is not None:
        sql = sql.replace(
            "SET 'parallelism.default' = '1';",
            "SET 'parallelism.default' = '1';\n"
            f"SET 'table.exec.source.idle-timeout' = '{idle_timeout} ms';",
        )
    return sql


def _watermark_to_walltime(arrivals: list[Arrival]) -> dict[int, int]:
    """Earliest arrival instant at which the watermark could have reached each value.

    With a zero-lateness strategy the watermark equals the greatest event time
    seen, so it reaches ``W`` when the first record of event time ``W`` lands.
    Values between observed event times are mapped to the next one up, which is
    the first instant the watermark is at least that high.
    """
    first_at: dict[int, int] = {}
    for a in arrivals:
        if a.event_t not in first_at or a.at_t < first_at[a.event_t]:
            first_at[a.event_t] = a.at_t
    ordered = sorted(first_at)
    running = {}
    best = 0
    for et in ordered:
        best = max(best, first_at[et])
        running[et] = best
    return running


def run_flink(
    arrivals: list[Arrival],
    *,
    window: int,
    idle_timeout: int | None = None,
    runtime_mode: str = "STREAMING",
    timeout: int = 300,
    attempts: int = 3,
) -> FlinkRun:
    """Execute the job in a throwaway container and parse its verdicts.

    Retried a few times because starting a fresh cluster per run occasionally
    loses the race with Docker on a loaded machine.  A retry re-runs the job
    from scratch on the same input; it does not paper over a job that ran and
    produced a different answer, which is what :func:`determinism` measures.
    """
    last: Exception | None = None
    for _ in range(attempts):
        try:
            return _run_once(arrivals, window=window, idle_timeout=idle_timeout,
                             runtime_mode=runtime_mode, timeout=timeout)
        except (RuntimeError, subprocess.SubprocessError) as exc:
            last = exc
    raise RuntimeError(f"Flink job failed after {attempts} attempts: {last}")


def _run_once(
    arrivals: list[Arrival],
    *,
    window: int,
    idle_timeout: int | None,
    runtime_mode: str,
    timeout: int,
) -> FlinkRun:
    workdir = Path(tempfile.mkdtemp(prefix="reconstream-flink-"))
    try:
        (workdir / "out").mkdir()
        _write_inputs(arrivals, workdir)
        (workdir / "job.sql").write_text(_render_job(window, idle_timeout, runtime_mode))
        script = (
            "/opt/flink/bin/start-cluster.sh >/dev/null 2>&1\n"
            "for i in $(seq 1 30); do /opt/flink/bin/flink list >/dev/null 2>&1 && break; sleep 1; done\n"
            "/opt/flink/bin/sql-client.sh -f /data/job.sql > /tmp/sql.log 2>&1\n"
            'JOB=$(grep -o "Job ID: [0-9a-f]*" /tmp/sql.log | tail -1 | cut -d" " -f3)\n'
            "for i in $(seq 1 120); do\n"
            '  S=$(/opt/flink/bin/flink list -a 2>/dev/null | grep "$JOB" | '
            'grep -oE "FINISHED|FAILED" | head -1)\n'
            '  [ -n "$S" ] && { echo "STATUS=$S"; break; }\n'
            "  sleep 1\n"
            "done\n"
        )
        proc = subprocess.run(
            ["docker", "run", "--rm", "-v", f"{workdir}:/data", IMAGE, "bash", "-c", script],
            capture_output=True, text=True, timeout=timeout,
        )
        if "STATUS=FINISHED" not in proc.stdout:
            # Surface the planner's own message.  A rejected statement exits
            # cleanly with no job id, and without this the failure arrives as an
            # empty string -- which cost a full experiment run to diagnose once.
            raise RuntimeError(
                f"Flink job did not finish (window={window}, idle={idle_timeout}): "
                f"{proc.stdout.strip()[-600:] or '<no output>'} :: {proc.stderr.strip()[-300:]}"
            )

        wm_map = _watermark_to_walltime(arrivals)
        wm_values = sorted(wm_map)
        horizon = max(a.at_t for a in arrivals)

        def to_walltime(wm: int | None) -> tuple[int, bool]:
            """Wall-clock instant for a watermark value, and whether it flushed."""
            if wm is None:
                return 0, False
            if wm > wm_values[-1]:
                return horizon, True
            for et in wm_values:
                if et >= wm:
                    return wm_map[et], False
            return horizon, True

        decisions: dict[str, Decision] = {}
        rows = dup_rows = flushed = 0
        seen_match: set[str] = set()
        for path in glob.glob(str(workdir / "out" / "part-*")):
            for row in csv.reader(open(path)):
                if not row:
                    continue
                rows += 1
                oid, verdict = row[0], row[1]
                bank_seq = int(row[2]) if len(row) > 2 and row[2] else None
                wm = int(row[3]) if len(row) > 3 and row[3] else None
                at_t, was_flush = to_walltime(wm)
                if was_flush:
                    flushed += 1
                if verdict == "matched":
                    if oid in seen_match:
                        dup_rows += 1
                        continue
                    seen_match.add(oid)
                    decisions[oid] = Decision(oid, Verdict.MATCHED, at_t, bank_seq, 0)
                elif oid not in decisions:
                    decisions[oid] = Decision(oid, Verdict.EXCEPTION, at_t)
        return FlinkRun(decisions, rows, dup_rows, flushed, window, idle_timeout, runtime_mode)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
