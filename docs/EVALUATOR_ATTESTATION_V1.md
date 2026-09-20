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
- exact algorithm id.

The reference implementation uses HMAC-SHA256 and requires at least 32 bytes of key
material. It uses constant-time tag comparison.

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

Key custody, key-to-provider identity binding, rotation, revocation, hardware-backed
attestation, and remote trust roots remain external governance problems.

## Compatibility

The attestation layer is additive.

Existing structural evaluator-response validation remains available and retains its
existing claim ceiling. A caller must explicitly use
`commit_attested_evaluator_response()` to obtain the stronger key-possession
verification result.

This source candidate performs no network call, provider mutation, credential
change, reload effect, deployment, or runtime cutover.
