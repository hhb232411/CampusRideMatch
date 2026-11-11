from flask import Blueprint, abort, flash, g, redirect, render_template, url_for

from .auth import login_required
from .db import get_db


bp = Blueprint("notifications", __name__, url_prefix="/notifications")


def create_notification(database, user_id, event_type, trip_id=None, request_id=None):
    database.execute(
        """INSERT INTO notifications (user_id, event_type, trip_id, request_id)
           VALUES (?, ?, ?, ?)""",
        (user_id, event_type, trip_id, request_id),
    )


@bp.route("")
@login_required
def list_notifications():
    items = get_db().execute(
        """SELECT n.*, t.trip_date, oa.name AS origin_area, da.name AS destination_area
           FROM notifications n
           LEFT JOIN trips t ON t.id = n.trip_id
           LEFT JOIN location_areas oa ON oa.id = t.origin_area_id
           LEFT JOIN location_areas da ON da.id = t.destination_area_id
           WHERE n.user_id = ?
           ORDER BY n.created_at DESC, n.id DESC""",
        (g.user["id"],),
    ).fetchall()
    return render_template("notifications/list.html", notifications=items)


@bp.post("/<int:notification_id>/read")
@login_required
def mark_read(notification_id):
    database = get_db()
    item = database.execute(
        "SELECT * FROM notifications WHERE id = ?", (notification_id,)
    ).fetchone()
    if item is None:
        abort(404)
    if item["user_id"] != g.user["id"]:
        abort(403)
    database.execute(
        """UPDATE notifications SET read_at = COALESCE(read_at, CURRENT_TIMESTAMP)
           WHERE id = ? AND user_id = ?""",
        (notification_id, g.user["id"]),
    )
    database.commit()
    if item["trip_id"]:
        return redirect(url_for("trips.detail", trip_id=item["trip_id"]))
    return redirect(url_for("notifications.list_notifications"))


@bp.post("/read-all")
@login_required
def mark_all_read():
    database = get_db()
    database.execute(
        """UPDATE notifications SET read_at = CURRENT_TIMESTAMP
           WHERE user_id = ? AND read_at IS NULL""",
        (g.user["id"],),
    )
    database.commit()
    flash("All notifications marked as read.", "success")
    return redirect(url_for("notifications.list_notifications"))
