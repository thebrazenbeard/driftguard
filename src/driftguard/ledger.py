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
    MeasurementMode,
    MonitoredSubject,
    RecoveryStatus,
    RecoveryVerification,
    ReloadAcknowledgement,
    SaveState,
    require_sha256_digest,
)
from .sequential import (
    SequentialDetectionReceipt,
    SequentialDetectorSpec,
    SequentialRegistrationReceipt,
    SequentialStatus,
    advance_cusum,
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

                CREATE TABLE IF NOT EXISTS sequential_detectors (
                    detector_id TEXT PRIMARY KEY,
                    spec_digest TEXT NOT NULL,
                    spec_json TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    state_digest TEXT NOT NULL,
                    measurement_digest TEXT NOT NULL,
                    subject_digest TEXT NOT NULL,
                    subject_epoch INTEGER NOT NULL CHECK (subject_epoch >= 0),
                    registration_digest TEXT NOT NULL,
                    registration_session_generation INTEGER NOT NULL
                        CHECK (registration_session_generation >= 0),
                    registration_event_id INTEGER NOT NULL
                        CHECK (registration_event_id >= 1),
                    registration_evaluation_digest TEXT NOT NULL,
                    expected_session_generation INTEGER NOT NULL
                        CHECK (expected_session_generation >= 0),
                    generation INTEGER NOT NULL CHECK (generation >= 0),
                    last_evaluation_event_id INTEGER NOT NULL
                        CHECK (last_evaluation_event_id >= 1),
                    last_turn INTEGER NOT NULL CHECK (last_turn >= 0),
                    observation_count INTEGER NOT NULL CHECK (observation_count >= 0),
                    consecutive_unknown INTEGER NOT NULL
                        CHECK (consecutive_unknown >= 0),
                    gap_invalid INTEGER NOT NULL DEFAULT 0,
                    cusum_values TEXT NOT NULL,
                    alarm_dimensions TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );

                CREATE TABLE IF NOT EXISTS sequential_detection_events (
                    receipt_digest TEXT PRIMARY KEY,
                    detector_id TEXT NOT NULL,
                    spec_digest TEXT NOT NULL,
                    generation_before INTEGER NOT NULL,
                    generation_after INTEGER NOT NULL,
                    evaluation_event_id INTEGER NOT NULL,
                    evaluation_digest TEXT NOT NULL,
                    turn_index INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    observation_count INTEGER NOT NULL,
                    consecutive_unknown INTEGER NOT NULL,
                    gap_invalid INTEGER NOT NULL,
                    session_generation_before INTEGER NOT NULL,
                    session_generation_after INTEGER NOT NULL,
                    turn_gap INTEGER NOT NULL,
                    dimension_scores TEXT NOT NULL,
                    cusum_values TEXT NOT NULL,
                    alarm_dimensions TEXT NOT NULL,
                    reasons TEXT NOT NULL,
                    FOREIGN KEY(detector_id) REFERENCES sequential_detectors(detector_id)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS
                    sequential_events_detector_evaluation_uq
                    ON sequential_detection_events(
                        detector_id, evaluation_event_id
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
    def _assert_subject_epoch_current(
        db: sqlite3.Connection,
        subject: MonitoredSubject,
    ) -> None:
        latest = db.execute(
            """
            SELECT MAX(epoch) AS max_epoch
              FROM subject_epochs
             WHERE subject_id=?
            """,
            (subject.subject_id,),
        ).fetchone()
        if latest is None or latest["max_epoch"] is None:
            raise StaleGenerationError(
                "monitored subject epoch is not registered"
            )
        if int(latest["max_epoch"]) != subject.epoch:
            raise StaleGenerationError(
                "monitored subject epoch has been superseded"
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
                    self._assert_subject_epoch_current(db, subject)
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
                if subject is not None:
                    self._assert_subject_epoch_current(db, subject)

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

    def register_sequential_detector(
        self,
        *,
        spec: SequentialDetectorSpec,
        state: SaveState,
        subject: MonitoredSubject,
    ) -> SequentialRegistrationReceipt:
        """Precommit a detector strictly after the current evaluation frontier."""
        if type(spec) is not SequentialDetectorSpec:
            raise ValueError("spec must be exact SequentialDetectorSpec")
        if type(state) is not SaveState:
            raise ValueError("state must be exact SaveState")
        if type(subject) is not MonitoredSubject:
            raise ValueError("subject must be exact MonitoredSubject")
        if state.measurement_mode is not MeasurementMode.CALIBRATED_QUORUM:
            raise ValueError(
                "sequential detector requires CALIBRATED_QUORUM state"
            )
        spec.validate_runtime(state=state, subject=subject)

        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._assert_subject_epoch_current(db, subject)
            session = db.execute(
                "SELECT * FROM sessions WHERE session_id=?",
                (spec.session_id,),
            ).fetchone()
            if session is None:
                raise StaleGenerationError(
                    "sequential detector requires an existing session"
                )
            if str(session["state_digest"]) != spec.state_digest:
                raise StaleGenerationError(
                    "sequential detector session state mismatch"
                )
            if session["subject_digest"] != spec.subject_digest:
                raise StaleGenerationError(
                    "sequential detector session subject mismatch"
                )
            if int(session["subject_epoch"]) != spec.subject_epoch:
                raise StaleGenerationError(
                    "sequential detector session subject epoch mismatch"
                )

            existing = db.execute(
                "SELECT * FROM sequential_detectors WHERE detector_id=?",
                (spec.detector_id,),
            ).fetchone()
            if existing is not None:
                if str(existing["spec_digest"]) != spec.digest:
                    raise StaleGenerationError(
                        "detector id is already bound to another spec"
                    )
                return SequentialRegistrationReceipt(
                    detector_id=spec.detector_id,
                    spec_digest=spec.digest,
                    session_id=spec.session_id,
                    session_generation=int(
                        existing["registration_session_generation"]
                    ),
                    anchor_event_id=int(existing["registration_event_id"]),
                    anchor_evaluation_digest=str(
                        existing["registration_evaluation_digest"]
                    ),
                    subject_digest=spec.subject_digest,
                    subject_epoch=spec.subject_epoch,
                )

            anchor = db.execute(
                """
                SELECT * FROM evaluation_events
                 WHERE session_id=?
                 ORDER BY event_id DESC
                 LIMIT 1
                """,
                (spec.session_id,),
            ).fetchone()
            if anchor is None:
                raise StaleGenerationError(
                    "sequential detector registration requires an "
                    "existing evaluation frontier"
                )
            if str(anchor["state_digest"]) != spec.state_digest:
                raise StaleGenerationError(
                    "sequential registration anchor state mismatch"
                )
            if anchor["subject_digest"] != spec.subject_digest:
                raise StaleGenerationError(
                    "sequential registration anchor subject mismatch"
                )
            if int(anchor["subject_epoch"]) != spec.subject_epoch:
                raise StaleGenerationError(
                    "sequential registration anchor subject epoch mismatch"
                )

            registration = SequentialRegistrationReceipt(
                detector_id=spec.detector_id,
                spec_digest=spec.digest,
                session_id=spec.session_id,
                session_generation=int(session["generation"]),
                anchor_event_id=int(anchor["event_id"]),
                anchor_evaluation_digest=str(anchor["evaluation_digest"]),
                subject_digest=spec.subject_digest,
                subject_epoch=spec.subject_epoch,
            )
            zero_state = tuple(
                (item.dimension_id, 0.0)
                for item in sorted(
                    spec.dimensions,
                    key=lambda row: row.dimension_id,
                )
            )
            spec_json = json.dumps(
                spec.payload(),
                sort_keys=True,
                separators=(",", ":"),
            )
            db.execute(
                """
                INSERT INTO sequential_detectors(
                    detector_id,spec_digest,spec_json,session_id,
                    state_digest,measurement_digest,subject_digest,
                    subject_epoch,registration_digest,
                    registration_session_generation,
                    registration_event_id,registration_evaluation_digest,
                    expected_session_generation,generation,
                    last_evaluation_event_id,last_turn,
                    observation_count,consecutive_unknown,gap_invalid,
                    cusum_values,alarm_dimensions
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    spec.detector_id,
                    spec.digest,
                    spec_json,
                    spec.session_id,
                    spec.state_digest,
                    spec.measurement_digest,
                    spec.subject_digest,
                    spec.subject_epoch,
                    registration.digest,
                    registration.session_generation,
                    registration.anchor_event_id,
                    registration.anchor_evaluation_digest,
                    registration.session_generation,
                    0,
                    registration.anchor_event_id,
                    int(anchor["turn_index"]),
                    0,
                    0,
                    0,
                    json.dumps(zero_state),
                    json.dumps(()),
                ),
            )
            return registration

    def advance_sequential_detector(
        self,
        *,
        spec: SequentialDetectorSpec,
        state: SaveState,
        subject: MonitoredSubject,
        evaluation_digest: str,
        expected_generation: int,
    ) -> SequentialDetectionReceipt:
        if type(spec) is not SequentialDetectorSpec:
            raise ValueError("spec must be exact SequentialDetectorSpec")
        if type(state) is not SaveState:
            raise ValueError("state must be exact SaveState")
        if type(subject) is not MonitoredSubject:
            raise ValueError("subject must be exact MonitoredSubject")
        require_sha256_digest(
            evaluation_digest,
            "sequential evaluation digest",
        )
        if (
            type(expected_generation) is not int
            or isinstance(expected_generation, bool)
            or expected_generation < 0
        ):
            raise ValueError(
                "sequential expected_generation must be non-negative int"
            )
        if state.measurement_mode is not MeasurementMode.CALIBRATED_QUORUM:
            raise ValueError(
                "sequential detector requires CALIBRATED_QUORUM state"
            )
        spec.validate_runtime(state=state, subject=subject)

        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._assert_subject_epoch_current(db, subject)
            detector = db.execute(
                "SELECT * FROM sequential_detectors WHERE detector_id=?",
                (spec.detector_id,),
            ).fetchone()
            if detector is None:
                raise StaleGenerationError(
                    "sequential detector is not registered"
                )
            if str(detector["spec_digest"]) != spec.digest:
                raise StaleGenerationError(
                    "sequential detector spec changed"
                )
            generation = int(detector["generation"])
            if generation != expected_generation:
                raise StaleGenerationError(
                    "sequential detector generation mismatch"
                )
            last_event_id = int(detector["last_evaluation_event_id"])
            event = db.execute(
                """
                SELECT * FROM evaluation_events
                 WHERE session_id=? AND event_id>?
                 ORDER BY event_id
                 LIMIT 1
                """,
                (spec.session_id, last_event_id),
            ).fetchone()
            if event is None:
                raise StaleGenerationError(
                    "sequential detector has no next evaluation event"
                )
            if str(event["evaluation_digest"]) != evaluation_digest:
                raise StaleGenerationError(
                    "sequential detector must process the exact next "
                    "evaluation event"
                )
            if str(event["state_digest"]) != spec.state_digest:
                raise StaleGenerationError(
                    "sequential evaluation state mismatch"
                )
            if event["subject_digest"] != spec.subject_digest:
                raise StaleGenerationError(
                    "sequential evaluation subject mismatch"
                )
            if int(event["subject_epoch"]) != spec.subject_epoch:
                raise StaleGenerationError(
                    "sequential evaluation subject epoch mismatch"
                )
            expected_session_generation = int(
                detector["expected_session_generation"]
            )
            session_generation_before = int(event["generation_before"])
            session_generation_after = int(event["generation_after"])
            turn_gap = int(event["turn_index"]) - int(detector["last_turn"])
            session_discontinuity = (
                session_generation_before != expected_session_generation
            )
            turn_gap_exceeded = turn_gap > spec.max_turn_gap

            behavioral = event["behavioral_decision"]
            if behavioral is None:
                raise StaleGenerationError(
                    "sequential detector requires typed strict evaluation"
                )

            previous_cusum = tuple(
                (str(item[0]), float(item[1]))
                for item in json.loads(str(detector["cusum_values"]))
            )
            prior_alarms = tuple(
                str(item)
                for item in json.loads(str(detector["alarm_dimensions"]))
            )
            scores = tuple(
                (str(item[0]), float(item[1]))
                for item in json.loads(str(event["dimension_scores"]))
            )
            observation_count = int(detector["observation_count"])
            consecutive_unknown = int(detector["consecutive_unknown"])
            gap_invalid = bool(detector["gap_invalid"])
            reasons: tuple[str, ...]

            if gap_invalid:
                status = SequentialStatus.INVALID_GAP
                updated_cusum = previous_cusum
                alarm_dimensions = prior_alarms
                reasons = ("detector_evidence_gap_invalid",)
            elif session_discontinuity or turn_gap_exceeded:
                gap_invalid = True
                status = SequentialStatus.INVALID_GAP
                updated_cusum = previous_cusum
                alarm_dimensions = prior_alarms
                continuity_reasons = []
                if session_discontinuity:
                    continuity_reasons.append(
                        "session_generation_discontinuity"
                    )
                if turn_gap_exceeded:
                    continuity_reasons.append("turn_gap_exceeded")
                reasons = tuple(continuity_reasons)
            elif Decision(str(behavioral)) is Decision.UNKNOWN:
                consecutive_unknown += 1
                updated_cusum = previous_cusum
                alarm_dimensions = prior_alarms
                if consecutive_unknown > spec.max_consecutive_unknown:
                    gap_invalid = True
                    status = SequentialStatus.INVALID_GAP
                    reasons = ("unknown_budget_exceeded",)
                elif prior_alarms:
                    status = SequentialStatus.ALARM
                    reasons = (
                        "evaluation_behavior_unknown",
                        *tuple(
                            f"cusum_alarm_latched:{dimension_id}"
                            for dimension_id in prior_alarms
                        ),
                    )
                else:
                    status = SequentialStatus.SKIPPED_UNKNOWN
                    reasons = ("evaluation_behavior_unknown",)
            else:
                consecutive_unknown = 0
                updated_cusum, alarm_dimensions = advance_cusum(
                    policies=spec.dimensions,
                    previous=previous_cusum,
                    scores=scores,
                    prior_alarms=prior_alarms,
                )
                observation_count += 1
                if alarm_dimensions:
                    status = SequentialStatus.ALARM
                    reasons = tuple(
                        f"cusum_alarm:{dimension_id}"
                        for dimension_id in alarm_dimensions
                    )
                else:
                    status = SequentialStatus.MONITORING
                    reasons = ("cusum_within_policy",)

            successor = generation + 1
            db.execute(
                """
                UPDATE sequential_detectors
                   SET generation=?, last_evaluation_event_id=?,
                       last_turn=?, observation_count=?,
                       consecutive_unknown=?,gap_invalid=?,
                       expected_session_generation=?,
                       cusum_values=?, alarm_dimensions=?
                 WHERE detector_id=? AND generation=?
                """,
                (
                    successor,
                    int(event["event_id"]),
                    int(event["turn_index"]),
                    observation_count,
                    consecutive_unknown,
                    int(gap_invalid),
                    session_generation_after,
                    json.dumps(updated_cusum),
                    json.dumps(alarm_dimensions),
                    spec.detector_id,
                    generation,
                ),
            )
            if db.execute("SELECT changes()").fetchone()[0] != 1:
                raise StaleGenerationError(
                    "sequential detector compare-and-swap failed"
                )

            receipt = SequentialDetectionReceipt(
                detector_id=spec.detector_id,
                spec_digest=spec.digest,
                session_id=spec.session_id,
                generation_before=generation,
                generation_after=successor,
                evaluation_event_id=int(event["event_id"]),
                evaluation_digest=evaluation_digest,
                turn_index=int(event["turn_index"]),
                status=status,
                observation_count=observation_count,
                consecutive_unknown=consecutive_unknown,
                gap_invalid=gap_invalid,
                session_generation_before=session_generation_before,
                session_generation_after=session_generation_after,
                turn_gap=turn_gap,
                dimension_scores=scores,
                cusum_values=updated_cusum,
                alarm_dimensions=alarm_dimensions,
                reasons=reasons,
            )
            db.execute(
                """
                INSERT INTO sequential_detection_events(
                    receipt_digest,detector_id,spec_digest,
                    generation_before,generation_after,
                    evaluation_event_id,evaluation_digest,turn_index,
                    status,observation_count,consecutive_unknown,
                    gap_invalid,session_generation_before,
                    session_generation_after,turn_gap,
                    dimension_scores,cusum_values,
                    alarm_dimensions,reasons
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    receipt.digest,
                    receipt.detector_id,
                    receipt.spec_digest,
                    receipt.generation_before,
                    receipt.generation_after,
                    receipt.evaluation_event_id,
                    receipt.evaluation_digest,
                    receipt.turn_index,
                    receipt.status.value,
                    receipt.observation_count,
                    receipt.consecutive_unknown,
                    int(receipt.gap_invalid),
                    receipt.session_generation_before,
                    receipt.session_generation_after,
                    receipt.turn_gap,
                    json.dumps(receipt.dimension_scores),
                    json.dumps(receipt.cusum_values),
                    json.dumps(receipt.alarm_dimensions),
                    "|".join(receipt.reasons),
                ),
            )
            return receipt

    def sequential_detector_row(self, detector_id: str) -> dict | None:
        if type(detector_id) is not str or not detector_id.strip():
            raise ValueError("detector_id must be a non-empty exact string")
        with closing(self._connect()) as db, db:
            row = db.execute(
                "SELECT * FROM sequential_detectors WHERE detector_id=?",
                (detector_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def sequential_events(self, detector_id: str) -> tuple[dict, ...]:
        if type(detector_id) is not str or not detector_id.strip():
            raise ValueError("detector_id must be a non-empty exact string")
        with closing(self._connect()) as db, db:
            rows = db.execute(
                """
                SELECT * FROM sequential_detection_events
                 WHERE detector_id=?
                 ORDER BY generation_before
                """,
                (detector_id,),
            ).fetchall()
            return tuple(dict(row) for row in rows)

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
            if subject is not None:
                self._assert_subject_epoch_current(db, subject)
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
            if subject is not None:
                self._assert_subject_epoch_current(db, subject)

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

    def assert_subject_current(self, subject: MonitoredSubject) -> None:
        if type(subject) is not MonitoredSubject:
            raise ValueError("subject must be exact MonitoredSubject")
        with closing(self._connect()) as db, db:
            self._assert_subject_epoch_current(db, subject)

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
