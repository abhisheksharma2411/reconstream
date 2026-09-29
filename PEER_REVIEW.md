# Peer review — ReconStream

Adversarial review run 2026-09-29, after a clean-room re-run regenerated every
result from one revision. Numbers re-derived from `results/*.json` rather than
from the prose.

**Recommendation: accept with minor revision.** The contract is sound and the
paper reports where its own proposal loses, which is rare. The substantive work
of this review was forcing the Flink section to stop quoting single draws of a
quantity that is not stable, and the paper is stronger for it.

---

## What this review changed

### 1. The paper was quoting one draw of a random variable as a measurement

An earlier run showed Flink disagreeing with itself on 26.1% and 40.7% of
obligations on a loaded machine; a re-run on an idle machine gave 0.9% and
0.0%. The paper withdrew the observation and wrote that contention "plausibly"
explained it — an untested causal story stated in the text.

E10 tests it. Six measurements per condition, load applied deliberately as
twelve busy-loop workers on twelve cores. **Load does not explain it.** The
shipped run gives idle 0.0–11.30% against loaded 0.0–7.83%, means 0.43 points
apart *in the direction opposite to the hypothesis*, with the largest idle
reading exceeding every one of the six loaded readings. An earlier execution of
the same controlled comparison gave idle 0.0–21.74% and loaded 0.0–25.22%. Two
executions of one controlled experiment disagreeing by that much is the result:
the instability rate is a random variable whose spread within a condition
dwarfs any difference between conditions.

### 2. Seven claims were stale against `results/` at HEAD

`verify_claims.py` failed on seven E7 entries before this review — the prose
had been written from an earlier draw and never updated after the last two
re-runs. Four fed the abstract's range.

### 3. Claims that pinned a cell were fitted to one draw

The old claims asserted which `(window, seed)` cells were stable. The re-run
relocated the instability: previously window 160 seed 1 varied while window 320
was flat; now seed 1 repeats exactly and the movement is in seed 2 and window
320. Claims now assert the **shape** — window 80 flat on both seeds, exactly
one seed moving at each of the other two windows, ordering across windows
preserved — which survives a re-run for the right reason.

### 4. The abstract overstated reproducibility

It read "14.9–20.2%, reproducibly across two independent runs of the whole
experiment". Per-window means moved from 14.91/17.96/20.20 to
14.91/18.18/20.09 between runs that changed no code. The range is now
14.9–20.1% and the reproducibility claim is scoped to the ordering, which does
hold.

### 5. Three gate scripts existed and nothing ran them

`verify_claims.py`, `check_provenance.py` and `check_prose_numbers.py` were all
in `scripts/` and absent from the Makefile, so `make reproduce` could finish
green while results spanned three revisions and `e7_flink.json` had been
produced from a dirty tree. Now wired into `make verify` and into `reproduce`.
E10 was also missing from the `experiments` target, so a fresh clone never
produced a file the paper cites.

## Verified and unchanged

| Claim | Source | Verdict |
|---|---|---|
| Idleness timeout introduces violations on 5.42% (95% CI [3.94, 6.92]) | `e4_idleness` | exact |
| Shift: spurious breaks 18.3–23.0%, violations ≤1.01% | `e3_shift` | exact |
| 240 bank-side and 413 ledger-side bound violations | `e3_shift` | exact |
| Per-source horizon: 12.7% lower mean latency, p99 224 vs 446 | `e5_costs` | exact |
| SQL and reference agree on all 4,395 verdicts | `e6_sql_parity` | exact |

## Minor

**The prose-number gate's tolerance passed a stale figure.** The abstract
carried 20.2% after the true value moved to 20.09%, and
`check_prose_numbers.py` did not flag it. The gate is useful but its band is
wide enough to hide a real drift; worth tightening or reporting the margin.

## Scope, correctly stated by the paper

The simulated watermark arms agree with Flink on 77.0% and 78.8% of
obligations, so the timing results in the frontier table are properties of the
models and the paper says so rather than presenting them as measurements of the
engine. Proposition on idleness is proved and modelled but *not* confirmed on
the engine, because a bounded file source never idles in processing time.

**AI-written style score: 1/10.** Zero markers in the rendered PDF. One
markdown asterisk pair was reaching the rendered output (`*decision rule*`) and
is now `\emph{}`.
