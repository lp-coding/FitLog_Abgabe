"""sessions.py

Dieses Modul ist für das Erfassen der Trainingsdaten, sprich einer Trainingssession, zuständig.

Routen:
- Neue Session für einen Plan starten /sessions/new?plan_id=<id>
- Session erfassen (Eingabemaske) /sessions/<session_id>/record
- Session speichern und beenden /sessions/<session_id>/finish
- Session abbrechen bzw. dadurch löschen /sessions/<session_id>/abort

Hinweis:
Eine Session besteht aus einem Kopfdatensatz in `sessions` (Plan, Start bzw. Ende)
und den Übungseinträgen in `session_entries` (Sätze, Wdh., Gewicht, Notiz).
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import sqlite3
from sqlite3 import Connection

from flask import Blueprint, render_template, request, redirect, url_for, abort, flash

from ..db import get_db

# Alle Endpunkte sind unter /sessions/... erreichbar
bp = Blueprint("sessions", __name__, url_prefix="/sessions")


def _utcnow_iso() -> str:
    """Gibt einen String mit Zeitstempel im Format: 2025-12-31T14:23:07 zurück."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0, tzinfo=None)
        .isoformat(timespec="seconds")
    )


def _load_session(db: Connection, session_id: int) -> sqlite3.Row:
    """Lädt den Session Header mit Planname oder bricht mit 404 ab.

        db -- für die DB Connection
        session_id -- ID der Session

        return -- Session-Datensatz mit plan_name
    """
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


def _load_record_items(db: Connection, session_id: int) -> List[sqlite3.Row]:
    """Lädt die Zeilen für das Erfassungsformular einer Session.

        Pro Übung im Trainingsplan wird eine Zeile bereitgestellt:
        - Existiert bereits ein Eintrag in `session_entries`, werden diese Werte verwendet.
        - Sonst werden die Default-Werte aus `plan_exercises` genutzt.
        - Notiz: Session-Notiz hat Vorrang, sonst Plan-Notiz, sonst leer.

        db -- offene SQLite-Connection
        session_id -- ID der Session

        return -- Liste von Rows (exercise_id, name, sets, reps, weight_kg, note)
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
    db: Connection, plan_id: int, session_id: int
) -> None:
    """Übernimmt Gewichte aus der Session als neue Standard Gewichte des Plans.

    Für jede Übung mit einem gültigen, positiven Gewicht in dieser Session wird
    `plan_exercises.default_weight_kg` aktualisiert. Dadurch werden die nächsten
    Sessions mit aktuellen Gewichten vorbelegt.

        db -- für die DB Connection
        plan_id -- ID des Plans
        session_id -- ID der Session
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


def _upsert_entries(db: Connection, session_id: int, form: Dict[str, Any]) -> None:
    """Schreibt Session Einträge anhand der Formulardaten.

        db -- für die DB Connection
        session_id -- ID der Session
        form -- Das Formular (request.form)
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
            # Komma als Dezimaltrennzeichen zulassen
            return float(s.replace(",", "."))
        except ValueError:
            return None

    # exercise_id steuert, welche Zeilen verarbeitet werden (eine pro Übung im Formular)
    # form parameter wird WOHL NICHT BENUTZT daher : exercise_ids = [int(x) for x in form.getlist("exercise_id") if str(x).isdigit()]
    exercise_ids = [int(x) for x in request.form.getlist("exercise_id") if str(x).isdigit()]

    for ex_id in exercise_ids:
        sets_val = to_int(get(f"ex[{ex_id}][sets]"))
        reps = to_int(get(f"ex[{ex_id}][reps]"))
        weight = to_float(get(f"ex[{ex_id}][weight]"))
        note = get(f"ex[{ex_id}][note]")

        # "Übung ausgelassen": sets explizit 0 -> Eintrag entfernen (falls vorhanden).
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


def _update_plan_notes_from_form(db: Connection, plan_id: int, form: Dict[str, Any]) -> None:
    """Übernimmt Notizen aus dem Record-Formular dauerhaft in den Trainingsplan.

        db -- für die DB Connection
        plan_id -- ID des Plans
        form -- Das Formular (request.form)
    """

    def get(key: str) -> str:
        return str(form.get(key) or "").strip()

    # Vermutlich ERSETZEN DURCH : exercise_ids = [int(x) for x in form.getlist("exercise_id") if str(x).isdigit()]
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
    """Legt eine neue Session für einen Trainingsplan an und öffnet die Erfassungsmaske."""
    db = get_db()

    plan_id = request.args.get("plan_id", type=int)
    if plan_id is None:
        abort(400, description="plan_id wird benötigt.")

    # Nur aktive Pläne dürfen trainiert werden.
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
    """Zeigt die Erfassungsmaske einer Session mit den aktuellen Gewichten und Sätzen usw."""
    db = get_db()
    sess = _load_session(db, session_id)
    items = _load_record_items(db, session_id)
    return render_template("record.html", sess=sess, items=items)


@bp.post("/<int:session_id>/finish")
def finish_session(session_id: int):
    """Speichert alle Eingaben der Session und setzt `ended_at`."""
    db = get_db()
    sess = _load_session(db, session_id)

    _upsert_entries(db, session_id, request.form)
    _update_plan_notes_from_form(db, sess["plan_id"], request.form)

    # Optional: Falls die Dauer in Minuten angegeben wurde, wird ended_at = started_at + Minuten gesetzt.
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
        # KANN VERMUTLICH NOCH RAUS mit utcnow
        except Exception:
            start_dt = datetime.utcnow()
        ended_at_iso = (start_dt + timedelta(minutes=mins)).isoformat(timespec="seconds")
        db.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (ended_at_iso, session_id))
    else:
        # Wenn keine Dauer angegeben ist, endet die Session zum aktuellen Zeitpunkt.
        db.execute(
            "UPDATE sessions SET ended_at = COALESCE(ended_at, ?) WHERE id = ?",
            (_utcnow_iso(), session_id),
        )

    # Letzte Gewichte der Session als Defaults übernehmen
    _update_plan_defaults_from_session(db, sess["plan_id"], session_id)

    db.commit()
    flash("Training wurde gespeichert", "success")
    return redirect(url_for("index"))


@bp.post("/<int:session_id>/abort")
def abort_session(session_id: int):
    """Bricht die Session ab und löscht diese. Die Einträge in der DB werden per CASCADE mitgelöscht."""
    db = get_db()
    _ = _load_session(db, session_id)

    db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    db.commit()

    flash("Training abgebrochen.", "info")
    return redirect(url_for("index"))
