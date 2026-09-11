# Assumptions

Decisions taken without asking, with the reasoning, so a reader can disagree
with a specific choice rather than with the whole artifact.

## Modelling

**Two evidence sources, not four.** P1 models four systems; reconciliation here
is ledger against bank. The processor and ERP streams exist in the underlying
simulator but are not consumed. Reconciling more than two sources is a
generalisation of the same contract — the horizon becomes a vector — and adding
it would have widened the claim without testing it.

**Lateness bounds are declared, not learned.** A source model states a maximum
lag per source. Real deployments would estimate it from history, and a
mis-estimated bound is exactly the model violation the checker reports. Learning
the bound online is future work and is described as such.

**Bounded lateness rather than a distribution.** The contract quantifies over
continuations consistent with a *bound*. A probabilistic version — "no
counterpart will arrive with probability 0.999" — is more realistic and weaker,
and would make S1 a confidence statement rather than a guarantee. The bounded
form is chosen because it is checkable exactly and because a reconciliation
control that is right 99.9% of the time is, at the volumes in question, wrong
several times a day in a way nobody can localise.

**Obligations are ledger-side.** A bank credit with no ledger expectation is
counted as an orphan and reported, but is not graded. The reverse direction is
a real reconciliation concern and is a stated limitation rather than a claim.

**Settlement window defaults to zero.** The window is the time the *movement*
may take; lateness is the time *reporting* it may take. They are separate
parameters in the code and conflating them is one of the defects in the corpus.
Setting the window to zero makes the experiments measure lateness alone.

## Workload

**True break rate of 4%.** Genuine missing credits are injected independently of
the fault profile, so the positive class is identical across regimes. Without
them a reconciler that never raises a break would score perfectly. Four percent
is above typical production break rates, chosen so the class is large enough to
estimate recall on at these corpus sizes.

**Amounts are drawn from P1's eight retail figures.** That makes attribute
matching genuinely ambiguous, which is realistic and is the point of including
that arm. `build_workload(duplicate_amounts=False)` makes amounts unique, which
separates the ambiguity failure from the lateness failure.

**Cases are spread over a 1440-tick day.** Interleaving matters: attribute
matching can only mispair movements that are in flight together.

## Economics

The three cost constants are argued rather than measured, and every monetary
figure is swept over an order of magnitude in E5. Counts and rates are the
primary results. Where the ordering of the arms changes across the sweep — and
it does, in the faulty regime — that is reported rather than a single figure
from the centre of the grid.

## Infrastructure

**PostgreSQL 16.4 and Flink 1.20 are pinned.** Both are ordinary versions
rather than chosen for behaviour. The SQL uses no PostgreSQL-specific feature
except a `jsonb` cast in the model-violation query, which exists for
convenience and is not part of any claim.

**Flink runs in STREAMING mode on a bounded filesystem source.** Batch mode was
tried first and is unsuitable for the question: it sees the whole input, so it
cannot decide prematurely, and it answers correctly by construction. That is
worth knowing — offline batch reconciliation is sound — and it is reported, but
it is not the streaming behaviour under study.

**Decision instants inside Flink are recovered, not directly instrumented.**
The job reports `CURRENT_WATERMARK` with each row, and the watermark value is
mapped back to the wall-clock instant at which it could first have been
reached. With a zero-lateness watermark strategy that mapping is exact. Rows
carrying the end-of-input watermark are flush artefacts of a bounded source and
are counted separately rather than scored.

## Deliberate omissions

**No language model is involved.** Reconciliation here is a decision procedure,
not a reasoning task, and nothing in the contribution needs one.

**No real bank data.** Everything is generated. The generator, its seeds and a
content fingerprint for every workload are in the results files.
