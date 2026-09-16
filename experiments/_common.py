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



#: Paths that are outputs of a run rather than inputs to it. A run writes its
#: own results, and on the second experiment of a batch the first one's output
#: would otherwise make the tree look dirty and mark every later result as
#: irreproducible. What has to be clean is the code and the data that went in.
GENERATED = ("results/", "figures/", "paper/")


def _dirty_inputs(root) -> str:
    """Uncommitted changes outside the generated directories."""
    out = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    changed = []
    for line in out:
        path = line[3:].strip().strip('"')
        if path.startswith("R ") or " -> " in path:
            path = path.split(" -> ")[-1]
        if not any(path.startswith(g) for g in GENERATED):
            changed.append(path)
    return "; ".join(sorted(changed))

def git_rev() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        dirty = _dirty_inputs(ROOT)
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
