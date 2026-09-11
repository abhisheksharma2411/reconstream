# ReconStream v1.0.0

First public release: the temporal correctness contract for streaming financial
reconciliation, its checker, and the experiments in the paper.

**Contract.** S1 (no premature break), S2 (no premature match), L1
(decisiveness) and M1 (stability), stated against a declared per-source
lateness model. The checker scores each verdict on two independent axes —
admissibility, computable with no ground truth, and outcome, which needs it.

**Findings.**
- An idleness timeout of 5 ticks puts 5.42% of obligations into contract
  violation (95% CI [3.94, 6.92]) on traffic where the same job without it is
  exactly sound; violations vanish at the bank's posting period, as predicted.
- Under lateness shift every reconciler tested degrades to 11.8–14.8% spurious
  breaks while contract violations stay at or below 1.01%.
- One horizon per source halves the break-latency tail at equal soundness
  (p99 224 vs 446 ticks), and is *not* cheaper at every cost setting.
- The contract runs as SQL: 4,395/4,395 agreement with the reference checker.

**Artifact.** `make reproduce` runs clean-room end to end. 27 tests;
`scripts/verify_claims.py` checks all 70 numeric claims in the paper against
the raw results.

Consumes FinalityBench (DOI 10.5281/zenodo.22262591) as a library.
