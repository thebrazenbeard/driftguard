from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import sqlite3

from .core import DriftGuardEngine, StaleGenerationError
from .model import (
    Decision,
    DriftEvidence,
    Evaluation,
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
