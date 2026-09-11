# Publishing checklist

## 1. GitHub

```bash
gh repo create abhisheksharma2411/reconstream --public \
  --source . --remote origin --push
```

Push **without** a release first. The GitHub→Zenodo webhook only fires for
releases published *after* the repository is enabled in Zenodo, and a brand-new
repository does not appear in Zenodo's list until it is synced — on this account
"Sync now" alone has not been enough; the toggle appeared only after a retry.

## 2. Zenodo (before tagging)

1. Zenodo → Account → GitHub → Sync now.
2. Find `reconstream`, switch the toggle **on**. Retry the sync if it is absent.
3. Only then cut the release:

```bash
git tag -a v1.0.0 -m "ReconStream v1.0.0"
git push origin v1.0.0
gh release create v1.0.0 --title "ReconStream v1.0.0" --notes-file RELEASE_NOTES.md
```

If the webhook still does nothing, deposit manually — the DOI is identical and
OpenAIRE harvests it to ORCID either way:

```bash
git archive --format=zip --prefix=reconstream-1.0.0/ v1.0.0 -o reconstream-1.0.0.zip
```

## 3. Insert the DOI

```bash
python scripts/insert_doi.py 10.5281/zenodo.XXXXXXX
python scripts/verify_claims.py     # must print "all claims verified"
make paper
git commit -am "Insert the minted Zenodo DOI" && git push
```

The placeholder is LaTeX-escaped in the paper (`ZENODO\_DOI\_PLACEHOLDER`) and
plain in the CFF. The script handles both and fails loudly if the paper did not
change — a sibling project's version matched only the plain spelling, reported
success on the CFF and silently left the paper untouched.

## 4. arXiv

Primary **cs.DB**; cross-list **cs.SE**, **cs.DC**. cs.DB may need endorsement;
if it is unavailable, cs.SE primary with cs.DB cross-listed is the fallback.

Upload `paper/arxiv/` (the .tex plus the four figure PDFs). The bibliography is
an inline `thebibliography`, so no `.bbl` is needed. Check before submitting:

- [ ] every figure in the package is referenced in the text (arXiv rejects
      unreferenced figures — this caught a sibling paper)
- [ ] the abstract matches the body after every revision
- [ ] the comments field states the right table and figure counts
- [ ] no stray backslashes in the abstract text field

## 5. After posting

Add the arXiv ID to `CITATION.cff` and `README.md`, and to
`~/.claude/.../memory/paper-factory-progress.md` so later papers cite this one
correctly rather than as a manuscript in preparation.
