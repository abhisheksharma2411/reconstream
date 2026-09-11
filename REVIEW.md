# Claim-to-evidence matrix, limitations, readiness

Every claim the paper makes, the experiment that supports it, and how far it
generalises. Numbers are checked mechanically against `results/` by
`scripts/verify_claims.py` (70 claims, all verified); this file is the argument,
that script is the audit.

## Claims

| # | Claim | Evidence | Strength |
|---|---|---|---|
| C1 | A verdict's *admissibility* is decidable from the stream and a declared source model, with no ground truth | `contract.py`, `checker.py`; construction | Definitional |
| C2 | Admissibility and correctness are genuinely independent axes | E3: bound violations rise 0→57.9% while contract violations stay ≤1.11%, and accuracy falls to 13–15.6% | Strong; measured across a 9-point sweep |
| C3 | The documented idleness fix is unsound below the slow source's posting period | E4: 5.42% [3.94, 6.92] violations at τ=5 on calm traffic; exactly 0.00% at τ≥60 | Strong; predicted by Prop. 2 before measurement |
| C4 | A timeout measured from the ledger inherits the ledger's jitter | Prop. 1 (proved); E2: s.d. 5.0 vs 60.8/69.8 ticks; unit test on two hand-built arrivals | Strong; proof plus measurement |
| C5 | A per-source horizon dominates on break latency at matched soundness | E2: 221.6 [220.8, 222.1] vs 253.8 [245.7, 262.5]; p99 224 vs 446 | Strong; non-overlapping CIs |
| C6 | A per-source horizon is **not** uniformly cheaper | E5: cheapest at 125/125 calm points, 30/125 shifted | Reported as a negative result |
| C7 | Attribute matching cannot satisfy S2 at any deadline | E1: never calibrates; 22.82% false matches on calm traffic | Strong for this amount distribution |
| C8 | The contract is checkable as SQL over an ordinary schema | E6: 4,395/4,395 agreement with the reference implementation | Strong |
| C9 | Only lateness and duplication touch the reconciliation path | E8: reorder, partial commit and stale read identical to fault-free to 3 digits | Strong for this simulator's fault model |
| C10 | A real Flink interval join violates S1 in its ordinary configuration | E7: 14.48–20.20% of obligations (config means), identical to 2 d.p. across two independent full runs | Strong for this setup |
| C11 | The simulated watermark arms are **not** a faithful model of Flink | E7: 77.4% / 78.8% partition agreement; the constructions differ structurally | Reported as a negative result |

## What the evidence does not support

- **Proposition 2 on the real engine.** Flink's idleness timeout is measured in
  processing time, and a bounded file source is consumed in milliseconds, so the
  setting never engages — three of its four values give identical numbers. The
  proposition is supported by its proof and by the model (E4) and is *not*
  confirmed on Flink. Confirming it needs a source paced in processing time,
  which means a broker rather than a file.
- **The timing results as measurements of Flink.** They are properties of the
  models, which agree with the engine on only 77–79% of obligations (C11).
- **Engine nondeterminism.** An earlier loaded-machine run showed 26.1% and
  40.7% of verdicts flipping across identical repetitions. The clean re-run
  gives 0.9% and 0.0%. The observation is reported in the paper as
  unreproduced, with the inferred mechanism labelled as an inference. It is not
  a claim.

- **Field rates.** Every number is from one synthetic generator. The lateness
  *shape* — a fast ledger and a batching bank — is realistic; the rates are not
  field rates and the paper says so.
- **More than two sources.** The contract generalises on paper; it is untested.
- **Learned bounds.** Bounds are declared. A deployment would estimate them, and
  a mis-estimate is exactly the model violation the checker reports — which is
  convenient but is not the same as having tested the estimator.
- **Ledger-side only.** Unexpected bank credits are counted as orphans and
  reported, not graded.
- **Cost figures.** Three constants are argued, not measured. Where the ordering
  of arms depends on them, the dependence is reported instead of a figure.

## Reproducibility

`make reproduce` runs clean-room: fetch P1, start PostgreSQL and Flink, run
E1–E8, regenerate figures from `results/`, rebuild the paper, run the tests.
Every results file records the git revision, the P1 commit consumed, the seeds
and a content fingerprint of each workload. No number in the paper is typed by
hand, and `scripts/verify_claims.py` fails the build if one drifts.

Tests: 27, covering the contract predicates, each reconciler's specific
behaviour, workload determinism and the positive class, the independence of the
two grading axes, and bootstrap properties.

## Adversarial review, and what it changed

The self-review found five things worth changing; all were fixed before this
file was written.

1. **The frontier claim was wrong as first stated.** "A per-source horizon
   dominates a timeout" is false at the calibrated operating point. Narrowed to
   the tail at matched soundness, with the contrary cost result (C6) reported.
2. **"Contract violations stay at or below 0.65%"** was taken from the sweep's
   endpoints rather than its maximum. The real maximum is 1.11%. Caught by
   `verify_claims.py`, corrected in both the abstract and the body.
3. **The calm regime had no genuine breaks**, making "never raise an exception"
   optimal. A controlled true-break class was added, drawn before any fault so
   it is identical across regimes.
4. **Closure delay pooled matches with exceptions**, which are closed early by
   design, producing a negative mean that flattered every arm. Split.
5. **A latent key collision** in the checker's pairing lookup. It changed no
   published number, because both sides carry the same identity, but it was
   wrong. Found by a unit test, not by the experiments.
6. **The positive class was not constant across regimes**, contrary to what the
   paper first claimed. Injection fixes 45 break cases in both regimes, but
   delivery loss destroys further bank evidence, so the graded class is 37 in
   calm traffic and 210 under faults. Every spurious-break figure is now a rate
   over the credits the bank actually settled, and a test asserts the
   distinction.
7. **Averages were quoted as a range** in the Flink section. `verify_claims.py`
   caught that the per-run span (14.78–23.01%) is wider than the span of
   per-configuration means (14.91–20.20%); both are now stated.
8. **A nondeterminism finding did not survive its own re-run.** The first E7
   run — made while seven other experiments shared the machine — showed the Flink
   job disagreeing with itself on 26–41% of obligations. It had already reached
   the abstract. The clean re-run gives 0.9% and 0.0%, so the claim was pulled
   from the abstract and the body, and what remains is the observation plus an
   explicit statement that it did not reproduce. The violation rates, by
   contrast, are identical across both runs.
9. **A SQL precision limit silently truncated the Flink sweep.**
   `INTERVAL '320' SECOND` exceeds the default `SECOND(2)` precision, so every
   window above 99 ticks was rejected by the planner and the experiment failed
   with an empty error. Only the harness's silence made it hard to find; it now
   surfaces the planner's message.

## Readiness

Ready to submit, with one dependency: the Zenodo DOI is not minted (see
`BLOCKERS.md`) and the paper carries a placeholder. Everything else — code,
data generator, Docker, figures, tests, claim verification — is complete and
reproducible.
