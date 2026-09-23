# DriftGuard R11 Governed Benchmark + Holdout Precommit V4

Status: statistical/research candidate restacked on current canonical DriftGuard main.

V4 closes four governance defects found after the final V3 self-review: post-claim runtime ambiguity could be mislabeled as semantic failure, prior HOLDOUT observations could be reused through metadata relabeling, free-form study IDs could reset lineage, and a study ID could silently change its confirmatory subject.

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

R11 V4 implements that protocol.

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

The role-independent trajectory-content digest hashes canonical trajectory observation/shift payloads while excluding `trajectory_id` and corpus identity/version metadata.

It prevents exact observation reuse from being disguised by corpus, version, artifact, or trajectory-ID relabeling.

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
- SHA-256 of the exact runtime `comparison.py`;
- SHA-256 of the exact runtime `sequential.py`;
- SHA-256 of the exact runtime `model.py`.

`assert_runtime_sources_match()` re-hashes those five local source files at seal, reveal, and run admission.

The five source-file hashes are locally rechecked evidence.

`sequential.py` is part of the execution subject because the calibrated CUSUM
recurrence used by R9/R10 is implemented there; binding only the detector parameters
would not bind the detector implementation.

`model.py` is also part of the closure because the benchmark/calibration/comparison/
sequential stack uses its canonical digest, source-binding, and detector-spec support
semantics. `model.py` has no DriftGuard-local imports, so these five files close the
current R11-local import graph.

The repository and Git commit strings are declared provenance fields. R11 does not independently interrogate Git to prove that the running files came from the declared commit.

A stronger code-origin claim would require a separately trusted package/build/signature or Git-attestation boundary.

## Precommit plan

`BenchmarkPrecommitPlan` freezes before governed reveal:

- caller-facing study ID;
- derived governed study-subject digest;
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

The R11 HOLDOUT corpus digest must differ from every disclosed predecessor holdout digest.

V4 additionally derives a governed study-subject digest from the benchmark portfolio, DESIGN observation content, exact execution-source subject, detector specification, family policies, normalized detector candidates, and selection rule. A caller cannot reset the same governed subject by changing `study_id`, and one `study_id` cannot silently drift to a different governed subject.

The ledger also persists each HOLDOUT trajectory-content digest and rejects exact observation-content reuse across prior attempts even when corpus/version/trajectory metadata changes.

The predecessor-holdout list remains declared provenance ancestry. R11 still cannot discover hidden holdouts that were never entered into the governed ledger.

## Durable attempt ledger

`BenchmarkAttemptLedger` persists one study's attempt state inside one exact chosen SQLite ledger.

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

An abandoned pre-execution attempt can leave:

`SEALED -> ABORTED`

or:

`SEALED -> REVEALED -> ABORTED`

Once an attempt reaches `EXECUTING`, ordinary operator abort/invalidate APIs can no
longer make it terminal. The execution claim has consumed retry authority.

A known semantic execution failure inside the governed run path may transition
`EXECUTING -> INVALIDATED` only through the factory-gated semantic-failure
transition bound to the exact precommit, reveal receipt, and execution binding.

If completion, storage, or reconciliation is ambiguous after the execution claim,
the attempt remains `EXECUTING`. R11 V4 provides no operator reason-string escape
from that state. A future resolution would require a separately typed reconciliation
protocol; until then the active attempt blocks a successor.

## One governed study subject and one active attempt, per ledger

Within one exact `BenchmarkAttemptLedger`, a derived governed study subject is bound to one caller-facing `study_id`. Reusing that subject under a different ID is rejected, and changing the governed subject under the same ID is rejected as silent redesign.

A study may not seal another attempt while one is:

- `SEALED`;
- `REVEALED`;
- `EXECUTING`.

A successor attempt may be sealed only after all prior attempts are terminal.

The successor precommit must reference every prior terminal attempt receipt digest.

It must also disclose every prior attempt HOLDOUT corpus digest, while the ledger independently rejects reuse of any prior HOLDOUT trajectory-content digest.

This makes abandoned and failed attempts durable ancestry rather than optional history inside that ledger and closes exact-content relabeling attacks.

R11 does not prove that no parallel/replacement ledger exists. A stronger
"complete study history" claim requires external custody or an independently anchored
ledger identity/root; creating or substituting another unanchored SQLite file is
outside this local-ledger claim.

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

After the execution claim, unexpected runtime/resource/implementation failures are ambiguous and remain `EXECUTING`. They are not converted into `INVALIDATED`.

The V4 implementation currently recognizes one explicit governed semantic violation after the claim: an R10 comparison attempting to authorize promotion. That exact condition uses the private factory-gated semantic-failure transition before raising `BenchmarkSemanticFailure`. Other `RuntimeError`, `OSError`, `MemoryError`, detector-execution failures, result-construction failures, and storage/finalization ambiguity propagate while the attempt stays `EXECUTING` and blocks successors.

Public `abort_attempt()` and `invalidate_attempt()` are limited to pre-execution `SEALED` / `REVEALED` states. They cannot resolve `EXECUTING`.

If semantic-failure invalidation or durable completion is itself ambiguous, R11 does
not infer safe retry. The attempt remains active/ambiguous until separately
reconciled.

If that invalidation write itself fails ambiguously, R11 does not infer that
invalidation succeeded and does not restore retry authority; the attempt remains
non-retryable unless durable state is separately reconciled.

Durable completion itself is a separate ambiguity boundary. If the final
`EXECUTING -> EXECUTED` storage transition fails ambiguously, R11 deliberately
does **not** convert the attempt to retryable state. It remains `EXECUTING` until
an external recovery/reconciliation procedure establishes what durable transition
occurred.

On successful durable completion, the run receipt is persisted through:

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

Factory provenance alone is not treated as sufficient transition authority.
Every durable reveal/run transition re-binds the supplied receipt to the exact:

- study ID;
- attempt ID;
- precommit digest;
- execution-binding digest;
- HOLDOUT seal / manifest / corpus / artifact digests for reveal;
- reveal digest plus exact R9 calibration-plan and R10 comparison-plan digests for run.

A valid receipt from study B therefore cannot advance or complete study A.

`BenchmarkRunResult` cross-checks the run receipt against the exact embedded R10 comparison receipt digest.

As elsewhere in DriftGuard, Python module-private/factory tokens and a writable local SQLite database are API-governance boundaries, not hostile-process, operating-system, or hardware isolation.

## Hostile regressions

R11 V4 tests freeze:

- exact eight-phenomenon coverage;
- one exact global dimension set;
- exact DESIGN/HOLDOUT portfolio matching;
- rejection of identical DESIGN/HOLDOUT trajectory content;
- exact future R9/R10 plan digest binding;
- exact execution-source hash binding, including `sequential.py`;
- declared prior R9/R10 holdout exclusion;
- one active attempt per study;
- same attempt/precommit ID cannot bind divergent subject;
- reveal requires durable seal;
- reveal replay rejection;
- execution claim is single-use before comparison;
- run replay rejection;
- explicit governed promotion semantic violation terminalizes `INVALIDATED`;
- unexpected RuntimeError/OSError/MemoryError after execution claim remain `EXECUTING` and block retry;
- result-construction and durable completion ambiguity remain `EXECUTING` and block retry;
- exact HOLDOUT observation reuse is rejected after metadata relabeling;
- study-ID relabeling cannot reset one governed study subject;
- same-study subject drift is rejected as redesign;
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
- cross-study reveal receipt replay rejection;
- cross-study execution-start replay rejection;
- cross-study run receipt replay rejection;
- explicit non-access/trusted-time claim ceiling.

The test corpora are protocol fixtures, not production benchmark evidence.

## Claim ceiling

An R11 V4 PASS means:

> these exact benchmark manifests, derived study subject, attempt commitments, disclosed prior-holdout provenance, exact prior HOLDOUT content nonreuse within this ledger, benchmark/calibration/comparison/sequential/model execution-source hashes, HOLDOUT digest/bytes, R9 qualification plan, R10 comparison plan, and durable single-use state transitions compose deterministically under the governed protocol.

It does not prove:

- HOLDOUT non-access before precommit;
- trusted timestamp ordering;
- complete discovery of every historical holdout outside this ledger;
- semantic equivalence detection for transformed/near-duplicate datasets beyond canonical exact content;
- semantic equivalence detection for arbitrarily transformed study subjects beyond the governed canonical subject;
- external custody;
- repository/commit authenticity beyond declared metadata;
- exact Python interpreter / standard-library implementation identity;
- database tamper resistance against arbitrary local write access;
- absence of parallel/replacement unanchored ledgers;
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

R11 V4 is stacked on the clean composed DriftGuard subject that carries:

- R6 measurement validity;
- repaired R7 subject identity/epoch authority;
- R8 sequential detection;
- final R9 calibration semantics;
- R10 detector comparison;
- subject-bound evaluator attestation;
- subject-current reload/effect admission;
- generic actuator non-promotion semantics.

R11 remains statistical/research evidence. It does not authorize merge, deployment, credentials, provider actions, reloads, or other protected effects.
