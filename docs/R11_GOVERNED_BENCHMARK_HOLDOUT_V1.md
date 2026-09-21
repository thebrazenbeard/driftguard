# DriftGuard R11 Governed Benchmark + Holdout Precommit V2

Status: statistical/research candidate stacked on clean composed R10/attestation/effect head
`9df4800d81ab2e937ffa97263b8095305a845661`.

## Purpose

R8 provides a governed prospective sequential detector.

R9 provides frozen-corpus calibration qualification.

R10 compares CUSUM, Page-Hinkley, and EWMA on one exact qualification subject while refusing to promote a winner from that same HOLDOUT.

The composed base additionally carries subject-bound evaluator attestation and subject-current reload/effect admission.

R11 governs the benchmark study itself.

The problem is not merely "have a test set."

A meaningful detector benchmark needs:

- explicit stress-family coverage;
- exact provenance;
- exact DESIGN/HOLDOUT separation;
- frozen candidates and acceptance criteria before governed HOLDOUT reveal;
- exact future R9 and R10 plan identities;
- one durable study/attempt history so failed or abandoned attempts cannot disappear;
- one-at-a-time and single-use attempt semantics;
- explicit predecessor-attempt and prior-holdout disclosure;
- exact execution-source binding;
- a reveal boundary that proves exact digest equality;
- an explicit ceiling on what "untouched" can actually mean.

R11 V2 implements that protocol.

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

It does not prove that a trajectory was causally produced by the named phenomenon. That requires the external generation/collection evidence named by the provenance binding.

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

The role-independent trajectory-content digest hashes only the sorted trajectory payloads.

It prevents trivial reuse of the exact same trajectories merely by relabeling the corpus from DESIGN to HOLDOUT.

It does not prove statistical independence between two different trajectory sets.

## Canonical artifact bytes

R11 defines one exact serialization for a benchmark corpus:

`canonical_corpus_artifact_bytes(corpus)`

It is compact canonical JSON of the exact R9 corpus payload.

At reveal time, supplied HOLDOUT bytes must equal this exact serialization.

This closes a provenance loophole where the object digest could refer to corpus A while the file digest referred to unrelated file B.

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

It does not establish independent sampling, separate operators, separate random seeds, absence of common upstream contamination, or absence of prior HOLDOUT access.

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

It does not prove that nobody saw the underlying data before the commitment, and it does not supply trusted wall-clock ordering.

## Execution binding

`BenchmarkExecutionBinding` binds:

- declared repository;
- declared 40-hex Git commit subject;
- schema version;
- SHA-256 of the exact runtime `benchmark.py`;
- SHA-256 of the exact runtime `calibration.py`;
- SHA-256 of the exact runtime `comparison.py`.

`assert_runtime_sources_match()` re-hashes those three local source files at seal, reveal, and run admission.

The source-file hashes are locally rechecked evidence.

The repository and Git commit strings are declared provenance fields. R11 does not independently interrogate Git to prove that the running files came from the declared commit.

A stronger code-origin claim would require a separately trusted package/build/signature or Git-attestation boundary.

## Precommit plan

`BenchmarkPrecommitPlan` freezes before governed reveal:

- study ID;
- attempt ID;
- precommit ID;
- exact predecessor terminal-attempt receipt digests;
- exact disclosed predecessor holdout digests;
- exact execution binding;
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

The R11 HOLDOUT digest must differ from every disclosed predecessor holdout digest.

The predecessor-holdout list is itself a declared governance input. R11 can enforce non-reuse only for holdouts actually disclosed to the plan; it cannot discover hidden prior holdouts by itself.

## Durable attempt ledger

`BenchmarkAttemptLedger` persists one study's attempt state in SQLite.

Attempt states are:

- `SEALED`
- `REVEALED`
- `EXECUTING`
- `EXECUTED`
- `INVALIDATED`
- `ABORTED`

The current attempt row is supplemented by an append-only `benchmark_attempt_events` trail.

A successful attempt therefore leaves:

`SEALED -> REVEALED -> EXECUTING -> EXECUTED`

An abandoned revealed attempt can leave:

`SEALED -> REVEALED -> ABORTED`

An execution failure after the single-use execution claim is converted to `INVALIDATED`.

## One active attempt per study

A study may not seal another attempt while one is:

- `SEALED`;
- `REVEALED`;
- `EXECUTING`.

A successor attempt may be sealed only after all prior attempts are terminal.

The successor precommit must reference every prior terminal attempt receipt digest.

It must also disclose every prior attempt HOLDOUT digest.

This makes abandoned and failed attempts durable ancestry rather than optional history.

## Single-use reveal

`reveal_holdout()` requires:

- exact `BenchmarkAttemptLedger`;
- an already durably `SEALED` attempt;
- exact precommit;
- exact execution binding;
- exact precommitted HOLDOUT manifest;
- exact R9 HOLDOUT corpus;
- exact canonical corpus artifact bytes.

It verifies:

- runtime source hashes;
- study/attempt/precommit identity;
- manifest digest;
- corpus role;
- corpus ID/version/digest;
- role-independent trajectory-content digest;
- exact family set;
- exact dimensions;
- exact shift labels;
- exact canonical artifact bytes;
- exact artifact SHA-256.

The ledger transition from `SEALED` to `REVEALED` is CAS-like and single-use.

Only that path can emit a `HoldoutRevealReceipt`.

The receipt claim is:

`EXACT_DIGEST_REVEAL_MATCH_NOT_NONACCESS_PROOF`.

## Single-use execution

`run_precommitted_holdout()` first re-admits:

- exact precommit;
- exact execution binding;
- exact durable `REVEALED` attempt;
- exact reveal receipt;
- exact manifest/corpus;
- exact CUSUM spec;
- exact future R9/R10 plans.

Immediately before detector comparison, the ledger atomically claims:

`REVEALED -> EXECUTING`

A concurrent or replayed execution can no longer reach the comparison path after that claim is consumed.

If comparison execution raises after the claim, the attempt is terminalized as `INVALIDATED`.

On success, the run receipt is persisted through:

`EXECUTING -> EXECUTED`

The run receipt remains non-promoting.

## What "precommitted" means here

Within R11, "precommitted" means:

> the exact candidate, criterion, benchmark metadata, HOLDOUT digest, future calibration/comparison plans, attempt ancestry, prior-holdout disclosure, and execution-source hashes were fixed in the durable precommit before R11's governed reveal/run transitions.

It does not mean:

> R11 proved that no human, process, model, repository administrator, CI system, or other tool had ever inspected the HOLDOUT before the precommit.

That stronger claim requires external custody, trusted time, access-control, and provenance evidence.

R11 intentionally does not invent those guarantees.

## Promotion boundary

R11 has no detector-selection authority.

The run receipt requires:

`promotion_authorized = false`

and the embedded R10 comparison receipt must also remain non-promoting.

The run claim is:

`PRECOMMITTED_COMPARISON_EXECUTED_NO_SELECTION_OR_PROMOTION_AUTHORITY`.

If one detector appears better on this HOLDOUT, R11 still does not authorize adopting it.

A subsequent promotion requires a separately governed selection/qualification protocol and, where selection occurred using this HOLDOUT, another independently governed qualification subject.

## Receipt integrity

`BenchmarkAttemptReceipt`, `HoldoutRevealReceipt`, and `BenchmarkRunReceipt` are factory-gated.

Direct construction of digest-bearing lookalikes is rejected.

`BenchmarkRunResult` cross-checks the run receipt against the exact embedded R10 comparison receipt digest.

As elsewhere in DriftGuard, Python module-private/factory tokens and a writable local SQLite database are API-governance boundaries, not hostile-process, operating-system, or hardware isolation.

## Hostile regressions

R11 V2 tests freeze:

- exact eight-phenomenon coverage;
- one exact global dimension set;
- exact DESIGN/HOLDOUT portfolio matching;
- rejection of identical DESIGN/HOLDOUT trajectory content;
- exact future R9/R10 plan digest binding;
- exact execution-source hash binding;
- declared prior R9/R10 holdout exclusion;
- one active attempt per study;
- same attempt/precommit ID cannot bind divergent subject;
- reveal requires durable seal;
- reveal replay rejection;
- execution claim is single-use before comparison;
- run replay rejection;
- append-only successful attempt history;
- durable aborted-attempt history;
- successor attempt must reference all terminal predecessors;
- successor attempt must disclose prior attempt holdouts;
- exact canonical artifact-byte reveal;
- changed execution binding rejection;
- exact precommitted R10 execution;
- no promotion authority;
- changed CUSUM spec rejection;
- direct attempt/reveal/run receipt construction rejection;
- explicit non-access/trusted-time claim ceiling.

The test corpora are protocol fixtures, not production benchmark evidence.

## Claim ceiling

An R11 V2 PASS means:

> these exact benchmark manifests, study/attempt commitments, disclosed prior-holdout set, execution-source hashes, HOLDOUT digest/bytes, R9 qualification plan, R10 comparison plan, and durable single-use state transitions compose deterministically under the governed protocol.

It does not prove:

- HOLDOUT non-access before precommit;
- trusted timestamp ordering;
- complete discovery of every historical holdout;
- external custody;
- repository/commit authenticity beyond declared metadata;
- database tamper resistance against arbitrary local write access;
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

## Composition base

R11 V2 is stacked on the clean composed DriftGuard subject that carries:

- R6 measurement validity;
- repaired R7 subject identity/epoch authority;
- R8 sequential detection;
- final R9 calibration semantics;
- R10 detector comparison;
- subject-bound evaluator attestation;
- subject-current reload/effect admission;
- generic actuator non-promotion semantics.

R11 remains statistical/research evidence. It does not authorize merge, deployment, credentials, provider actions, reloads, or other protected effects.
