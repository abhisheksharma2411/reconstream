"""Locate FinalityBench (P1), whose event streams this paper reconciles.

ReconStream does not invent a payment world.  It takes P1's canonical log and
its fault engine as given, and asks a different question of them: given the
*delivery streams* P1 already produces for the ledger and the bank, when is a
reconciler entitled to declare a match or a break?  Rebuilding the world here
would make the answer unfalsifiable, because any disagreement with P1 could be
blamed on a divergent simulator rather than on the reconciler.

Resolution order:

1. an installed ``finalitybench`` package;
2. a sibling checkout at ``../finalitybench/src`` (the usual local layout);
3. a clone under ``vendor/finalitybench`` that ``make setup`` creates.

Failing all three we raise with the exact command to fix it.  There is
deliberately no stand-in: a hand-rolled substitute would change what the paper
is about.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P1_REPO = "https://github.com/abhisheksharma2411/finalitybench.git"
P1_VERSION = "1.0.1"

_CANDIDATES = (
    ROOT.parent / "finalitybench" / "src",
    ROOT / "vendor" / "finalitybench" / "src",
)


def ensure_p1() -> Path:
    """Put FinalityBench on ``sys.path`` and return the source root used."""
    try:
        import finalitybench  # noqa: F401

        return Path(finalitybench.__file__).resolve().parent.parent
    except ImportError:
        pass

    for candidate in _CANDIDATES:
        if (candidate / "finalitybench" / "__init__.py").exists():
            sys.path.insert(0, str(candidate))
            return candidate

    raise ImportError(
        "FinalityBench (P1) not found. ReconStream reconciles its event streams "
        "and does not reimplement them. Fetch it with:\n"
        f"    git clone --branch v{P1_VERSION} {P1_REPO} vendor/finalitybench\n"
        "or place a checkout beside this repository."
    )


def clone_p1(dest: Path | None = None) -> Path:
    """Clone P1 at its released tag.  Used by ``make setup``."""
    dest = dest or (ROOT / "vendor" / "finalitybench")
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", f"v{P1_VERSION}", P1_REPO, str(dest)],
        check=True,
    )
    return dest


def p1_provenance() -> dict[str, str]:
    """Which P1 the numbers were produced against.  Printed with every result."""
    root = ensure_p1()
    import finalitybench

    rev = "unknown"
    repo = Path(root).parent
    try:
        rev = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return {
        "version": getattr(finalitybench, "__version__", "unknown"),
        "path": str(root),
        "git": rev,
    }
