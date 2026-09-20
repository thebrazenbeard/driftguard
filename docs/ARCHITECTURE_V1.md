# DriftGuard V1 Architecture

Status: executable reference implementation candidate.

## Goal

DriftGuard monitors observable behavioral divergence from a versioned save-state and determines when that exact state should be reloaded. It does not claim access to hidden model state, consciousness, or identity continuity.

## State model

A save-state binds:

- an immutable state ID + version;
- exact restore text;
- named behavioral dimensions with weights, criticality, and minimum evidence independence;
- a governed probe-source registry;
- reload thresholds, periodic interval, and cooldown policy.

Each probe source binds an exact source reference/version to:

- the maximum independence class it may claim;
- the exact dimensions it may judge.

The canonical state digest covers all of the above.

## Evidence model

Each V1 drift evidence item carries:

- unique evidence and execution IDs;
- one dimension and drift score in [0, 1];
- exactly one governed probe source;
- claimed independence;
- exact save-state digest;
- exact observation digest;
- exact turn index.

Admission fails closed when evidence is stale, duplicated, under-independent, overclaims its source's independence ceiling, comes from an ungoverned source, crosses source/dimension scope, or leaves a required dimension uncovered.

The source registry is an authority boundary, not proof of provider honesty. A dishonest caller can still forge a source identity unless a future integration supplies cryptographic/provider attestation.

## Decision model

Epistemic status and reload action are intentionally separate.

`decision` describes evidence interpretation:

- `STABLE`
- `WARN`
- `RELOAD`
- `UNKNOWN`

`reload_required` is the operational directive.

That separation matters because a periodic reload can still be required while evidence is `UNKNOWN`. An attacker cannot suppress scheduled restoration merely by denying or corrupting drift evidence.

Critical-dimension or aggregate threshold breaches can also require reload when evidence is complete.

## Reload clocks

Two clocks are separate:

- `restore_anchor_turn`: last session-start or acknowledged restore anchor;
- `last_reload_decision_turn`: last turn where DriftGuard required a reload.

The first controls periodic reload due-ness. The second controls decision cooldown.

A reload decision never advances the restore anchor.

Only an explicit reload acknowledgement bound to the exact state digest, evaluation digest, and turn may advance the restore anchor. The acknowledgement remains a caller assertion of downstream effect; it is not behavioral proof.

## Post-reload behavioral replay

Behavioral recovery is a third state, separate from both reload decision and reload acknowledgement.

A recovery verification binds one accepted acknowledgement to one already-committed evaluation receipt. The replay must:

- use the same pinned save-state digest;
- occur on a strictly later turn than the acknowledged reload decision;
- be the **first ledger mutation** after that acknowledgement;
- still be the session's latest committed evaluation when verification is recorded;
- pass the same exact state/observation/turn/source/independence admission rules as every other evaluation.

This first-replay rule prevents cherry-picking a later clean observation after an earlier post-reload WARN, RELOAD, or UNKNOWN result.

Recovery status is:

- `VERIFIED_STABLE`: admitted behavioral evidence is below the ordinary warning threshold and has no critical-dimension breach;
- `NOT_STABLE`: admitted behavioral evidence is at/above the warning threshold or has a critical breach;
- `UNKNOWN`: replay evidence fails closed or cannot establish aggregate behavioral drift.

Recovery classification deliberately ignores the periodic reload clock and reload-decision cooldown. A replay can be behaviorally stable while an independent periodic policy still requires another reload.

Each acknowledgement gets at most one durable recovery verification. A `NOT_STABLE` or `UNKNOWN` result is not silently retried against a later observation; a later recovery claim requires a later governed reload/acknowledgement cycle.

`VERIFIED_STABLE` means only that the admitted first post-acknowledgement replay is behaviorally stable under the pinned save-state policy. It does not prove the reload caused the stable behavior, prove provider honesty, or reveal hidden model state.

## Persistence and concurrency

SQLite provides:

- monotonic session generation;
- compare-and-swap on every durable mutation;
- monotonic turn ordering;
- save-state digest pinning;
- append-only evaluation receipts;
- append-only reload acknowledgements;
- append-only recovery-verification receipts with exact acknowledgement/evaluation/digest/generation binding.

Legacy V1 databases that used one conflated `last_reload_turn` are migrated conservatively: the old first turn becomes the restore anchor, while a later legacy reload value is treated only as a decision timestamp. An old decision is never promoted into a confirmed restore effect.

## Project Runner influence

Project Runner supplied the operational invariants: exact mutable predecessor, generation CAS, fail-closed stale work, explicit readback/receipt boundaries, and separation of capability from authority/effect.

## Rezon influence

Rezon supplied the epistemic invariants: canonical digest binding, exact source/version provenance, rejection of empty identities, scope-aware evidence admission, and distrust of self-promoted evidence.

## Remaining external boundary

V1 does not perform the model-provider reload itself and does not generate drift scores from conversation text. External evaluator/actuator integrations must preserve:

1. observation bytes separate from evaluator instructions;
2. exact state + observation + turn binding;
3. source identity and independence provenance;
4. effect reconciliation before retry if downstream delivery becomes ambiguous;
5. the acknowledgement -> first post-ack evaluation -> recovery-verification ordering before exporting any verified behavioral recovery claim.

Provider delivery, evaluator honesty, and causal attribution remain outside the native proof boundary.
