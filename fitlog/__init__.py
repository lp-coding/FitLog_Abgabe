from flask import Flask, render_template


def create_app():
    app = Flask(__name__)

    #auslagern
    app.config["SECRET_KEY"] = "secret_key"

    from .db import close_db, get_db
    app.teardown_appcontext(close_db)

    @app.get("/")
    def index():
        db = get_db()

        # Nur aktive Pläne anzeigen
        plans = db.execute(
            """
            SELECT id, name
            FROM training_plans
            WHERE deleted_at IS NULL
            ORDER BY name
            """
        ).fetchall()

        return render_template("index.html", plans=plans)

    from .blueprints.plans import bp as plans_bp
    app.register_blueprint(plans_bp)

    from .blueprints.sessions import bp as sessions_bp
    app.register_blueprint(sessions_bp)

    from .blueprints.progress import progress_bp
    app.register_blueprint(progress_bp)

    return app