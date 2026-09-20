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
    MonitoredSubject,
    RecoveryStatus,
    RecoveryVerification,
    ReloadAcknowledgement,
    SaveState,
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
    dimension_scores: tuple[tuple[str, float], ...] = ()
    behavioral_decision: Decision | None = None
    evidence_trace: tuple[
        tuple[str, str, str, str, float, str, str], ...
    ] = ()
    subject_digest: str | None = None
    subject_epoch: int | None = None


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
                    last_evaluation_digest TEXT NULL,
                    subject_digest TEXT NULL,
                    subject_epoch INTEGER NULL
                );

                CREATE TABLE IF NOT EXISTS subject_epochs (
                    subject_id TEXT NOT NULL,
                    epoch INTEGER NOT NULL CHECK (epoch >= 0),
                    subject_digest TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    PRIMARY KEY(subject_id, epoch)
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
                    dimension_scores TEXT NULL,
                    behavioral_decision TEXT NULL,
                    evidence_trace TEXT NULL,
                    subject_digest TEXT NULL,
                    subject_epoch INTEGER NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS
                    evaluation_events_session_digest_uq
                    ON evaluation_events(session_id, evaluation_digest);

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
                    subject_digest TEXT NULL,
                    subject_epoch INTEGER NULL,
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

        if "subject_digest" not in session_columns:
            db.execute(
                "ALTER TABLE sessions ADD COLUMN subject_digest TEXT NULL"
            )
        if "subject_epoch" not in session_columns:
            db.execute(
                "ALTER TABLE sessions ADD COLUMN subject_epoch INTEGER NULL"
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
        if "dimension_scores" not in event_columns:
            db.execute(
                "ALTER TABLE evaluation_events "
                "ADD COLUMN dimension_scores TEXT NULL"
            )
        if "behavioral_decision" not in event_columns:
            db.execute(
                "ALTER TABLE evaluation_events "
                "ADD COLUMN behavioral_decision TEXT NULL"
            )
        if "evidence_trace" not in event_columns:
            db.execute(
                "ALTER TABLE evaluation_events "
                "ADD COLUMN evidence_trace TEXT NULL"
            )
        if "subject_digest" not in event_columns:
            db.execute(
                "ALTER TABLE evaluation_events "
                "ADD COLUMN subject_digest TEXT NULL"
            )
        if "subject_epoch" not in event_columns:
            db.execute(
                "ALTER TABLE evaluation_events "
                "ADD COLUMN subject_epoch INTEGER NULL"
            )

        recovery_columns = self._columns(db, "recovery_verifications")
        if "subject_digest" not in recovery_columns:
            db.execute(
                "ALTER TABLE recovery_verifications "
                "ADD COLUMN subject_digest TEXT NULL"
            )
        if "subject_epoch" not in recovery_columns:
            db.execute(
                "ALTER TABLE recovery_verifications "
                "ADD COLUMN subject_epoch INTEGER NULL"
            )

    @staticmethod
    def _subject_manifest_json(subject: MonitoredSubject) -> str:
        return json.dumps(
            {
                "subject_id": subject.subject_id,
                "epoch": subject.epoch,
                "configuration_digest": subject.configuration_digest,
                "components": [
                    item.payload()
                    for item in sorted(
                        subject.components,
                        key=lambda row: row.component_id,
                    )
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def _bind_subject_epoch(
        self,
        db: sqlite3.Connection,
        subject: MonitoredSubject,
    ) -> None:
        manifest_json = self._subject_manifest_json(subject)
        existing = db.execute(
            """
            SELECT * FROM subject_epochs
             WHERE subject_id=? AND epoch=?
            """,
            (subject.subject_id, subject.epoch),
        ).fetchone()
        if existing is not None:
            if (
                str(existing["subject_digest"]) != subject.configuration_digest
                or str(existing["manifest_json"]) != manifest_json
            ):
                raise StaleGenerationError(
                    "subject epoch cannot be rebound to a different configuration"
                )
            return

        latest = db.execute(
            """
            SELECT MAX(epoch) AS max_epoch
              FROM subject_epochs
             WHERE subject_id=?
            """,
            (subject.subject_id,),
        ).fetchone()
        if latest is not None and latest["max_epoch"] is not None:
            expected_next = int(latest["max_epoch"]) + 1
            if subject.epoch != expected_next:
                raise StaleGenerationError(
                    "new subject epoch must advance exactly one beyond "
                    f"the latest registered epoch {expected_next - 1}"
                )
        db.execute(
            """
            INSERT INTO subject_epochs(
                subject_id,epoch,subject_digest,manifest_json
            ) VALUES(?,?,?,?)
            """,
            (
                subject.subject_id,
                subject.epoch,
                subject.configuration_digest,
                manifest_json,
            ),
        )

    @staticmethod
    def _validate_subject_readback(
        row: sqlite3.Row,
        subject: MonitoredSubject | None,
    ) -> None:
        stored_digest = (
            str(row["subject_digest"])
            if row["subject_digest"] is not None
            else None
        )
        stored_epoch = (
            int(row["subject_epoch"])
            if row["subject_epoch"] is not None
            else None
        )
        if stored_digest is None:
            if subject is not None:
                raise StaleGenerationError(
                    "legacy session cannot attach monitored subject during effect readback"
                )
            return
        if subject is None:
            raise StaleGenerationError(
                "subject-bound session requires current subject readback"
            )
        if subject.configuration_digest != stored_digest:
            raise StaleGenerationError(
                "current monitored subject does not match durable session"
            )
        if subject.epoch != stored_epoch:
            raise StaleGenerationError(
                "current monitored subject epoch does not match durable session"
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
        subject: MonitoredSubject | None = None,
        engine: DriftGuardEngine | None = None,
    ) -> CommitResult:
        if type(session_id) is not str or not session_id.strip():
            raise ValueError("session_id must be a non-empty exact string")
        require_sha256_digest(observation_digest, "observation digest")
        if type(expected_generation) is not int or expected_generation < 0:
            raise ValueError("expected_generation must be non-negative int")
        if subject is not None and type(subject) is not MonitoredSubject:
            raise ValueError("subject must be exact MonitoredSubject or None")
        subject_digest = (
            subject.configuration_digest if subject is not None else None
        )
        subject_epoch = subject.epoch if subject is not None else None
        engine = engine or DriftGuardEngine()

        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if row is None:
                if subject is not None:
                    self._bind_subject_epoch(db, subject)
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
                        restore_anchor_turn,last_reload_decision_turn,
                        subject_digest,subject_epoch
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        session_id,
                        state.digest,
                        generation,
                        turn_index,
                        last_turn,
                        restore_anchor_turn,
                        None,
                        subject_digest,
                        subject_epoch,
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
                stored_subject_digest = (
                    str(row["subject_digest"])
                    if row["subject_digest"] is not None
                    else None
                )
                stored_subject_epoch = (
                    int(row["subject_epoch"])
                    if row["subject_epoch"] is not None
                    else None
                )
                if stored_subject_digest != subject_digest:
                    raise StaleGenerationError(
                        "monitored subject changed inside an existing session"
                    )
                if stored_subject_epoch != subject_epoch:
                    raise StaleGenerationError(
                        "monitored subject epoch changed inside an existing session"
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
                subject=subject,
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
                    aggregate_drift,reasons,dimension_scores,
                    behavioral_decision,evidence_trace,
                    subject_digest,subject_epoch
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    json.dumps(evaluation.dimension_scores),
                    (
                        evaluation.behavioral_decision.value
                        if evaluation.behavioral_decision is not None
                        else None
                    ),
                    (
                        json.dumps(evaluation.evidence_trace)
                        if evaluation.evidence_trace
                        else None
                    ),
                    evaluation.subject_digest,
                    evaluation.subject_epoch,
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
        subject: MonitoredSubject | None = None,
    ) -> AcknowledgementResult:
        if type(session_id) is not str or not session_id.strip():
            raise ValueError("session_id must be a non-empty exact string")
        if type(acknowledgement) is not ReloadAcknowledgement:
            raise ValueError("acknowledgement must be exact ReloadAcknowledgement")
        if type(expected_generation) is not int or expected_generation < 0:
            raise ValueError("expected_generation must be non-negative int")
        if subject is not None and type(subject) is not MonitoredSubject:
            raise ValueError("subject must be exact MonitoredSubject or None")

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
            self._validate_subject_readback(row, subject)
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
                dimension_scores=(
                    tuple(
                        (str(item[0]), float(item[1]))
                        for item in json.loads(str(row["dimension_scores"]))
                    )
                    if row["dimension_scores"] is not None
                    else ()
                ),
                behavioral_decision=(
                    Decision(str(row["behavioral_decision"]))
                    if row["behavioral_decision"] is not None
                    else None
                ),
                evidence_trace=(
                    tuple(
                        (
                            str(item[0]),
                            str(item[1]),
                            str(item[2]),
                            str(item[3]),
                            float(item[4]),
                            str(item[5]),
                            str(item[6]),
                        )
                        for item in json.loads(str(row["evidence_trace"]))
                    )
                    if row["evidence_trace"] is not None
                    else ()
                ),
                subject_digest=(
                    str(row["subject_digest"])
                    if row["subject_digest"] is not None
                    else None
                ),
                subject_epoch=(
                    int(row["subject_epoch"])
                    if row["subject_epoch"] is not None
                    else None
                ),
            )

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
        subject: MonitoredSubject | None = None,
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
        if subject is not None and type(subject) is not MonitoredSubject:
            raise ValueError("subject must be exact MonitoredSubject or None")

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
            self._validate_subject_readback(row, subject)

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
            behavioral_decision = (
                Decision(str(replay["behavioral_decision"]))
                if replay["behavioral_decision"] is not None
                else None
            )
            if behavioral_decision is not None:
                if behavioral_decision is Decision.UNKNOWN:
                    status = RecoveryStatus.UNKNOWN
                    status_reason = "first_post_reload_replay_unknown"
                elif behavioral_decision in (Decision.WARN, Decision.RELOAD):
                    status = RecoveryStatus.NOT_STABLE
                    status_reason = (
                        "first_post_reload_replay_behaviorally_not_stable"
                    )
                else:
                    status = RecoveryStatus.VERIFIED_STABLE
                    status_reason = (
                        "first_post_reload_replay_behaviorally_stable"
                    )
            elif decision is Decision.UNKNOWN or aggregate_drift is None:
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
                    *(
                        (f"behavioral_decision:{behavioral_decision.value}",)
                        if behavioral_decision is not None
                        else ()
                    ),
                    *replay_reasons,
                ),
                generation=generation,
                subject_digest=(
                    str(replay["subject_digest"])
                    if replay["subject_digest"] is not None
                    else None
                ),
                subject_epoch=(
                    int(replay["subject_epoch"])
                    if replay["subject_epoch"] is not None
                    else None
                ),
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
                    observation_digest,evidence_digest,turn_index,status,reasons,
                    subject_digest,subject_epoch
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    verification.subject_digest,
                    verification.subject_epoch,
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

    def subject_epochs(self, subject_id: str) -> tuple[dict, ...]:
        if type(subject_id) is not str or not subject_id.strip():
            raise ValueError("subject_id must be a non-empty exact string")
        with closing(self._connect()) as db, db:
            rows = db.execute(
                """
                SELECT * FROM subject_epochs
                 WHERE subject_id=?
                 ORDER BY epoch
                """,
                (subject_id,),
            ).fetchall()
            return tuple(dict(row) for row in rows)

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
