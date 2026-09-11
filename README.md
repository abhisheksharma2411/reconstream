# ReconStream

**When is a reconciliation break real?** A temporal correctness contract for
streaming financial reconciliation, a checker for it that needs no ground
truth, and a measurement of how deployed idioms violate it.

A reconciliation system watches two evidence streams — what the ledger expected,
and what the bank actually paid — and must decide, continuously, whether money
that has not appeared is missing or merely unposted. Deployed pipelines settle
this with a timeout or a watermark. This repository asks the prior question:
**was the reconciler entitled to decide yet?**

## The contract

Relative to a declared per-source lateness bound:

| | property | |
|---|---|---|
| **S1** | no premature break | an exception needs the *bank's* horizon to have passed, not the stream's |
| **S2** | no premature match | identity pairings are stable on arrival; attribute pairings are not |
| **L1** | decisiveness | every obligation gets a terminal verdict in bounded time |
| **M1** | stability | a terminal verdict is not retracted |

The checker scores each verdict on two axes that are kept apart: whether it was
**admissible** (computable from the stream and the declared model, no oracle)
and whether it was **correct** (needs the oracle). The gap between them is the
finding.

## What we found

- **The documented fix for a stalled streaming join is unsound here.** An
  idleness timeout of 5 ticks puts 5.42% of obligations in contract violation
  (95% CI [3.94, 6.92]) on traffic where the same job without it is exactly
  sound. Violations vanish at exactly the bank's posting period, as predicted
  before measurement.
- **Under lateness shift, every reconciler was entitled to every verdict it got
  wrong.** Spurious breaks reach 11.8–14.8% while contract violations stay
  ≤1.01%; the checker attributes the loss to 240 bank-side and 413 ledger-side
  bound violations.
- **One horizon per source halves the break-latency tail** at equal soundness
  (p99 224 vs 446 ticks; s.d. 5.0 vs 60.8) — but is *not* cheaper at every cost
  setting, and we report where it loses.
- **Attribute matching cannot be made sound by tuning.** It never calibrates,
  mispairing 22.8% of verdicts on calm traffic.
- **The contract runs as SQL.** The query and the reference implementation
  agree on all 4,395 verdicts compared.

## Reproducing

```bash
make reproduce
```

Fetches FinalityBench, starts PostgreSQL and Flink in Docker, runs E1–E8,
regenerates every figure from `results/` and rebuilds the paper. No number in
the paper is entered by hand.

Piecemeal:

```bash
make setup        # venv + fetch FinalityBench (P1)
make up           # PostgreSQL event store on :55432
make flink-image  # pull the pinned Flink image
make experiments  # E1-E8 into results/
make figures      # figures/ from results/
make test         # 27 unit tests and sanity checks
make paper        # paper/reconstream.pdf
```

Everything except the figures, the tests and the PostgreSQL arm is standard
library only.

## Layout

```
src/reconstream/
  contract.py    the four properties, the source model, admissibility
  checker.py     run a reconciler, grade admissibility and outcome separately
  matchers.py    four baselines from practice + the typed horizon
  streams.py     P1 deliveries re-presented as evidence arrivals
  workload.py    interleaved cases, with a controlled true-break class
  store.py       the contract as SQL over an event store
  flink.py       the same workloads through a real Flink interval join
  bootstrap.py   percentile bootstrap resampling *cases*, not obligations
  calibrate.py   pick each arm's parameter the way an operator would
  cost.py        what each kind of mistake costs
experiments/     E1-E8, each writing one JSON to results/
```

## Relationship to FinalityBench

This repository does **not** rebuild the payment world. It consumes
[FinalityBench](https://github.com/abhisheksharma2411/finalitybench)
(DOI [10.5281/zenodo.22262591](https://doi.org/10.5281/zenodo.22262591)) as a
library: its canonical log, fault engine and per-system delivery streams. The
ledger trails a settlement by 2 ticks and the bank posts on a 60-tick cycle —
that heterogeneity is the research problem, and it is taken from the simulator
rather than imposed. `make setup` finds a sibling checkout or clones the
released tag.

## Honest limitations

Two sources, not many. Bounds are declared rather than learned. Obligations are
ledger-side, so unexpected bank credits are counted but not graded. The workload
is synthetic throughout — its lateness *shape* is realistic, but the rates here
are properties of this generator and are not field rates. Cost constants are
argued, not measured, and where the ordering of arms depends on them we report
the dependence instead of a single figure. See `ASSUMPTIONS.md` and the paper's
Limitations section.

## Citing

See `CITATION.cff`. The paper is `paper/reconstream.pdf`.

## Licence

MIT. Author: Abhishek Sharma (ORCID 0009-0007-1103-2103).
