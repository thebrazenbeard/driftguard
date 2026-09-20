from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import json
import sqlite3

from .core import DriftGuardEngine, StaleGenerationError
from .model import (
    Decision,
    DriftEvidence,
    Evaluation,
    RecoveryStatus,
    RecoveryVerification,
    ReloadAcknowledgement,
    SaveState,
    SourceBinding,
    require_sha256_digest,
)


@dataclass(frozen=True)
class CommitResult:
    evaluation: Evaluation
    successor_generation: int


@dataclass(frozen=True)
class AcknowledgementResult:
    ack_id: str
    successor_generation: int
    restore_anchor_turn: int


@dataclass(frozen=True)
class EvaluationEventReceipt:
    session_id: str
    generation_before: int
    generation_after: int
    turn_index: int
    state_digest: str
    observation_digest: str | None
    evidence_digest: str
    evaluation_digest: str
    decision: Decision
    reload_required: bool
    aggregate_drift: float | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class EvaluatorAttestationEventReceipt:
    verification_digest: str
    session_id: str
    evaluation_digest: str
    request_digest: str
    response_digest: str
    policy_digest: str
    key_id: str
    key_fingerprint_sha256: str
    key_epoch: int
    algorithm: str
    signature_sha256: str
    covered_sources: tuple[SourceBinding, ...]

    def __post_init__(self) -> None:
        for value, label in (
            (self.verification_digest, "verification_digest"),
            (self.evaluation_digest, "evaluation_digest"),
            (self.request_digest, "request_digest"),
            (self.response_digest, "response_digest"),
            (self.policy_digest, "policy_digest"),
            (self.key_fingerprint_sha256, "key_fingerprint_sha256"),
            (self.signature_sha256, "signature_sha256"),
        ):
            require_sha256_digest(value, label)
        if type(self.session_id) is not str or not self.session_id.strip():
            raise ValueError("session_id must be a non-empty exact string")
        if type(self.key_id) is not str or not self.key_id.strip():
            raise ValueError("key_id must be a non-empty exact string")
        if type(self.key_epoch) is not int or isinstance(self.key_epoch, bool) or self.key_epoch < 1:
            raise ValueError("key_epoch must be a positive exact integer")
        if type(self.algorithm) is not str or not self.algorithm.strip():
            raise ValueError("algorithm must be a non-empty exact string")
        if type(self.covered_sources) is not tuple:
            raise ValueError("covered_sources must be an exact tuple")
        if any(type(item) is not SourceBinding for item in self.covered_sources):
            raise ValueError("covered_sources must contain exact SourceBinding values")
        if len(self.covered_sources) != len(set(self.covered_sources)):
            raise ValueError("covered_sources must be unique")


@dataclass(frozen=True)
class ReloadAcknowledgementEventReceipt:
    ack_id: str
    session_id: str
    generation_before: int
    generation_after: int
    evaluation_digest: str
    state_digest: str
    turn_index: int


@dataclass(frozen=True)
class RecoveryCommitResult:
    verification: RecoveryVerification
    successor_generation: int


class DriftLedger:
    def __init__(self, path: str) -> None:
        self.path = path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as db, db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    state_digest TEXT NOT NULL,
                    generation INTEGER NOT NULL CHECK (generation >= 0),
                    first_turn INTEGER NOT NULL CHECK (first_turn >= 0),
                    last_turn INTEGER NOT NULL CHECK (last_turn >= -1),
                    restore_anchor_turn INTEGER NOT NULL CHECK (restore_anchor_turn >= 0),
                    last_reload_decision_turn INTEGER NULL,
                    last_evaluation_digest TEXT NULL
                );

                CREATE TABLE IF NOT EXISTS evaluation_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    generation_before INTEGER NOT NULL,
                    generation_after INTEGER NOT NULL,
                    turn_index INTEGER NOT NULL,
                    state_digest TEXT NOT NULL,
                    observation_digest TEXT NULL,
                    evidence_digest TEXT NOT NULL,
                    evaluation_digest TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reload_required INTEGER NOT NULL DEFAULT 0,
                    aggregate_drift REAL NULL,
                    reasons TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS
                    evaluation_events_session_digest_uq
                    ON evaluation_events(session_id, evaluation_digest);

                CREATE TABLE IF NOT EXISTS evaluator_attestations (
                    verification_digest TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    evaluation_digest TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    response_digest TEXT NOT NULL,
                    policy_digest TEXT NOT NULL,
                    key_id TEXT NOT NULL,
                    key_fingerprint_sha256 TEXT NOT NULL,
                    key_epoch INTEGER NOT NULL CHECK (key_epoch >= 1),
                    algorithm TEXT NOT NULL,
                    signature_sha256 TEXT NOT NULL,
                    covered_sources_json TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS
                    evaluator_attestations_session_evaluation_uq
                    ON evaluator_attestations(session_id, evaluation_digest);

                CREATE TABLE IF NOT EXISTS reload_acknowledgements (
                    ack_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    generation_before INTEGER NOT NULL,
                    generation_after INTEGER NOT NULL,
                    evaluation_digest TEXT NOT NULL,
                    state_digest TEXT NOT NULL,
                    turn_index INTEGER NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS
                    reload_ack_session_evaluation_uq
                    ON reload_acknowledgements(session_id, evaluation_digest);
                CREATE TABLE IF NOT EXISTS recovery_verifications (
                    verification_digest TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    ack_id TEXT NOT NULL,
                    generation_before INTEGER NOT NULL,
                    generation_after INTEGER NOT NULL,
                    acknowledged_evaluation_digest TEXT NOT NULL,
                    replay_evaluation_digest TEXT NOT NULL,
                    state_digest TEXT NOT NULL,
                    observation_digest TEXT NOT NULL,
                    evidence_digest TEXT NOT NULL,
                    turn_index INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    reasons TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id),
                    FOREIGN KEY(ack_id) REFERENCES reload_acknowledgements(ack_id)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS
                    recovery_verifications_session_ack_uq
                    ON recovery_verifications(session_id, ack_id);

                CREATE UNIQUE INDEX IF NOT EXISTS
                    recovery_verifications_session_replay_uq
                    ON recovery_verifications(
                        session_id, replay_evaluation_digest
                    );
                """
            )
            self._migrate_legacy_v1(db)

    @staticmethod
    def _columns(db: sqlite3.Connection, table: str) -> set[str]:
        return {
            str(row["name"])
            for row in db.execute(f"PRAGMA table_info({table})").fetchall()
        }

    def _migrate_legacy_v1(self, db: sqlite3.Connection) -> None:
        session_columns = self._columns(db, "sessions")
        if "restore_anchor_turn" not in session_columns:
            db.execute("ALTER TABLE sessions ADD COLUMN restore_anchor_turn INTEGER")
            db.execute(
                "UPDATE sessions SET restore_anchor_turn=first_turn "
                "WHERE restore_anchor_turn IS NULL"
            )
        if "last_reload_decision_turn" not in session_columns:
            db.execute(
                "ALTER TABLE sessions ADD COLUMN last_reload_decision_turn INTEGER"
            )
            if "last_reload_turn" in session_columns:
                db.execute(
                    """
                    UPDATE sessions
                       SET last_reload_decision_turn =
                           CASE
                             WHEN last_reload_turn > first_turn
                             THEN last_reload_turn
                             ELSE NULL
                           END
                    """
                )

        event_columns = self._columns(db, "evaluation_events")
        if "observation_digest" not in event_columns:
            db.execute(
                "ALTER TABLE evaluation_events ADD COLUMN observation_digest TEXT"
            )
        if "reload_required" not in event_columns:
            db.execute(
                "ALTER TABLE evaluation_events "
                "ADD COLUMN reload_required INTEGER NOT NULL DEFAULT 0"
            )

    def evaluate_and_commit(
        self,
        *,
        session_id: str,
        state: SaveState,
        evidence: tuple[DriftEvidence, ...],
        observation_digest: str,
        turn_index: int,
        expected_generation: int,
        engine: DriftGuardEngine | None = None,
    ) -> CommitResult:
        if type(session_id) is not str or not session_id.strip():
            raise ValueError("session_id must be a non-empty exact string")
        require_sha256_digest(observation_digest, "observation digest")
        if type(expected_generation) is not int or expected_generation < 0:
            raise ValueError("expected_generation must be non-negative int")
        engine = engine or DriftGuardEngine()

        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if row is None:
                if expected_generation != 0:
                    raise StaleGenerationError(
                        "new session requires expected_generation=0"
                    )
                generation = 0
                last_turn = -1
                restore_anchor_turn = turn_index
                last_reload_decision_turn = None
                db.execute(
                    """
                    INSERT INTO sessions(
                        session_id,state_digest,generation,first_turn,last_turn,
                        restore_anchor_turn,last_reload_decision_turn
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        session_id,
                        state.digest,
                        generation,
                        turn_index,
                        last_turn,
                        restore_anchor_turn,
                        None,
                    ),
                )
            else:
                generation = int(row["generation"])
                last_turn = int(row["last_turn"])
                restore_anchor_turn = int(row["restore_anchor_turn"])
                last_reload_decision_turn = (
                    int(row["last_reload_decision_turn"])
                    if row["last_reload_decision_turn"] is not None
                    else None
                )
                if generation != expected_generation:
                    raise StaleGenerationError(
                        f"expected generation {expected_generation}, observed {generation}"
                    )
                if row["state_digest"] != state.digest:
                    raise StaleGenerationError(
                        "save-state digest changed inside an existing session"
                    )

            if turn_index <= last_turn:
                raise StaleGenerationError(
                    f"turn index must advance beyond {last_turn}"
                )

            evaluation = engine.evaluate(
                state=state,
                evidence=evidence,
                observation_digest=observation_digest,
                turn_index=turn_index,
                generation=generation,
                restore_anchor_turn=restore_anchor_turn,
                last_reload_decision_turn=last_reload_decision_turn,
            )
            successor = generation + 1
            next_reload_decision = (
                turn_index
                if evaluation.reload_required
                else last_reload_decision_turn
            )
            db.execute(
                """
                UPDATE sessions
                   SET generation=?, last_turn=?, last_reload_decision_turn=?,
                       last_evaluation_digest=?
                 WHERE session_id=? AND generation=?
                """,
                (
                    successor,
                    turn_index,
                    next_reload_decision,
                    evaluation.digest,
                    session_id,
                    generation,
                ),
            )
            if db.execute("SELECT changes()").fetchone()[0] != 1:
                raise StaleGenerationError("generation compare-and-swap failed")
            db.execute(
                """
                INSERT INTO evaluation_events(
                    session_id,generation_before,generation_after,turn_index,
                    state_digest,observation_digest,evidence_digest,
                    evaluation_digest,decision,reload_required,
                    aggregate_drift,reasons
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    session_id,
                    generation,
                    successor,
                    turn_index,
                    state.digest,
                    observation_digest,
                    evaluation.evidence_digest,
                    evaluation.digest,
                    evaluation.decision.value,
                    int(evaluation.reload_required),
                    evaluation.aggregate_drift,
                    "|".join(evaluation.reasons),
                ),
            )
            return CommitResult(
                evaluation=evaluation,
                successor_generation=successor,
            )

    def acknowledge_reload(
        self,
        *,
        session_id: str,
        state: SaveState,
        acknowledgement: ReloadAcknowledgement,
        expected_generation: int,
    ) -> AcknowledgementResult:
        if type(session_id) is not str or not session_id.strip():
            raise ValueError("session_id must be a non-empty exact string")
        if type(acknowledgement) is not ReloadAcknowledgement:
            raise ValueError("acknowledgement must be exact ReloadAcknowledgement")
        if type(expected_generation) is not int or expected_generation < 0:
            raise ValueError("expected_generation must be non-negative int")

        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if row is None:
                raise StaleGenerationError("cannot acknowledge unknown session")
            generation = int(row["generation"])
            if generation != expected_generation:
                raise StaleGenerationError(
                    f"expected generation {expected_generation}, observed {generation}"
                )
            if row["state_digest"] != state.digest:
                raise StaleGenerationError(
                    "save-state digest changed inside an existing session"
                )
            if acknowledgement.state_digest != state.digest:
                raise StaleGenerationError("acknowledgement state digest mismatch")

            event = db.execute(
                """
                SELECT * FROM evaluation_events
                 WHERE session_id=? AND evaluation_digest=?
                """,
                (session_id, acknowledgement.evaluation_digest),
            ).fetchone()
            if event is None:
                raise StaleGenerationError(
                    "acknowledgement does not bind a recorded evaluation"
                )
            if int(event["reload_required"]) != 1:
                raise StaleGenerationError(
                    "only a reload-required evaluation may be acknowledged"
                )
            if int(event["turn_index"]) != acknowledgement.turn_index:
                raise StaleGenerationError("acknowledgement turn mismatch")
            if event["state_digest"] != acknowledgement.state_digest:
                raise StaleGenerationError("acknowledgement event state mismatch")
            if acknowledgement.turn_index < int(row["restore_anchor_turn"]):
                raise StaleGenerationError(
                    "acknowledgement predates the current restore anchor"
                )
            if db.execute(
                """
                SELECT 1 FROM reload_acknowledgements
                 WHERE session_id=? AND evaluation_digest=?
                """,
                (session_id, acknowledgement.evaluation_digest),
            ).fetchone():
                raise StaleGenerationError(
                    "reload decision already acknowledged"
                )
            if db.execute(
                "SELECT 1 FROM reload_acknowledgements WHERE ack_id=?",
                (acknowledgement.ack_id,),
            ).fetchone():
                raise StaleGenerationError("acknowledgement id already consumed")

            successor = generation + 1
            db.execute(
                """
                UPDATE sessions
                   SET generation=?, restore_anchor_turn=?
                 WHERE session_id=? AND generation=?
                """,
                (
                    successor,
                    acknowledgement.turn_index,
                    session_id,
                    generation,
                ),
            )
            if db.execute("SELECT changes()").fetchone()[0] != 1:
                raise StaleGenerationError(
                    "acknowledgement generation compare-and-swap failed"
                )
            db.execute(
                """
                INSERT INTO reload_acknowledgements(
                    ack_id,session_id,generation_before,generation_after,
                    evaluation_digest,state_digest,turn_index
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    acknowledgement.ack_id,
                    session_id,
                    generation,
                    successor,
                    acknowledgement.evaluation_digest,
                    acknowledgement.state_digest,
                    acknowledgement.turn_index,
                ),
            )
            return AcknowledgementResult(
                ack_id=acknowledgement.ack_id,
                successor_generation=successor,
                restore_anchor_turn=acknowledgement.turn_index,
            )

    def evaluation_receipt(
        self,
        *,
        session_id: str,
        evaluation_digest: str,
    ) -> EvaluationEventReceipt | None:
        if type(session_id) is not str or not session_id.strip():
            raise ValueError("session_id must be a non-empty exact string")
        require_sha256_digest(evaluation_digest, "evaluation digest")
        with closing(self._connect()) as db, db:
            row = db.execute(
                """
                SELECT * FROM evaluation_events
                 WHERE session_id=? AND evaluation_digest=?
                """,
                (session_id, evaluation_digest),
            ).fetchone()
            if row is None:
                return None
            return EvaluationEventReceipt(
                session_id=str(row["session_id"]),
                generation_before=int(row["generation_before"]),
                generation_after=int(row["generation_after"]),
                turn_index=int(row["turn_index"]),
                state_digest=str(row["state_digest"]),
                observation_digest=(
                    str(row["observation_digest"])
                    if row["observation_digest"] is not None
                    else None
                ),
                evidence_digest=str(row["evidence_digest"]),
                evaluation_digest=str(row["evaluation_digest"]),
                decision=Decision(str(row["decision"])),
                reload_required=bool(row["reload_required"]),
                aggregate_drift=(
                    float(row["aggregate_drift"])
                    if row["aggregate_drift"] is not None
                    else None
                ),
                reasons=tuple(
                    item
                    for item in str(row["reasons"]).split("|")
                    if item
                ),
            )

    @staticmethod
    def _attestation_row_to_receipt(row: sqlite3.Row) -> EvaluatorAttestationEventReceipt:
        raw_sources = json.loads(str(row["covered_sources_json"]))
        if type(raw_sources) is not list:
            raise ValueError("covered_sources_json must decode to a list")
        sources = tuple(
            SourceBinding(
                ref=item.get("ref"),
                version=item.get("version"),
            )
            for item in raw_sources
            if type(item) is dict
        )
        if len(sources) != len(raw_sources):
            raise ValueError("covered_sources_json contains invalid source row")
        return EvaluatorAttestationEventReceipt(
            verification_digest=str(row["verification_digest"]),
            session_id=str(row["session_id"]),
            evaluation_digest=str(row["evaluation_digest"]),
            request_digest=str(row["request_digest"]),
            response_digest=str(row["response_digest"]),
            policy_digest=str(row["policy_digest"]),
            key_id=str(row["key_id"]),
            key_fingerprint_sha256=str(row["key_fingerprint_sha256"]),
            key_epoch=int(row["key_epoch"]),
            algorithm=str(row["algorithm"]),
            signature_sha256=str(row["signature_sha256"]),
            covered_sources=tuple(sorted(sources)),
        )

    def _record_verified_evaluator_attestation(
        self,
        *,
        evaluation_digest: str,
        verification: object,
    ) -> EvaluatorAttestationEventReceipt:
        # Deferred import avoids a module cycle. The verification type itself is
        # constructor-gated by evaluator_attestation.verify_evaluator_attestation().
        from .evaluator_attestation import EvaluatorAttestationVerification

        if type(verification) is not EvaluatorAttestationVerification:
            raise ValueError(
                "durable evaluator attestation requires verifier-created capability"
            )
        require_sha256_digest(evaluation_digest, "evaluation digest")

        event = self.evaluation_receipt(
            session_id=verification.session_id,
            evaluation_digest=evaluation_digest,
        )
        if event is None:
            raise ValueError(
                "evaluator attestation requires durable evaluation receipt"
            )
        if event.state_digest != verification.state_digest:
            raise ValueError("attestation state/evaluation mismatch")
        if event.observation_digest != verification.observation_digest:
            raise ValueError("attestation observation/evaluation mismatch")
        if event.turn_index != verification.turn_index:
            raise ValueError("attestation turn/evaluation mismatch")
        if event.generation_before != verification.generation_before:
            raise ValueError("attestation generation/evaluation mismatch")
        if event.evidence_digest != verification.evidence_digest:
            raise ValueError("attestation evidence/evaluation mismatch")

        candidate = EvaluatorAttestationEventReceipt(
            verification_digest=verification.digest,
            session_id=verification.session_id,
            evaluation_digest=evaluation_digest,
            request_digest=verification.request_digest,
            response_digest=verification.response_digest,
            policy_digest=verification.policy_digest,
            key_id=verification.key_id,
            key_fingerprint_sha256=verification.key_fingerprint_sha256,
            key_epoch=verification.key_epoch,
            algorithm=verification.algorithm.value,
            signature_sha256=verification.signature_sha256,
            covered_sources=tuple(sorted(verification.covered_sources)),
        )
        covered_json = json.dumps(
            [
                {"ref": item.ref, "version": item.version}
                for item in candidate.covered_sources
            ],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                """
                SELECT * FROM evaluator_attestations
                 WHERE session_id=? AND evaluation_digest=?
                """,
                (candidate.session_id, candidate.evaluation_digest),
            ).fetchone()
            if existing is not None:
                receipt = self._attestation_row_to_receipt(existing)
                if receipt != candidate:
                    raise ValueError(
                        "durable evaluator attestation diverges from candidate"
                    )
                return receipt

            db.execute(
                """
                INSERT INTO evaluator_attestations(
                    verification_digest,session_id,evaluation_digest,
                    request_digest,response_digest,policy_digest,key_id,
                    key_fingerprint_sha256,key_epoch,algorithm,
                    signature_sha256,covered_sources_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    candidate.verification_digest,
                    candidate.session_id,
                    candidate.evaluation_digest,
                    candidate.request_digest,
                    candidate.response_digest,
                    candidate.policy_digest,
                    candidate.key_id,
                    candidate.key_fingerprint_sha256,
                    candidate.key_epoch,
                    candidate.algorithm,
                    candidate.signature_sha256,
                    covered_json,
                ),
            )
            readback = db.execute(
                """
                SELECT * FROM evaluator_attestations
                 WHERE verification_digest=?
                """,
                (candidate.verification_digest,),
            ).fetchone()
            if readback is None:
                raise ValueError("evaluator attestation readback missing")
            receipt = self._attestation_row_to_receipt(readback)
            if receipt != candidate:
                raise ValueError(
                    "evaluator attestation readback diverges from candidate"
                )
            return receipt

    def evaluator_attestation_receipt(
        self,
        *,
        session_id: str,
        evaluation_digest: str,
    ) -> EvaluatorAttestationEventReceipt | None:
        if type(session_id) is not str or not session_id.strip():
            raise ValueError("session_id must be a non-empty exact string")
        require_sha256_digest(evaluation_digest, "evaluation digest")
        with closing(self._connect()) as db, db:
            row = db.execute(
                """
                SELECT * FROM evaluator_attestations
                 WHERE session_id=? AND evaluation_digest=?
                """,
                (session_id, evaluation_digest),
            ).fetchone()
            if row is None:
                return None
            return self._attestation_row_to_receipt(row)

    def acknowledgement_receipt(
        self,
        *,
        ack_id: str,
    ) -> ReloadAcknowledgementEventReceipt | None:
        if type(ack_id) is not str or not ack_id.strip():
            raise ValueError("ack_id must be a non-empty exact string")
        with closing(self._connect()) as db, db:
            row = db.execute(
                """
                SELECT * FROM reload_acknowledgements
                 WHERE ack_id=?
                """,
                (ack_id,),
            ).fetchone()
            if row is None:
                return None
            return ReloadAcknowledgementEventReceipt(
                ack_id=str(row["ack_id"]),
                session_id=str(row["session_id"]),
                generation_before=int(row["generation_before"]),
                generation_after=int(row["generation_after"]),
                evaluation_digest=str(row["evaluation_digest"]),
                state_digest=str(row["state_digest"]),
                turn_index=int(row["turn_index"]),
            )

    def verify_recovery(
        self,
        *,
        session_id: str,
        state: SaveState,
        ack_id: str,
        replay_evaluation_digest: str,
        expected_generation: int,
    ) -> RecoveryCommitResult:
        """Bind the first post-acknowledgement evaluation as recovery evidence.

        This proves only the observed replay status. It does not prove that the
        reload caused the observed behavior.
        """
        if type(session_id) is not str or not session_id.strip():
            raise ValueError("session_id must be a non-empty exact string")
        if type(ack_id) is not str or not ack_id.strip():
            raise ValueError("ack_id must be a non-empty exact string")
        require_sha256_digest(
            replay_evaluation_digest,
            "replay evaluation digest",
        )
        if type(expected_generation) is not int or expected_generation < 0:
            raise ValueError("expected_generation must be non-negative int")

        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM sessions WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise StaleGenerationError(
                    "cannot verify recovery for unknown session"
                )
            generation = int(row["generation"])
            if generation != expected_generation:
                raise StaleGenerationError(
                    f"expected generation {expected_generation}, observed {generation}"
                )
            if row["state_digest"] != state.digest:
                raise StaleGenerationError(
                    "save-state digest changed inside an existing session"
                )

            ack = db.execute(
                """
                SELECT * FROM reload_acknowledgements
                 WHERE session_id=? AND ack_id=?
                """,
                (session_id, ack_id),
            ).fetchone()
            if ack is None:
                raise StaleGenerationError(
                    "recovery verification requires a recorded acknowledgement"
                )
            if ack["state_digest"] != state.digest:
                raise StaleGenerationError(
                    "recovery acknowledgement state digest mismatch"
                )
            if int(ack["turn_index"]) != int(row["restore_anchor_turn"]):
                raise StaleGenerationError(
                    "recovery acknowledgement is not the current restore anchor"
                )
            if db.execute(
                """
                SELECT 1 FROM recovery_verifications
                 WHERE session_id=? AND ack_id=?
                """,
                (session_id, ack_id),
            ).fetchone():
                raise StaleGenerationError(
                    "recovery acknowledgement already verified"
                )

            replay = db.execute(
                """
                SELECT * FROM evaluation_events
                 WHERE session_id=? AND evaluation_digest=?
                """,
                (session_id, replay_evaluation_digest),
            ).fetchone()
            if replay is None:
                raise StaleGenerationError(
                    "recovery replay does not bind a recorded evaluation"
                )
            if replay["state_digest"] != state.digest:
                raise StaleGenerationError(
                    "recovery replay state digest mismatch"
                )
            if int(replay["turn_index"]) <= int(ack["turn_index"]):
                raise StaleGenerationError(
                    "recovery replay must occur after acknowledgement turn"
                )
            if int(replay["generation_before"]) != int(
                ack["generation_after"]
            ):
                raise StaleGenerationError(
                    "recovery replay must be the first ledger mutation "
                    "after acknowledgement"
                )
            if int(replay["generation_after"]) != generation:
                raise StaleGenerationError(
                    "recovery replay must be the latest committed ledger mutation"
                )
            if row["last_evaluation_digest"] != replay_evaluation_digest:
                raise StaleGenerationError(
                    "recovery replay is not the session's latest evaluation"
                )

            decision = Decision(str(replay["decision"]))
            replay_reasons = tuple(
                item
                for item in str(replay["reasons"]).split("|")
                if item
            )
            aggregate_drift = (
                float(replay["aggregate_drift"])
                if replay["aggregate_drift"] is not None
                else None
            )
            if decision is Decision.UNKNOWN or aggregate_drift is None:
                status = RecoveryStatus.UNKNOWN
                status_reason = "first_post_reload_replay_unknown"
            elif (
                "critical_dimension_breach" in replay_reasons
                or aggregate_drift >= state.policy.warn_threshold
            ):
                status = RecoveryStatus.NOT_STABLE
                status_reason = (
                    "first_post_reload_replay_behaviorally_not_stable"
                )
            else:
                status = RecoveryStatus.VERIFIED_STABLE
                status_reason = (
                    "first_post_reload_replay_behaviorally_stable"
                )

            verification = RecoveryVerification(
                ack_id=ack_id,
                acknowledged_evaluation_digest=str(
                    ack["evaluation_digest"]
                ),
                replay_evaluation_digest=replay_evaluation_digest,
                state_digest=state.digest,
                observation_digest=str(replay["observation_digest"]),
                evidence_digest=str(replay["evidence_digest"]),
                turn_index=int(replay["turn_index"]),
                status=status,
                reasons=(
                    status_reason,
                    f"replay_decision:{decision.value}",
                    *replay_reasons,
                ),
                generation=generation,
            )
            successor = generation + 1
            db.execute(
                """
                UPDATE sessions
                   SET generation=?
                 WHERE session_id=? AND generation=?
                """,
                (successor, session_id, generation),
            )
            if db.execute("SELECT changes()").fetchone()[0] != 1:
                raise StaleGenerationError(
                    "recovery generation compare-and-swap failed"
                )
            db.execute(
                """
                INSERT INTO recovery_verifications(
                    verification_digest,session_id,ack_id,
                    generation_before,generation_after,
                    acknowledged_evaluation_digest,
                    replay_evaluation_digest,state_digest,
                    observation_digest,evidence_digest,turn_index,status,reasons
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    verification.digest,
                    session_id,
                    ack_id,
                    generation,
                    successor,
                    verification.acknowledged_evaluation_digest,
                    verification.replay_evaluation_digest,
                    verification.state_digest,
                    verification.observation_digest,
                    verification.evidence_digest,
                    verification.turn_index,
                    verification.status.value,
                    "|".join(verification.reasons),
                ),
            )
            return RecoveryCommitResult(
                verification=verification,
                successor_generation=successor,
            )

    def session_row(self, session_id: str) -> dict | None:
        with closing(self._connect()) as db, db:
            row = db.execute(
                "SELECT * FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            return dict(row) if row is not None else None

    def events(self, session_id: str) -> tuple[dict, ...]:
        with closing(self._connect()) as db, db:
            rows = db.execute(
                """
                SELECT * FROM evaluation_events
                 WHERE session_id=?
                 ORDER BY event_id
                """,
                (session_id,),
            ).fetchall()
            return tuple(dict(row) for row in rows)

    def acknowledgements(self, session_id: str) -> tuple[dict, ...]:
        with closing(self._connect()) as db, db:
            rows = db.execute(
                """
                SELECT * FROM reload_acknowledgements
                 WHERE session_id=?
                 ORDER BY rowid
                """,
                (session_id,),
            ).fetchall()
            return tuple(dict(row) for row in rows)

    def recoveries(self, session_id: str) -> tuple[dict, ...]:
        with closing(self._connect()) as db, db:
            rows = db.execute(
                """
                SELECT * FROM recovery_verifications
                 WHERE session_id=?
                 ORDER BY rowid
                """,
                (session_id,),
            ).fetchall()
            return tuple(dict(row) for row in rows)
