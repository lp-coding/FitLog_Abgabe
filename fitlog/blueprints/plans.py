"""plans.py

Dieses Modul legt alle Routen für das Verwalten von Trainingsplänen fest.

Routen:
- Plan anlegen /plans/create
- Plan bearbeiten /plans/<id>/edit
- Plan speichern /plans/<id>/update
- Übung zu Plan hinzufügen /plans/<id>/add-exercise
- Übung aus Plan löschen /plans/<id>/remove-exercise
- Plan archivieren /plans/<id>/delete
"""

import sqlite3
from sqlite3 import Connection
from datetime import datetime, timezone
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from ..db import get_db

# Alle Endpunkte sind unter /plans/... erreichbar
bp = Blueprint("plans", __name__, url_prefix="/plans")


def _utcnow_iso() -> str:
    """Gibt einen String mit Zeitstempel im Format: 2025-12-31T14:23:07 zurück."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0, tzinfo=None)
        .isoformat(timespec="seconds")
    )


def _load_active_plan(db: Connection, plan_id: int) -> sqlite3.Row:
    """Lädt einen aktiven Trainingsplan oder bricht mit HTTP 404 ab.

        db -- für die DB Connection
        plan_id -- ID des gewünschten Plans

        return -- Datensatz (id, name) des aktiven Plans
    """
    # deleted_at = NULL bedeutet, dass der Plan aktiv ist.
    plan = db.execute(
        "SELECT id, name FROM training_plans WHERE id = ? AND deleted_at IS NULL",
        (plan_id,),
    ).fetchone()
    if not plan:
        abort(404, "Plan nicht gefunden oder archiviert.")
    return plan


@bp.post("/create")
def create_plan():
    """Legt einen neuen Trainingsplan mit dem Namen aus dem Formular an."""

    name = (request.form.get("name") or "").strip()
    next_url = request.form.get("next") or url_for("index")

    if not name:
        flash("Bitte einen Namen angeben.", "error")
        return redirect(next_url)

    db = get_db()
    try:
        db.execute("INSERT INTO training_plans (name) VALUES (?)", (name,))
        db.commit()
        flash(f"Plan „{name}“ erstellt.", "success")
    except sqlite3.IntegrityError:
        # Wenn ein aktiver Plan mit diesem Namen bereits existiert.
        db.rollback()
        flash("Es existiert bereits ein aktiver Plan mit diesem Namen.", "error")

    return redirect(next_url)


@bp.get("/<int:plan_id>/edit")
def edit_plan(plan_id: int):
    """Zeigt die Bearbeitungsansicht eines Plans inklusive enthaltener Übungen."""
    db = get_db()
    plan = _load_active_plan(db, plan_id)

    items = db.execute(
        """
        SELECT
            e.id   AS exercise_id,
            e.name AS name,
            pe.position,
            COALESCE(pe.default_sets, 3)      AS default_sets,
            COALESCE(pe.default_reps, 10)     AS default_reps,
            COALESCE(pe.default_weight_kg, 0) AS default_weight_kg,
            COALESCE(pe.note, '')             AS note
        FROM plan_exercises pe
        JOIN exercises e ON e.id = pe.exercise_id
        WHERE pe.plan_id = ?
        ORDER BY COALESCE(pe.position, 999999), e.name COLLATE NOCASE
        """,
        (plan_id,),
    ).fetchall()

    # COLLATE NOCASE: Sortierung ohne Beachtung der Groß- und Kleinschreibung.
    all_exercises = db.execute(
        "SELECT id, name FROM exercises ORDER BY name COLLATE NOCASE"
    ).fetchall()

    return render_template("edit.html", plan=plan, items=items, all_exercises=all_exercises)


@bp.post("/<int:plan_id>/update")
def update_plan(plan_id: int):
    """Speichert folgende Änderungen am Plan: Name, neue Default-Werte sowie Notizen pro Übung."""
    db = get_db()
    _ = _load_active_plan(db, plan_id)

    name = (request.form.get("plan_name") or "").strip()
    if not name:
        flash("Bitte einen Plan-Namen angeben.", "error")
        return redirect(url_for("plans.edit_plan", plan_id=plan_id))

    # Mehrere Listen werden aus dem Formular geholt
    ex_ids = request.form.getlist("exercise_id[]", type=int)
    positions = request.form.getlist("position[]", type=int)
    sets_ = request.form.getlist("default_sets[]", type=int)
    reps_ = request.form.getlist("default_reps[]", type=int)
    weights_ = request.form.getlist("default_weight_kg[]", type=float)
    notes_ = request.form.getlist("note[]")

    try:
        db.execute("UPDATE training_plans SET name = ? WHERE id = ?", (name, plan_id))

        # Zur Sicherheit werden nur vollständig vorhandene Zeilen aktualisiert.
        n = min(len(ex_ids), len(positions), len(sets_), len(reps_), len(weights_), len(notes_))
        for i in range(n):
            db.execute(
                """
                UPDATE plan_exercises
                   SET position = ?,
                       default_sets = ?,
                       default_reps = ?,
                       default_weight_kg = ?,
                       note = ?
                 WHERE plan_id = ?
                   AND exercise_id = ?
                """,
                (positions[i], sets_[i], reps_[i], weights_[i], notes_[i], plan_id, ex_ids[i]),
            )

        db.commit()
        flash("Plan gespeichert.", "success")
        return redirect(url_for("index"))

    except sqlite3.IntegrityError:
        # Wenn der neue Name bereits vergeben ist.
        db.rollback()
        flash("Es existiert bereits ein aktiver Plan mit diesem Namen.", "error")
        return redirect(url_for("plans.edit_plan", plan_id=plan_id))


@bp.post("/<int:plan_id>/add-exercise")
def add_exercise(plan_id: int):
    """Fügt eine Übung zu einem Plan hinzu. Diese wird standardmäßig am Ende einsortiert."""
    db = get_db()
    _ = _load_active_plan(db, plan_id)

    exercise_id = request.form.get("exercise_id", type=int)
    if not exercise_id:
        flash("Bitte eine Übung auswählen.", "error")
        return redirect(url_for("plans.edit_plan", plan_id=plan_id))

    # Die Übung muss existieren
    exists = db.execute("SELECT 1 FROM exercises WHERE id = ?", (exercise_id,)).fetchone()
    if not exists:
        flash("Übung nicht gefunden.", "error")
        return redirect(url_for("plans.edit_plan", plan_id=plan_id))

    # Neue Übung wird hinten angehängt: max(position) + 1
    next_pos = db.execute(
        "SELECT COALESCE(MAX(position), 0) + 1 FROM plan_exercises WHERE plan_id = ?",
        (plan_id,),
    ).fetchone()[0]

    try:
        db.execute(
            "INSERT INTO plan_exercises (plan_id, exercise_id, position) VALUES (?, ?, ?)",
            (plan_id, exercise_id, next_pos),
        )
        db.commit()
        flash("Übung zum Plan hinzugefügt.", "success")
    except sqlite3.IntegrityError:
        # Wenn die exercise_id bereits als Eintrag dort existiert.
        db.rollback()
        flash("Diese Übung ist in diesem Plan bereits enthalten.", "error")

    return redirect(url_for("plans.edit_plan", plan_id=plan_id))


@bp.post("/<int:plan_id>/remove-exercise")
def remove_exercise(plan_id: int):
    """Entfernt eine Übung aus einem Plan."""
    db = get_db()

    exercise_id = request.form.get("exercise_id", type=int)
    if not exercise_id:
        return jsonify({"ok": False, "msg": "exercise_id fehlt"}), 400

    db.execute(
        "DELETE FROM plan_exercises WHERE plan_id = ? AND exercise_id = ?",
        (plan_id, exercise_id),
    )
    db.commit()

    # Als JSON, damit kein Reload der Seite nötig ist.
    return jsonify({"ok": True})


@bp.post("/<int:plan_id>/delete")
def delete_plan(plan_id: int):
    """Archiviert einen Plan, indem `deleted_at` gesetzt wird."""
    db = get_db()
    plan = db.execute(
        "SELECT id, name, deleted_at FROM training_plans WHERE id = ?",
        (plan_id,),
    ).fetchone()

    if not plan:
        return jsonify({"ok": False, "msg": "Plan nicht gefunden."}), 404
    if plan["deleted_at"]:
        return jsonify({"ok": False, "msg": "Plan ist bereits archiviert."}), 409

    # Plan bleibt erhalten, gilt aber als nicht mehr aktiv.
    db.execute(
        "UPDATE training_plans SET deleted_at = ? WHERE id = ?",
        (_utcnow_iso(), plan_id),
    )
    db.commit()

    # Antwort als JSON, damit es kein Reload gibt.
    return jsonify({"ok": True, "msg": f"Plan „{plan['name']}“ archiviert."})
