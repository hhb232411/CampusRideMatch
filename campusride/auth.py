from functools import wraps

import sqlite3

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db


bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))
        return view(**kwargs)

    return wrapped_view


@bp.route("/register", methods=("GET", "POST"))
def register():
    if g.user is not None:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        display_name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip() or None
        password = request.form.get("password", "")
        error = validate_account(username, display_name, email, password)

        if error is None:
            try:
                database = get_db()
                database.execute(
                    """
                    INSERT INTO users (username, password_hash, display_name, email, phone)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (username, generate_password_hash(password), display_name, email, phone),
                )
                database.commit()
            except sqlite3.IntegrityError:
                error = "Username or email is already registered."
            else:
                flash("Account created. You can now log in.", "success")
                return redirect(url_for("auth.login"))

        flash(error, "error")

    return render_template("auth/register.html")


def validate_account(username, display_name, email, password):
    if not 3 <= len(username) <= 30:
        return "Username must contain 3 to 30 characters."
    if not display_name or len(display_name) > 60:
        return "Display name is required and must not exceed 60 characters."
    if "@" not in email or len(email) > 120:
        return "Enter a valid email address."
    if len(password) < 8:
        return "Password must contain at least 8 characters."
    return None


@bp.route("/login", methods=("GET", "POST"))
def login():
    if g.user is not None:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Incorrect username or password.", "error")
        else:
            language = session.get("language", "en")
            session.clear()
            session["language"] = language
            session["user_id"] = user["id"]
            return redirect(url_for("index"))

    return render_template("auth/login.html")


@bp.post("/logout")
def logout():
    language = session.get("language", "en")
    session.clear()
    session["language"] = language
    return redirect(url_for("index"))


@bp.route("/profile", methods=("GET", "POST"))
@login_required
def profile():
    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip() or None

        if not display_name or len(display_name) > 60:
            flash("Display name is required and must not exceed 60 characters.", "error")
        elif "@" not in email or len(email) > 120:
            flash("Enter a valid email address.", "error")
        else:
            try:
                database = get_db()
                database.execute(
                    "UPDATE users SET display_name = ?, email = ?, phone = ? WHERE id = ?",
                    (display_name, email, phone, g.user["id"]),
                )
                database.commit()
            except sqlite3.IntegrityError:
                flash("That email address is already registered.", "error")
            else:
                flash("Profile updated.", "success")
                return redirect(url_for("auth.profile"))

    rating = get_db().execute(
        """
        SELECT ROUND(AVG(rating), 2) AS average_rating, COUNT(*) AS review_count
        FROM reviews WHERE reviewee_id = ?
        """,
        (g.user["id"],),
    ).fetchone()
    return render_template("auth/profile.html", rating=rating)
