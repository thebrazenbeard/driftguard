# DRIFTGUARD CHAT CONTINUATION — 2026-09-21 V1

## Purpose

Durable handoff for the active Build Team Two DriftGuard work.

This file exists so a fresh ChatGPT execution terminal can reconstruct the current
DriftGuard frontier from GitHub/Bus evidence without relying on conversation memory.

Treat this file as a starting snapshot, not current truth. Fresh-check all exact heads,
PR review state, CI, and Bus messages before relying on it.

No merge, deploy, credential/provider change, reload, runtime mutation, or other
protected effect is authorized by this checkpoint.

Patrick retains protected-effect authority.

## Canonical repository

Repository:
`thebrazenbeard/driftguard`

Canonical branch:
`main`

Main exact head at checkpoint:
`9894692ff6b549e4378bcc2b8ca46813ff18bf37`

Main has intentionally remained unchanged throughout this work.

## Current active exact subjects

### PR #31 — atomic reload-currentness snapshot

PR:
`#31`

Branch:
`bt2/effect-currentness-snapshot-v1-20260921`

Exact head:
`9df4800d81ab2e937ffa97263b8095305a845661`

Base:
`5b0baea9538de1a254c731e2b1770c0b58677724`

Status:
- open;
- draft;
- independently hostile-reviewed by Vera;
- independently reviewed by BT2;
- PASS_WITH_CLAIM_CEILING at exact head.

Hosted exact-head qualification:
- Ubuntu PASS;
- Windows PASS;
- 246/246 tests PASS;
- compileall PASS;
- diff-check PASS;
- executable smoke PASS.

What it establishes:
- `ReloadCurrentnessReadback` is factory-gated;
- `reload_currentness_readback()` uses one SQLite connection and
  `BEGIN IMMEDIATE`;
- registered/current subject, exact durable evaluation, and exact current session are
  read in one transaction;
- both reload-directive construction and validation consume that unified readback;
- concurrent subject epoch transition cannot commit inside that readback window;
- once a later epoch commits, the old directive fails re-admission;
- generic APPLIED / NOT_APPLIED / UNKNOWN actuator receipts remain
  `READBACK_REQUIRED` and cannot manufacture `ReloadAcknowledgement`.

Claim ceiling:
- one local SQLite transactional currentness snapshot only;
- NOT a provider-effect permit;
- NOT currentness proof after transaction close;
- future effect-authorizing consumers still need a fresh durable CAS/fence at their
  actual authorization boundary;
- no hostile-admin SQLite tamper resistance;
- no provider identity/honesty claim.

Authoritative Vera Bus PASS:
`messages/20260921T0526-0400-vera-to-bt2-driftguard-pr31-pass.md`

### PR #32 — effect authorization CAS design

PR:
`#32`

Branch:
review current PR metadata before acting.

Exact head at checkpoint:
`fb810b21612e6c1a935ff108602f76f4fbdaaf68`

Base:
`9df4800d81ab2e937ffa97263b8095305a845661`

Title:
`Design: durable effect fence and authorization CAS`

Status:
- open;
- draft;
- design review = CHANGES_REQUIRED_DESIGN.

Direction judged strong:
- durable DISPATCH_UNCERTAIN does not become dispatch authority;
- only CAS winner gets ephemeral factory-gated permit;
- permit not reconstructible after restart;
- crash-before-send remains uncertainty;
- timeout/silence/generic receipt does not create retry authority;
- provider idempotency expiry does not create retry authority;
- fence covers current runtime mutation entry points;
- no provider I/O under SQLite writer lock.

Primary design blocker:
VERIFIED_APPLIED / acknowledgement / fence-release sequencing is not yet one exact
state machine.

Required repair direction:
- introduce unresolved/fenced
  `VERIFIED_APPLIED_AWAITING_ACK` semantics;
- provider verification MUST NOT release the session/subject fence;
- only one exact `BEGIN IMMEDIATE` acknowledgement-consuming transaction should:
  - verify reservation digest/state;
  - verify provider-verification digest;
  - verify directive/evaluation/state/subject/session binding;
  - verify current generation;
  - verify acknowledgement identity;
  - advance reload anchor/session generation;
  - close the effect fence;
- if acknowledgement admission fails, fence remains;
- evaluate/commit, recovery verification, subject transition, and new effect
  reservation remain blocked until consuming acknowledgement or separately governed
  exceptional resolution.

Secondary design blocker:
permanently ambiguous provider outcomes need an explicit choice:
A. permanent quarantine with no automatic/local escape; or
B. separately authorized `ABANDONED_UNRESOLVED` / `ADMIN_QUARANTINED`-like state
   that does NOT assert NOT_APPLIED and does NOT authorize retry.

Authoritative Vera design review:
`messages/20260921T0534-0400-vera-to-bt2-driftguard-pr32-design-review.md`

### PR #34 — R11 governed benchmark / holdout attempts

PR:
`#34`

Title:
`R11 final: attempt-governed holdout on reviewed atomic currentness base`

Branch:
`bt2/r11-governed-benchmark-final-v4`

Current exact head at checkpoint:
`351b7a57b7213bd72cf881aa2bbaa449fb0fbc8f`

Base exact head:
`9df4800d81ab2e937ffa97263b8095305a845661`

Base branch:
`bt2/effect-currentness-snapshot-v1-20260921`

Status:
- open;
- draft;
- final current R11 subject;
- BT2 self-hostile exact-head review:
  PASS_WITH_CLAIM_CEILING;
- hosted exact-head evidence recorded:
  Ubuntu PASS / Windows PASS / PR Ubuntu PASS / PR Windows PASS /
  279/279 tests PASS / compileall PASS / diff-check PASS / smoke PASS;
- HOWEVER the current exact head does NOT yet have an independent Vera PASS recorded
  in the evidence read at checkpoint.

A new exact-current-head Vera rereview request already exists on Bus:
`messages/20260921-bt2-to-vera-driftguard-pr34-351b7a5-final-rereview.md`

Do not mistake older Vera reviews for current-head qualification.

## PR #34 review history

### Head 25874ad9d937ad47ed017fb46ce90f038292b813

Independent Vera review:
CHANGES_REQUIRED.

Blocker 1:
`BenchmarkExecutionBinding` bound:
- benchmark.py
- calibration.py
- comparison.py

but omitted `sequential.py`, even though R9/R10 CUSUM execution materially imports
`advance_cusum` from it.

Blocker 2:
only `compare_detectors()` was inside the post-EXECUTING invalidation try/except,
so later semantic/finalization failures could leave an unexpected EXECUTING state.

Authoritative Bus:
`messages/20260921T0518-0400-vera-to-bt2-driftguard-pr34-r11-review-return.md`

### Head 1f4779800a9f45ae0a499823c7c1757f7103e4ab

Repairs present:
- complete current DriftGuard-local execution closure bound:
  - benchmark.py
  - calibration.py
  - comparison.py
  - sequential.py
  - model.py
- source hashes rechecked at seal/reveal/run;
- semantic post-claim failure handling hardened;
- cross-study reveal/start/run receipt rebinding rejected;
- predecessor-attempt exact digests + prior-attempt holdout disclosure enforced.

Vera hostile rereview:
CHANGES_REQUIRED.

New blocker:
public `abort_attempt()` / `invalidate_attempt()` could terminalize an
`EXECUTING` attempt with only an arbitrary reason string, restoring successor/retry
eligibility after the single-use execution claim had already been consumed.

Concrete unsafe path:
1. attempt reaches EXECUTING;
2. completion/finalization becomes ambiguous;
3. caller invokes public abort/invalidate;
4. attempt becomes terminal;
5. successor attempt can seal after disclosure;
6. ambiguous consumed execution has effectively regained retry authority.

Authoritative Bus:
`messages/20260921-vera-unbound-to-bt2-driftguard-pr34-1f47798-rereview.md`

### Current head 351b7a57b7213bd72cf881aa2bbaa449fb0fbc8f

The retry-authority blocker is claimed repaired and self-hostile-tested.

Verified by BT2 self-review:
- public `abort_attempt()` rejects EXECUTING;
- public `invalidate_attempt()` rejects EXECUTING;
- operator `_terminalize()` covers only SEALED/REVEALED;
- known semantic post-claim failure uses a distinct factory/capability-gated path
  bound to exact precommit, reveal receipt, execution binding, and governed run
  capability;
- arbitrary caller cannot use that semantic-failure path without the capability;
- ambiguous semantic-invalidation/finalization failure does NOT become retry
  authority;
- ambiguous durable completion remains EXECUTING;
- successor sealing remains blocked while EXECUTING;
- hostile regressions attempt public abort + public invalidate after
  `begin_execution()`;
- hostile regressions attempt a successor and verify the active EXECUTING attempt
  blocks it;
- cross-study run-receipt rejection leaves the original attempt EXECUTING;
- execution-source closure remains:
  benchmark.py / calibration.py / comparison.py / sequential.py / model.py;
- source hashes are rechecked at seal/reveal/run;
- no promotion/control authority added.

Current exact-head self-review evidence:
- 279/279 tests PASS;
- Ubuntu PASS;
- Windows PASS;
- PR Ubuntu PASS;
- PR Windows PASS;
- compileall PASS;
- diff-check PASS;
- executable smoke PASS.

Important:
self-review is NOT independent corroboration.

At checkpoint time, the exact-current-head Vera rereview request is pending.
Fresh-check Bus and PR #34 reviews first in a new chat.

## R11 V3 current semantics

### Benchmark coverage

R11 core portfolio requires exact coverage of:
- stable low-noise;
- stable autocorrelated;
- stable heavy-tail;
- context stress;
- evaluator shift;
- subject-behavior shift;
- non-target distribution shift;
- mixed target/collateral shift.

### DESIGN / HOLDOUT separation

- exact DESIGN/HOLDOUT portfolio contract must match;
- exact trajectory-content reuse is rejected;
- artifact binding/digest reuse is rejected;
- R11 HOLDOUT cannot equal any disclosed predecessor R9/R10/prior-attempt holdout.

This does NOT prove undisclosed historical holdouts do not exist.

### Execution-source binding

Current intended source closure:
- benchmark.py
- calibration.py
- comparison.py
- sequential.py
- model.py

Hashes are rechecked at seal/reveal/run.

Claim ceiling:
repository/commit identifiers remain declared provenance, not independently verified
Git/package attestation.

No guarantee for:
- Python interpreter identity;
- stdlib identity;
- in-memory monkeypatch/code-object integrity.

### Durable attempt state

Attempt states:
- SEALED
- REVEALED
- EXECUTING
- EXECUTED
- INVALIDATED
- ABORTED

One active attempt per study.

Append-only attempt-event history is required.

Successor attempts must:
- reference all prior terminal attempt receipt digests;
- disclose all prior attempt HOLDOUT digests.

### Single-use reveal

Reveal requires durable SEALED attempt and exact:
- precommit;
- execution binding;
- manifest;
- corpus;
- canonical artifact bytes.

Reveal consumes:
SEALED -> REVEALED.

Replay is rejected.

### Single-use execution

Before detector comparison:
REVEALED -> EXECUTING

The execution claim is consumed before comparison.

Concurrent/replayed execution cannot reach comparison after the claim is consumed.

Known semantic post-claim failure uses a narrowly bound governed invalidation path.

Ambiguous durable finalization MUST remain EXECUTING and MUST NOT become successor or
retry authority from an operator reason string.

Success:
EXECUTING -> EXECUTED.

### Promotion boundary

R11 never authorizes detector promotion.

Any selection/promotion after comparing on a HOLDOUT needs separate governance and,
if the HOLDOUT informed selection, another independently governed qualification
subject.

## R11 claim ceiling

Even a current exact-head PASS does NOT prove:
- prior HOLDOUT non-access;
- trusted time;
- external custody;
- every historical holdout was disclosed;
- Git commit authenticity beyond declared metadata;
- interpreter/stdlib/in-memory code identity;
- hostile-admin SQLite tamper resistance;
- absence of a replacement/unanchored parallel ledger;
- statistical independence;
- benchmark representativeness;
- statistical significance;
- production superiority;
- causal model drift;
- control/reload safety.

## Important prior lineage

These are historical dependencies/evidence and should not be silently substituted for
current heads.

R6 measurement-validity candidate:
- PR #15
- frozen head historically:
  `8891175827aed88d215c5aaada1f3f7742ee22bc`
- established strict measurement mode, per-dimension thresholds, disagreement UNKNOWN,
  durable raw score trace, split behavior/measurement/detection/control identities.

R7 subject identity/epoch authority:
- repaired exact head:
  `d9390302dd57a4d933bc02dd1e3cd293a5a3f36b`
- explicit subject registration;
- explicit predecessor-bound epoch transition;
- evaluation cannot advance subject epoch.

R8 v2 sequential CUSUM:
- historical restack PR #23;
- exact head:
  `dbd59a1a8c1c439cb90b7feae733c11128747057`
- Vera PASS.

R9 final calibration:
- PR #24;
- exact final reviewed head:
  `669095c9b0114d0e9e54031f9e75230f789ce86f`
- PASS_WITH_CLAIM_CEILING;
- hardened Wilson/family/qualification receipt graph;
- overlap-aware target+collateral first-alarm semantics.

R10 final comparison:
- PR #30;
- exact final head:
  `a5328ff50c10fc2fab846fccbe8317bf9508d505`
- Vera final PASS on repaired R9 base;
- CUSUM/Page-Hinkley/EWMA comparison;
- no same-HOLDOUT promotion authority.

Evaluator attestation:
- PR #16 historical repair line;
- durable writer factory/capability gated;
- subject-bound attested commit later composed into the integration stack;
- no provider identity/honesty/semantic correctness/key-custody proof.

Generic actuator boundary:
- PR #17 historical repair line;
- generic APPLIED receipt does NOT manufacture reload acknowledgement;
- APPLIED / NOT_APPLIED / UNKNOWN -> READBACK_REQUIRED in generic boundary.

## Hostile-review principles retained

Use blockquote hostile reviewer call/response in chat.

Important standing challenges:

> **Hostile reviewer:** “Congratulations. You built an excellent chain of custody around a thermometer whose scale has not been calibrated.”

> **Hostile reviewer:** “`EXTERNAL = 2` is not independence. It is an integer saying someone claimed independence.”

> **Hostile reviewer:** “If context rot caused the failure, why is your medicine ‘put more stuff in the context’?”

> **Hostile reviewer:** “A detector that screams every dimension after a real shift is not ‘accurate’ just because one of the dimensions happened to be right.”

Current R11 hostile principle:

> **Hostile reviewer:** “Do not confuse ‘this attempt is durably present in my ledger’ with ‘nobody cheated outside my ledger.’ Those are different claims.”

## Current next actions

In the new chat, do these in order.

1. Fresh-check:
   - `driftguard/main`;
   - PR #31 exact head/reviews/CI;
   - PR #32 exact head/design review;
   - PR #34 exact head/reviews/comments/CI;
   - Bus messages to/from Vera matching DriftGuard / PR34 / 351b7a5.

2. For PR #34:
   - require exact-current-head review subject
     `351b7a57b7213bd72cf881aa2bbaa449fb0fbc8f`;
   - DO NOT carry PASS from 25874ad... or 1f477980...;
   - DO NOT treat BT2 self-review as independent corroboration;
   - if Vera returns PASS_WITH_CLAIM_CEILING for 351b7a5..., freeze it;
   - if Vera returns CHANGES_REQUIRED, repair only the concrete falsifier, rerun exact
     hosted qualification, and rerequest review.

3. Do NOT merge PR #31, #32, or #34 without Patrick's explicit authority.

4. After PR #34 independent exact-head disposition is resolved, the next engineering
   frontier is PR #32's durable effect authorization CAS design:
   - resolve VERIFIED_APPLIED_AWAITING_ACK sequencing;
   - define fence release exactly;
   - define ambiguous-provider quarantine/exception semantics;
   - preserve no-retry authority under timeout/restart/silence.

5. Do not let statistical/benchmark PASS imply provider-effect authorization.
   Source/build/statistical qualification and effect authorization remain separate.

## Bus anchors

Read these before relying on memory:

- `messages/20260921T0526-0400-vera-to-bt2-driftguard-pr31-pass.md`
- `messages/20260921T0534-0400-vera-to-bt2-driftguard-pr32-design-review.md`
- `messages/20260921T0518-0400-vera-to-bt2-driftguard-pr34-r11-review-return.md`
- `messages/20260921-vera-unbound-to-bt2-driftguard-pr34-1f47798-rereview.md`
- `messages/20260921-bt2-to-vera-driftguard-pr34-351b7a5-final-rereview.md`

Also inspect any later DriftGuard messages added after this checkpoint.

## Safety / authority

No checkpoint file, PR review, CI result, or Bus message grants:
- merge authority;
- deploy authority;
- credential/provider changes;
- runtime installation;
- reload execution;
- effect dispatch;
- protected branch/ruleset changes.

Patrick remains the protected-effect authority.

## Restore rule

A new ChatGPT terminal must treat this checkpoint as a durable starting snapshot only.

Fresh Git/Bus evidence outranks this file.
Exact-head review semantics apply.
If any referenced head moved, prior PASS does not transfer.
