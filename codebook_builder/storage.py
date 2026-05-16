"""SQLite storage layer for the codebook generator.

The SQLite file is intended to live on Box (or any path the API server can write
to). The API server is the sole writer; readers (Alteryx, scripts) connect via
the SQLite ODBC driver or query the file directly. Migrations are idempotent.

Typical use::

    from codebook_builder.storage import connect, run_migrations

    conn = connect("/path/to/codebook.sqlite")
    run_migrations(conn)
"""
from __future__ import annotations

import dataclasses
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"

DEFAULT_DB_PATH_ENV = "CODEBOOK_DB_PATH"


def resolve_db_path(explicit: str | os.PathLike | None = None) -> Path:
    """Resolve which SQLite file to use. Explicit arg > env var > local default."""
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get(DEFAULT_DB_PATH_ENV)
    if env:
        return Path(env).expanduser().resolve()
    return (REPO_ROOT / "codebook.sqlite").resolve()


def connect(db_path: str | os.PathLike | None = None) -> sqlite3.Connection:
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None)  # autocommit; we manage txns
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def applied_migrations(conn: sqlite3.Connection) -> set[str]:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    )
    if cur.fetchone() is None:
        return set()
    return {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}


def run_migrations(conn: sqlite3.Connection) -> list[str]:
    """Apply any migration files in db/migrations/ that haven't been applied yet.

    Returns the list of migration versions that were applied this run.

    SQLite's ``executescript`` manages its own transaction lifecycle, so we
    call it directly rather than nesting inside ``transaction()``.
    """
    applied = applied_migrations(conn)
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    newly_applied: list[str] = []
    for path in files:
        version = path.stem
        if version in applied:
            continue
        conn.executescript(path.read_text())
        newly_applied.append(version)
    return newly_applied


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[None]:
    conn.execute("BEGIN")
    try:
        yield
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


# --------------------------------------------------------------------- models


@dataclasses.dataclass
class Variable:
    variable_name: str
    label: str | None = None
    question_text: str | None = None
    variable_type: str | None = None
    domain: str | None = None
    dimension: str | None = None
    scale: str | None = None
    reverse_scored: bool = False
    derivation_logic: str | None = None
    source_instrument: str | None = None
    cours: str | None = None
    notes: str | None = None
    flag: str | None = None
    position: int | None = None
    response_options: list[tuple[float | None, str]] = dataclasses.field(default_factory=list)
    # (value_numeric, value_text) pairs; order preserved


# --------------------------------------------------------------------- writes


def upsert_survey(
    conn: sqlite3.Connection,
    *,
    survey_id: str,
    title: str,
    qualtrics_id: str | None = None,
    owner: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO surveys(survey_id, qualtrics_id, title, owner)
        VALUES (?,?,?,?)
        ON CONFLICT(survey_id) DO UPDATE SET
            title        = excluded.title,
            qualtrics_id = COALESCE(excluded.qualtrics_id, surveys.qualtrics_id),
            owner        = COALESCE(excluded.owner, surveys.owner),
            last_seen_at = datetime('now')
        """,
        (survey_id, qualtrics_id, title, owner),
    )


def upsert_instrument(
    conn: sqlite3.Connection,
    *,
    instrument_id: str,
    survey_id: str,
    name: str,
    role: str | None = None,
    language: str = "en",
) -> None:
    conn.execute(
        """
        INSERT INTO instruments(instrument_id, survey_id, name, role, language)
        VALUES (?,?,?,?,?)
        ON CONFLICT(instrument_id) DO UPDATE SET
            survey_id = excluded.survey_id,
            name      = excluded.name,
            role      = COALESCE(excluded.role, instruments.role),
            language  = COALESCE(excluded.language, instruments.language)
        """,
        (instrument_id, survey_id, name, role, language),
    )


def start_run(
    conn: sqlite3.Connection,
    *,
    survey_id: str,
    source: str,
    source_uri: str | None,
    parser_version: str,
    claude_model: str | None,
    triggered_by: str | None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO ingestion_runs(survey_id, source, source_uri, parser_version, claude_model, triggered_by)
        VALUES (?,?,?,?,?,?)
        """,
        (survey_id, source, source_uri, parser_version, claude_model, triggered_by),
    )
    return int(cur.lastrowid)


def finish_run(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    status: str,
    n_variables: int,
    notes: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE ingestion_runs
        SET   status = ?, n_variables = ?, notes = ?, finished_at = datetime('now')
        WHERE id = ?
        """,
        (status, n_variables, notes, run_id),
    )


def insert_variables(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    survey_id: str,
    instrument_id: str | None,
    variables: Sequence[Variable],
) -> int:
    inserted = 0
    for v in variables:
        cur = conn.execute(
            """
            INSERT INTO variables(
                ingestion_run_id, survey_id, instrument_id,
                variable_name, label, question_text,
                variable_type, domain, dimension, scale,
                reverse_scored, derivation_logic, source_instrument,
                cours, notes, flag, position
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id, survey_id, instrument_id,
                v.variable_name, v.label, v.question_text,
                v.variable_type, v.domain, v.dimension, v.scale,
                1 if v.reverse_scored else 0, v.derivation_logic, v.source_instrument,
                v.cours, v.notes, v.flag, v.position,
            ),
        )
        var_id = int(cur.lastrowid)
        for order_index, (value_numeric, value_text) in enumerate(v.response_options):
            conn.execute(
                """
                INSERT INTO response_options(variable_id, value_numeric, value_text, order_index)
                VALUES (?,?,?,?)
                """,
                (var_id, value_numeric, value_text, order_index),
            )
        inserted += 1
    return inserted


# --------------------------------------------------------------------- reads


def latest_helper_rows(
    conn: sqlite3.Connection,
    survey_id: str,
    *,
    legacy: bool = False,
) -> list[dict]:
    """Return the latest helper rows for a survey.

    Modern: queries ``v_helper_modern`` directly (already filters to latest run).
    Legacy: hand-rolled query — the view itself omits survey_id by design to
    keep the column shape stable for back-compat workflows.
    """
    if legacy:
        rows = conn.execute(
            """
            SELECT
                v.cours                              AS Class,
                NULL                                 AS Timestamp,
                v.dimension                          AS Dimension,
                COALESCE(v.label, v.question_text)   AS Name,
                ro.value_numeric                     AS Value_Numeric,
                ro.value_text                        AS Value_Text
            FROM       variables       v
            JOIN       v_latest_run    lr ON lr.ingestion_run_id = v.ingestion_run_id
            LEFT JOIN  response_options ro ON ro.variable_id    = v.variable_id
            WHERE      v.survey_id = ?
            ORDER      BY v.position, ro.order_index
            """,
            (survey_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM v_helper_modern WHERE SurveyID = ? ORDER BY Position, Value_Order",
            (survey_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_surveys(conn: sqlite3.Connection, q: str | None = None) -> list[dict]:
    if q:
        rows = conn.execute(
            """
            SELECT s.*,
                   (SELECT COUNT(*) FROM ingestion_runs WHERE survey_id = s.survey_id) AS n_runs
            FROM   surveys s
            WHERE  s.survey_id LIKE ? OR s.title LIKE ? OR s.qualtrics_id LIKE ?
            ORDER  BY s.last_seen_at DESC
            """,
            (f"%{q}%", f"%{q}%", f"%{q}%"),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT s.*,
                   (SELECT COUNT(*) FROM ingestion_runs WHERE survey_id = s.survey_id) AS n_runs
            FROM   surveys s
            ORDER  BY s.last_seen_at DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def get_run(conn: sqlite3.Connection, run_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM ingestion_runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def runs_for_survey(conn: sqlite3.Connection, survey_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM ingestion_runs WHERE survey_id = ? ORDER BY started_at DESC",
        (survey_id,),
    ).fetchall()
    return [dict(r) for r in rows]
