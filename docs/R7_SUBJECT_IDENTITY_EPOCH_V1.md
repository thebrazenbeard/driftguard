# DriftGuard R7 Monitored Subject Identity + Epoch V1

Status: stacked candidate on R6 measurement-validity head `8891175827aed88d215c5aaada1f3f7742ee22bc`.

## Problem

A behavioral time series is meaningful only if DriftGuard knows what subject it is measuring.

Without an explicit subject boundary, any of these can masquerade as "model drift":

- provider/runtime changes;
- model/version changes;
- instruction changes;
- tool-contract changes;
- retrieval configuration changes;
- memory changes;
- inference/sampling changes;
- evaluator harness changes.

R7 therefore makes monitored-subject identity a first-class, digest-bound input.

## Required manifest surfaces

A `MonitoredSubject` must explicitly bind all of:

- `provider`;
- `model`;
- `instructions`;
- `tools`;
- `retrieval`;
- `memory`;
- `inference`;
- `harness`.

Every component has:

- a component ID;
- exact ref;
- exact version;
- SHA-256 digest of the canonical identity material used by the caller.

A disabled surface must still be represented. For example, "retrieval disabled" should have a governed ref/version and digest of the exact disabled configuration. Omitting it is not equivalent to disabling it.

Extra components are allowed, but required components may not be omitted or duplicated.

## Two identities

R7 separates configuration from time-series epoch.

`configuration_digest` hashes the subject ID and all sorted component bindings/digests.

`epoch` is an explicit non-negative integer.

`epoch_digest` binds the configuration digest and epoch together.

Two epochs may intentionally use the same configuration digest. This is useful for a controlled restart, new baseline campaign, or other deliberate segmentation without pretending the runtime configuration changed.

## Durable epoch registry

The ledger maintains a durable `subject_epochs` registry.

For one `subject_id`:

- one epoch can bind only one exact configuration;
- an existing epoch cannot be rebound to a different configuration;
- a newly introduced epoch must advance exactly one beyond the latest registered epoch;
- the latest registered epoch is the live/current epoch;
- once a later epoch exists, earlier-epoch sessions are superseded for new evaluation/effect work.

The first epoch observed by a new ledger may be any non-negative value. This allows controlled import of an already-versioned external subject lineage without inventing missing historical epochs.

## Session boundary

A subject-bound session pins:

- full save-state digest;
- subject configuration digest;
- subject epoch.

Inside a session, DriftGuard fails closed if the caller attempts to:

- change subject configuration;
- change epoch;
- remove subject identity;
- attach subject identity late to a legacy unbound session.

A new subject epoch therefore requires a new session/time-series boundary.

## Evidence binding

Subject-aware `DriftEvidence` binds:

- subject configuration digest;
- subject epoch.

When an evaluation is subject-bound, unbound evidence, evidence from another configuration, or evidence from another epoch is rejected.

Legacy evidence remains byte/digest compatible when the optional R7 fields are absent.

## External evaluator boundary

A subject-bound evaluator request is:

`DRIFTGUARD_EXTERNAL_EVALUATOR_REQUEST_V3`.

It binds the subject configuration digest and epoch in addition to the existing state/observation/turn/generation/measurement contract.

An evaluator response whose evidence names another subject or epoch is rejected.

## Effect/readback boundary

Subject identity is not checked only at measurement time.

For a subject-bound session, current subject readback is required when:

- building a reload directive;
- acknowledging a reload;
- verifying the first post-reload recovery replay.

The reload directive becomes `DRIFTGUARD_RELOAD_DIRECTIVE_V2` and explicitly carries subject digest + epoch.

A superseded epoch cannot mint a new reload directive.

## What a component digest means

A SHA-256 binding proves equality with the exact bytes that were hashed.

It does **not** prove that those bytes truthfully represent hidden provider state.

If a provider does not expose a weight hash or internal runtime image, the model component should hash a canonical *observed identity record*, for example provider, public model identifier, release/revision identifier, API metadata, and any other available attestation.

The claim must remain:

"same observed/provider-declared identity record"

not:

"cryptographically proven same hidden model weights."

## Compatibility

R7 fields are optional outside subject-bound mode.

When no subject is supplied:

- legacy evidence serialization is unchanged;
- legacy Evaluation digests are unchanged;
- old ledger sessions remain unbound;
- historical recovery receipts remain valid under their prior claim ceilings.

An existing legacy session cannot later attach R7 subject identity. Start a new session instead.

## Claim ceiling

R7 establishes deterministic monitored-subject provenance and epoch boundaries.

It does not establish:

- truthfulness of provider-declared metadata;
- hidden model-weight identity when unavailable;
- server/process/container identity unless explicitly represented in a component;
- statistical stationarity inside an epoch;
- that a component digest was collected from the actual runtime rather than caller fabrication;
- behavioral-drift causality;
- context-window health;
- evaluator validity;
- sequential change-point validity;
- restore effect or causal recovery.

## Next frontier

With R6 preserving calibrated per-dimension/source observations and R7 preventing subject changes from contaminating one live epoch, the next coherent layer is longitudinal detection.

That layer should consume the durable score streams and use a precommitted sequential method rather than isolated threshold crossings. Candidate families include CUSUM, Page-Hinkley, EWMA, and adaptive-window methods, but the detector must be calibrated against false-alarm behavior and must never erase the raw observations it summarizes.
