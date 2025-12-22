from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

from ..db import get_db

bp = Blueprint("plans", __name__, url_prefix="/plans")


def _utcnow_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )


def _load_active_plan(db: sqlite3.Connection, plan_id: int) -> sqlite3.Row:
    plan = db.execute(
        "SELECT id, name FROM training_plans WHERE id = ? AND deleted_at IS NULL",
        (plan_id,),
    ).fetchone()
    if not plan:
        abort(404, "Plan nicht gefunden oder archiviert.")
    return plan


@bp.post("/create")
def create_plan():
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
        db.rollback()
        flash("Es existiert bereits ein aktiver Plan mit diesem Namen.", "error")

    return redirect(next_url)


@bp.get("/<int:plan_id>/edit")
def edit_plan(plan_id: int):
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

    all_exercises = db.execute(
        "SELECT id, name FROM exercises ORDER BY name COLLATE NOCASE"
    ).fetchall()

    return render_template("edit.html", plan=plan, items=items, all_exercises=all_exercises)


@bp.post("/<int:plan_id>/update")
def update_plan(plan_id: int):
    db = get_db()
    _ = _load_active_plan(db, plan_id)

    name = (request.form.get("plan_name") or "").strip()
    if not name:
        flash("Bitte einen Plan-Namen angeben.", "error")
        return redirect(url_for("plans.edit_plan", plan_id=plan_id))

    ex_ids = request.form.getlist("exercise_id[]", type=int)
    positions = request.form.getlist("position[]", type=int)
    sets_ = request.form.getlist("default_sets[]", type=int)
    reps_ = request.form.getlist("default_reps[]", type=int)
    weights_ = request.form.getlist("default_weight_kg[]", type=float)
    notes_ = request.form.getlist("note[]")

    try:
        db.execute("UPDATE training_plans SET name = ? WHERE id = ?", (name, plan_id))

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
        db.rollback()
        flash("Es existiert bereits ein aktiver Plan mit diesem Namen.", "error")
        return redirect(url_for("plans.edit_plan", plan_id=plan_id))


@bp.post("/<int:plan_id>/add-exercise")
def add_exercise(plan_id: int):
    db = get_db()
    _ = _load_active_plan(db, plan_id)

    exercise_id = request.form.get("exercise_id", type=int)
    if not exercise_id:
        flash("Bitte eine Übung auswählen.", "error")
        return redirect(url_for("plans.edit_plan", plan_id=plan_id))

    exists = db.execute("SELECT 1 FROM exercises WHERE id = ?", (exercise_id,)).fetchone()
    if not exists:
        flash("Übung nicht gefunden.", "error")
        return redirect(url_for("plans.edit_plan", plan_id=plan_id))

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
        db.rollback()
        flash("Diese Übung ist in diesem Plan bereits enthalten.", "error")

    return redirect(url_for("plans.edit_plan", plan_id=plan_id))


@bp.post("/<int:plan_id>/remove-exercise")
def remove_exercise(plan_id: int):
    db = get_db()
    exercise_id = request.form.get("exercise_id", type=int)
    if not exercise_id:
        return jsonify({"ok": False, "msg": "exercise_id fehlt"}), 400

    db.execute(
        "DELETE FROM plan_exercises WHERE plan_id = ? AND exercise_id = ?",
        (plan_id, exercise_id),
    )
    db.commit()
    return jsonify({"ok": True})


@bp.post("/<int:plan_id>/delete")
def delete_plan(plan_id: int):
    db = get_db()
    plan = db.execute(
        "SELECT id, name, deleted_at FROM training_plans WHERE id = ?",
        (plan_id,),
    ).fetchone()

    if not plan:
        return jsonify({"ok": False, "msg": "Plan nicht gefunden."}), 404
    if plan["deleted_at"]:
        return jsonify({"ok": False, "msg": "Plan ist bereits archiviert."}), 409

    db.execute(
        "UPDATE training_plans SET deleted_at = ? WHERE id = ?",
        (_utcnow_iso(), plan_id),
    )
    db.commit()
    return jsonify({"ok": True, "msg": f"Plan „{plan['name']}“ archiviert."})
