# DriftGuard R11 Governed Benchmark + Holdout Precommit V1

Status: statistical/research candidate stacked on clean R10 v3 head
`1900f80e43a9c4bd40040865fb82b5d2e148d3d8`.

## Purpose

R8 provides a governed prospective sequential detector.

R9 provides frozen-corpus calibration qualification.

R10 compares CUSUM, Page-Hinkley, and EWMA on one exact qualification subject while
refusing to promote a winner from that same HOLDOUT.

R11 governs the benchmark subject itself.

The problem is not merely "have a test set."

A meaningful detector benchmark needs:

- explicit stress-family coverage;
- exact provenance;
- exact DESIGN/HOLDOUT separation;
- frozen candidates and acceptance criteria before governed HOLDOUT reveal;
- exact future R9 and R10 plan identities;
- a reveal boundary that can prove exact digest equality;
- an explicit ceiling on what "untouched" can actually mean.

R11 implements that protocol.

## Core benchmark portfolio

`DRIFTGUARD_R11_CORE_V1` requires exactly one family for each phenomenon:

1. `STABLE_LOW_NOISE`
2. `STABLE_AUTOCORRELATED`
3. `STABLE_HEAVY_TAIL`
4. `CONTEXT_STRESS`
5. `EVALUATOR_SHIFT`
6. `SUBJECT_BEHAVIOR_SHIFT`
7. `NON_TARGET_DISTRIBUTION_SHIFT`
8. `MIXED_TARGET_COLLATERAL_SHIFT`

All families use one exact detector dimension set.

Each family manifest binds:

- family ID;
- phenomenon label;
- provenance ref/version;
- exact provenance SHA-256 digest;
- exact dimension set;
- exact expected shift-dimension labels.

The phenomenon label is provenance/benchmark metadata.

It does not prove that a trajectory was causally produced by the named phenomenon.
That requires the external generation/collection evidence named by the provenance
binding.

## Corpus manifest

A `BenchmarkCorpusManifest` binds:

- manifest ID;
- corpus ID/version;
- exact DESIGN or HOLDOUT role;
- exact R9 `CalibrationCorpus.digest`;
- role-independent trajectory-content digest;
- exact canonical artifact ref/version;
- SHA-256 of exact canonical corpus artifact bytes;
- exact core-family manifests.

The role-independent trajectory-content digest hashes only the sorted trajectory
payloads.

It prevents trivial reuse of the exact same trajectories merely by relabeling the
corpus from DESIGN to HOLDOUT.

It does not prove statistical independence between two different trajectory sets.

## Canonical artifact bytes

R11 defines one exact serialization for a benchmark corpus:

`canonical_corpus_artifact_bytes(corpus)`

It is compact canonical JSON of the exact R9 corpus payload.

At reveal time, supplied HOLDOUT bytes must equal this exact serialization.

This closes a provenance loophole where:

- the object digest could refer to corpus A;
- the file digest could refer to unrelated file B;
- both could still appear together in one manifest.

R11 requires one exact object/file subject.

## DESIGN versus HOLDOUT

A precommit requires:

- one DESIGN manifest;
- one HOLDOUT seal.

They must have the same benchmark portfolio contract:

- same family IDs;
- same phenomenon mapping;
- same dimensions;
- same expected shift labels.

They must not reuse:

- identical role-independent trajectory content;
- the same artifact binding;
- the same artifact digest.

This blocks trivial exact-data reuse.

It does not establish:

- independent sampling;
- separate operators;
- separate random seeds;
- absence of common upstream contamination;
- absence of prior HOLDOUT access.

Those remain external provenance questions.

## HOLDOUT seal

A `HoldoutCorpusSeal` binds the exact future:

- HOLDOUT manifest digest;
- portfolio digest;
- corpus digest;
- trajectory-content digest;
- artifact ref/version;
- artifact SHA-256.

Its explicit claim is:

`DIGEST_PRECOMMIT_NOT_PROOF_OF_NONACCESS_OR_TRUSTED_TIME`

A hash commitment proves equality to a committed digest.

It does **not** prove that nobody saw the underlying data before the commitment.

It also does not provide trusted wall-clock ordering by itself.

## Precommit plan

`BenchmarkPrecommitPlan` freezes before governed reveal:

- DESIGN manifest digest;
- HOLDOUT seal;
- exact R8 CUSUM spec digest;
- exact R9 family policies;
- exact R10 candidate set;
- exact future R9 calibration-plan ID and digest;
- exact future R10 comparison-plan ID and digest;
- precommit artifact ref/version + SHA-256;
- selection rule:
  `COMPARE_ONLY_NO_PROMOTION`.

The CUSUM candidate must bind the exact precommitted CUSUM spec.

R9 family-policy IDs must exactly equal the HOLDOUT family IDs.

The candidate tuple must be canonical.

Construction also instantiates the exact future R9/R10 plan objects, so an invalid
future comparison contract fails during precommit rather than after reveal.

## What "precommitted" means here

Within R11, "precommitted" means:

> the exact candidate, criterion, benchmark-metadata, HOLDOUT-digest, future
> calibration-plan, and future comparison-plan subject is fixed in the
> `BenchmarkPrecommitPlan` before R11's governed reveal/run call.

It does not mean:

> R11 proved that the human, process, model, CI system, repository administrator, or
> another tool had never inspected the HOLDOUT data before that call.

That stronger claim requires an external custody/time/authorization system.

R11 intentionally refuses to invent one.

## Reveal

`reveal_holdout()` requires:

- exact precommit object;
- exact precommitted HOLDOUT manifest;
- exact R9 HOLDOUT corpus;
- exact canonical corpus artifact bytes.

It verifies:

- manifest digest;
- corpus role;
- corpus ID/version/digest;
- role-independent trajectory-content digest;
- exact family set;
- exact dimensions;
- exact shift labels;
- exact canonical artifact bytes;
- exact artifact SHA-256.

Only that path can emit a `HoldoutRevealReceipt`.

The receipt claim is:

`EXACT_DIGEST_REVEAL_MATCH_NOT_NONACCESS_PROOF`.

## Run

`run_precommitted_holdout()` requires the exact:

- precommit;
- reveal receipt;
- manifest;
- corpus;
- CUSUM spec.

It then reconstructs the already-precommitted R9 calibration plan and R10 comparison
plan and executes `compare_detectors()`.

It cannot substitute:

- another CUSUM spec;
- another HOLDOUT corpus;
- another R9 policy;
- another R10 candidate;
- another comparison plan.

Only this path can emit a `BenchmarkRunReceipt`.

## Promotion boundary

R11 has no detector-selection authority.

The run receipt requires:

`promotion_authorized = false`

and R10's embedded comparison receipt must also remain non-promoting.

The run claim is:

`PRECOMMITTED_COMPARISON_EXECUTED_NO_SELECTION_OR_PROMOTION_AUTHORITY`.

If one detector appears better on this HOLDOUT, R11 still does not authorize adopting
it.

A subsequent promotion requires a separately governed selection/qualification
protocol and, where selection occurred using this HOLDOUT, another untouched
qualification subject.

## Receipt integrity

`HoldoutRevealReceipt` and `BenchmarkRunReceipt` are factory-gated.

Direct construction of a digest-bearing lookalike is rejected.

`BenchmarkRunResult` cross-checks the run receipt against the exact embedded R10
comparison receipt digest.

As elsewhere in DriftGuard, Python module-private/factory tokens are API-governance
boundaries, not hostile-process or hardware isolation.

## Hostile regressions

R11 tests freeze:

- exact eight-phenomenon coverage;
- one exact global dimension set;
- exact corpus/manifest binding;
- exact DESIGN/HOLDOUT portfolio matching;
- rejection of identical DESIGN/HOLDOUT trajectory content;
- exact future R9/R10 plan digest binding;
- candidate mutation moves precommit identity;
- R9 policy mutation moves precommit identity;
- exact canonical artifact-byte reveal;
- changed HOLDOUT rejection;
- direct reveal-receipt construction rejection;
- explicit non-access/trusted-time claim ceiling;
- exact precommitted R10 execution;
- no promotion authority;
- changed CUSUM spec rejection;
- direct run-receipt construction rejection;
- DESIGN manifest cannot be sealed as HOLDOUT.

The test corpus is a protocol fixture, not production benchmark evidence.

## Claim ceiling

An R11 PASS means:

> these exact benchmark manifests, candidate/criterion commitments, HOLDOUT digest,
> reveal bytes, R9 qualification plan, and R10 comparison plan compose
> deterministically under the governed protocol.

It does not prove:

- HOLDOUT non-access before precommit;
- trusted timestamp ordering;
- external custody;
- data independence;
- production representativeness;
- causal truth of phenomenon labels;
- IID/stationarity;
- evaluator stationarity;
- absence of benchmark contamination;
- statistical significance of algorithm differences;
- production superiority;
- causal model drift;
- control/reload safety.

## Separate integration gate

R11 is a statistical/research layer on the repaired R7-R10 stack.

It does not erase the independent whole-system composition gate.

Before DriftGuard as a whole can be called integrated, the reviewed measurement,
subject, evaluator-attestation, and effect-boundary controls still need one composed,
cross-qualified source subject, after which the statistical stack must be restacked
and requalified on that composed base.

R11's evidence remains useful, but it is not a substitute for that integration work.
