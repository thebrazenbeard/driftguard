# Evaluator Attestation V1

Status: R6 source candidate / optional stronger evaluator-authenticity layer.

## Problem

DriftGuard's external evaluator boundary already binds evaluator evidence to:

- the exact save-state digest;
- observation digest;
- turn;
- expected generation;
- requested source/version contract.

That prevents many replay and rebinding failures, but the structural source identity is
still a caller-supplied claim. A caller that can fabricate a complete evaluator
response can also fabricate the source label unless a stronger authenticity layer
is present.

## V1 mechanism

Evaluator Attestation V1 adds an optional detached authentication tag over the
exact evaluator subject.

The signed subject binds:

- exact evaluator request digest;
- exact evaluator response digest;
- exact attestation-policy digest;
- governed key id;
- SHA-256 fingerprint of the exact key material;
- positive key epoch;
- exact algorithm id.

The reference implementation uses HMAC-SHA256 and requires at least 32 bytes of key
material. The policy digest binds SHA-256(key_material) plus a positive key epoch.
The builder and verifier reject supplied key material whose fingerprint does not
match the frozen policy. Tag comparison is constant-time.

The policy additionally binds the exact source/version identities that the key is
allowed to authenticate. Every source present in the evaluator response must be
both:

1. requested by the evaluator request; and
2. authorized by the attestation policy.

A policy cannot silently grant a source that was absent from the original request.

## What verification means

A successful V1 verification means:

> the exact request/response/policy subject carries a valid HMAC under the supplied
> key material for the configured key identity.

The verification claim is intentionally:

`KEY_POSSESSION_VERIFIED_NOT_PROVIDER_HONESTY_OR_INDEPENDENCE`

This does **not** prove:

- that a named provider actually controls the key;
- that the provider or evaluator is honest;
- that the evaluator is independent;
- that the key was not copied or compromised;
- that the score is semantically correct;
- model identity, consciousness, or hidden state;
- provider-side execution or token consumption.

The key fingerprint proves that the same frozen key material was used; it still does
not establish who controls that key. The epoch makes explicit key rotation move the
policy/attestation subject.

Key custody, key-to-provider identity binding, revocation, hardware-backed
attestation, and remote trust roots remain external governance problems.

## Compatibility

The attestation layer is additive.

Existing structural evaluator-response validation remains available and retains its
existing claim ceiling. A caller must explicitly use
`commit_attested_evaluator_response()` to obtain the stronger key-possession
verification result.

The attested commit path writes a dedicated immutable ledger receipt bound to the
exact session, committed evaluation digest, evaluator request/response digests,
attestation policy digest, key id, key fingerprint, key epoch, algorithm,
signature digest, and covered source/version set. Readback equality is part of the
stronger claim. An ordinary evaluator commit has no such receipt and therefore
remains ordinary.

Durable admission is not a free-form ledger write. The ledger has no public
record_evaluator_attestation(fields...) API. Its private admission boundary accepts
only the exact verifier-created EvaluatorAttestationVerification capability and
cross-checks that capability against the committed evaluation's exact session,
state, observation, turn, predecessor generation, and evidence digest before
persisting the receipt. A valid verification for response A therefore cannot be
rebound to an unrelated ordinary evaluation B.

If structural evaluation commit succeeds but attestation persistence does not, the
evaluation is not silently upgraded: absence of the durable attestation receipt is
authoritative for the attested/unattested distinction.

The stronger verification and attested-commit objects are verifier/factory-created
only; ordinary direct construction is rejected.

This source candidate performs no network call, provider mutation, credential
change, reload effect, deployment, or runtime cutover.
