"""Replace ``manuscript in preparation'' with a real arXiv identifier.

These papers cite each other, and a sibling that has not been posted yet can
only be cited as forthcoming. That is honest while it is true and stale the
moment it stops being true, and a bibliography that says a paper is in
preparation after it is on arXiv is the kind of thing a reviewer notices and a
reader cannot check.

So the fix is one command per sibling, run when that sibling goes up:

    python scripts/insert_arxiv_ids.py reconstream 2609.01234
    python scripts/insert_arxiv_ids.py --list

Keys are the \\bibitem keys, which are the same across all the sibling papers,
so the same invocation works in every repository. The script refuses an
identifier that is not shaped like an arXiv one, refuses a key the paper does
not cite, and reports doing nothing rather than reporting success when the
entry has already been updated.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Every sibling any of these papers cites, by \bibitem key.
SIBLINGS = {
    "causalloss": "CausalLoss-Fin",
    "reconstream": "ReconStream",
    "streamcheck": "StreamCheck",
    "shadowmig": "ShadowMigBench",
    "stablerecon": "StableRecon",
    "railsem": "RailSem",
    "railshift": "RailShiftBench",
    "t4": "LLM retry-safe payment services",
    "t8": "payment idempotency contract",
    "holdspec": "HoldSpec",
    "finalitybench": "FinalityBench",
}

FORTHCOMING = re.compile(
    r"(?:manuscript in preparation|under review|in preparation|forthcoming)"
    r"(,\s*(\d{4}))?", re.IGNORECASE)

ARXIV = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")


def paper_path() -> Path:
    candidates = sorted(p for p in (ROOT / "paper").glob("*.tex")
                        if not p.name.endswith("_table.tex"))
    if not candidates:
        raise SystemExit("no paper/*.tex found")
    return candidates[0]


def entries(text: str) -> dict[str, tuple[int, int, str]]:
    """Each \\bibitem's key mapped to its span and body."""
    out: dict[str, tuple[int, int, str]] = {}
    marks = [(m.group(1), m.start(), m.end())
             for m in re.finditer(r"\\bibitem\{([^}]+)\}", text)]
    for i, (key, _, body_start) in enumerate(marks):
        body_end = marks[i + 1][1] if i + 1 < len(marks) else len(text)
        out[key] = (body_start, body_end, text[body_start:body_end])
    return out


def listing() -> int:
    text = paper_path().read_text()
    found = entries(text)
    print(f"{paper_path().relative_to(ROOT)}: {len(found)} references")
    any_pending = False
    for key, (_, _, body) in found.items():
        if key in SIBLINGS and FORTHCOMING.search(body):
            print(f"  pending  {key:<14} {SIBLINGS[key]}")
            any_pending = True
        elif key in SIBLINGS:
            print(f"  done     {key:<14} {SIBLINGS[key]}")
    if not any_pending:
        print("  nothing pending")
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] in ("--list", "-l"):
        return listing()
    if len(argv) != 2:
        print(__doc__)
        return 2

    key, ident = argv
    ident = ident.removeprefix("arXiv:").removeprefix("arxiv:")
    if not ARXIV.match(ident):
        print(f"refusing {ident!r}: not shaped like an arXiv identifier")
        return 2
    if key not in SIBLINGS:
        print(f"unknown key {key!r}. Known: {', '.join(sorted(SIBLINGS))}")
        return 2

    path = paper_path()
    text = path.read_text()
    found = entries(text)
    if key not in found:
        print(f"this paper does not cite {key!r}; nothing to do")
        return 0

    start, end, body = found[key]
    if not FORTHCOMING.search(body):
        print(f"{key}: already has a published form, not touching it")
        return 0

    # Keep the year if the entry carried one: the sibling papers are all
    # dated, and dropping the date on the way to an identifier loses
    # information the reference had.
    def _replace(m: re.Match) -> str:
        year = m.group(2)
        return f"arXiv:{ident}" + (f", {year}" if year else "")

    new_body = FORTHCOMING.sub(_replace, body, count=1)
    path.write_text(text[:start] + new_body + text[end:])
    print(f"{path.relative_to(ROOT)}: {key} -> arXiv:{ident}")
    print("rebuild the paper and the arXiv package: make paper arxiv")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
