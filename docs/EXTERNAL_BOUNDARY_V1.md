# DriftGuard External Evaluator / Actuator Boundary V1

Status: DRAFT COMPOSED SOURCE CANDIDATE / NO EXTERNAL EFFECT.

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

An `ExternalEvaluatorResponse` binds the exact evaluator request digest plus the canonical evidence-set digest. The same response object therefore cannot be replayed across another session/request even when state, observation, turn, probe scope, and generation otherwise match. Its `DriftEvidence` must bind the same state digest, observation digest, and turn, and may cite only probe bindings present in the request. `commit_evaluator_response()` accepts only this exact request-bound response and commits with the request's exact `expected_generation`, so a delayed evaluator response cannot silently ride a later generation.

The response envelope is structural binding, not cryptographic evaluator attestation. A dishonest caller that can forge an entirely new response remains outside the current trust claim. DriftGuard's existing core admission remains authoritative for dimension coverage, independence ceilings, duplicate execution ids, and decision logic.

An evaluator request or response does not prove evaluator identity honesty or actual independence.

## Reload actuator directive

`ReloadDirective` is constructible only when the supplied reload-required `CommitResult` exactly matches a durable `evaluation_events` row read back through the same `DriftLedger`. A bare in-memory dataclass is insufficient. It binds:

- session id;
- evaluation digest;
- state digest;
- reload turn;
- expected post-decision generation;
- exact restore packet bytes and SHA-256.

The directive is a request for an external effect. It is constructible only while that reload-required evaluation is still the session's current durable generation and last evaluation. A historical reload event cannot be replayed into a new effect request after acknowledgement or later evaluation moves the session forward.

The directive is not evidence that the effect happened.

A transportable ReloadDirective remains an untrusted value even if its fields and
self-digest are well formed. Before an actuator receipt is interpreted,
validate_reload_directive() re-admits the directive against:

- the exact pinned SaveState;
- the exact deterministic restore-packet bytes for that state;
- the durable reload-required evaluation receipt;
- the receipt generation transition;
- the session current generation, state digest, and last evaluation.

reconcile_actuator_receipt() requires the same SaveState and DriftLedger and
performs that validation before any APPLIED, NOT_APPLIED, or UNKNOWN receipt is
interpreted.

A generic ActuatorReceipt is transport/readback evidence only. It is not
independently authenticated provider-effect proof. Therefore APPLIED, NOT_APPLIED,
and UNKNOWN all return READBACK_REQUIRED and no ReloadAcknowledgement.

DriftLedger.acknowledge_reload() is an explicit downstream trust boundary. It
validates an acknowledgement against durable reload-required evaluation and
session currentness, but it does not itself prove provider application. Callers
must invoke it only after effect proof has been independently established outside
the generic ActuatorReceipt path.

Direct ReloadDirective construction cannot create directive provenance, a generic
ActuatorReceipt cannot manufacture an acknowledgement, and a once-valid directive
becomes stale after the durable session moves forward.

## Ambiguous delivery

`ActuatorReceipt.status` is one of:

- `APPLIED`;
- `NOT_APPLIED`;
- `UNKNOWN`.

Reconciliation is fail-closed:

- `APPLIED` -> `READBACK_REQUIRED`, no acknowledgement;
- `NOT_APPLIED` -> `READBACK_REQUIRED`, no acknowledgement;
- `UNKNOWN` -> `READBACK_REQUIRED`, no acknowledgement.

A generic transport receipt never manufactures a `ReloadAcknowledgement`, regardless
of its status label.

A bare generic receipt never grants retry authority. This module does not perform retries. A provider-specific adapter must establish independently verified non-application through provider readback before any later layer may authorize a retry.

## Acknowledgement is not recovery

A generic actuator `APPLIED` receipt is not sufficient support for a reload
acknowledgement. Provider application must be independently established outside the
generic receipt path before a caller may submit a `ReloadAcknowledgement` to the
ledger.

A valid acknowledgement may advance DriftGuard's restore anchor, but it still does
not prove behavioral recovery.

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


## R7 subject-currentness composition

A legacy V1 reload directive is valid only on an entirely unbound
`subject=None` path.

A subject-bound V2 reload directive requires one exact subject across:

- directive subject digest/epoch;
- durable evaluation receipt subject digest/epoch;
- durable session subject digest/epoch;
- supplied `MonitoredSubject`;
- durable subject-epoch registry currentness.

`validate_reload_directive(..., subject=...)` performs those checks before any
actuator receipt is interpreted. `reconcile_actuator_receipt()` passes the same
subject through that validation.

Consequently, a directive that was valid under S@N becomes validation-ineligible
after an explicit S@N -> S@N+1 transition, even if its other state/evaluation fields
have not changed.
