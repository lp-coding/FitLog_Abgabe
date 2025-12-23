from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import sqlite3

from flask import Blueprint, render_template, request, redirect, url_for, abort, flash

from ..db import get_db

bp = Blueprint("sessions", __name__, url_prefix="/sessions")


def _utcnow_iso() -> str:
    """UTC timestamp ISO (seconds), timezone-naiv gespeichert."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )


def _load_session(db: sqlite3.Connection, session_id: int) -> sqlite3.Row:
    """Load session header + plan name."""
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
    Eine Zeile je Übung im Plan, prefilled mit:
      - session_entries (falls vorhanden) sonst Plan-Defaults
      - Notiz wird nur angezeigt (session_entries.note > plan_exercises.note > '')
    """
    return db.execute(
        """
        SELECT
            e.id   AS exercise_id,
            e.name AS name,
            COALESCE(se.sets,      pe.default_sets,      3)  AS sets,
            COALESCE(se.reps,      pe.default_reps,      10) AS reps,
            COALESCE(se.weight_kg, pe.default_weight_kg, 0)  AS weight_kg,
            COALESCE(se.note,      pe.note,             '') AS note
        FROM sessions s
        JOIN plan_exercises pe ON pe.plan_id = s.plan_id
        JOIN exercises      e  ON e.id       = pe.exercise_id
        LEFT JOIN session_entries se
               ON se.session_id  = s.id
              AND se.exercise_id = e.id
        WHERE s.id = ?
        ORDER BY COALESCE(pe.position, 999999), e.name COLLATE NOCASE
        """,
        (session_id,),
    ).fetchall()


# ------------------------------
# Persist / Updates
# ------------------------------
def _update_plan_defaults_from_session(
    db: sqlite3.Connection, plan_id: int, session_id: int
) -> None:
    """
    Für jede Übung mit positivem Gewicht in dieser Session:
    -> plan_exercises.default_weight_kg aktualisieren.
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
        ex_id = row["exercise_id"]
        try:
            w = float(row["weight_kg"])
        except (TypeError, ValueError):
            continue
        if w <= 0:
            continue

        db.execute(
            """
            UPDATE plan_exercises
               SET default_weight_kg = ?
             WHERE plan_id = ?
               AND exercise_id = ?
            """,
            (w, plan_id, ex_id),
        )


def _upsert_entries(db: sqlite3.Connection, session_id: int, form: Dict[str, Any]) -> None:
    """
    Erwartet Inputs wie: ex[<exercise_id>][weight|reps|sets]
    IDs kommen aus hidden inputs: <input type="hidden" name="exercise_id" ...>
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

    exercise_ids = [int(x) for x in request.form.getlist("exercise_id") if str(x).isdigit()]

    for ex_id in exercise_ids:
        sets_val = to_int(get(f"ex[{ex_id}][sets]"))
        reps = to_int(get(f"ex[{ex_id}][reps]"))
        weight = to_float(get(f"ex[{ex_id}][weight]"))
        note = get(f"ex[{ex_id}][note]")

        # "Übung ausgelassen": sets explizit 0 -> Eintrag entfernen (falls vorhanden)
        if sets_val == 0:
            db.execute(
                "DELETE FROM session_entries WHERE session_id = ? AND exercise_id = ?",
                (session_id, ex_id),
            )
            continue

        db.execute(
            """
            INSERT INTO session_entries (session_id, exercise_id, weight_kg, reps, sets, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, exercise_id) DO UPDATE SET
              weight_kg  = excluded.weight_kg,
              reps       = excluded.reps,
              sets       = excluded.sets,
              note       = excluded.note,
              created_at = excluded.created_at
            """,
            (session_id, ex_id, weight, reps, sets_val, note, _utcnow_iso()),
        )


def _update_plan_notes_from_form(
    db: sqlite3.Connection, plan_id: int, form: Dict[str, Any]
) -> None:
    """Übernimmt Notizen aus dem Record-Formular dauerhaft in den Trainingsplan."""

    def get(key: str) -> str:
        return str(form.get(key) or "").strip()

    exercise_ids = [int(x) for x in request.form.getlist("exercise_id") if str(x).isdigit()]

    for ex_id in exercise_ids:
        note = get(f"ex[{ex_id}][note]")
        db.execute(
            """
            UPDATE plan_exercises
               SET note = ?
             WHERE plan_id = ?
               AND exercise_id = ?
            """,
            (note, plan_id, ex_id),
        )


# ------------------------------
# Routen
# ------------------------------
@bp.get("/new")
def new_session():
    """Neue Session für einen Plan anlegen und zur Erfassungsmaske springen."""
    db = get_db()

    plan_id = request.args.get("plan_id", type=int)
    if plan_id is None:
        abort(400, description="plan_id is required")

    plan = db.execute(
        "SELECT id FROM training_plans WHERE id = ? AND deleted_at IS NULL",
        (plan_id,),
    ).fetchone()
    if not plan:
        abort(404)

    cur = db.execute(
        "INSERT INTO sessions (plan_id, started_at) VALUES (?, ?)",
        (plan_id, _utcnow_iso()),
    )
    session_id = cur.lastrowid
    db.commit()

    return redirect(url_for("sessions.record_session", session_id=session_id))


@bp.get("/<int:session_id>/record")
def record_session(session_id: int):
    """Erfassungsmaske für eine laufende Session anzeigen."""
    db = get_db()
    sess = _load_session(db, session_id)
    items = _load_record_items(db, session_id)
    return render_template("record.html", sess=sess, items=items)


@bp.post("/<int:session_id>/finish")
def finish_session(session_id: int):
    """Training speichern & beenden."""
    db = get_db()
    sess = _load_session(db, session_id)

    _upsert_entries(db, session_id, request.form)
    _update_plan_notes_from_form(db, sess["plan_id"], request.form)

    raw_minutes = (request.form.get("duration_minutes") or "").strip()
    mins = 0.0
    if raw_minutes:
        try:
            mins = max(0.0, float(raw_minutes.replace(",", ".")))
        except ValueError:
            mins = 0.0

    if mins > 0.0:
        try:
            start_dt = datetime.fromisoformat(sess["started_at"])
        except Exception:
            start_dt = datetime.utcnow()
        ended_at_iso = (start_dt + timedelta(minutes=mins)).isoformat(timespec="seconds")
        db.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (ended_at_iso, session_id))
    else:
        db.execute(
            "UPDATE sessions SET ended_at = COALESCE(ended_at, ?) WHERE id = ?",
            (_utcnow_iso(), session_id),
        )

    _update_plan_defaults_from_session(db, sess["plan_id"], session_id)

    db.commit()
    flash("Training wurde gespeichert", "success")
    return redirect(url_for("index"))


@bp.post("/<int:session_id>/abort")
def abort_session(session_id: int):
    """Training abbrechen – löscht Session (Entries werden per CASCADE gelöscht)."""
    db = get_db()
    _ = _load_session(db, session_id)

    db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    db.commit()

    flash("Training abgebrochen.", "info")
    return redirect(url_for("index"))
