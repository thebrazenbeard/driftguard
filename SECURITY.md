# Security Policy

## Reporting a vulnerability

Please do not open a public issue for a vulnerability that could expose secrets, bypass a gate, forge provenance, widen authority, or cause an unintended protected effect.

Use GitHub's private vulnerability reporting for this repository when available.

A useful report includes:

- affected commit or release;
- the exact policy/input/state required to reproduce it;
- expected behavior;
- observed behavior;
- whether the issue can turn `BLOCK` or `UNKNOWN` into `PASS`;
- whether it can alter trusted baseline/policy provenance;
- whether it can widen filesystem, process, provider, or deployment authority.

Do not include live credentials or unrelated private data.

## Security model

DriftGuard treats missing or unverifiable evidence as a first-class condition rather than silently passing it.

The GitHub Action's automatic trusted-ref mode reads policy and baseline from pre-change Git state. This reduces self-modifying-gate attacks, but does not replace repository branch protection or workflow governance.

DriftGuard does not claim to protect against an attacker who already controls the trusted repository history, required workflow definition, GitHub organization policy, runner, evaluator, or other external trust roots.
