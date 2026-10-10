# Blockers

Things that could not be done in this environment, what was done instead, and
what it would take to finish them.

## Zenodo DOI not minted

Zenodo archives only **public** repositories, and only on a GitHub release
published *after* the repository is enabled in Zenodo's GitHub settings. This
repository is not yet public, so no DOI can be minted.

The paper does **not** promise one. Its Artifact Availability section names the
repository and the tag the paper was built from, and nothing more — a DOI is
not advertised unless it exists.

**To finish:** enable `reconstream` in Zenodo's GitHub settings *before* cutting
the release, then publish the release; the DOI is minted automatically. Insert
it with `python scripts/insert_doi.py 10.5281/zenodo.XXXXXXX` and rebuild. If
the webhook stalls, `git archive --format=zip --prefix=reconstream-1.0.0/ v1.0.0`
and upload manually — the DOI is identical and OpenAIRE still harvests it.

## arXiv submission

arXiv has no submission API, so the package is built and verified but not
submitted. Primary class cs.DB; cross-list cs.SE and cs.DC. Submission needs
the author's login, and cs.DB may require endorsement.

## Flink timing is recovered, not instrumented

Flink exposes no hook for "when did this row leave the operator" in SQL. The
job selects `CURRENT_WATERMARK` with each row and the watermark is mapped back
to the wall-clock instant it could first have been reached, which is exact
under a zero-lateness watermark strategy. Direct instrumentation would need a
DataStream job with a custom source that paces by event time, and a Kafka
producer to drive it. That is a larger build and was not attempted; the
limitation is stated in the paper.

## Kafka not used

The brief mentions Kafka alongside Flink. The filesystem connector was
sufficient to drive the interval join and to test
Proposition~2 against the real engine, and adding a broker would have
introduced a second source of nondeterminism without changing what is
measured. Not attempted; noted here rather than implied.
