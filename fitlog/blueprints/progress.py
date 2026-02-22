"""progress.py

Dieses Modul stellt den Trainingsfortschritt bereit.

Routen:
- Auswertungsseite /progress/
- Für einen ausgewählten Plan wird das aktuelle Gewicht pro enthaltene Übung in einem Balkendiagramm dargestellt:
    /progress/plan/<id>/png
- Für eine ausgewählte Übung kann die Entwicklung der Trainingsgewichte in einem Liniendiagramm visualisiert werden:
    /progress/exercise/<id>/png

Die Diagramme werden mit Matplotlib als PNG erstellt und im Browser angezeigt.
"""
import io
from datetime import datetime
from typing import List, Optional, Tuple
import matplotlib
# Nutzt headless Modus, um Diagramme ohne GUI als PNG zu rendern.
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from flask import Blueprint, Response, abort, render_template, request, url_for
from ..db import get_db

# Alle Endpunkte sind unter /progress/... erreichbar
progress_bp = Blueprint("progress", __name__, url_prefix="/progress")


def _fetch_plan_name(plan_id: int) -> Optional[str]:
    """Liest den Namen eines aktiven Trainingsplans aus der DB.

    plan_id -- ID des Plans
    returns -- Planname oder None, wenn nicht vorhanden bzw. gelöscht.
    """
    db = get_db()
    row = db.execute(
        "SELECT name FROM training_plans WHERE id = ? AND deleted_at IS NULL",
        (plan_id,),
    ).fetchone()
    return row["name"] if row else None


def _fetch_exercise_name(exercise_id: int) -> Optional[str]:
    """Liest den Namen einer Übung aus der DB.

    exercise_id -- ID der Übung
    returns -- Übungsname oder None, wenn nicht vorhanden
    """
    db = get_db()
    row = db.execute("SELECT name FROM exercises WHERE id = ?", (exercise_id,)).fetchone()
    return row["name"] if row else None


def _fetch_plan_exercises_with_latest_weight(plan_id: int) -> List[Tuple[str, float]]:
    """Ermittelt pro Übung eines Plans das aktuelle Gewicht für das Balkendiagramm.

    - Wenn es Trainingshistorie gibt: letztes erfasstes Gewicht aus `session_entries`
    - Fallback: `plan_exercises.default_weight_kg` für noch nie trainierte Übungen

    plan_id -- ID des Trainingsplans
    returns -- Liste von (exercise_name, latest_weight_kg)
    """
    db = get_db()

    # Reihenfolge ist erst nach Position, dann alphabetisch ohne Beachtung der Groß- und Kleinschreibung.
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

        # Letztes Gewicht dieser Übung im Plan suchen (nach Zeitstempel absteigend).
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
    """Liest den Gewichtsverlauf einer Übung aus der DB.

    Es wird pro Eintrag ein Datum (YYYY-MM-DD) und das erfasste Gewicht zurückgegeben.
    Als Datum wird der erste verfügbare Zeitstempel genutzt (created_at / ended_at / started_at).

    exercise_id -- ID der Übung
    returns     -- Liste von (YYYY-MM-DD, weight_kg)
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
    """Gibt eine Matplotlib Figure als PNG zurück.

    fig               -- Matplotlib Figure
    download_filename -- optional für Dateiname bei Download

    returns           -- Flask Response mit image/png
    """
    buf = io.BytesIO()
    fig.savefig(buf, format="png")

    # Schließen, um Speicherverbrauch bei vielen Requests zu vermeiden.
    plt.close(fig)
    buf.seek(0)

    headers = {}
    if download_filename:
        # Einfache Absicherung gegen kaputte Header durch Ersetzen von Anführungszeichen.
        safe = download_filename.replace('"', "'")
        headers["Content-Disposition"] = f'attachment; filename="{safe}"'

    return Response(buf.getvalue(), mimetype="image/png", headers=headers)


@progress_bp.get("/")
def overview():
    """Auswertungsseite: Auswahl von Diagrammtyp und Bezug. Je nach Typ entweder Plan oder Übung."""
    db = get_db()

    plans = db.execute(
        "SELECT id, name FROM training_plans WHERE deleted_at IS NULL ORDER BY name COLLATE NOCASE"
    ).fetchall()
    exercises = db.execute(
        "SELECT id, name FROM exercises ORDER BY name COLLATE NOCASE"
    ).fetchall()

    # steuert, ob ein Plan- oder Übungsdiagramm angezeigt wird.
    diagram_type = request.args.get("diagram_type", "plan")
    if diagram_type not in ("plan", "exercise"):
        diagram_type = "plan"

    selected_plan_id = request.args.get("plan_id", type=int)
    selected_exercise_id = request.args.get("exercise_id", type=int)

    image_url: Optional[str] = None
    title_suffix = ""
    selected_plan_name: Optional[str] = None
    selected_exercise_name: Optional[str] = None

    # Je nach Auswahl wird die passende Route als <img> Quelle verwendet.
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
    """Erzeugt das Balkendiagramm "aktuelles Gewicht pro Übung" für einen Plan.

    plan_id -- Primärschlüssel des darzustellenden Plans
    """
    plan_name = _fetch_plan_name(plan_id)
    if not plan_name:
        abort(404, "Plan nicht gefunden!")

    data = _fetch_plan_exercises_with_latest_weight(plan_id)
    labels = [name for name, _ in data]
    values = [val for _, val in data]

    # Größe so gewählt, dass Labels noch lesbar bleiben.
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

    # Optionaler Download durch anhängen von /png?download=1
    download = request.args.get("download", type=int) == 1
    filename = f"progress_plan_{plan_name}.png" if download else None
    return _png_response(fig, filename)


@progress_bp.get("/exercise/<int:exercise_id>/png")
def exercise_png(exercise_id: int):
    """Erzeugt das Liniendiagramm „Gewicht über Zeit“ für eine Übung.

    exercise_id -- Primärschlüssel der darzustellenden Übung
    """
    exercise_name = _fetch_exercise_name(exercise_id)
    if not exercise_name:
        abort(404, "Übung nicht gefunden!")

    history = _fetch_exercise_history(exercise_id)

    # Datumsstrings werden für die Achse in date Objekte umgewandelt.
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
