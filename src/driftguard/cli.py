from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import DriftGuardEngine
from .ledger import DriftLedger
from .model import (
    DriftEvidence,
    ReloadAcknowledgement,
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
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="driftguard")
    sub = parser.add_subparsers(dest="command", required=True)

    digest = sub.add_parser("state-digest")
    digest.add_argument("--state", required=True)

    file_digest = sub.add_parser("file-digest")
    file_digest.add_argument("--file", required=True)

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

    ack = sub.add_parser("ack-reload")
    ack.add_argument("--state", required=True)
    ack.add_argument("--ack", required=True)
    ack.add_argument("--db", required=True)
    ack.add_argument("--session", required=True)
    ack.add_argument("--expected-generation", required=True, type=int)

    args = parser.parse_args(argv)

    if args.command == "file-digest":
        print(raw_bytes_digest(Path(args.file).read_bytes()))
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
        result = ledger.evaluate_and_commit(
            session_id=args.session,
            state=state,
            evidence=_evidence(args.evidence),
            observation_digest=observation_digest,
            turn_index=args.turn,
            expected_generation=args.expected_generation,
        )
        print(json.dumps(_evaluation_payload(result), sort_keys=True, indent=2))
        return 0
    if args.command == "ack-reload":
        ledger = DriftLedger(args.db)
        acknowledgement = ReloadAcknowledgement.from_mapping(_load_json(args.ack))
        result = ledger.acknowledge_reload(
            session_id=args.session,
            state=state,
            acknowledgement=acknowledgement,
            expected_generation=args.expected_generation,
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
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
