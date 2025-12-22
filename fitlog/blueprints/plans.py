from datetime import datetime
import sqlite3
from flask import (
    Blueprint, jsonify, render_template, request,
    redirect, url_for, flash, abort
)
from ..db import get_db

bp = Blueprint("plans", __name__, url_prefix="/plans")


# -------------------------------------------------------------------
#
# -------------------------------------------------------------------
@bp.post("/create")
def create_plan():
    name = (request.form.get("name") or "").strip()
    # wohin danach? (kommt als hidden "next"; sonst Startseite)
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
        # z. B. UNIQUE(name) bei aktiven Plänen
        flash("Es existiert bereits ein aktiver Plan mit diesem Namen.", "error")

    return redirect(next_url)

# -------------------------------------------------------------------
# Bearbeiten-Ansicht
# -------------------------------------------------------------------
@bp.get("/<int:plan_id>/edit")
def edit_plan(plan_id: int):
    db = get_db()
    plan = db.execute(
        "SELECT id, name FROM training_plans WHERE id = ? AND deleted_at IS NULL",
        (plan_id,),
    ).fetchone()
    if not plan:
        abort(404, "Plan nicht gefunden oder gelöscht.")

    items = db.execute(
        """
        SELECT e.id              AS exercise_id,
               e.name            AS name,
               pe.position       AS position,
               COALESCE(pe.default_sets, 3)      AS default_sets,
               COALESCE(pe.default_reps, 10)     AS default_reps,
               COALESCE(pe.default_weight_kg, 0) AS default_weight_kg,
               pe.note           AS note
        FROM plan_exercises pe
        JOIN exercises e ON e.id = pe.exercise_id
        WHERE pe.plan_id = ?
        ORDER BY COALESCE(pe.position, 9999), e.name
        """,
        (plan_id,),
    ).fetchall()

    all_exercises = db.execute("SELECT id, name FROM exercises ORDER BY name").fetchall()

    return render_template("edit.html", plan=plan, items=items, all_exercises=all_exercises)

# -------------------------------------------------------------------
# Änderungen speichern -> danach zur Startseite (/)
# -------------------------------------------------------------------
@bp.post("/<int:plan_id>/update")
def update_plan(plan_id: int):
    db = get_db()
    name = (request.form.get("plan_name") or "").strip()
    if not name:
        flash("Bitte einen Plan-Namen angeben.", "error")
        return redirect(url_for("plans.edit_plan", plan_id=plan_id))

    db.execute("UPDATE training_plans SET name = ? WHERE id = ?", (name, plan_id))

    ex_ids    = request.form.getlist("exercise_id[]", type=int)
    positions = request.form.getlist("position[]", type=int)
    sets_     = request.form.getlist("default_sets[]", type=int)
    reps_     = request.form.getlist("default_reps[]", type=int)
    weights_  = request.form.getlist("default_weight_kg[]", type=float)
    notes_    = request.form.getlist("note[]")

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
             WHERE plan_id = ? AND exercise_id = ?
            """,
            (positions[i], sets_[i], reps_[i], weights_[i], notes_[i], plan_id, ex_ids[i]),
        )

    db.commit()
    flash("Plan gespeichert.", "success")
    return redirect(url_for("index"))

# -------------------------------------------------------------------
# Übung hinzufügen (bleibt auf Edit)
# -------------------------------------------------------------------
@bp.post("/<int:plan_id>/add-exercise")
def add_exercise(plan_id: int):
    db = get_db()
    exercise_id = request.form.get("exercise_id", type=int)
    if not exercise_id:
        flash("Bitte eine Übung auswählen.", "error")
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
        flash("Diese Übung ist in diesem Plan bereits enthalten.", "error")

    return redirect(url_for("plans.edit_plan", plan_id=plan_id))

# -------------------------------------------------------------------
# Übung aus Plan entfernen (AJAX)
# -------------------------------------------------------------------
@bp.post("/<int:plan_id>/remove-exercise")
def remove_exercise(plan_id: int):
    db = get_db()
    exercise_id = request.form.get("exercise_id", type=int)
    if not exercise_id:
        return jsonify({"ok": False, "msg": "exercise_id fehlt"}), 400
    db.execute("DELETE FROM plan_exercises WHERE plan_id = ? AND exercise_id = ?", (plan_id, exercise_id))
    db.commit()
    return jsonify({"ok": True})

# -------------------------------------------------------------------
# Plan archivieren (Soft-Delete, optional genutzt)
# -------------------------------------------------------------------
@bp.post("/<int:plan_id>/delete")
def delete_plan(plan_id: int):
    db = get_db()
    plan = db.execute("SELECT id, name, deleted_at FROM training_plans WHERE id = ?", (plan_id,)).fetchone()
    if not plan:
        return jsonify({"ok": False, "msg": "Plan nicht gefunden."}), 404
    if plan["deleted_at"]:
        return jsonify({"ok": False, "msg": "Plan ist bereits archiviert."}), 409

    db.execute(
        "UPDATE training_plans SET deleted_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat(timespec="seconds"), plan_id),
    )
    db.commit()
    return jsonify({"ok": True, "msg": f"Plan „{plan['name']}“ archiviert."})
