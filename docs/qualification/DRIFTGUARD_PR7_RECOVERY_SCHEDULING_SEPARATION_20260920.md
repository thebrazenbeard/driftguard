# DriftGuard PR #7 Recovery/Scheduling Separation — 2026-09-20

Status: **REPAIR CANDIDATE / SOURCE-ONLY / UNMERGED**

## Exact predecessor

DriftGuard PR #7 exact head:

`860bebd61baf2d5e8aa92ccf45adf52d573b3fb4`

PR #7 correctly added the external evaluator/actuator boundary, first post-acknowledgement replay binding, and bounded multi-checkpoint recovery qualification. It also preserved generation adjacency, so a later clean replay cannot replace the first post-acknowledgement replay.

## Exact defect

PR #7 used the operational `reload_required` flag as a behavioral recovery predicate.

Exact-head RED 1:

- save-state `max_turns_without_reload=1`;
- accepted reload acknowledgement at turn 1;
- first post-ack replay at turn 2;
- admitted drift score: `0.0`;
- aggregate drift: `0.0`;
- replay decision: `RELOAD`;
- `reload_required=true`;
- sole reason: `periodic_reload_due`.

Observed PR #7 result:

`qualify_post_reload_behavior()` rejected the replay with:

`ValueError: behavioral replay did not establish stable bounded recovery`

Exact-head RED 2:

A recovery-window checkpoint with:

- aggregate drift `0.0`;
- `Decision.RELOAD`;
- `reload_required=true`;
- sole reason `periodic_reload_due`

was classified:

`RELAPSE_RELOAD_REQUIRED`.

Both results violate DriftGuard's existing architecture: epistemic/behavioral state and operational reload scheduling are separate.

## Repair

A single shared `classify_behavioral_evaluation()` now classifies exact save-state-bound evaluations as:

- `STABLE`;
- `DEGRADED`;
- `RELAPSE`;
- `INDETERMINATE`.

Classification uses:

- exact save-state digest;
- `critical_dimension_breach`;
- admitted aggregate drift;
- the save-state warning/reload thresholds;
- UNKNOWN/incomplete evidence.

It does **not** use `reload_required` as a proxy for behavioral drift.

Consequences:

- periodic-only reload + complete low-drift evidence => behaviorally STABLE;
- periodic reload + warn-level drift => DEGRADED;
- aggregate at/above reload threshold => RELAPSE even if cooldown suppresses the immediate operational effect;
- valid critical breach => RELAPSE even when overall decision is UNKNOWN;
- UNKNOWN without a critical breach => INDETERMINATE.

Recovery-window receipts preserve both `behavioral_trace` and the independent `reload_required_trace`.

The former `RELAPSE_RELOAD_REQUIRED` disposition is replaced by `RELAPSE_BEHAVIORAL_DRIFT` on this unmerged Draft lineage so the durable vocabulary does not keep encoding the conflation.

## Local repair qualification

Pre-documentation repair head:

`3bdd2161452e53a15f59dd9646b8f72730bdf032`

Fresh exact-checkout execution with `PYTHONPATH` bound to the checkout:

- compileall: PASS;
- full unittest suite: **72/72 PASS**;
- diff-check against PR #7 exact head: PASS.

The first repair run failed with implementation wiring errors (missing `Evaluation` import and two tests lacking the new exact-state argument). Those failures were fixed without changing the behavioral design; the later 72/72 result is the accepted repair evidence.

## Claim ceiling

This repair establishes source/test behavior for recovery classification only.

It does not prove:

- evaluator honesty or actual independence;
- provider reload execution;
- causal attribution from reload to later behavior;
- hidden-state restoration;
- permanent recovery;
- identity continuity or consciousness;
- merge/deployment/runtime authority.

No merge, deployment, provider/model mutation, credential/permission change, Project Settings change, or other protected effect occurred.
