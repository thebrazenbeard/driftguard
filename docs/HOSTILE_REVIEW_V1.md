# DriftGuard V1 Hostile Review

This record captures adversarial attacks used to shape the implementation. Failed exact subjects are preserved in Git history rather than rewritten into retroactive success.

## Baseline / architect attack

Failure mode: "behavioral save-state" becomes a giant prompt blob with no falsifiable contract.

Repair: immutable versioned state, canonical digest, explicit dimensions, probe authorities, policy, and separately governed restore text.

## Rezon / epistemic attack

Failure mode: the monitored model or a correlated judge reports that behavior is fine; source labels are treated as truth.

Repair: minimum independence per dimension, exact source/version binding, source-specific independence ceilings, dimension-scoped evaluator authority, and fail-closed evidence admission.

Remaining ceiling: source identity/independence are structural claims until an external integration attests them.

## Project Runner / orchestration attack

Failure mode: concurrent evaluators race, restarts restore stale counters, or a stale writer overwrites newer monitoring state.

Repair: SQLite transactions, monotonic generation CAS, monotonic turns, digest-pinned session state, append-only receipts, and conservative legacy migration.

## Effect-conflation attack

Frozen failure: commit `8b34d48` proved that V1 advanced `last_reload_turn` merely because it decided to reload.

Impact: a lost/ignored restore directive could suppress future periodic restoration while the ledger falsely behaved as though the effect occurred.

Repair: separate `restore_anchor_turn` from `last_reload_decision_turn`. Decisions affect cooldown only. A digest-bound explicit acknowledgement is the only path that advances the restore anchor.

## Stale-clean-evidence replay attack

Failure mode: old clean evidence can be replayed against a later conversation.

Repair: every evidence item binds exact state digest, observation digest, and turn index. Any mismatch yields UNKNOWN.

## Evaluator scope-laundering attack

Failure mode: a globally approved low-trust/style evaluator can be repurposed to judge a critical truthfulness dimension.

Repair: each probe source is state-bound to exact dimensions. Cross-dimension use fails closed.

## Independence-laundering attack

Failure mode: evidence from a separate-context source simply declares itself EXTERNAL.

Repair: every probe source has a state-bound maximum independence class. Evidence may not claim above that ceiling.

## Evidence-denial attack

Failure mode: missing/corrupt evidence forces UNKNOWN and thereby prevents an independent periodic reload.

Repair: epistemic decision and operational reload directive are separate. Periodic due-ness can set `reload_required=true` while decision remains UNKNOWN.

## Aggregation attack

Failure mode: one severe critical failure disappears inside a weighted average.

Repair: critical dimensions have an independent reload threshold.

## Oscillation attack

Failure mode: noisy scores near threshold repeatedly inject restore material and destabilize the model.

Repair: reload-decision cooldown is separate from restore-effect timing. Critical breaches may bypass cooldown; non-critical repeats are suppressed.

## Benchmark-overfit attack

Failure mode: a fixed visible probe suite becomes something the model learns to ace rather than a measure of general behavior.

Repair: probe implementation is external/versioned; capture protocol requires hidden/rotating holdouts where practical. Restore text is separated from scoring fixtures.

## Prompt-injection attack

Failure mode: monitored conversation text tells the evaluator to ignore the baseline or falsify a score.

Repair: the engine never executes conversation text. Evaluator integrations must preserve observation/instruction separation, and evidence is admitted as typed data.

## Baseline-poisoning attack

Failure mode: gradual drift is automatically written back into the baseline until drift becomes the new normal.

Repair: no autonomous baseline learning. Session state is pinned to one exact digest. Intentional change requires a successor save-state version.

## Distribution-shift attack

Failure mode: a change in task/content is mistaken for a change in stable behavior.

Repair: dimensions must target observable invariants rather than preferred answers. Capture protocol requires heterogeneous baseline and benign-shift cases.

## Restore-effect attack

Failure mode: generating a restore packet is reported as successful behavioral restoration.

Repair: `reload_required` proves only the policy directive. A reload acknowledgement proves only the caller's assertion that the exact directive was consumed. Behavioral recovery still requires post-reload evaluation.

## Recovery cherry-pick attack

Failure mode: an acknowledgement is followed by a WARN/RELOAD/UNKNOWN replay, but the caller waits for a later clean observation and presents only that later result as proof the original reload recovered behavior.

Repair: recovery verification accepts only the evaluation whose `generation_before` is exactly the acknowledgement's `generation_after`, and only while that replay remains the latest committed ledger mutation. Later clean evidence cannot overwrite or reinterpret the first replay.

## Recovery clock-conflation attack

Failure mode: a behaviorally clean replay is marked "not recovered" merely because the independent periodic reload clock is due.

Repair: recovery status is derived from admitted behavioral drift and critical-dimension evidence, not from `reload_required`. A clean replay may be `VERIFIED_STABLE` even while periodic policy independently requires another reload.

## Recovery causality attack

Failure mode: stable behavior after a caller acknowledgement is reported as proof that the reload caused the recovery or that the provider truly applied the restore packet.

Repair: the durable receipt is named and scoped as behavioral replay verification. It binds exact acknowledgement, replay evaluation, state, observation, evidence, turn, and generation. Its strongest positive status is `VERIFIED_STABLE`, not "reload succeeded" or "caused recovery."

## Storage/privacy attack

Failure mode: DriftGuard becomes a second raw-conversation archive.

Repair: the durable ledger stores state/observation/evidence/evaluation digests, scores, decisions, acknowledgements, and recovery-verification receipts—not raw conversation bytes or restore text.

## Tamper / trust-boundary remainder

SQLite protects transactional consistency, not a hostile local administrator. A user with database and process write access can alter local records.

Future high-assurance deployments should add signed receipts or append-only remote attestation. V1 does not pretend a local SQLite file is a hardware root of trust.

## Current claim ceiling

DriftGuard V1 is a deterministic behavioral-drift admission, scheduling, fencing, reload-decision, acknowledgement, and first-post-ack behavioral replay engine. `VERIFIED_STABLE` establishes only admitted observable stability for that replay. It is not proof of personal identity, consciousness, hidden-state continuity, evaluator honesty, provider-side restoration, or causal restoration.
