import os
import secrets
from pathlib import Path

from flask import Flask, abort, g, redirect, render_template, request, session

from . import auth, db, notifications, trips
from .i18n import get_language, translate


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("CAMPUSRIDE_SECRET_KEY") or _local_secret(app.instance_path),
        DATABASE=os.path.join(app.instance_path, "campusride.sqlite"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("CAMPUSRIDE_SECURE_COOKIES") == "1",
        CSRF_ENABLED=True,
    )

    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(trips.bp)
    app.register_blueprint(notifications.bp)

    @app.before_request
    def csrf_and_notification_context():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        if (request.method == "POST" and app.config.get("CSRF_ENABLED", True)
                and not app.config.get("TESTING", False)):
            submitted = request.form.get("csrf_token", "")
            if not secrets.compare_digest(submitted, session["csrf_token"]):
                abort(400, description="Invalid CSRF token.")
        g.unread_notification_count = 0
        if g.get("user") is not None:
            g.unread_notification_count = db.get_db().execute(
                "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_at IS NULL",
                (g.user["id"],),
            ).fetchone()[0]

    @app.context_processor
    def inject_language_helpers():
        return {"_": translate, "current_language": get_language(),
                "csrf_token": lambda: session["csrf_token"]}

    @app.post("/language/<language>")
    def set_language(language):
        if language in ("en", "zh"):
            session["language"] = language
        destination = request.form.get("next", "/")
        if not destination.startswith("/") or destination.startswith("//"):
            destination = "/"
        return redirect(destination)

    @app.route("/")
    def index():
        statistics = db.get_db().execute(
            """
            SELECT
                (SELECT COUNT(*) FROM trips) AS trip_count,
                (SELECT COUNT(*) FROM trips WHERE status = 'Completed') AS completed_count,
                (SELECT COUNT(*) FROM users) AS user_count
            """
        ).fetchone()
        return render_template("index.html", statistics=statistics)

    return app


def _local_secret(instance_path):
    """Create a private persistent development key instead of using a public default."""
    path = Path(instance_path) / ".secret_key"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    value = secrets.token_urlsafe(48)
    path.write_text(value, encoding="utf-8")
    return value
