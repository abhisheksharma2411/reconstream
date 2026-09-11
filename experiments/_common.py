"""Shared setup for every experiment: paths, provenance, result writing.

Every results file records the git revision, the P1 artifact it consumed, the
workload fingerprint and the seeds, so a number in the paper can be traced to
the exact inputs that produced it.  P1 shipped result files stamped
``git: unversioned`` because the experiments ran minutes before the first
commit; writing the revision here and refusing to pretend otherwise is the
cheap fix for that.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"

sys.path.insert(0, str(SRC))

from reconstream._p1 import p1_provenance  # noqa: E402


def git_rev() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return out + ("-dirty" if dirty else "")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unversioned"


def provenance() -> dict:
    return {
        "git": git_rev(),
        "p1": p1_provenance(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def write(name: str, payload: dict) -> Path:
    RESULTS.mkdir(exist_ok=True)
    payload = {"provenance": provenance(), **payload}
    path = RESULTS / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"wrote {path.relative_to(ROOT)}")
    return path


def load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text())
