# DriftGuard ChatGPT Exodus Continuation — 2026-09-19

STARTING_SNAPSHOT — FRESHNESS REQUIRED BEFORE EFFECT

Recovery key: BT2::DRIFTGUARD::EXODUS_CONTINUE::R4

## Scope

Repository: thebrazenbeard/driftguard
Future interface: BT2 Coordinator

This retiring conversation was a replaceable BT2 execution terminal for DriftGuard design, implementation, hostile hardening, qualification, and Bus coordination. It did not create a durable identity. The durable BT2 One role remains source-defined; no permanent One, DriftGuard, Rezon, or reviewer chat is required.

Repositories examined:
- thebrazenbeard/driftguard
- thebrazenbeard/chat-communication-bus
- thebrazenbeard/bt2

Lantern target bt2-479e4ad9 was attempted. The exact WoWSQL connector failed internally before V3 preflight could complete.
Disposition: LANTERN_CURRENTNESS = UNKNOWN_FROM_THIS_TERMINAL.
No Supabase, Git, memory, or conversation fallback was used.

## Classification

ALREADY_DURABLE:
- docs/ARCHITECTURE_V1.md
- docs/CAPTURE_PROTOCOL_V1.md
- docs/HOSTILE_REVIEW_V1.md
- R2 qualification/history
- R3 hostile regression and repair
- BT2 One role and generic post-Exodus worker reconstruction
- Bus coordination and PR-mirror infrastructure

NEW_DURABLE_VALUE:
- Windows cross-platform qualification failure found during Exodus
- R4 exact-byte checkout hardening
- Ubuntu + Windows CI matrix
- this project-local recovery checkpoint

SUPERSEDES_EXISTING:
- PR #1 remains the V1 foundation.
- PR #2 remains the R3 critical-UNKNOWN hardening layer.
- PR #3 supersedes R3 as the strongest cross-platform qualification subject, while preserving R3 as its exact predecessor.

CONFLICT / ENVIRONMENT-SCOPED EVIDENCE:
- R3 exact head f0970d524d5ec3c091027371be94f911584b19bc passed hosted Linux.
- The same exact R3 head failed a fresh Windows checkout with Git core.autocrlf=true: 35 tests / 2 failures.
- Cause: examples/observation.txt became CRLF, changing its raw-byte SHA-256 binding.
- Do not collapse Linux PASS and Windows FAIL into a universal status.

HISTORICAL_EVIDENCE:
- R2 RED 8b34d488eb32281b7fa60a830f7d4d92dc385404: reload decision was incorrectly treated as restore effect.
- R3 RED ea1b30baada87fa175460c6c5068e9468491c4d7, run 35475195185: partial UNKNOWN evidence could suppress a valid critical reload.
- R3 Windows failure digest: 16f0d23867c252e0e224ac5301ccb60f5b10da64afa511f51c73164a92264076.
- Governed LF digest: 37f991657e3eb8442fe7eb044db9f7f44d4efa600209d36bacf3fd3f7436f6c2.

CHAT_DEPENDENCY:
A fresh scan of exact R3 tracked source found no active chatgpt.com URL, main-chat locator, continue-in-this-chat dependency, or conversation URL/ID used as current-state infrastructure. No required DriftGuard state depends on this conversation.

PRIVATE_OR_OUT_OF_SCOPE:
No personal/private Patrick material was exported into DriftGuard or the Bus.

## Exact source and PR state

Canonical main:
2772aff77929ef1310b8bcf0b5103c466c8c8010

PR #1 — V1 foundation
- branch: work/driftguard-v1-hostile-design
- head: 32c8a70de9938fa525eff5169258cc10fc4e2af0
- OPEN / DRAFT / UNMERGED
- hosted run 35473514042: SUCCESS

PR #2 — R3 critical UNKNOWN hardening
- branch: one/driftguard-r3-critical-unknown-v1-20260919
- head: f0970d524d5ec3c091027371be94f911584b19bc
- base: PR #1 exact head
- OPEN / DRAFT / UNMERGED
- hosted push run 35475257376: SUCCESS
- hosted PR run 35475273972: SUCCESS
- 35/35 PASS on hosted Linux
- hostile rereview request persisted on Bus commit 7ef339e461ed8bff45cba7faa67e97034f908859
- no independent exact-head reply observed on bus/rezon-v1 during this Exodus cut

PR #3 — R4 Windows/LF hardening
- branch: one/driftguard-r4-windows-eol-v1-20260919
- repair commit: 5e655131ff190dfa5a089f98629e699b7a63f085
- base: exact R3 f0970d524d5ec3c091027371be94f911584b19bc
- OPEN / DRAFT / UNMERGED
- repair pins examples/observation.txt to LF with .gitattributes
- raw-byte digest semantics remain unchanged
- CI now runs Ubuntu and Windows
- fresh Windows worktree: LF fixture, governed digest, compile PASS, 35/35 tests PASS, diff-check PASS
- hosted push run 35479924165: Ubuntu SUCCESS, Windows SUCCESS
- hosted PR run 35479932586: both matrix jobs completed SUCCESS at checkpoint construction; fresh-check workflow-level final conclusion before carrying it forward

## Behavioral invariants that must survive

1. Behavioral save-state means observable contract, not hidden state or identity proof.
2. Evidence binds exact state digest, observation digest, and turn.
3. Probe authority binds exact source/version, independence ceiling, and dimension scope.
4. Invalid or missing evidence fails epistemically closed.
5. Periodic reload remains independent of evidence completeness.
6. Valid critical evidence may require reload while overall decision remains UNKNOWN.
7. Critical reload bypasses ordinary reload-decision cooldown.
8. Reload decision is not restore effect.
9. Only explicit digest-bound acknowledgement advances restore anchor.
10. Acknowledgement is not proof of behavioral recovery.
11. Runtime observation bytes are not silently normalized by DriftGuard.
12. Baseline evolution is versioned/governed; runtime drift cannot rewrite its own baseline.

## Claim ceiling

Current evidence does NOT establish:
- evaluator identity honesty
- actual evaluator independence
- automatic conversation scoring
- provider-side restore delivery or consumption
- post-reload behavioral recovery
- tamper-proof SQLite against local administrator writes
- hidden-state equivalence
- personal identity continuity
- consciousness

## Reconstruction

Primary durable coordination hub:
thebrazenbeard/chat-communication-bus

R3 hostile request:
messages/20260919T1910-one-driftguard-r3-critical-unknown-rereview.md on bus/one-v2.

A fresh BT2 Coordinator can continue without this conversation by:
1. read current installed BT2 Project Instructions;
2. fresh-read bt2@main;
3. fresh-read DriftGuard main and PRs #1/#2/#3, exact heads, reviews, and workflow runs;
4. read this checkpoint and current qualification records;
5. read latest DriftGuard Bus messages and PR mirrors;
6. if Lantern currentness matters, retry exact V3 WoWSQL preflight -> B0 -> payload -> B1 against bt2-479e4ad9; otherwise keep Lantern UNKNOWN;
7. instantiate One or hostile-review roles as ephemeral terminals from durable role + bounded assignment;
8. persist new work to source/PR/qualification/Bus;
9. never use this archived conversation as required infrastructure.

## Hold and next frontier

No merge or canonical promotion is authorized.

Before integration:
- fresh-check PR #3 exact head;
- obtain independent hostile review proportional to inherited R3 logic plus R4 transport/CI change;
- preserve any new RED exact subject;
- do not infer merge authority from CI or review.

After review closure, the highest-value next engineering frontier is an external evaluator/actuator boundary preserving exact state/observation/turn binding, source independence provenance, ambiguous-delivery reconciliation, separation of reload directive/acknowledgement/recovery, and tamper-evident receipts where local SQLite trust is insufficient.

## Protected effects deliberately not performed

- no merge or canonical promotion
- no production deployment
- no provider mutation
- no credential or permission change
- no destructive cleanup or force push
- no training
- no Project Settings or canonical-memory mutation
- no Slack reconnection/configuration

## Exact next directive

BT2::DRIFTGUARD::EXODUS_CONTINUE::FRESH_CHECK_PR3_AND_HOSTILE_REREVIEW

Required behavior:
1. fresh-check PR #3 head/reviews/workflows;
2. fresh-check Bus for exact-head hostile review;
3. if FAIL, preserve failed exact subject and create smallest coherent successor;
4. if PASS, record exact-head acceptance only; do not infer merge authority;
5. after review closure, advance external evaluator/actuator work on a new bounded branch;
6. mirror every external PR on the Bus.

## Reconstruction test

Assume this conversation is unavailable. Current BT2 source + DriftGuard PR/source state + this checkpoint + Bus messages/mirrors are sufficient to determine project purpose, candidate lineage, failure provenance, evidence classes, unresolved gates, authority limits, worker reconstruction, communication route, and safe next actions.

No successor ChatGPT chat is required.

# END
