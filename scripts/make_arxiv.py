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


#: Fields a human chooses once. Everything else in the metadata file is counted
#: from the source or read off the built PDF, because the hand-maintained
#: version drifted: it claimed 8 pages for a 9-page paper and carried a literal
#: "10.5281/zenodo.PLACEHOLDER" into the Comments field.
TITLE = ("When Is a Reconciliation Break Real? A Temporal Correctness Contract "
         "for Streaming Financial Reconciliation")
AUTHORS = "Abhishek Sharma"
PRIMARY_CLASS = "cs.DB"
CROSS_LIST = "cs.SE, cs.DC"
ACM_CLASS = "H.2.4; D.2.4; H.2.8"
REPO_URL = "https://github.com/abhisheksharma2411/reconstream"


def _counts(tex: str, pdf: Path) -> dict:
    pages = ""
    if pdf.exists():
        out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if line.startswith("Pages"):
                pages = line.split()[-1]
    return {
        "pages": pages,
        "figures": len(re.findall(r"\\includegraphics", tex)),
        "tables": len(re.findall(r"\\begin\{table", tex)),
        "propositions": len(re.findall(r"\\begin\{proposition", tex)),
    }


def _metadata(tex: str, pdf: Path, tag: str) -> str:
    c = _counts(tex, pdf)
    comments = (
        f"{c['pages']} pages, {c['figures']} figures, {c['tables']} tables, "
        f"{c['propositions']} propositions. Code, workload generator, Docker "
        f"configuration and every raw results file are at {REPO_URL} "
        f"(tag {tag}); `make reproduce` rebuilds every figure, table and number "
        f"in the paper from the raw results."
    )
    return f"""TITLE
{TITLE}

AUTHORS
{AUTHORS}

PRIMARY CLASS
{PRIMARY_CLASS}

CROSS-LIST
{CROSS_LIST}

COMMENTS
{comments}

REPORT NUMBER
(leave blank -- no institutional report series)

JOURNAL REFERENCE
(leave blank -- not published in a journal or proceedings)

EXTERNAL DOI
(leave blank. This field is for a DOI of THIS PAPER in a journal or
proceedings. A Zenodo *software* DOI is not that, and asserting one here
claims a published version that does not exist. If the artifact is archived,
put its DOI in COMMENTS and in the paper's Artifact Availability section.)

ACM CLASS
{ACM_CLASS}

MSC CLASS
(leave blank -- not a mathematics paper)

UPLOAD
paper/reconstream-arxiv.tar.gz -- one file. Do not upload the PDF; arXiv
compiles the source. The abstract to paste is paper/arxiv_abstract.txt.
"""


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

    # From CITATION.cff, not `git describe`: the metadata has to name the tag
    # being cut, and at build time that tag does not exist yet.
    cff = (ROOT / "CITATION.cff").read_text()
    m = re.search(r"^version:\s*v?(\S+)", cff, re.M)
    tag = f"v{m.group(1)}" if m else "untagged"
    meta = _metadata(tex, PAPER / "reconstream-arxiv-verified.pdf", tag or "untagged")
    (PAPER / "arxiv_metadata.txt").write_text(meta)

    print(f"arxiv package: {len(wanted)} referenced files + reconstream.tex")
    for f in sorted(OUT.iterdir()):
        print(f"  {f.name}")
    print(f"  tarball     {tarball.relative_to(ROOT)} ({tarball.stat().st_size/1024:.0f} KB)")
    print(f"  standalone  {"OK" if ok else "FAILED"}, {detail}")
    print(f"  abstract    {len(abstract)} chars (arXiv limit 1920)")
    print(f"  metadata    paper/arxiv_metadata.txt (tag {tag or 'untagged'})")
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
