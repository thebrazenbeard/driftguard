# DriftGuard External Evaluator / Actuator Boundary V1

Status: source candidate. No provider integration, no runtime authority, no deployment.

## Purpose

DriftGuard's native engine intentionally does not score conversations and does not
apply model-provider restores. Those are external systems. This boundary makes the
handoff explicit without allowing a connected evaluator or actuator to silently
promote itself into authority.

The boundary is transport-neutral and dependency-free. It does not perform HTTP,
provider API calls, model inference, credential use, retries, or recovery claims.

## Evaluator boundary

DriftGuard creates a digest-bound `EvaluatorRequest` from the governed save-state.

The request binds:

- exact governed probe source ref + version;
- exact dimension;
- source maximum independence;
- dimension minimum independence;
- exact state digest;
- exact observation digest;
- exact turn.

Observation bytes and evaluator instructions remain transport concerns and should
remain separate. The request binds the observation bytes by digest but does not
store them in the DriftGuard ledger.

The evaluator response is deliberately narrow:

- response schema;
- exact request digest;
- external execution ID;
- drift score;
- claimed independence.

The response does **not** get fields for source, dimension, state, observation, or
turn. DriftGuard injects those from the governed request when it creates
`DriftEvidence`. Unknown response fields fail closed.

This blocks a connected evaluator from self-selecting a stronger source identity,
crossing dimension scope, or rebinding its score to different state/observation
bytes. It still does not prove that the remote evaluator is honest or that its
claimed execution identity is cryptographically authentic.

## Reload actuator boundary

A native reload-required `CommitResult` may produce one `ReloadAttempt`.

The attempt binds:

- session ID;
- evaluation digest;
- state digest;
- turn;
- generation after the reload decision;
- exact UTF-8 restore-packet digest.

Its deterministic attempt ID is an idempotency/reconciliation key. It does not
prove delivery.

An external actuator may return one of:

- `CONSUMED_UNVERIFIED`
- `REJECTED`
- `AMBIGUOUS`

Every admitted receipt must bind the exact attempt fields.

Retry policy remains fail-closed:

- `AMBIGUOUS` => `RECONCILE_BEFORE_RETRY`
- `REJECTED` => `NO_AUTOMATIC_RETRY`
- `CONSUMED_UNVERIFIED` => `EFFECT_ALREADY_ASSERTED_DO_NOT_RETRY`

The boundary contains no automatic retry function.

Only `CONSUMED_UNVERIFIED` may be transformed into DriftGuard's existing
`ReloadAcknowledgement`. That acknowledgement still means only that the caller
asserts the exact restore packet was consumed. It may advance the native restore
anchor, but it does not establish provider honesty or behavioral recovery.

## Behavioral recovery remains external

This module intentionally exports no `POST_EFFECT_VERIFIED`, recovery-pass, or
behaviorally-verified acknowledgement.

A stronger recovery claim requires a later observation plus governed post-reload
behavioral evaluation. That evidence must be kept separate from the actuator's
delivery/consumption receipt.

## Non-effects

This source candidate does not:

- contact any model provider;
- execute a restore;
- retry an ambiguous effect;
- provision credentials;
- prove evaluator identity or independence;
- prove provider delivery;
- prove behavioral recovery;
- mutate a baseline save-state;
- merge, deploy, install, or activate DriftGuard.
