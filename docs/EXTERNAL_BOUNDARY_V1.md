# DriftGuard External Evaluator / Actuator Boundary V1

Status: DRAFT SOURCE CANDIDATE / STACKED ON PR #4 / NO EXTERNAL EFFECT.

## Purpose

DriftGuard V1 already separates drift evaluation, reload decisions, reload acknowledgements, and behavioral recovery claims. This boundary adds transport-facing subjects without making a transport authoritative over DriftGuard semantics.

The boundary is deliberately dependency-free. It does not perform network I/O.

## External evaluator request

`ExternalEvaluatorRequest` binds:

- session id;
- exact save-state digest;
- exact observation digest;
- turn index;
- expected DriftGuard generation;
- exact governed probe source ref/version;
- maximum source independence;
- authorized dimension scope.

Returned `DriftEvidence` must bind the same state digest, observation digest, and turn, and may cite only probe bindings present in the request. `commit_evaluator_response()` is the safe bridge into the ledger: it validates the response and commits with the request's exact `expected_generation`, so a delayed evaluator response cannot silently ride a later generation. DriftGuard's existing core admission remains authoritative for dimension coverage, independence ceilings, duplicate execution ids, and decision logic.

An evaluator request or response does not prove evaluator identity honesty or actual independence.

## Reload actuator directive

`ReloadDirective` is constructible only when the supplied reload-required `CommitResult` exactly matches a durable `evaluation_events` row read back through the same `DriftLedger`. A bare in-memory dataclass is insufficient. It binds:

- session id;
- evaluation digest;
- state digest;
- reload turn;
- expected post-decision generation;
- exact restore packet bytes and SHA-256.

The directive is a request for an external effect. It is not evidence that the effect happened.

## Ambiguous delivery

`ActuatorReceipt.status` is one of:

- `APPLIED`;
- `NOT_APPLIED`;
- `UNKNOWN`.

Reconciliation is fail-closed:

- `APPLIED` -> construct a digest-bound `ReloadAcknowledgement` candidate;
- `NOT_APPLIED` -> retry may be allowed by the caller;
- `UNKNOWN` -> `READBACK_REQUIRED`; blind retry is not authorized.

This module does not perform retries. A provider-specific adapter must reconcile an ambiguous outcome through provider readback before retry.

## Acknowledgement is not recovery

An actuator `APPLIED` receipt may support a reload acknowledgement. That acknowledgement may advance DriftGuard's restore anchor through the existing ledger.

It still does not prove behavioral recovery.

`qualify_post_reload_behavior()` requires the acknowledgement and the later replay to be present in the same `DriftLedger`; bare caller-constructed result objects are insufficient. It also requires the exact `SaveState`, whose digest must match both acknowledgement and replay. The later committed evaluation must:

- bind the same save-state;
- occur after the acknowledgement turn;
- begin at the acknowledgement successor generation;
- have complete admitted evidence;
- contain no critical-dimension breach;
- remain below the save-state warning threshold.

The behavioral classifier deliberately does **not** use `reload_required` as a proxy for drift. A periodic reload is an operational scheduling decision and may be due even when the admitted behavioral replay is below every drift threshold.

A replay at or above the warning threshold is degraded; at or above the reload threshold (or with a critical breach) it is relapse; incomplete/UNKNOWN evidence is indeterminate. Only behaviorally stable replay produces a bounded `POST_RELOAD_BEHAVIORAL_REPLAY_PASS` receipt.

This receipt says the governed replay was stable at that later turn. It does not prove hidden-state restoration, identity continuity, consciousness, or universal future stability.

## Tamper-evident external receipts

`ExternalReceiptChainEntry` provides a hash-linked subject suitable for persistence in an external append-only or independently anchored store.

The SQLite cross-check prevents ordinary caller-side laundering of unrecorded dataclasses into effect/recovery claims, but it does not defend against a local administrator who can rewrite the database. The hash chain is tamper-evident only relative to a trusted external anchor. Keeping both the mutable SQLite ledger and the only copy of the receipt-chain root under the same local administrator does not create tamper-proof storage.

## Non-effects

This source does not:

- contact an evaluator;
- execute a reload;
- retry an ambiguous effect;
- acknowledge a reload in the ledger;
- claim behavioral recovery without replay;
- create credentials;
- deploy a service;
- mutate a provider;
- merge any PR.
