from __future__ import annotations

import hashlib
import json
from typing import Any

from .ledger import AcknowledgementResult, CommitResult
from .model import ReloadAcknowledgement


DISCOVERY_EFFECT_SCHEMA_VERSION = "DISCOVERY_EFFECT_ATTEMPT_V0"
DRIFTGUARD_R4_SOURCE_REF = (
    "one/driftguard-r4-windows-eol-v1-20260919"
    "@e815c75ffccf469d9d1c09d58c0050798c8e4f53"
)
_ACTION_CLASS = "BEHAVIORAL_STATE_RELOAD"
_TARGET_KIND = "DRIFTGUARD_BEHAVIORAL_SAVE_STATE"


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _require_session_id(session_id: str) -> str:
    if type(session_id) is not str or not session_id.strip():
        raise ValueError("session_id must be a non-empty exact string")
    return session_id


def _target(
    *,
    state_digest: str,
    session_id: str,
    expected_generation: int,
    evaluation_digest: str,
) -> dict[str, str]:
    return {
        "kind": _TARGET_KIND,
        "locator": f"state_sha256:{state_digest}",
        "expected_precondition": json.dumps(
            {
                "session_id": session_id,
                "expected_generation": expected_generation,
                "evaluation_digest": evaluation_digest,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
    }


def reload_decision_envelope(
    *,
    session_id: str,
    commit: CommitResult,
) -> dict[str, Any]:
    """Export a reload-required native decision as PRE_EFFECT.

    This adapter is observational/interchange-only. It does not execute a reload,
    decide retry policy, or advance DriftGuard state.
    """
    session_id = _require_session_id(session_id)
    if type(commit) is not CommitResult:
        raise ValueError("commit must be exact CommitResult")
    evaluation = commit.evaluation
    if evaluation.reload_required is not True:
        raise ValueError("only reload-required evaluations have an effect attempt")
    if commit.successor_generation != evaluation.generation + 1:
        raise ValueError("commit successor generation does not match evaluation")

    return {
        "schema_version": DISCOVERY_EFFECT_SCHEMA_VERSION,
        "source_system": "driftguard",
        "source_operation_id": evaluation.digest,
        "source_state": f"{evaluation.decision.value}:RELOAD_REQUIRED",
        "source_ref": DRIFTGUARD_R4_SOURCE_REF,
        "source_payload_sha256": evaluation.digest,
        "action_class": _ACTION_CLASS,
        "target": _target(
            state_digest=evaluation.state_digest,
            session_id=session_id,
            expected_generation=commit.successor_generation,
            evaluation_digest=evaluation.digest,
        ),
        "normalized_phase": "PRE_EFFECT",
        "retry_disposition": "DOMAIN_DECIDES",
        "receipts": [
            {"kind": "evaluation_digest", "value": evaluation.digest},
            {"kind": "state_digest", "value": evaluation.state_digest},
            {
                "kind": "claim_ceiling",
                "value": "RELOAD_DECISION_NOT_EFFECT",
            },
        ],
    }


def reload_acknowledgement_envelope(
    *,
    session_id: str,
    acknowledgement: ReloadAcknowledgement,
    result: AcknowledgementResult,
    expected_generation: int,
) -> dict[str, Any]:
    """Export an accepted downstream acknowledgement as POST_EFFECT_UNVERIFIED.

    DriftGuard V1 explicitly treats the acknowledgement as a caller assertion of
    downstream effect, not proof of behavioral recovery. This adapter therefore
    has no path that maps an acknowledgement to POST_EFFECT_VERIFIED.
    """
    session_id = _require_session_id(session_id)
    if type(acknowledgement) is not ReloadAcknowledgement:
        raise ValueError("acknowledgement must be exact ReloadAcknowledgement")
    if type(result) is not AcknowledgementResult:
        raise ValueError("result must be exact AcknowledgementResult")
    if type(expected_generation) is not int or expected_generation < 0:
        raise ValueError("expected_generation must be non-negative int")
    if result.ack_id != acknowledgement.ack_id:
        raise ValueError("acknowledgement/result id mismatch")
    if result.restore_anchor_turn != acknowledgement.turn_index:
        raise ValueError("acknowledgement/result restore-anchor mismatch")
    if result.successor_generation != expected_generation + 1:
        raise ValueError("acknowledgement/result generation mismatch")

    source_payload = {
        "acknowledgement": {
            "ack_id": acknowledgement.ack_id,
            "evaluation_digest": acknowledgement.evaluation_digest,
            "state_digest": acknowledgement.state_digest,
            "turn_index": acknowledgement.turn_index,
        },
        "result": {
            "ack_id": result.ack_id,
            "successor_generation": result.successor_generation,
            "restore_anchor_turn": result.restore_anchor_turn,
        },
    }

    return {
        "schema_version": DISCOVERY_EFFECT_SCHEMA_VERSION,
        "source_system": "driftguard",
        "source_operation_id": acknowledgement.ack_id,
        "source_state": "RELOAD_ACKNOWLEDGED_CALLER_ASSERTION",
        "source_ref": DRIFTGUARD_R4_SOURCE_REF,
        "source_payload_sha256": _canonical_sha256(source_payload),
        "action_class": _ACTION_CLASS,
        "target": _target(
            state_digest=acknowledgement.state_digest,
            session_id=session_id,
            expected_generation=expected_generation,
            evaluation_digest=acknowledgement.evaluation_digest,
        ),
        "normalized_phase": "POST_EFFECT_UNVERIFIED",
        "retry_disposition": "DOMAIN_DECIDES",
        "receipts": [
            {"kind": "ack_id", "value": acknowledgement.ack_id},
            {
                "kind": "evaluation_digest",
                "value": acknowledgement.evaluation_digest,
            },
            {"kind": "state_digest", "value": acknowledgement.state_digest},
            {
                "kind": "restore_anchor_turn",
                "value": str(result.restore_anchor_turn),
            },
            {
                "kind": "claim_ceiling",
                "value": "CALLER_ACKNOWLEDGED_NOT_BEHAVIORALLY_VERIFIED",
            },
        ],
    }


__all__ = [
    "DISCOVERY_EFFECT_SCHEMA_VERSION",
    "DRIFTGUARD_R4_SOURCE_REF",
    "reload_acknowledgement_envelope",
    "reload_decision_envelope",
]
