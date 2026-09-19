# DriftGuard V1 Architecture

Status: design + executable reference implementation candidate.

## Goal

DriftGuard monitors behavioral divergence from a versioned behavioral save-state and decides when restoration material should be reloaded. It does not claim to measure consciousness, identity, or inaccessible model-internal state. Its subject is observable behavior under an explicit contract.

## Core invariants

1. A save-state is immutable inside a monitoring session. Intentional evolution creates a new version; it is never silently learned into the baseline.
2. Drift is a vector over named behavioral dimensions, not one opaque similarity score.
3. Evidence and authority are separate. A model saying it still follows the baseline is not independent evidence that it does.
4. Every evidence item has an exact execution identity plus non-empty source/version bindings. Allowed probe sources are declared by the save-state.
5. Each dimension declares the minimum independence required of its evidence.
6. Missing, duplicate, under-independent, or ungoverned evidence yields UNKNOWN, not a guessed score.
7. A reload decision returns a digest-bound restore packet. The engine itself does not claim that a provider actually consumed or obeyed it.
8. Reload decisions use cooldown behavior so DriftGuard cannot create an endless self-induced reload loop. Critical dimensions can bypass cooldown.
9. A periodic reload can be required even when measured drift is low. Detection and periodic refresh are separate mechanisms.
10. Session persistence uses monotonic turn numbers and generation compare-and-swap. Stale writers cannot overwrite newer monitoring state.

## Project Runner influence

Project Runner contributes the operational discipline: exact mutable predecessors, monotonic generations, fail-closed stale work, postcondition readback, and explicit separation of execution capability from authority. DriftGuard V1 applies the same pattern to monitoring-session generations and save-state pinning rather than treating every invocation as fresh state.

## Rezon influence

Rezon contributes epistemic discipline: canonical digests, explicit source/version association, rejection of empty provenance identities, and distrust of self-promoted evidence. DriftGuard therefore admits probe evidence only through explicit source bindings and independence requirements.

## Decision semantics

STABLE: complete admissible evidence is below thresholds and no periodic reload is due.

WARN: drift exceeds the warning threshold, or a non-critical reload condition is currently suppressed by cooldown.

RELOAD: aggregate drift, a critical dimension, or the periodic interval requires a restore packet.

UNKNOWN: evidence is incomplete, conflicting, insufficiently independent, or outside the save-state's governed probe sources.

UNKNOWN is intentionally not auto-converted to RELOAD in V1. Some deployments may choose that policy later, but hiding uncertainty inside a remediation action would erase useful evidence.

## Evidence ceiling

The reference engine can prove deterministic admission and decision behavior for its inputs. It cannot prove that an external evaluator is genuinely independent merely because a JSON field says so; cryptographic/provider attestation is a future boundary. It also cannot prove that a generated restore packet changed a model's behavior unless a separate post-reload probe establishes that effect.
