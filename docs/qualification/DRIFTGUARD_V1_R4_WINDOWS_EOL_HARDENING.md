# DriftGuard V1 R4 Windows EOL Hardening

Status: CANDIDATE / WINDOWS REGRESSION REPAIR / UNMERGED.

## Exact predecessor

R3 exact subject:
`f0970d524d5ec3c091027371be94f911584b19bc`

R3 hosted Linux evidence:
- push run `35475257376`: SUCCESS;
- pull-request run `35475273972`: SUCCESS;
- R3 qualification at that cut: 35/35 PASS on hosted Linux.

R3 remains valid as Linux-hosted evidence. It is not promoted to cross-platform PASS.

## Exodus-discovered Windows failure

During the ChatGPT Exodus reconstruction audit, a fresh Windows checkout of exact R3 was executed with Git `core.autocrlf=true`.

Observed exact local result:
- `python -m compileall -q src tests`: reached test execution;
- `python -m unittest discover -s tests -q`: **35 tests / 2 failures**;
- failing tests:
  - `test_example_evaluation_executes_end_to_end`;
  - `test_file_digest_is_deterministic`.

Exact cause:
- tracked fixture content is LF in Git;
- Windows checkout converted `examples/observation.txt` to CRLF;
- DriftGuard correctly hashes raw observation bytes;
- Windows worktree digest became
  `16f0d23867c252e0e224ac5301ccb60f5b10da64afa511f51c73164a92264076`;
- governed example evidence is bound to LF digest
  `37f991657e3eb8442fe7eb044db9f7f44d4efa600209d36bacf3fd3f7436f6c2`;
- therefore the example correctly failed evidence admission as `UNKNOWN`.

Disposition:
`R3_CROSS_PLATFORM_QUALIFICATION = FAIL / CHANGES_REQUIRED`.

This is not a defect in raw-byte hashing. It is a repository byte-preservation defect.

## R4 repair

R4 preserves exact-byte semantics and repairs repository transport:

1. add `.gitattributes` with:
   `examples/observation.txt text eol=lf`;
2. keep the existing raw-byte digest expectations unchanged;
3. expand GitHub Actions from Ubuntu-only to an Ubuntu + Windows matrix;
4. execute the same unit suite, compile check, diff check, and example CLI smoke on both operating systems.

The repair does not canonicalize or silently normalize runtime observation bytes. It only ensures this committed reference fixture is checked out with the byte representation to which its evidence is bound.

## Claim ceiling

A green R4 proves the committed reference fixture and suite behave consistently on the tested Ubuntu and Windows runners. It does not prove arbitrary caller transports preserve bytes, evaluator honesty, provider-side restore delivery, behavioral recovery, hidden-state continuity, consciousness, or identity.

No merge, deployment, provider mutation, credential change, or protected effect is authorized by this qualification.
