# fitlog/routes/progress.py
from __future__ import annotations

import io
from typing import List, Tuple, Optional
from datetime import datetime

from flask import Blueprint, Response, render_template, request, abort, redirect, url_for

# Matplotlib im Headless-Mode
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Hole get_db aus deinem Projekt.
try:
    from fitlog.db import get_db  # bevorzugt
except Exception:
    # Fallback, falls der Pfad sich mal ändert
    from fitlog.database import get_db  # type: ignore  # noqa: F401

progress_bp = Blueprint("progress", __name__, url_prefix="/progress")


# ---------------------------
# Hilfsfunktionen (SQL, etc.)
# ---------------------------

def _fetch_plan_name(db, plan_id: int) -> Optional[str]:
    row = db.execute(
        "SELECT name FROM training_plans WHERE id = ? AND deleted_at IS NULL",
        (plan_id,),
    ).fetchone()
    return row["name"] if row else None


def _fetch_exercise_name(db, exercise_id: int) -> Optional[str]:
    row = db.execute(
        "SELECT name FROM exercises WHERE id = ?",
        (exercise_id,),
    ).fetchone()
    return row["name"] if row else None


def _fetch_plan_exercises_with_latest_weight(db, plan_id: int) -> List[Tuple[str, float]]:
    """
    Liefert Liste von (exercise_name, latest_weight_kg) für alle Übungen eines Plans.

    latest_weight_kg:
      - letztes erfasstes Gewicht aus session_entries / sessions
      - falls keine Erfassung existiert, 0.0 als Fallback.
    """
    # 1) Alle Übungen im Plan (Reihenfolge via position, falls vorhanden)
    plan_rows = db.execute(
        """
        SELECT e.id AS exercise_id, e.name AS exercise_name,
               COALESCE(pe.default_weight_kg, 0) AS default_weight_kg
        FROM plan_exercises pe
        JOIN exercises e ON e.id = pe.exercise_id
        WHERE pe.plan_id = ?
        ORDER BY COALESCE(pe.position, 999999), e.name
        """,
        (plan_id,),
    ).fetchall()

    if not plan_rows:
        return []

    # 2) Für jede Übung: letztes Gewicht aus session_entries/sessions für Sessions dieses Plans
    result: List[Tuple[str, float]] = []
    for r in plan_rows:
        ex_id = r["exercise_id"]
        ex_name = r["exercise_name"]
        default_weight = float(r["default_weight_kg"])

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

        if rec and rec["weight_kg"] is not None:
            latest = float(rec["weight_kg"])
        else:
            latest = default_weight

        result.append((ex_name, latest))

    return result


def _fetch_exercise_history(
    db,
    exercise_id: int,
    plan_id: Optional[int],
) -> List[Tuple[str, float]]:
    """
    Liefert Verlauf (ISO-Datum, Gewicht) für eine Übung.
    Optional nach Plan filterbar.
    Sortiert nach Datum/Zeit aufsteigend.
    """
    if plan_id:
        rows = db.execute(
            """
            SELECT
                DATE(COALESCE(se.created_at, s.ended_at, s.started_at)) AS day,
                se.weight_kg
            FROM session_entries se
            JOIN sessions s ON s.id = se.session_id
            WHERE se.exercise_id = ?
              AND s.plan_id = ?
            ORDER BY COALESCE(se.created_at, s.ended_at, s.started_at)
            """,
            (exercise_id, plan_id),
        ).fetchall()
    else:
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
    for row in rows:
        if row["weight_kg"] is None:
            continue
        history.append((row["day"], float(row["weight_kg"])))
    return history


# ---------------------------
# HTML-Seiten
# ---------------------------

@progress_bp.get("/")
def overview() -> Response:
    """
    Übersicht „Trainingsfortschritt“.

    Von hier aus:
      - Diagrammtyp wählen (Planübersicht oder Übungsverlauf)
      - passenden Plan bzw. Übung auswählen
      - Diagramm als PNG anzeigen lassen (in der Seite eingebettet)
    """
    db = get_db()

    plans = db.execute(
        "SELECT id, name FROM training_plans WHERE deleted_at IS NULL ORDER BY name"
    ).fetchall()
    exercises = db.execute(
        "SELECT id, name FROM exercises ORDER BY name"
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
        selected_plan_name = _fetch_plan_name(db, selected_plan_id)
        if selected_plan_name:
            image_url = url_for("progress.plan_png", plan_id=selected_plan_id)
            title_suffix = f" – {selected_plan_name}"
        else:
            selected_plan_id = None

    elif diagram_type == "exercise" and selected_exercise_id:
        selected_exercise_name = _fetch_exercise_name(db, selected_exercise_id)
        if selected_exercise_name:
            image_url = url_for("progress.exercise_png", exercise_id=selected_exercise_id)
            title_suffix = f" – {selected_exercise_name}"
        else:
            selected_exercise_id = None

    return render_template(
        "progress_plan.html",  # gemeinsames Template für beide Diagrammtypen
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


@progress_bp.get("/plan/<int:plan_id>")
def plan_view(plan_id: int) -> Response:
    """
    Kompatibilitäts-Endpoint: vorbefüllte Plan-Ansicht.
    Leitet intern auf die Übersichtsseite mit gesetztem diagram_type=plan weiter.
    """
    db = get_db()
    plan_name = _fetch_plan_name(db, plan_id)
    if not plan_name:
        abort(404, "Plan not found")

    return redirect(
        url_for("progress.overview", diagram_type="plan", plan_id=plan_id)
    )


@progress_bp.get("/exercise/<int:exercise_id>")
def exercise_view(exercise_id: int) -> Response:
    """
    Kompatibilitäts-Endpoint: vorbefüllte Übungsansicht.
    Leitet intern auf die Übersichtsseite mit gesetztem diagram_type=exercise weiter.
    Optionaler plan_id-Filter bleibt als Query-Parameter erhalten.
    """
    db = get_db()
    exercise_name = _fetch_exercise_name(db, exercise_id)
    if not exercise_name:
        abort(404, "Exercise not found")

    plan_id = request.args.get("plan_id", type=int)
    return redirect(
        url_for(
            "progress.overview",
            diagram_type="exercise",
            exercise_id=exercise_id,
            plan_id=plan_id,
        )
    )


# ---------------------------
# PNG-Endpoints
# ---------------------------

@progress_bp.get("/plan/<int:plan_id>/png")
def plan_png(plan_id: int):
    """
    PNG für einen Plan zeichnen.
    Balkendiagramm: aktuelles (zuletzt erfasstes) Gewicht je Übung im Plan.
    Optional: ?download=1 setzt Attachment-Header.
    """
    db = get_db()
    plan_name = _fetch_plan_name(db, plan_id)
    if not plan_name:
        abort(404, "Plan not found")

    data = _fetch_plan_exercises_with_latest_weight(db, plan_id)
    labels = [name for name, _ in data]
    values = [val for _, val in data]

    fig, ax = plt.subplots(figsize=(7.5, 3.8), dpi=140)
    ax.bar(labels, values)
    ax.set_title(f"Current weights per exercise – {plan_name}")
    ax.set_ylabel("Weight (kg)")
    ax.set_xlabel("Exercise")
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    plt.setp(ax.get_xticklabels(), rotation=18, ha="right")
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)

    download = request.args.get("download", type=int) == 1
    headers = {}
    if download:
        safe_name = plan_name.replace('"', "'")
        headers["Content-Disposition"] = f'attachment; filename="progress_plan_{safe_name}.png"'

    return Response(buf.getvalue(), mimetype="image/png", headers=headers)


@progress_bp.get("/exercise/<int:exercise_id>/png")
def exercise_png(exercise_id: int):
    """
    PNG für eine Übung zeichnen.
    Liniendiagramm: Gewicht über die Zeit.
    Optional: ?plan_id=... zum Filtern, ?download=1 für Attachment-Header.
    """
    plan_id = request.args.get("plan_id", type=int)

    db = get_db()
    exercise_name = _fetch_exercise_name(db, exercise_id)
    if not exercise_name:
        abort(404, "Exercise not found")

    history = _fetch_exercise_history(db, exercise_id, plan_id)
    dates = [datetime.strptime(day, "%Y-%m-%d").date() for day, _ in history]
    weights = [w for _, w in history]

    fig, ax = plt.subplots(figsize=(7.5, 3.2), dpi=140)

    if weights:
        # Linie mit Markern, x-Achse = Datum, y-Achse = Gewicht
        ax.plot(dates, weights, marker="o", linewidth=2)
    else:
        ax.text(
            0.5, 0.5,
            "No data yet",
            ha="center", va="center", transform=ax.transAxes
        )

    title = f"Weight over time – {exercise_name}"
    if plan_id:
        plan_name = _fetch_plan_name(db, plan_id)
        if plan_name:
            title += f" (Plan: {plan_name})"

    ax.set_title(title)
    ax.set_ylabel("Weight (kg)")
    ax.set_xlabel("Date")
    ax.grid(True, linestyle=":", alpha=0.4)
    fig.autofmt_xdate()
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)

    download = request.args.get("download", type=int) == 1
    headers = {}
    if download:
        base = exercise_name.replace('"', "'")
        suffix = f"_plan{plan_id}" if plan_id else ""
        headers["Content-Disposition"] = f'attachment; filename=\"progress_exercise_{base}{suffix}.png\"'
    return Response(buf.getvalue(), mimetype="image/png", headers=headers)
