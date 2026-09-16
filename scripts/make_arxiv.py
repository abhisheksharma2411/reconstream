"""Build the arXiv package from the paper, rather than beside it.

The submission tree is flat: no ``../figures`` and no subdirectories. Copying
by hand is how a package ends up one figure behind the paper it claims to be,
which is exactly what happened here once. So derive it, and check afterwards
that every file the tex asks for is present.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper"
OUT = PAPER / "arxiv"


def main() -> int:
    tex = (PAPER / "reconstream.tex").read_text()
    flat = tex.replace("{../figures/", "{")

    OUT.mkdir(exist_ok=True)
    for stale in OUT.glob("*"):
        stale.unlink()
    (OUT / "reconstream.tex").write_text(flat)

    wanted = set(re.findall(r"\\includegraphics\[[^\]]*\]\{([^}]+)\}", flat))
    wanted |= {f"{n}.tex" for n in re.findall(r"\\input\{([^}]+)\}", flat)}

    missing = []
    for name in sorted(wanted):
        src = (ROOT / "figures" / name)
        if not src.exists():
            src = PAPER / name
        if src.exists():
            shutil.copy2(src, OUT / name)
        else:
            missing.append(name)

    pdf = PAPER / "reconstream.pdf"
    if pdf.exists():
        shutil.copy2(pdf, OUT / pdf.name)

    if missing:
        print(f"MISSING from the package: {missing}")
        return 1
    print(f"arxiv package: {len(wanted)} referenced files + reconstream.tex")
    for f in sorted(OUT.iterdir()):
        print(f"  {f.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
