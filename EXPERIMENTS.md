# Experiment log

Every experiment writes one JSON to `results/`, stamped with the git revision,
the FinalityBench commit it consumed, the seeds and a content fingerprint of
each workload. What follows is the log of what was run, what it showed, and
what had to be changed because of it.

## Iterations that changed the design

**The calm regime had no genuine breaks.** The first version of the workload
drew breaks only from P1's delivery-loss fault family, which drops processor
and ERP deliveries rather than bank ones. The consequence was that on
fault-free traffic every obligation eventually matched, so "never raise an
exception" was the optimal policy and every exception was by definition an
error. Fixed by injecting a controlled true-break class (`true_break_rate`,
4%) drawn *before* any fault is applied, so the positive class is byte-identical
across regimes and a change in break rate cannot be the workload. A test
asserts that equality.

**Closure delay pooled matches and exceptions.** The first liveness metric
averaged over all terminal verdicts. Matches close as soon as the evidence
lands, which is *before* the decision point, so the mean came out negative and
a reconciler looked timely for the one verdict whose timeliness was never in
question. Split into exception-only closure, which is what the paper reports,
with match closure retained separately.

**The frontier claim was wrong as first stated.** The hypothesis was that a
per-source horizon dominates a timeout. At the calibrated operating point it
does not: the typed horizon decides earliest and is therefore the most exposed
when a bound is violated, and E5 finds the merged watermark cheapest on 75 of
125 grid points under shift. The claim was narrowed to the tail at matched
soundness, where the intervals separate and the mechanism is provable
(Proposition 1), and the unfavourable cost result is reported alongside it.

**A latent key collision in the checker.** Matched pairings were looked up by
`(seq, copy)`, but the ledger and bank deliveries of one canonical event share
a sequence number, so the lookup could return the wrong side. It happened not
to change any published number --- both sides carry the same identity, which is
all the comparison used --- but it was wrong and is now keyed to bank arrivals
only. Found by a unit test on two hand-built arrivals, not by the experiments.

**`mispaired` was invisible.** An obligation paired with another movement's
record, where the obligation had no counterpart of its own, was scored only as
a false match, hiding the fact that the reconciler had also consumed someone
else's credit. Both are now recorded.

**Flink batch mode answered the wrong question.** The first Flink job ran with
`execution.runtime-mode = BATCH`, which sees the whole input and therefore
cannot decide prematurely; it matched ground truth exactly. That is a real and
reportable fact about offline reconciliation, and it is useless for studying
streaming verdicts. Switched to STREAMING, with `CURRENT_WATERMARK` selected
alongside each row so the decision instant can be recovered.

## The experiments

| | question | result file |
|---|---|---|
| E1 | Calibrate each arm on calm traffic, run unchanged on both regimes | `e1_main.json` |
| E2 | Sweep each family's parameter: the soundness/liveness frontier | `e2_frontier.json` |
| E3 | Hold the calibration, move the lateness distribution | `e3_shift.json` |
| E4 | Sweep the idleness timeout against the bank's posting period | `e4_idleness.json` |
| E5 | Sweep the three cost constants over an order of magnitude | `e5_costs.json` |
| E6 | Does the SQL formulation agree with the reference implementation? | `e6_sql_parity.json` |
| E7 | Does a real Flink interval join satisfy the contract? | `e7_flink.json` |
| E8 | Which fault family causes which violation; the defect corpus | `e8_defects.json` |

## Protocol

Five seeds of 200 interleaved cases per regime. Calibration seeds (1--5) and
evaluation seeds (101--105, 201--205, 301--305) are disjoint wherever an arm is
scored on traffic it might have been tuned against.

Confidence intervals are percentile bootstrap with 2,000 replicates resampling
**cases**, not obligations: obligations from one case share its amount,
archetype and fault draw, and resampling them independently would give
intervals that are too narrow. Comparisons between arms use a shared case
resample so the paired interval exploits that both arms saw the same stream.

Calibration rule, applied identically to every family: the smallest parameter on
an ascending grid with zero contract violations and zero spurious breaks on calm
traffic. A family that never qualifies is recorded as not converged and
evaluated at the largest parameter tried, rather than being quietly handed its
least-bad setting. Amount/date matching never converges.

## Negative and null results

- Reordering, partial commits and stale reads have **no effect** on the
  ledger-to-bank path: results identical to the fault-free arm to three digits.
  They perturb systems that are not on the reconciliation path.
- Duplicate delivery causes **zero** errors for every identity-based
  reconciler, while costing amount/date matching 36.4% false matches.
- The typed horizon is **not** cheapest under shift at its calibrated point.
- Offline batch reconciliation in Flink is **sound by construction**, because
  it has no partial-evidence problem at all. The cost is that it has no answer
  until the batch runs.
