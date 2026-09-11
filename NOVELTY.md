# Novelty and prior art

Checked against live search on 2026-09-11, and against the guardrail list in
the project brief. The claim below is narrower than the one I started with,
because two of the three things I expected to claim are already occupied.

## What is claimed

A **temporal correctness contract for operational reconciliation on
asynchronous streams**: a statement of when a reconciler is *entitled* to
declare a match or a break, relative to a declared per-source lateness model;
a checker for it that needs no ground truth; and a measurement of how deployed
idioms violate it.

The contribution that survives contact with the prior art is the separation of
**contract violation** (the reconciler decided before it was allowed to) from
**model violation** (an input broke the lateness bound it declared) from
**irreducible loss** (the money genuinely is not there). All three present to
an operator as "the break rate went up", and the first two are decidable
online without knowing the answer.

## What is not claimed

Not claimed: a first reconciliation benchmark, a first temporal logic for
out-of-order streams, or three-valued monitoring under partial knowledge. All
three exist. The banned-claims list in the brief rules out the first; the
second and third are Basin et al.'s.

## Occupied ground, and how this differs

**Runtime verification over out-of-order streams** — Basin, Klaedtke and
Zălinescu (RV 2017; ACM TOCL 20(3), 2019, arXiv:1909.11593) monitor MTL with
freeze quantifiers over streams whose events arrive out of order, with a
three-valued semantics for partial knowledge and online algorithms that are
sound and complete. POLÍMON (arXiv:2404.15723) is a more recent tool in the
same line. This is the closest work and the machinery is theirs: a verdict that
is not yet determined is exactly their third value.

*Difference*: they supply a general monitoring framework, parameterised by a
formula. What is missing, and what this paper supplies, is the formula — what
the property *is* for reconciliation, which turns on a notion neither their
logic nor a stream processor has: which source an absence of evidence is about.
S1 is not "eventually a match occurs"; it is "silence from the bank carries no
information until the bank's horizon has passed", and the bank's horizon is not
the stream's.

**FinBalance** (arXiv:2606.15949) and **FinRCA-Bench** (arXiv:2608.18534)
benchmark reconciliation for language models — multi-document accounting
bundles and accounts-payable-to-bank evidence retrieval respectively. Both
present the model with a complete evidence set and ask for the right answer.

*Difference*: the question here is not what the answer is given the evidence,
but whether you are allowed to answer yet given only part of it. Neither
benchmark has a time axis on which evidence is still arriving, so neither can
express a premature verdict.

**Temporal stream models with consistency levels** — the CEDR/Trill line, and
the patent family around it (for example US 8,315,990), separate valid time,
occurrence time and system time and define consistency levels over
speculative output and retraction.

*Difference*: that work gives a reconciler the option of retracting, which is
M1 in the contract here, and is orthogonal to S1. A system that retracts freely
still needs to know when its first verdict was justified, and in reconciliation
retraction is often not available — a dunning notice has been sent.

**Reconciliation over unbounded streams** — US 12,045,262 and US 12,411,706
(Discover, now Capital One; priority 2022-08-10) inject window- and shard-open
sentinels to bound an unbounded stream into reconcilable units, with producer
-defined rules carried in the close sentinel.

*Difference*: this is an implementation technique for delimiting units of work,
with no formal temporal property and no notion of when a verdict is admissible.
It is complementary — sentinels are one way to realise a declared horizon.

**Exactly-once and watermark literature** — Flink and Spark documentation, and
the broad EOS literature, cover watermarks, allowed lateness, interval joins
and idleness in general terms.

*Difference*: general, and about delivery rather than about decision. The
specific result here — that the documented idleness fix for a stalled join is
unsound for reconciliation whenever the timeout is below the slow source's
posting period — does not appear to be stated anywhere, and is tested against
the engine in E7.

**Practitioner writing** on exception management (Kani, Rexi, Ledgerise and
similar) does describe the phenomenon: an item inside its settlement window is
"pending", not a break. That is the right instinct and it is the contract's S1
in informal clothes. What is absent is any statement of the property, any way
to check a pipeline against it, and any measurement.

## Sibling papers

P1 (FinalityBench, DOI 10.5281/zenodo.22262591) supplies the world: the
canonical log, the fault engine, and the ledger and bank delivery streams that
every workload here is built from. Its concern is an agent acting before an
outcome is determined; this paper's is a reconciler deciding before evidence
could have arrived. The two are the same mistake seen from opposite ends of the
pipeline, and the shared machinery is what makes them comparable.

P2 (CausalLoss-Fin) attributes realised loss to infrastructure or policy after
the fact, using counterfactuals over a structural model. That is a post-hoc
analysis and needs ground truth. The decomposition here is a monitor and needs
none, which is why it can run in production and P2's cannot.

T8 supplies operation identity — what makes two records the same money
movement — which is what lets S2 be satisfied immediately by an identity
pairing and never by an attribute pairing.

## Narrowing that happened during the work

The original framing claimed "a temporal correctness contract for streaming
reconciliation" without qualification. Two narrowings were forced:

1. The three-valued treatment of incomplete knowledge is Basin et al.'s, so
   the contract is presented as an instantiation for a domain, not as new
   monitoring theory.
2. The first version of the frontier claim was that a per-source horizon
   dominates a timeout. On the calibrated operating point it does not: E5 finds
   the merged watermark cheapest on 75 of 125 grid points in the faulty regime.
   The claim is now about the *tail* at matched soundness, where the
   improvement is real and the confidence intervals separate, and the
   unfavourable cost result is reported alongside it.
