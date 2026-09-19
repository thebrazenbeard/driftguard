from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import DriftGuardEngine
from .ledger import DriftLedger
from .model import DriftEvidence, SaveState


def _load_json(path: str):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


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
        "aggregate_drift": evaluation.aggregate_drift,
        "dimension_scores": list(evaluation.dimension_scores),
        "reasons": list(evaluation.reasons),
        "state_digest": evaluation.state_digest,
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

    restore = sub.add_parser("restore-packet")
    restore.add_argument("--state", required=True)

    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--state", required=True)
    evaluate.add_argument("--evidence", required=True)
    evaluate.add_argument("--db", required=True)
    evaluate.add_argument("--session", required=True)
    evaluate.add_argument("--turn", required=True, type=int)
    evaluate.add_argument("--expected-generation", required=True, type=int)

    args = parser.parse_args(argv)
    state = _state(args.state)

    if args.command == "state-digest":
        print(state.digest)
        return 0
    if args.command == "restore-packet":
        print(DriftGuardEngine.restore_packet(state))
        return 0
    if args.command == "evaluate":
        ledger = DriftLedger(args.db)
        result = ledger.evaluate_and_commit(
            session_id=args.session,
            state=state,
            evidence=_evidence(args.evidence),
            turn_index=args.turn,
            expected_generation=args.expected_generation,
        )
        print(json.dumps(_evaluation_payload(result), sort_keys=True, indent=2))
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
