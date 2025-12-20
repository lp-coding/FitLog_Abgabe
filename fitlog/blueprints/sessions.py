from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import sqlite3

from flask import (
    Blueprint, current_app, render_template, request,
    redirect, url_for, abort, flash
)
bp = Blueprint("sessions", __name__, url_prefix="/sessions")


# ------------------------------
# DB Infrastruktur
# ------------------------------
def get_db() -> sqlite3.Connection:
    """Open a SQLite connection with row_factory=Row and FK enabled."""
    db_path = current_app.config.get("DATABASE")
    if not db_path:
        from pathlib import Path
        db_path = str(Path(current_app.instance_path) / "fitlog.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _utcnow_iso() -> str:
    """UTC timestamp ISO (seconds)."""
    return (
        datetime.now(timezone.utc)
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )


# ------------------------------
# Schema-Helfer (robust bei optionalen Spalten)
# ------------------------------
def _table_has_column(db: sqlite3.Connection, table: str, column: str) -> bool:
    """True, falls Tabelle 'table' eine Spalte 'column' besitzt."""
    rows = db.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"].lower() == column.lower() for r in rows)


# ------------------------------
# Loader
# ------------------------------
def _load_session(db: sqlite3.Connection, session_id: int) -> sqlite3.Row:
    """Load session header + plan name (joins training_plans)."""
    row = db.execute(
        """
        SELECT
            s.id,
            s.plan_id,
            s.started_at,
            s.ended_at,
            tp.name AS plan_name
        FROM sessions s
        JOIN training_plans tp ON tp.id = s.plan_id
        WHERE s.id = ?
        """,
        (session_id,),
    ).fetchone()
    if not row:
        abort(404)
    return row


def _load_record_items(db: sqlite3.Connection, session_id: int) -> List[sqlite3.Row]:
    """
    Prefilled inputs for record form (eine Zeile je Übung):
      - Basis: alle Übungen aus dem Plan
      - Prefill-Priorität: session_entries > plan_exercises-Defaults
      - Notiz-Fallback: session_entries.note > plan_exercises.note > ''
      - Sätze: COALESCE(se.sets, pe.default_sets, 3)
        (Spalten 'sets' / 'default_sets' sind optional und werden nur gelesen, wenn vorhanden)
    """
    has_se_sets = _table_has_column(db, "session_entries", "sets")
    has_pe_sets = _table_has_column(db, "plan_exercises", "default_sets")

    se_sets_expr = "se.sets" if has_se_sets else "NULL"
    pe_sets_expr = "pe.default_sets" if has_pe_sets else "NULL"

    sql = f"""
        SELECT
            e.id   AS exercise_id,
            e.name AS name,

            /* Sätze mit robustem Fallback auf 3 */
            COALESCE({se_sets_expr}, {pe_sets_expr}, 3) AS sets,

            COALESCE(se.reps,      pe.default_reps,       10) AS reps,
            COALESCE(se.weight_kg, pe.default_weight_kg,   0) AS weight_kg,
            COALESCE(se.note,      pe.note,               '') AS note
        FROM sessions s
        JOIN plan_exercises pe ON pe.plan_id   = s.plan_id
        JOIN exercises      e  ON e.id         = pe.exercise_id
        LEFT JOIN session_entries se
               ON se.session_id  = s.id
              AND se.exercise_id = e.id
        WHERE s.id = ?
        ORDER BY COALESCE(pe.position, 999999), e.name COLLATE NOCASE
    """
    return db.execute(sql, (session_id,)).fetchall()


def _update_plan_defaults_from_session(
    db: sqlite3.Connection,
    plan_id: int,
    session_id: int,
) -> None:
    """Update per-plan default weights from the latest session.

    Für jede Übung, die in dieser Session mit einem positiven Gewicht
    geloggt wurde, wird das entsprechende `default_weight_kg` im
    `plan_exercises`-Eintrag des zugehörigen Plans aktualisiert.

    Effekt: Beim nächsten Training werden automatisch die zuletzt
    geschafften Gewichte als Standard vorgeschlagen.
    """
    rows = db.execute(
        """
        SELECT exercise_id, weight_kg
          FROM session_entries
         WHERE session_id = ?
           AND weight_kg IS NOT NULL
        """,
        (session_id,),
    ).fetchall()

    for row in rows:
        weight = row["weight_kg"]
        ex_id = row["exercise_id"]

        # Nur sinnvolle, positive Gewichte übernehmen
        try:
            w = float(weight)
        except (TypeError, ValueError):
            continue
        if w <= 0:
            continue

        db.execute(
            """
            UPDATE plan_exercises
               SET default_weight_kg = ?
             WHERE plan_id     = ?
               AND exercise_id = ?
            """,
            (w, plan_id, ex_id),
        )

import re
from typing import Any, Dict, Optional

def _upsert_entries(db, session_id: int, form: Dict[str, Any]) -> None:
    """
    Erwartet Inputs wie: ex[<exercise_id>][weight|reps|sets|note]
    Speichert pro exercise_id genau einen Eintrag in session_entries.
    """

    def get(key: str) -> str:
        return str(form.get(key) or "").strip()

    def to_int(s: str) -> Optional[int]:
        if s == "":
            return None
        try:
            return int(s)
        except ValueError:
            return None

    def to_float(s: str) -> Optional[float]:
        if s == "":
            return None
        try:
            return float(s.replace(",", "."))
        except ValueError:
            return None

    has_se_sets = _table_has_column(db, "session_entries", "sets")

    # IDs aus hidden inputs (falls vorhanden)
    exercise_ids = [int(x) for x in request.form.getlist("exercise_id") if str(x).isdigit()]

    # Fallback: IDs aus ex[...] Keys ableiten
    if not exercise_ids:
        ids = set()
        rx = re.compile(r"^ex\[(\d+)\]\[")
        for k in form.keys():
            m = rx.match(k)
            if m:
                ids.add(int(m.group(1)))
        exercise_ids = sorted(ids)

    for ex_id in exercise_ids:
        sets_val = to_int(get(f"ex[{ex_id}][sets]"))
        reps     = to_int(get(f"ex[{ex_id}][reps]"))
        weight   = to_float(get(f"ex[{ex_id}][weight]"))
        note     = get(f"ex[{ex_id}][note]")

        # "Übung ausgelassen": wenn sets explizit 0 -> lösche ggf. bestehenden Eintrag
        if sets_val == 0:
            db.execute(
                "DELETE FROM session_entries WHERE session_id = ? AND exercise_id = ?",
                (session_id, ex_id),
            )
            continue

        if has_se_sets:
            db.execute(
                """
                INSERT INTO session_entries (session_id, exercise_id, weight_kg, reps, sets, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, exercise_id) DO UPDATE SET
                  weight_kg = excluded.weight_kg,
                  reps      = excluded.reps,
                  sets      = excluded.sets,
                  note      = excluded.note,
                  created_at= excluded.created_at
                """,
                (session_id, ex_id, weight, reps, sets_val, note, _utcnow_iso()),
            )
        else:
            db.execute(
                """
                INSERT INTO session_entries (session_id, exercise_id, weight_kg, reps, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, exercise_id) DO UPDATE SET
                  weight_kg = excluded.weight_kg,
                  reps      = excluded.reps,
                  note      = excluded.note,
                  created_at= excluded.created_at
                """,
                (session_id, ex_id, weight, reps, note, _utcnow_iso()),
            )



def _upsert_entries(db, session_id: int, form: Dict[str, Any]) -> None:
    """
    Erwartet Inputs wie: ex[<exercise_id>][weight|reps|sets|note]
    Speichert pro exercise_id genau einen Eintrag in session_entries.
    """

    def get(key: str) -> str:
        return str(form.get(key) or "").strip()

    def to_int(s: str) -> Optional[int]:
        if s == "":
            return None
        try:
            return int(s)
        except ValueError:
            return None

    def to_float(s: str) -> Optional[float]:
        if s == "":
            return None
        try:
            return float(s.replace(",", "."))
        except ValueError:
            return None

    has_se_sets = _table_has_column(db, "session_entries", "sets")

    # IDs aus hidden inputs (falls vorhanden)
    exercise_ids = [int(x) for x in request.form.getlist("exercise_id") if str(x).isdigit()]

    # Fallback: IDs aus ex[...] Keys ableiten
    if not exercise_ids:
        ids = set()
        rx = re.compile(r"^ex\[(\d+)\]\[")
        for k in form.keys():
            m = rx.match(k)
            if m:
                ids.add(int(m.group(1)))
        exercise_ids = sorted(ids)

    for ex_id in exercise_ids:
        sets_val = to_int(get(f"ex[{ex_id}][sets]"))
        reps     = to_int(get(f"ex[{ex_id}][reps]"))
        weight   = to_float(get(f"ex[{ex_id}][weight]"))
        note     = get(f"ex[{ex_id}][note]")

        # "Übung ausgelassen": wenn sets explizit 0 -> lösche ggf. bestehenden Eintrag
        if sets_val == 0:
            db.execute(
                "DELETE FROM session_entries WHERE session_id = ? AND exercise_id = ?",
                (session_id, ex_id),
            )
            continue

        if has_se_sets:
            db.execute(
                """
                INSERT INTO session_entries (session_id, exercise_id, weight_kg, reps, sets, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, exercise_id) DO UPDATE SET
                  weight_kg = excluded.weight_kg,
                  reps      = excluded.reps,
                  sets      = excluded.sets,
                  note      = excluded.note,
                  created_at= excluded.created_at
                """,
                (session_id, ex_id, weight, reps, sets_val, note, _utcnow_iso()),
            )
        else:
            db.execute(
                """
                INSERT INTO session_entries (session_id, exercise_id, weight_kg, reps, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, exercise_id) DO UPDATE SET
                  weight_kg = excluded.weight_kg,
                  reps      = excluded.reps,
                  note      = excluded.note,
                  created_at= excluded.created_at
                """,
                (session_id, ex_id, weight, reps, note, _utcnow_iso()),
            )


# ------------------------------
# Routen
# ------------------------------
@bp.get("/new")
def new_session():
    """Neue Session für einen Plan anlegen und zur Erfassungsmaske springen."""
    db = get_db()

    # plan_id aus Query-Param (?plan_id=...)
    plan_id = request.args.get("plan_id", type=int)
    if plan_id is None:
        db.close()
        abort(400, description="plan_id is required")

    # prüfen, ob Plan existiert
    plan = db.execute(
        "SELECT id, name FROM training_plans WHERE id = ? AND deleted_at IS NULL",
        (plan_id,),
    ).fetchone()

    if not plan:
        db.close()
        abort(404)

    started_at = _utcnow_iso()
    cur = db.execute(
        "INSERT INTO sessions (plan_id, started_at) VALUES (?, ?)",
        (plan_id, started_at),
    )
    session_id = cur.lastrowid
    db.commit()
    db.close()

    return redirect(url_for("sessions.record_session", session_id=session_id))



@bp.get("/<int:session_id>/record")
def record_session(session_id: int):
    """Erfassungsmaske für eine laufende Session anzeigen."""
    db = get_db()
    sess = _load_session(db, session_id)
    items = _load_record_items(db, session_id)
    db.close()
    return render_template(
        "sessions/record.html",
        session=sess,  # optional alias, falls irgendwo 'session' verwendet wird
        sess=sess,     # wichtig: so heißt es im Template
        items=items,
    )



@bp.post("/<int:session_id>/record")
def record_session_post(session_id: int):
    """Zwischenspeichern der Eingaben, Session bleibt offen."""
    db = get_db()
    _ = _load_session(db, session_id)
    _upsert_entries(db, session_id, request.form)
    db.commit()
    db.close()
    flash("Zwischenspeicherung erfolgreich", "success")
    return redirect(url_for("sessions.record_session", session_id=session_id))


@bp.post("/<int:session_id>/finish")
def finish_session(session_id: int):
    """Training speichern & beenden."""
    db = get_db()
    sess = _load_session(db, session_id)
    _upsert_entries(db, session_id, request.form)

    # Optional: Dauer in Minuten
    raw_minutes = request.form.get("duration_minutes_override")
    if not raw_minutes:
        # Alias unterstützen (z. B. neues Template-Feld 'duration_minutes')
        raw_minutes = request.form.get("duration_minutes")

    if raw_minutes:
        try:
            mins = max(0.0, float(str(raw_minutes).replace(",", ".").strip()))
        except ValueError:
            mins = 0.0
    else:
        mins = 0.0

    if mins > 0.0:
        try:
            start_dt = datetime.fromisoformat(sess["started_at"])
        except Exception:
            start_dt = datetime.utcnow()
        ended_at_iso = (start_dt + timedelta(minutes=mins)).isoformat(timespec="seconds")
        db.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (ended_at_iso, session_id))
    else:
        # klassischer „Training beenden“-Klick -> Ende jetzt, falls nicht schon gesetzt
        db.execute(
            "UPDATE sessions SET ended_at = COALESCE(ended_at, ?) WHERE id = ?",
            (_utcnow_iso(), session_id),
        )

    # Nach Abschluss der Session: Standardgewichte im Plan aktualisieren
    _update_plan_defaults_from_session(db, sess["plan_id"], session_id)

    db.commit()
    db.close()
    flash("Training wurde gespeichert", "success")
    return redirect(url_for("index"))


@bp.post("/<int:session_id>/abort")
def abort_session(session_id: int):
    """Training abbrechen – löscht Session und Einträge."""
    db = get_db()
    _ = _load_session(db, session_id)
    db.execute("DELETE FROM session_entries WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    db.commit()
    db.close()
    flash("Training abgebrochen.", "info")
    return redirect(url_for("index"))
