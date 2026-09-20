# DriftGuard R5 Converged Recovery Qualification — 2026-09-20

Status: **CONVERGED REPAIR CANDIDATE / SOURCE-ONLY / UNMERGED**

## Exact lineage

Common predecessor:
- PR #7 exact head `860bebd61baf2d5e8aa92ccf45adf52d573b3fb4`

Parallel partial repairs:
- PR #9 exact head `f02c28883869b38eff5caf452ad15af6acbe0fac`
  - closes the forged in-memory recovery-window evidence hole by re-reading exact durable ledger rows;
  - still inherits PR #7's conflation of `reload_required` with behavioral relapse.
- PR #10 exact head `9d1d284b11cb33658f5111ed09a061b0cbc5b50c`
  - separates behavioral recovery from periodic/cooldown reload scheduling;
  - still inherits PR #7's ability to qualify a recovery window from caller-constructed in-memory commits without durable ledger rows.

This candidate is stacked on PR #9 and converges both repairs.

## Defect A — forged recovery window

PR #7 accepted a recovery-window subject with no durable ledger rows. PR #9 reproduced:

- fabricated `BehavioralRecoveryReceipt`;
- fabricated subsequent `CommitResult` objects;
- empty `DriftLedger`;
- result: `SUSTAINED_BOUNDED_RECOVERY`.

PR #9 repairs this by requiring same-session durable acknowledgement/replay/checkpoint rows and exact rebinding.

The converged candidate preserves that repair and additionally re-binds persisted aggregate drift and reasons used by behavioral classification.

## Defect B — operational reload mislabeled behavioral relapse

Exact PR #7 reproduction:

- save-state periodic interval: 1 turn;
- accepted acknowledgement;
- first post-ack replay drift score / aggregate: `0.0`;
- decision: `RELOAD`;
- `reload_required=true`;
- sole reason: `periodic_reload_due`.

PR #7:
- rejected the initial behavioral-recovery pass;
- classified the same kind of later recovery-window checkpoint as `RELAPSE_RELOAD_REQUIRED`.

That violates DriftGuard's own separation between observed behavioral evidence and operational reload scheduling.

## Converged contract

Behavioral classification is exact-save-state-bound:

- `STABLE`: complete admitted evidence below warning threshold and no critical breach;
- `DEGRADED`: aggregate drift at/above warning threshold but below reload threshold;
- `RELAPSE`: aggregate drift at/above reload threshold or valid `critical_dimension_breach`;
- `INDETERMINATE`: UNKNOWN/incomplete evidence without a valid critical breach.

`reload_required` remains a separate operational trace.

Consequences:

- periodic-only reload + low complete drift => behaviorally STABLE;
- periodic-only reload + warn-level drift => DEGRADED;
- cooldown-suppressed aggregate above reload threshold => RELAPSE;
- UNKNOWN + valid critical breach => RELAPSE;
- UNKNOWN + periodic reload only => INDETERMINATE.

Recovery-window receipts bind both:
- exact durable decision/reload/aggregate/reasons evidence;
- `behavioral_trace`;
- independent `reload_required_trace`.

The unmerged Draft disposition `RELAPSE_RELOAD_REQUIRED` is replaced by `RELAPSE_BEHAVIORAL_DRIFT`.

The actual durable initial replay decision/reload flag is preserved in the window trace. It is not rewritten to synthetic `STABLE/false` merely because its behavioral classification is stable.

## Local qualification

Pre-documentation converged repair head:

`6763383208dfeac15e0064f0fa63a1fd7e6833ef`

Fresh isolated Windows checkout with `PYTHONPATH` bound to that checkout:

- compileall: PASS;
- full unittest: **77/77 PASS**;
- diff-check against PR #9 exact head: PASS.

Adversarial coverage includes:

- zero-ledger fabricated recovery subject rejection;
- cross-session durable-row rejection;
- durable aggregate/reason mismatch rejection;
- periodic-only clean first replay accepted behaviorally;
- warn-level periodic replay rejected as stable recovery;
- periodic-only clean later checkpoint remains behaviorally stable;
- periodic reload cannot hide warn-level drift;
- aggregate above reload threshold remains relapse even when the immediate reload effect is suppressed;
- UNKNOWN critical breach remains relapse;
- UNKNOWN periodic-only remains indeterminate;
- actual initial operational decision/reload trace is preserved;
- baseline mutation, generation gaps, and non-monotonic turns fail closed.

## Claim ceiling

This is source and executed-test evidence for the converged R5 recovery boundary only.

It does not prove:
- evaluator identity honesty or actual independence;
- provider restore execution;
- that a reload caused later behavior;
- hidden-state restoration;
- permanent recovery;
- identity continuity or consciousness;
- deployment, merge, or protected-effect authority.

No merge, deployment, provider/model mutation, credential/permission change, Project Settings change, or other protected effect occurred.
