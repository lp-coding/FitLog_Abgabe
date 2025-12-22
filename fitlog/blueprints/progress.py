from __future__ import annotations

import io
from datetime import datetime
from typing import List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from flask import Blueprint, Response, abort, render_template, request, url_for

from ..db import get_db

progress_bp = Blueprint("progress", __name__, url_prefix="/progress")


def _fetch_plan_name(plan_id: int) -> Optional[str]:
    db = get_db()
    row = db.execute(
        "SELECT name FROM training_plans WHERE id = ? AND deleted_at IS NULL",
        (plan_id,),
    ).fetchone()
    return row["name"] if row else None


def _fetch_exercise_name(exercise_id: int) -> Optional[str]:
    db = get_db()
    row = db.execute("SELECT name FROM exercises WHERE id = ?", (exercise_id,)).fetchone()
    return row["name"] if row else None


def _fetch_plan_exercises_with_latest_weight(plan_id: int) -> List[Tuple[str, float]]:
    """
    Liefert Liste von (exercise_name, latest_weight_kg) für alle Übungen eines Plans.
    Fallback, wenn keine Historie: plan_exercises.default_weight_kg.
    """
    db = get_db()

    plan_rows = db.execute(
        """
        SELECT
            e.id   AS exercise_id,
            e.name AS exercise_name,
            COALESCE(pe.default_weight_kg, 0) AS default_weight_kg
        FROM plan_exercises pe
        JOIN exercises e ON e.id = pe.exercise_id
        WHERE pe.plan_id = ?
        ORDER BY COALESCE(pe.position, 999999), e.name COLLATE NOCASE
        """,
        (plan_id,),
    ).fetchall()

    result: List[Tuple[str, float]] = []
    for r in plan_rows:
        ex_id = r["exercise_id"]
        ex_name = r["exercise_name"]
        default_weight = float(r["default_weight_kg"] or 0)

        rec = db.execute(
            """
            SELECT se.weight_kg
            FROM session_entries se
            JOIN sessions s ON s.id = se.session_id
            WHERE s.plan_id = ?
              AND se.exercise_id = ?
              AND se.weight_kg IS NOT NULL
            ORDER BY COALESCE(se.created_at, s.ended_at, s.started_at) DESC
            LIMIT 1
            """,
            (plan_id, ex_id),
        ).fetchone()

        latest = float(rec["weight_kg"]) if rec and rec["weight_kg"] is not None else default_weight
        result.append((ex_name, latest))

    return result


def _fetch_exercise_history(exercise_id: int) -> List[Tuple[str, float]]:
    """
    Historie einer Übung abrufen: Liste von (YYYY-MM-DD, weight_kg).
    """
    db = get_db()
    rows = db.execute(
        """
        SELECT
            DATE(COALESCE(se.created_at, s.ended_at, s.started_at)) AS day,
            se.weight_kg
        FROM session_entries se
        JOIN sessions s ON s.id = se.session_id
        WHERE se.exercise_id = ?
        ORDER BY COALESCE(se.created_at, s.ended_at, s.started_at)
        """,
        (exercise_id,),
    ).fetchall()

    history: List[Tuple[str, float]] = []
    for r in rows:
        if r["weight_kg"] is None:
            continue
        history.append((r["day"], float(r["weight_kg"])))
    return history


def _png_response(fig, download_filename: Optional[str] = None) -> Response:
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)

    headers = {}
    if download_filename:
        safe = download_filename.replace('"', "'")
        headers["Content-Disposition"] = f'attachment; filename="{safe}"'

    return Response(buf.getvalue(), mimetype="image/png", headers=headers)


@progress_bp.get("/")
def overview() -> Response:
    db = get_db()

    plans = db.execute(
        "SELECT id, name FROM training_plans WHERE deleted_at IS NULL ORDER BY name COLLATE NOCASE"
    ).fetchall()
    exercises = db.execute(
        "SELECT id, name FROM exercises ORDER BY name COLLATE NOCASE"
    ).fetchall()

    diagram_type = request.args.get("diagram_type", "plan")
    if diagram_type not in ("plan", "exercise"):
        diagram_type = "plan"

    selected_plan_id = request.args.get("plan_id", type=int)
    selected_exercise_id = request.args.get("exercise_id", type=int)

    image_url: Optional[str] = None
    title_suffix = ""
    selected_plan_name: Optional[str] = None
    selected_exercise_name: Optional[str] = None

    if diagram_type == "plan" and selected_plan_id:
        selected_plan_name = _fetch_plan_name(selected_plan_id)
        if selected_plan_name:
            image_url = url_for("progress.plan_png", plan_id=selected_plan_id)
            title_suffix = f" – {selected_plan_name}"
        else:
            selected_plan_id = None

    if diagram_type == "exercise" and selected_exercise_id:
        selected_exercise_name = _fetch_exercise_name(selected_exercise_id)
        if selected_exercise_name:
            image_url = url_for("progress.exercise_png", exercise_id=selected_exercise_id)
            title_suffix = f" – {selected_exercise_name}"
        else:
            selected_exercise_id = None

    return render_template(
        "progress_plan.html",
        diagram_type=diagram_type,
        plans=plans,
        exercises=exercises,
        selected_plan_id=selected_plan_id,
        selected_exercise_id=selected_exercise_id,
        selected_plan_name=selected_plan_name,
        selected_exercise_name=selected_exercise_name,
        image_url=image_url,
        title_suffix=title_suffix,
    )


@progress_bp.get("/plan/<int:plan_id>/png")
def plan_png(plan_id: int):
    plan_name = _fetch_plan_name(plan_id)
    if not plan_name:
        abort(404, "Plan nicht gefunden!")

    data = _fetch_plan_exercises_with_latest_weight(plan_id)
    labels = [name for name, _ in data]
    values = [val for _, val in data]

    fig, ax = plt.subplots(figsize=(7.5, 3.8), dpi=140)

    if values:
        ax.bar(labels, values)
        plt.setp(ax.get_xticklabels(), rotation=18, ha="right")
    else:
        ax.text(0.5, 0.5, "Keine Übungen im Plan.", ha="center", va="center", transform=ax.transAxes)

    ax.set_title(f"Aktuelles Gewicht pro Übung – {plan_name}")
    ax.set_ylabel("Gewicht (kg)")
    ax.set_xlabel("Übung")
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    plt.tight_layout()

    download = request.args.get("download", type=int) == 1
    filename = f"progress_plan_{plan_name}.png" if download else None
    return _png_response(fig, filename)


@progress_bp.get("/exercise/<int:exercise_id>/png")
def exercise_png(exercise_id: int):
    exercise_name = _fetch_exercise_name(exercise_id)
    if not exercise_name:
        abort(404, "Übung nicht gefunden!")

    history = _fetch_exercise_history(exercise_id)
    dates = [datetime.strptime(day, "%Y-%m-%d").date() for day, _ in history]
    weights = [w for _, w in history]

    fig, ax = plt.subplots(figsize=(7.5, 3.2), dpi=140)

    if weights:
        ax.plot(dates, weights, marker="o", linewidth=2)
    else:
        ax.text(0.5, 0.5, "Noch keine Daten.", ha="center", va="center", transform=ax.transAxes)

    ax.set_title(f"Gewicht über Zeit – {exercise_name}")
    ax.set_ylabel("Gewicht (kg)")
    ax.set_xlabel("Datum")
    ax.grid(True, linestyle=":", alpha=0.4)
    fig.autofmt_xdate()
    plt.tight_layout()

    download = request.args.get("download", type=int) == 1
    filename = f"progress_exercise_{exercise_name}.png" if download else None
    return _png_response(fig, filename)
