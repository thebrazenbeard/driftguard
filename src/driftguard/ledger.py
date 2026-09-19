from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import sqlite3

from .core import DriftGuardEngine, StaleGenerationError
from .model import Decision, DriftEvidence, Evaluation, SaveState


@dataclass(frozen=True)
class CommitResult:
    evaluation: Evaluation
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
                    last_reload_turn INTEGER NOT NULL CHECK (last_reload_turn >= 0),
                    last_evaluation_digest TEXT NULL
                );

                CREATE TABLE IF NOT EXISTS evaluation_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    generation_before INTEGER NOT NULL,
                    generation_after INTEGER NOT NULL,
                    turn_index INTEGER NOT NULL,
                    state_digest TEXT NOT NULL,
                    evidence_digest TEXT NOT NULL,
                    evaluation_digest TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    aggregate_drift REAL NULL,
                    reasons TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );
                """
            )

    def evaluate_and_commit(
        self,
        *,
        session_id: str,
        state: SaveState,
        evidence: tuple[DriftEvidence, ...],
        turn_index: int,
        expected_generation: int,
        engine: DriftGuardEngine | None = None,
    ) -> CommitResult:
        if type(session_id) is not str or not session_id.strip():
            raise ValueError("session_id must be a non-empty exact string")
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
                last_turn = -1
                last_reload_turn = turn_index
                generation = 0
                db.execute(
                    """
                    INSERT INTO sessions(
                        session_id,state_digest,generation,first_turn,last_turn,
                        last_reload_turn
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (session_id, state.digest, 0, turn_index, -1, turn_index),
                )
            else:
                generation = int(row["generation"])
                last_turn = int(row["last_turn"])
                last_reload_turn = int(row["last_reload_turn"])
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
                turn_index=turn_index,
                generation=generation,
                last_reload_turn=last_reload_turn,
            )
            successor = generation + 1
            next_reload = (
                turn_index if evaluation.decision is Decision.RELOAD else last_reload_turn
            )
            db.execute(
                """
                UPDATE sessions
                   SET generation=?, last_turn=?, last_reload_turn=?,
                       last_evaluation_digest=?
                 WHERE session_id=? AND generation=?
                """,
                (
                    successor,
                    turn_index,
                    next_reload,
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
                    state_digest,evidence_digest,evaluation_digest,decision,
                    aggregate_drift,reasons
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    session_id,
                    generation,
                    successor,
                    turn_index,
                    state.digest,
                    evaluation.evidence_digest,
                    evaluation.digest,
                    evaluation.decision.value,
                    evaluation.aggregate_drift,
                    "|".join(evaluation.reasons),
                ),
            )
            return CommitResult(
                evaluation=evaluation,
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
