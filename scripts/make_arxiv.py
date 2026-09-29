"""Build the arXiv package from the paper, rather than beside it.

The submission tree is flat: no ``../figures`` and no subdirectories. Copying
by hand is how a package ends up one figure behind the paper it claims to be,
which is exactly what happened here once. So derive it, and check afterwards
that every file the tex asks for is present.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
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


    if missing:
        print(f"MISSING from the package: {missing}")
        return 1
    tarball = PAPER / "reconstream-arxiv.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        for f in sorted(OUT.iterdir()):
            tar.add(f, arcname=f.name)

    ok, detail = _verify(OUT, "reconstream")
    abstract = _abstract("reconstream")
    (PAPER / "arxiv_abstract.txt").write_text(abstract + "\n")

    print(f"arxiv package: {len(wanted)} referenced files + reconstream.tex")
    for f in sorted(OUT.iterdir()):
        print(f"  {f.name}")
    print(f"  tarball     {tarball.relative_to(ROOT)} ({tarball.stat().st_size/1024:.0f} KB)")
    print(f"  standalone  {"OK" if ok else "FAILED"}, {detail}")
    print(f"  abstract    {len(abstract)} chars (arXiv limit 1920)")
    if len(abstract) > 1920:
        print("  WARNING: abstract exceeds the arXiv limit")
        return 1
    return 0 if ok else 1


def _verify(out: Path, main: str) -> tuple[bool, str]:
    """Compile in a scratch copy holding only the submission files.

    arXiv unpacks the tarball into one directory and builds there. The only
    way to know the package works is to build it the way arXiv will, with
    nothing else on the path.
    """
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp) / "sub"
        shutil.copytree(out, scratch)
        log = ""
        for _ in range(3):
            log = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", f"{main}.tex"],
                cwd=scratch, capture_output=True, text=True,
            ).stdout
        pdf = scratch / f"{main}.pdf"
        if not pdf.exists():
            return False, log[-2000:]
        problems = []
        for pattern, label in (
            (r"Citation .* undefined", "undefined citation"),
            (r"Reference .* undefined", "undefined reference"),
            (r"File .* not found", "missing file"),
            (r"LaTeX Error", "LaTeX error"),
        ):
            hits = re.findall(pattern, log)
            if hits:
                problems.append(f"{len(hits)} {label}(s)")
        info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True)
        page = next((l for l in info.stdout.splitlines() if l.startswith("Pages")), "")
        shutil.copy2(pdf, PAPER / f"{main}-arxiv-verified.pdf")
        return (not problems), page + ("; " + ", ".join(problems) if problems else "; clean")


def _abstract(main: str) -> str:
    """The abstract with macros resolved, for pasting into the submission form.

    Kept generated rather than hand-copied: a stale abstract file is the one
    thing here that gets pasted somewhere permanent.
    """
    tex = (PAPER / f"{main}.tex").read_text()
    numbers = PAPER / "numbers.tex"
    macros = dict(re.findall(r"\\newcommand\{\\(\w+)\}\{([^}]*)\}",
                             numbers.read_text())) if numbers.exists() else {}
    match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.S)
    body = match.group(1) if match else ""
    for name, value in macros.items():
        body = body.replace(f"\\{name}{{}}", value).replace(f"\\{name}", value)
    for cmd in ("textbf", "emph", "texttt", "textit"):
        body = re.sub(r"\\" + cmd + r"\{([^}]*)\}", r"\1", body)
    body = body.replace("\\%", "%").replace("\\$", "$").replace("\\&", "&")
    body = body.replace("\\ ", " ").replace("~", " ")
    body = body.replace("---", "--").replace("``", '"').replace("\'\'", '"')
    body = body.replace("{,}", ",")
    body = re.sub(r"\s+", " ", body).strip()
    return body


if __name__ == "__main__":
    sys.exit(main())
