"""fitlog/__init__.py

Dieses Modul stellt die Application-Factory `create_app()` bereit.
Hier wird die Anwendung zentral erzeugt und je nach Bedarf konfiguriert.
"""

from flask import Flask, render_template


def create_app() -> Flask:
    """Erzeugt und konfiguriert die App.

        return -- konfigurierte Flask App mit registrierten Blueprints und DB (Datenbank) Teardown
    """
    app = Flask(__name__)

    # Der SECRET_KEY wird von Flask zum Signieren der Sessions verwendet.
    # Für einen echten Einsatz sollte der Wert z. B. aus einer Umgebungsvariable geladen werden.
    app.config["SECRET_KEY"] = "secret_key"

    from .db import close_db, get_db

    # Stellt sicher, dass nach jedem Request die DB-Verbindung wieder sauber geschlossen wird.
    app.teardown_appcontext(close_db)

    @app.get("/")
    def index():
        """Die Startseite zeigt eine Liste der aktuell vorhandenen Trainingspläne."""

        db = get_db()

        # Nur aktive Pläne anzeigen und diese werden alphabetisch nach `name` sortiert.
        plans = db.execute(
            """
            SELECT id, name
            FROM training_plans
            WHERE deleted_at IS NULL
            ORDER BY name
            """
        ).fetchall()

        return render_template("index.html", plans=plans)

    # Blueprints kapseln jeweils die einzelnen Funktionsbereiche (Pläne, Sessions und Auswertung)
    from .blueprints.plans import bp as plans_bp
    app.register_blueprint(plans_bp)

    from .blueprints.sessions import bp as sessions_bp
    app.register_blueprint(sessions_bp)

    from .blueprints.progress import progress_bp
    app.register_blueprint(progress_bp)

    return app