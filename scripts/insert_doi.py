"""Write the minted Zenodo DOI into the paper and CITATION.cff.

The placeholder appears LaTeX-escaped in the paper (``ZENODO\\_DOI\\_PLACEHOLDER``)
and unescaped in the CFF.  An earlier version of this script in a sibling
project matched only the unescaped spelling, reported success on the CFF and
silently changed nothing in the paper, so both spellings are handled here and
the script fails loudly if a target it expected to change did not.

Usage:  python scripts/insert_doi.py 10.5281/zenodo.XXXXXXX
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper" / "reconstream.tex"
CFF = ROOT / "CITATION.cff"
README = ROOT / "README.md"

#: The paper ships promising nothing: its Artifact Availability section names
#: the repository and the tag, and says nothing about a DOI, because a literal
#: placeholder or an unkept promise in a posted preprint is worse than silence.
#: So there is nothing to *replace* -- the DOI sentence is appended after the
#: tag sentence. This anchor is that sentence's ending.
ANCHOR = "which is the revision this paper was built from."

#: Older spellings, kept so the script still works on an unrevised checkout.
FORTHCOMING = "An archival DOI is forthcoming."

PLAIN = "ZENODO_DOI_PLACEHOLDER"
ESCAPED = r"ZENODO\_DOI\_PLACEHOLDER"


def main(doi: str) -> int:
    if not doi.startswith("10."):
        print(f"refusing to insert {doi!r}: does not look like a DOI")
        return 2

    changed, missed = [], []

    text = PAPER.read_text()
    escaped_doi = doi.replace("_", r"\_")
    if escaped_doi in text:
        print(f"the paper already cites {doi}; nothing to do")
        return 0
    if ANCHOR in text:
        PAPER.write_text(text.replace(
            ANCHOR,
            ANCHOR + f" The release is archived at DOI \\texttt{{{escaped_doi}}}.",
            1))
        changed.append(PAPER.name)
    elif FORTHCOMING in text:
        escaped = doi.replace("_", r"\_")
        PAPER.write_text(text.replace(
            FORTHCOMING, f"It is archived at DOI \\texttt{{{escaped}}}."))
        changed.append(PAPER.name)
    elif ESCAPED in text or PLAIN in text:
        PAPER.write_text(text.replace(ESCAPED, doi.replace("_", r"\_")).replace(PLAIN, doi))
        changed.append(PAPER.name)
    else:
        missed.append(PAPER.name)

    cff = CFF.read_text()
    if "doi:" not in cff.split("references:")[0]:
        lines = cff.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("license:"):
                lines.insert(i, f"doi: {doi}")
                break
        CFF.write_text("\n".join(lines) + "\n")
        changed.append(CFF.name)
    else:
        missed.append(f"{CFF.name} (already has a top-level doi)")

    readme = README.read_text()
    if "ZENODO" in readme:
        README.write_text(readme.replace(PLAIN, doi))
        changed.append(README.name)

    print("updated:", ", ".join(changed) or "nothing")
    if missed:
        print("not updated:", ", ".join(missed))
    if PAPER.name in [m.split()[0] for m in missed]:
        print("ERROR: the paper still has no DOI. Check the placeholder spelling.")
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
