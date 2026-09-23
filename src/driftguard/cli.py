from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ci_gate import CiPolicy, CiReport, evaluate_ci, render_markdown
from .core import DriftGuardEngine
from .ledger import DriftLedger
from .model import (
    DriftEvidence,
    MonitoredSubject,
    ReloadAcknowledgement,
    SubjectEpochTransition,
    SaveState,
    raw_bytes_digest,
)


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str):
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def _load_json(path: str):
    text = Path(path).read_text(encoding="utf-8")
    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
    )


def _state(path: str) -> SaveState:
    return SaveState.from_mapping(_load_json(path))


def _subject(path: str) -> MonitoredSubject:
    return MonitoredSubject.from_mapping(_load_json(path))


def _evidence(path: str) -> tuple[DriftEvidence, ...]:
    raw = _load_json(path)
    if type(raw) is not list:
        raise ValueError("evidence document must be a JSON array")
    return tuple(DriftEvidence.from_mapping(item) for item in raw)


def _evaluation_payload(result):
    evaluation = result.evaluation
    return {
        "decision": evaluation.decision.value,
        "reload_required": evaluation.reload_required,
        "aggregate_drift": evaluation.aggregate_drift,
        "dimension_scores": list(evaluation.dimension_scores),
        "reasons": list(evaluation.reasons),
        "state_digest": evaluation.state_digest,
        "observation_digest": evaluation.observation_digest,
        "evidence_digest": evaluation.evidence_digest,
        "evaluation_digest": evaluation.digest,
        "turn_index": evaluation.turn_index,
        "generation_before": evaluation.generation,
        "generation_after": result.successor_generation,
        "restore_packet": evaluation.restore_packet,
        "subject_digest": evaluation.subject_digest,
        "subject_epoch": evaluation.subject_epoch,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="driftguard")
    sub = parser.add_subparsers(dest="command", required=True)

    ci = sub.add_parser(
        "ci",
        help="deterministically gate candidate evaluation metrics against a baseline",
    )
    ci.add_argument("--policy", required=True)
    ci.add_argument("--baseline", required=True)
    ci.add_argument("--candidate", required=True)
    ci.add_argument("--output")
    ci.add_argument("--summary")

    digest = sub.add_parser("state-digest")
    digest.add_argument("--state", required=True)

    file_digest = sub.add_parser("file-digest")
    file_digest.add_argument("--file", required=True)

    subject_digest = sub.add_parser("subject-digest")
    subject_digest.add_argument("--subject", required=True)

    register_subject = sub.add_parser("register-subject")
    register_subject.add_argument("--subject", required=True)
    register_subject.add_argument("--db", required=True)

    transition_subject = sub.add_parser("transition-subject")
    transition_subject.add_argument("--predecessor", required=True)
    transition_subject.add_argument("--successor", required=True)
    transition_subject.add_argument("--transition", required=True)
    transition_subject.add_argument("--db", required=True)

    restore = sub.add_parser("restore-packet")
    restore.add_argument("--state", required=True)

    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--state", required=True)
    evaluate.add_argument("--evidence", required=True)
    evaluate.add_argument("--observation", required=True)
    evaluate.add_argument("--db", required=True)
    evaluate.add_argument("--session", required=True)
    evaluate.add_argument("--turn", required=True, type=int)
    evaluate.add_argument("--expected-generation", required=True, type=int)
    evaluate.add_argument("--subject")

    ack = sub.add_parser("ack-reload")
    ack.add_argument("--state", required=True)
    ack.add_argument("--ack", required=True)
    ack.add_argument("--db", required=True)
    ack.add_argument("--session", required=True)
    ack.add_argument("--expected-generation", required=True, type=int)
    ack.add_argument("--subject")

    verify = sub.add_parser("verify-recovery")
    verify.add_argument("--state", required=True)
    verify.add_argument("--db", required=True)
    verify.add_argument("--session", required=True)
    verify.add_argument("--ack-id", required=True)
    verify.add_argument("--replay-evaluation-digest", required=True)
    verify.add_argument("--expected-generation", required=True, type=int)
    verify.add_argument("--subject")

    args = parser.parse_args(argv)

    if args.command == "ci":
        result = evaluate_ci(
            policy=CiPolicy.load(args.policy),
            baseline=CiReport.load(args.baseline),
            candidate=CiReport.load(args.candidate),
        )
        payload = result.payload()
        payload["result_digest"] = result.digest
        rendered = json.dumps(payload, sort_keys=True, indent=2)
        print(rendered)
        if args.output:
            Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        if args.summary:
            Path(args.summary).write_text(
                render_markdown(result),
                encoding="utf-8",
            )
        return result.exit_code

    if args.command == "file-digest":
        print(raw_bytes_digest(Path(args.file).read_bytes()))
        return 0
    if args.command == "subject-digest":
        print(_subject(args.subject).configuration_digest)
        return 0
    if args.command == "register-subject":
        ledger = DriftLedger(args.db)
        receipt = ledger.register_subject_epoch(_subject(args.subject))
        print(
            json.dumps(
                {
                    "registration_digest": receipt.digest,
                    "subject_id": receipt.subject_id,
                    "epoch": receipt.epoch,
                    "subject_digest": receipt.subject_digest,
                },
                sort_keys=True,
                indent=2,
            )
        )
        return 0
    if args.command == "transition-subject":
        ledger = DriftLedger(args.db)
        transition = SubjectEpochTransition.from_mapping(
            _load_json(args.transition)
        )
        receipt = ledger.transition_subject_epoch(
            predecessor=_subject(args.predecessor),
            successor=_subject(args.successor),
            transition=transition,
        )
        print(
            json.dumps(
                {
                    "transition_digest": receipt.transition_digest,
                    "transition_id": receipt.transition_id,
                    "subject_id": receipt.subject_id,
                    "predecessor_epoch": receipt.predecessor_epoch,
                    "predecessor_digest": receipt.predecessor_digest,
                    "successor_epoch": receipt.successor_epoch,
                    "successor_digest": receipt.successor_digest,
                    "reason": receipt.reason,
                    "transition_claim": receipt.transition_claim,
                },
                sort_keys=True,
                indent=2,
            )
        )
        return 0

    state = _state(args.state)

    if args.command == "state-digest":
        print(state.digest)
        return 0
    if args.command == "restore-packet":
        print(DriftGuardEngine.restore_packet(state))
        return 0
    if args.command == "evaluate":
        observation_digest = raw_bytes_digest(Path(args.observation).read_bytes())
        ledger = DriftLedger(args.db)
        subject = _subject(args.subject) if args.subject else None
        result = ledger.evaluate_and_commit(
            session_id=args.session,
            state=state,
            evidence=_evidence(args.evidence),
            observation_digest=observation_digest,
            turn_index=args.turn,
            expected_generation=args.expected_generation,
            subject=subject,
        )
        print(json.dumps(_evaluation_payload(result), sort_keys=True, indent=2))
        return 0
    if args.command == "ack-reload":
        ledger = DriftLedger(args.db)
        acknowledgement = ReloadAcknowledgement.from_mapping(_load_json(args.ack))
        subject = _subject(args.subject) if args.subject else None
        result = ledger.acknowledge_reload(
            session_id=args.session,
            state=state,
            acknowledgement=acknowledgement,
            expected_generation=args.expected_generation,
            subject=subject,
        )
        print(
            json.dumps(
                {
                    "ack_id": result.ack_id,
                    "generation_after": result.successor_generation,
                    "restore_anchor_turn": result.restore_anchor_turn,
                },
                sort_keys=True,
                indent=2,
            )
        )
        return 0
    if args.command == "verify-recovery":
        ledger = DriftLedger(args.db)
        subject = _subject(args.subject) if args.subject else None
        result = ledger.verify_recovery(
            session_id=args.session,
            state=state,
            ack_id=args.ack_id,
            replay_evaluation_digest=args.replay_evaluation_digest,
            expected_generation=args.expected_generation,
            subject=subject,
        )
        verification = result.verification
        print(
            json.dumps(
                {
                    "verification_digest": verification.digest,
                    "status": verification.status.value,
                    "ack_id": verification.ack_id,
                    "acknowledged_evaluation_digest": (
                        verification.acknowledged_evaluation_digest
                    ),
                    "replay_evaluation_digest": (
                        verification.replay_evaluation_digest
                    ),
                    "state_digest": verification.state_digest,
                    "observation_digest": verification.observation_digest,
                    "evidence_digest": verification.evidence_digest,
                    "turn_index": verification.turn_index,
                    "reasons": list(verification.reasons),
                    "generation_before": verification.generation,
                    "generation_after": result.successor_generation,
                    "subject_digest": verification.subject_digest,
                    "subject_epoch": verification.subject_epoch,
                },
                sort_keys=True,
                indent=2,
            )
        )
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
