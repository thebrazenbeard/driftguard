# DriftGuard Recovery-Window Qualification V1

Status: **DRAFT STACKED SOURCE CANDIDATE / NO RUNTIME EFFECT**

## Purpose

The external boundary already separates reload directive, reload effect, reload acknowledgement, and behavioral replay. It can produce a bounded post-reload behavioral replay pass only after a later committed evaluation returns STABLE.

That is intentionally still one replay.

**ONE STABLE REPLAY != SUSTAINED RECOVERY**

**SUSTAINED BOUNDED RECOVERY != PERMANENT RECOVERY**

**OBSERVED BEHAVIORAL RECOVERY != HIDDEN-STATE RESTORATION**

This layer adds a precommitted multi-checkpoint recovery window so a single favorable observation cannot be promoted into a durability claim.

## Qualification subject

A recovery window starts only from an existing BehavioralRecoveryReceipt. That receipt already binds the exact acknowledgement, save-state digest, first stable post-acknowledgement replay, evidence/observation/evaluation digests, turn, and generation.

Later checkpoints must be committed DriftGuard evaluations.

The default reference policy requires:

- at least 3 stable checkpoints, including the initial replay;
- at least 4 turns from the first stable replay to the final checkpoint.

Those are reference defaults, not universal scientific constants. The policy digest is part of the qualification receipt, so changing the standard after outcomes are known changes the subject.

## Fail-closed continuity

Every later checkpoint must preserve:

- the same exact save-state digest;
- strictly increasing turn index;
- contiguous DriftGuard generations;
- a valid successor generation.

A state-digest change invalidates the window rather than qualifying recovery against a new baseline.

**BASELINE MUTATION != RECOVERY**

If intended behavior changes, version a new save-state and start a new qualification subject. Runtime drift cannot rewrite the baseline against which it is being measured.

## Dispositions

**PENDING_MORE_OBSERVATION**

All checkpoints are stable, but the precommitted checkpoint count or turn-span requirement has not been met.

**SUSTAINED_BOUNDED_RECOVERY**

Every admitted checkpoint in the bounded window is stable and the policy requirements are met.

This means only that the exact governed save-state was observed as stable at every admitted checkpoint in that exact window.

**DEGRADED_DRIFT_RETURNED**

At least one later checkpoint is WARN and no checkpoint requires reload. Drift has returned below the reload threshold.

**RELAPSE_RELOAD_REQUIRED**

At least one later checkpoint requires reload. This takes priority even when the epistemic decision is UNKNOWN, preserving the R3 invariant that valid critical or periodic reload requirements survive incomplete evidence.

**INDETERMINATE_EVIDENCE**

No checkpoint requires reload and none is WARN, but at least one later checkpoint is UNKNOWN. Missing evidence therefore blocks a sustained-recovery claim.

**UNKNOWN != STABLE**

## Temporal claim ceiling

A recovery-window receipt is bounded to its exact first and last turns.

A later relapse does not erase the historical observation that the earlier window was stable. It is new evidence that recovery did not persist to the later point.

An earlier stable window also must not be reused as proof of current stability without a fresh evaluation.

**PAST STABLE WINDOW != CURRENT STABILITY**

## Why this matters

Without this layer, an implementation could reload, obtain one favorable replay, declare recovery, and ignore immediate drift return on later turns. That turns a point observation into a durability claim.

Recovery-window qualification keeps durability explicit, versioned, policy-bound, and falsifiable while preserving the existing separation among decision, effect, acknowledgement, replay, and longer-horizon qualification.

## Non-effects and non-claims

This source does not perform evaluator network calls, execute reloads, retry ambiguous provider effects, modify save-states, deploy anything, prove evaluator honesty, prove provider hidden state, prove identity continuity or consciousness, prove permanent recovery, merge, or modify main.
