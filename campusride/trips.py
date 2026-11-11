import re
import sqlite3
from contextlib import nullcontext
from datetime import date, datetime

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .auth import login_required
from .db import get_db, immediate_transaction
from .notifications import create_notification


bp = Blueprint("trips", __name__, url_prefix="/trips")
TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def trip_has_expired(trip, now=None):
    """Local server time, minute precision; the end minute is inclusive.

    A trip ending at 14:10 remains joinable through 14:10:59 and expires
    at 14:11. No scheduler or stored lifecycle change is required.
    """
    now = now or datetime.now()
    return (trip["trip_date"], trip["end_time"]) < (
        now.date().isoformat(), now.strftime("%H:%M")
    )


def get_areas():
    return get_db().execute(
        "SELECT id, name FROM location_areas WHERE is_active = 1 ORDER BY name"
    ).fetchall()


def find_schedule_conflict(database, user_id, trip_date, start_time, end_time,
                           exclude_trip_id=None):
    """Return one active published/joined trip overlapping the candidate interval."""
    return database.execute(
        """
        SELECT DISTINCT t.id, t.trip_date, t.start_time, t.end_time
        FROM trips t
        WHERE t.status IN ('Open', 'Full')
          AND t.trip_date = ?
          AND t.start_time <= ? AND t.end_time >= ?
          AND (? IS NULL OR t.id <> ?)
          AND (
              t.publisher_id = ? OR EXISTS (
                  SELECT 1 FROM trip_participants tp
                  WHERE tp.trip_id = t.id AND tp.user_id = ? AND tp.status = 'Active'
              )
          )
        ORDER BY t.start_time LIMIT 1
        """,
        (trip_date, end_time, start_time, exclude_trip_id, exclude_trip_id,
         user_id, user_id),
    ).fetchone()


def conflict_message(conflict):
    return (f"Schedule conflict with trip #{conflict['id']} "
            f"({conflict['trip_date']} {conflict['start_time']}–{conflict['end_time']}).")


def get_trip_or_404(trip_id):
    trip = get_db().execute(
        """
        SELECT t.*, p.display_name AS publisher_name, p.email AS publisher_email,
               p.phone AS publisher_phone, oa.name AS origin_area,
               da.name AS destination_area,
               ROUND(AVG(rv.rating), 2) AS publisher_rating,
               COUNT(rv.id) AS publisher_review_count,
               (SELECT COUNT(*) FROM trip_participants current_tp
                WHERE current_tp.trip_id = t.id AND current_tp.status = 'Active')
                AS active_participant_count
        FROM trips t
        JOIN users p ON p.id = t.publisher_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        LEFT JOIN reviews rv ON rv.reviewee_id = p.id
        WHERE t.id = ?
        GROUP BY t.id
        """,
        (trip_id,),
    ).fetchone()
    if trip is None:
        abort(404)
    return trip


def validate_trip_form(form):
    trip_date = form.get("trip_date", "").strip()
    start_time = form.get("start_time", "").strip()
    end_time = form.get("end_time", "").strip()
    try:
        parsed_date = date.fromisoformat(trip_date)
    except ValueError:
        return "Enter a valid trip date."
    if parsed_date < date.today():
        return "Trip date cannot be in the past."
    if not TIME_PATTERN.fullmatch(start_time) or not TIME_PATTERN.fullmatch(end_time):
        return "Enter valid times using hour and minute."
    if start_time > end_time:
        return "Start time must not be later than end time."
    try:
        origin_id = int(form.get("origin_area_id", ""))
        destination_id = int(form.get("destination_area_id", ""))
        seats = int(form.get("seat_capacity", ""))
        publisher_party_size = int(form.get("publisher_party_size", ""))
    except ValueError:
        return "Choose valid areas and a seat count."
    if not 1 <= seats <= 20:
        return "Available seats must be between 1 and 20."
    if not 1 <= publisher_party_size <= 20:
        return "Publisher party size must be between 1 and 20."
    valid_area_count = get_db().execute(
        "SELECT COUNT(*) FROM location_areas WHERE is_active = 1 AND id IN (?, ?)",
        (origin_id, destination_id),
    ).fetchone()[0]
    expected_count = 1 if origin_id == destination_id else 2
    if valid_area_count != expected_count:
        return "Choose valid fixed areas."
    if len(form.get("origin_detail", "")) > 200 or len(form.get("destination_detail", "")) > 200:
        return "Specific locations must not exceed 200 characters."
    return None


@bp.route("/search")
def search():
    areas = get_areas()
    values = {key: request.args.get(key, "").strip() for key in (
        "trip_date", "origin_area_id", "destination_area_id", "start_time", "end_time"
    )}
    include_full = request.args.get("include_full") == "1"
    now = datetime.now()
    clauses = ["(t.trip_date > ? OR (t.trip_date = ? AND t.end_time >= ?))"]
    parameters = [now.date().isoformat(), now.date().isoformat(), now.strftime("%H:%M")]
    if include_full:
        clauses.append("t.status IN ('Open', 'Full')")
    else:
        clauses.extend(["t.status = 'Open'", "t.available_seats > 0"])
    error = None

    if values["trip_date"]:
        try:
            date.fromisoformat(values["trip_date"])
        except ValueError:
            error = "Enter a valid search date."
        else:
            clauses.append("t.trip_date = ?")
            parameters.append(values["trip_date"])

    for field, column, label in (
        ("origin_area_id", "t.origin_area_id", "origin"),
        ("destination_area_id", "t.destination_area_id", "destination"),
    ):
        if values[field]:
            if not values[field].isdigit():
                error = f"Choose a valid {label} area."
            else:
                clauses.append(f"{column} = ?")
                parameters.append(values[field])

    start_time = values["start_time"]
    end_time = values["end_time"]
    if start_time and not TIME_PATTERN.fullmatch(start_time):
        error = "Enter a valid earliest time."
    if end_time and not TIME_PATTERN.fullmatch(end_time):
        error = "Enter a valid latest time."
    if not error and start_time and end_time and start_time > end_time:
        error = "Search start time must not be later than end time."
    if not error:
        if end_time:
            clauses.append("t.start_time <= ?")
            parameters.append(end_time)
        if start_time:
            clauses.append("t.end_time >= ?")
            parameters.append(start_time)

    results = []
    if error:
        flash(error, "error")
    else:
        results = get_db().execute(
            f"""
            SELECT t.*, u.display_name AS publisher_name,
                   oa.name AS origin_area, da.name AS destination_area,
                   COUNT(tp.id) AS active_participant_count
            FROM trips t
            JOIN users u ON u.id = t.publisher_id
            JOIN location_areas oa ON oa.id = t.origin_area_id
            JOIN location_areas da ON da.id = t.destination_area_id
            LEFT JOIN trip_participants tp
              ON tp.trip_id = t.id AND tp.status = 'Active'
            WHERE {' AND '.join(clauses)}
            GROUP BY t.id
            ORDER BY CASE t.status WHEN 'Open' THEN 0 ELSE 1 END,
                     t.trip_date, t.start_time, t.created_at
            """,
            parameters,
        ).fetchall()
    return render_template("trips/search.html", areas=areas, results=results,
                           include_full=include_full)


@bp.route("/insights")
def insights():
    """Present small, reproducible aggregations over the live relational data."""
    database = get_db()
    status_counts = database.execute(
        """SELECT status, COUNT(*) AS trip_count
           FROM trips
           GROUP BY status
           ORDER BY CASE status
               WHEN 'Open' THEN 1 WHEN 'Full' THEN 2
               WHEN 'Completed' THEN 3 ELSE 4 END"""
    ).fetchall()
    popular_origins = database.execute(
        """SELECT a.name AS area_name, COUNT(*) AS trip_count
           FROM trips t
           JOIN location_areas a ON a.id = t.origin_area_id
           GROUP BY a.id, a.name
           ORDER BY trip_count DESC, a.name
           LIMIT 5"""
    ).fetchall()
    popular_destinations = database.execute(
        """SELECT a.name AS area_name, COUNT(*) AS trip_count
           FROM trips t
           JOIN location_areas a ON a.id = t.destination_area_id
           GROUP BY a.id, a.name
           ORDER BY trip_count DESC, a.name
           LIMIT 5"""
    ).fetchall()
    popular_routes = database.execute(
        """SELECT oa.name AS origin_area, da.name AS destination_area,
                  COUNT(*) AS trip_count
           FROM trips t
           JOIN location_areas oa ON oa.id = t.origin_area_id
           JOIN location_areas da ON da.id = t.destination_area_id
           GROUP BY t.origin_area_id, t.destination_area_id,
                    oa.name, da.name
           ORDER BY trip_count DESC, oa.name, da.name
           LIMIT 5"""
    ).fetchall()
    rating_summary = database.execute(
        """SELECT ROUND(AVG(rating), 2) AS average_rating,
                  COUNT(*) AS review_count,
                  COUNT(DISTINCT reviewee_id) AS rated_user_count
           FROM reviews"""
    ).fetchone()
    return render_template(
        "trips/insights.html",
        status_counts=status_counts,
        popular_origins=popular_origins,
        popular_destinations=popular_destinations,
        popular_routes=popular_routes,
        rating_summary=rating_summary,
    )


@bp.route("/publish", methods=("GET", "POST"))
@login_required
def publish():
    with immediate_transaction(get_db()) if request.method == "POST" else nullcontext():
        if request.method == "POST":
            error = validate_trip_form(request.form)
            if error is None:
                database = get_db()
                conflict = find_schedule_conflict(
                    database, g.user["id"], request.form["trip_date"],
                    request.form["start_time"], request.form["end_time"]
                )
                if conflict:
                    flash(conflict_message(conflict), "error")
                    return render_template("trips/form.html", areas=get_areas(), trip=None,
                                           today=date.today().isoformat())
                cursor = database.execute(
                    """
                    INSERT INTO trips (
                        publisher_id, trip_date, origin_area_id, origin_detail,
                        destination_area_id, destination_detail, start_time, end_time,
                        publisher_party_size, seat_capacity, available_seats
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (g.user["id"], request.form["trip_date"], request.form["origin_area_id"],
                     request.form.get("origin_detail", "").strip() or None,
                     request.form["destination_area_id"],
                     request.form.get("destination_detail", "").strip() or None,
                     request.form["start_time"], request.form["end_time"],
                     request.form["publisher_party_size"],
                     request.form["seat_capacity"], request.form["seat_capacity"]),
                )
                flash("Trip published.", "success")
                return redirect(url_for("trips.detail", trip_id=cursor.lastrowid))
            flash(error, "error")
        return render_template("trips/form.html", areas=get_areas(), trip=None, today=date.today().isoformat())


@bp.route("/<int:trip_id>")
def detail(trip_id):
    trip = get_trip_or_404(trip_id)
    database = get_db()
    viewer_request = None
    viewer_participation = None
    if g.user:
        viewer_request = database.execute(
            """SELECT * FROM match_requests
               WHERE trip_id = ? AND requester_id = ?
               ORDER BY created_at DESC, id DESC LIMIT 1""",
            (trip_id, g.user["id"]),
        ).fetchone()
        viewer_participation = database.execute(
            """SELECT * FROM trip_participants WHERE trip_id = ? AND user_id = ?
               ORDER BY joined_at DESC, id DESC LIMIT 1""",
            (trip_id, g.user["id"]),
        ).fetchone()

    participants = database.execute(
        """
        SELECT tp.*, u.display_name
        FROM trip_participants tp JOIN users u ON u.id = tp.user_id
        WHERE tp.trip_id = ? ORDER BY tp.joined_at
        """,
        (trip_id,),
    ).fetchall()

    visible_contacts = []
    can_see_publisher_contact = False
    if g.user and g.user["id"] == trip["publisher_id"]:
        visible_contacts = database.execute(
            """
            SELECT u.display_name, u.email, u.phone
            FROM trip_participants tp JOIN users u ON u.id = tp.user_id
            WHERE tp.trip_id = ? AND tp.status = 'Active'
            ORDER BY u.display_name
            """,
            (trip_id,),
        ).fetchall()
    elif viewer_participation and viewer_participation["status"] == "Active":
        can_see_publisher_contact = True

    return render_template(
        "trips/detail.html", trip=trip, participants=participants,
        viewer_request=viewer_request, viewer_participation=viewer_participation,
        visible_contacts=visible_contacts, can_see_publisher_contact=can_see_publisher_contact,
        trip_expired=trip_has_expired(trip),
    )


@bp.route("/<int:trip_id>/edit", methods=("GET", "POST"))
@login_required
def edit(trip_id):
    with immediate_transaction(get_db()) if request.method == "POST" else nullcontext():
        trip = get_trip_or_404(trip_id)
        if trip["publisher_id"] != g.user["id"]:
            abort(403)
        if trip["status"] in ("Completed", "Cancelled"):
            flash("Completed or cancelled trips cannot be edited.", "error")
            return redirect(url_for("trips.detail", trip_id=trip_id))

        active_count = get_db().execute(
            "SELECT COUNT(*) FROM trip_participants WHERE trip_id = ? AND status = 'Active'",
            (trip_id,),
        ).fetchone()[0]
        if request.method == "POST":
            if active_count:
                origin_detail = request.form.get("origin_detail", "").strip() or None
                destination_detail = request.form.get("destination_detail", "").strip() or None
                if len(origin_detail or "") > 200 or len(destination_detail or "") > 200:
                    flash("Specific locations must not exceed 200 characters.", "error")
                else:
                    database = get_db()
                    database.execute(
                        """UPDATE trips SET origin_detail = ?, destination_detail = ?,
                           updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                        (origin_detail, destination_detail, trip_id),
                    )
                    flash("Meeting details updated. Matching fields are locked after a participant joins.", "success")
                    return redirect(url_for("trips.detail", trip_id=trip_id))
            else:
                error = validate_trip_form(request.form)
                if error is None:
                    database = get_db()
                    conflict = find_schedule_conflict(
                        database, g.user["id"], request.form["trip_date"],
                        request.form["start_time"], request.form["end_time"], trip_id
                    )
                    if conflict:
                        flash(conflict_message(conflict), "error")
                        return render_template("trips/form.html", areas=get_areas(), trip=trip,
                                               active_count=active_count,
                                               today=date.today().isoformat())
                    seats = int(request.form["seat_capacity"])
                    database.execute(
                        """
                        UPDATE trips SET trip_date = ?, origin_area_id = ?, origin_detail = ?,
                            destination_area_id = ?, destination_detail = ?, start_time = ?, end_time = ?,
                            publisher_party_size = ?, seat_capacity = ?, available_seats = ?, status = 'Open',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (request.form["trip_date"], request.form["origin_area_id"],
                         request.form.get("origin_detail", "").strip() or None,
                         request.form["destination_area_id"],
                         request.form.get("destination_detail", "").strip() or None,
                         request.form["start_time"], request.form["end_time"],
                         request.form["publisher_party_size"], seats, seats, trip_id),
                    )
                    flash("Trip updated.", "success")
                    return redirect(url_for("trips.detail", trip_id=trip_id))
                flash(error, "error")
        return render_template("trips/form.html", areas=get_areas(), trip=trip,
                               active_count=active_count, today=date.today().isoformat())


@bp.post("/<int:trip_id>/cancel")
@login_required
def cancel_trip(trip_id):
    database = get_db()
    with immediate_transaction(database):
        trip = get_trip_or_404(trip_id)
        if trip["publisher_id"] != g.user["id"]:
            abort(403)
        if trip["status"] not in ("Open", "Full"):
            flash("This trip can no longer be cancelled.", "error")
            return redirect(url_for("trips.detail", trip_id=trip_id))
        affected = database.execute(
            """SELECT user_id, request_id FROM trip_participants
               WHERE trip_id = ? AND status = 'Active'""", (trip_id,)
        ).fetchall()
        changed = database.execute(
            """UPDATE trips SET status = 'Cancelled', available_seats = seat_capacity,
               updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND status IN ('Open', 'Full')""", (trip_id,)
        )
        if changed.rowcount != 1:
            raise sqlite3.IntegrityError("Trip changed during cancellation.")
        database.execute(
            """UPDATE match_requests SET status = 'Cancelled', updated_at = CURRENT_TIMESTAMP
               WHERE trip_id = ? AND status IN ('Pending', 'Accepted')""", (trip_id,)
        )
        database.execute(
            """UPDATE trip_participants SET status = 'TripCancelled', ended_at = CURRENT_TIMESTAMP
               WHERE trip_id = ? AND status = 'Active'""", (trip_id,)
        )
        for participant in affected:
            create_notification(database, participant["user_id"], "TripCancelled",
                                trip_id, participant["request_id"])
    flash("Trip cancelled; its history has been preserved.", "success")
    return redirect(url_for("trips.detail", trip_id=trip_id))


@bp.post("/<int:trip_id>/complete")
@login_required
def complete_trip(trip_id):
    database = get_db()
    with immediate_transaction(database):
        trip = get_trip_or_404(trip_id)
        if trip["publisher_id"] != g.user["id"]:
            abort(403)
        if trip["status"] not in ("Open", "Full"):
            flash("Only an active trip can be completed.", "error")
        elif date.fromisoformat(trip["trip_date"]) > date.today():
            flash("A future trip cannot be completed.", "error")
        else:
            changed = database.execute(
                """UPDATE trips SET status = 'Completed', updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND status IN ('Open', 'Full')""", (trip_id,)
            )
            if changed.rowcount != 1:
                raise sqlite3.IntegrityError("Trip changed during completion.")
            database.execute(
                """UPDATE match_requests SET status = 'Cancelled', updated_at = CURRENT_TIMESTAMP
                   WHERE trip_id = ? AND status = 'Pending'""", (trip_id,)
            )
            flash("Trip marked as completed. Participants may now leave reviews.", "success")
    return redirect(url_for("trips.detail", trip_id=trip_id))


@bp.post("/<int:trip_id>/request")
@login_required
def send_request(trip_id):
    database = get_db()
    try:
        with immediate_transaction(database):
            # Read dates, times, ownership and availability from the same locked snapshot.
            trip = get_trip_or_404(trip_id)
            error = None
            if trip["publisher_id"] == g.user["id"]:
                error = "You cannot request to join your own trip."
            elif trip["status"] != "Open" or trip["available_seats"] < 1:
                error = "This trip is not available."
            elif trip_has_expired(trip):
                error = "This trip has expired; join requests are closed."
            else:
                conflict = find_schedule_conflict(
                    database, g.user["id"], trip["trip_date"], trip["start_time"],
                    trip["end_time"], trip_id
                )
                if conflict:
                    error = conflict_message(conflict)
            if error:
                flash(error, "error")
                return redirect(url_for("trips.detail", trip_id=trip_id))
            cursor = database.execute(
                "INSERT INTO match_requests (trip_id, requester_id) VALUES (?, ?)",
                (trip_id, g.user["id"]),
            )
            create_notification(database, trip["publisher_id"], "RequestSubmitted",
                                trip_id, cursor.lastrowid)
    except sqlite3.IntegrityError:
        flash("You have already requested this trip.", "error")
    else:
        flash("Join request sent.", "success")
    return redirect(url_for("trips.detail", trip_id=trip_id))


@bp.post("/requests/<int:request_id>/cancel")
@login_required
def cancel_request(request_id):
    database = get_db()
    item = database.execute("SELECT * FROM match_requests WHERE id = ?", (request_id,)).fetchone()
    if item is None:
        abort(404)
    if item["requester_id"] != g.user["id"]:
        abort(403)
    cursor = database.execute(
        """UPDATE match_requests SET status = 'Cancelled', updated_at = CURRENT_TIMESTAMP
           WHERE id = ? AND status = 'Pending'""",
        (request_id,),
    )
    database.commit()
    flash("Request cancelled." if cursor.rowcount else "Only pending requests can be cancelled.",
          "success" if cursor.rowcount else "error")
    return redirect(url_for("trips.detail", trip_id=item["trip_id"]))


def get_owned_request_or_404(request_id):
    item = get_db().execute(
        """
        SELECT mr.*, t.publisher_id, t.status AS trip_status, t.available_seats
        FROM match_requests mr JOIN trips t ON t.id = mr.trip_id
        WHERE mr.id = ?
        """,
        (request_id,),
    ).fetchone()
    if item is None:
        abort(404)
    if item["publisher_id"] != g.user["id"]:
        abort(403)
    return item


@bp.post("/requests/<int:request_id>/accept")
@login_required
def accept_request(request_id):
    database = get_db()
    error = None
    try:
        database.execute("BEGIN IMMEDIATE")
        current = get_owned_request_or_404(request_id)
        if current["requester_id"] == current["publisher_id"]:
            error = "You cannot request to join your own trip."
        elif current["status"] != "Pending":
            error = "Only pending requests can be accepted."
        elif current["trip_status"] != "Open" or current["available_seats"] < 1:
            error = "The trip is no longer open or has no available seats."
        else:
            trip_times = database.execute(
                "SELECT trip_date, start_time, end_time FROM trips WHERE id = ?",
                (current["trip_id"],),
            ).fetchone()
            conflict = find_schedule_conflict(
                database, current["requester_id"], trip_times["trip_date"],
                trip_times["start_time"], trip_times["end_time"], current["trip_id"]
            )
            if trip_has_expired(trip_times):
                error = "This trip has expired; join requests are closed."
            elif conflict:
                error = conflict_message(conflict)
        if not error:
            updated = database.execute(
                """UPDATE trips
                   SET available_seats = available_seats - 1,
                       status = CASE WHEN available_seats = 1 THEN 'Full' ELSE 'Open' END,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND status = 'Open' AND available_seats > 0""",
                (current["trip_id"],),
            )
            if updated.rowcount != 1:
                error = "The trip changed while processing the request."
            else:
                database.execute(
                    "UPDATE match_requests SET status = 'Accepted', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (request_id,),
                )
                database.execute(
                    "INSERT INTO trip_participants (trip_id, user_id, request_id) VALUES (?, ?, ?)",
                    (current["trip_id"], current["requester_id"], request_id),
                )
                create_notification(database, current["requester_id"], "RequestAccepted",
                                    current["trip_id"], request_id)
        if error:
            database.rollback()
        else:
            database.commit()
    except Exception:
        database.rollback()
        raise
    flash(error or "Request accepted and participant added.", "error" if error else "success")
    return redirect(url_for("trips.requests_dashboard"))


@bp.post("/requests/<int:request_id>/reject")
@login_required
def reject_request(request_id):
    item = get_owned_request_or_404(request_id)
    database = get_db()
    try:
        database.execute("BEGIN IMMEDIATE")
        cursor = database.execute(
            """UPDATE match_requests SET status = 'Rejected', updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND status = 'Pending'""",
            (request_id,),
        )
        if cursor.rowcount:
            create_notification(database, item["requester_id"], "RequestRejected",
                                item["trip_id"], request_id)
        database.commit()
    except Exception:
        database.rollback()
        raise
    flash("Request rejected." if cursor.rowcount else "Only pending requests can be rejected.",
          "success" if cursor.rowcount else "error")
    return redirect(url_for("trips.requests_dashboard"))


def end_participation(participant_id, new_status, require_publisher):
    database = get_db()
    try:
        database.execute("BEGIN IMMEDIATE")
        participant = database.execute(
            """SELECT tp.*, t.publisher_id, t.status AS trip_status
               FROM trip_participants tp JOIN trips t ON t.id = tp.trip_id
               WHERE tp.id = ?""",
            (participant_id,),
        ).fetchone()
        if participant is None:
            database.rollback()
            abort(404)
        allowed = (participant["publisher_id"] == g.user["id"] if require_publisher
                   else participant["user_id"] == g.user["id"])
        if not allowed:
            database.rollback()
            abort(403)
        if participant["status"] != "Active":
            database.rollback()
            return participant["trip_id"], "This participation is no longer active."
        if participant["trip_status"] not in ("Open", "Full"):
            database.rollback()
            return participant["trip_id"], "Completed or cancelled trips cannot change participants."
        linked_request = database.execute(
            """SELECT 1 FROM match_requests WHERE id = ? AND trip_id = ?
               AND requester_id = ? AND status = 'Accepted'""",
            (participant["request_id"], participant["trip_id"], participant["user_id"]),
        ).fetchone()
        if linked_request is None:
            database.rollback()
            return participant["trip_id"], "Participation data is inconsistent; no changes were saved."
        updated = database.execute(
            """UPDATE trip_participants SET status = ?, ended_at = CURRENT_TIMESTAMP
               WHERE id = ? AND status = 'Active'""",
            (new_status, participant_id),
        )
        if updated.rowcount != 1:
            database.rollback()
            return participant["trip_id"], "Participation changed while processing."
        restored = database.execute(
            """UPDATE trips SET available_seats = available_seats + 1, status = 'Open',
               updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND status IN ('Open', 'Full')
                 AND available_seats < seat_capacity""",
            (participant["trip_id"],),
        )
        if restored.rowcount != 1:
            database.rollback()
            return participant["trip_id"], "Seat restoration failed; no changes were saved."
        database.execute(
            """UPDATE match_requests SET status = 'Cancelled', updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND status = 'Accepted'""",
            (participant["request_id"],),
        )
        if new_status == "Removed":
            create_notification(database, participant["user_id"], "ParticipantRemoved",
                                participant["trip_id"], participant["request_id"])
        database.commit()
    except Exception:
        database.rollback()
        raise
    return participant["trip_id"], None


@bp.post("/participants/<int:participant_id>/leave")
@login_required
def leave_trip(participant_id):
    trip_id, error = end_participation(participant_id, "Left", False)
    flash(error or "You left the trip; the seat was restored.", "error" if error else "success")
    return redirect(url_for("trips.detail", trip_id=trip_id))


@bp.post("/participants/<int:participant_id>/remove")
@login_required
def remove_participant(participant_id):
    trip_id, error = end_participation(participant_id, "Removed", True)
    flash(error or "Participant removed; the seat was restored.", "error" if error else "success")
    return redirect(url_for("trips.detail", trip_id=trip_id))


@bp.route("/mine")
@login_required
def my_trips():
    database = get_db()
    published = database.execute(
        """
        SELECT t.*, oa.name AS origin_area, da.name AS destination_area,
               COUNT(CASE WHEN tp.status = 'Active' THEN 1 END) AS active_participants
        FROM trips t
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        LEFT JOIN trip_participants tp ON tp.trip_id = t.id
        WHERE t.publisher_id = ? GROUP BY t.id ORDER BY t.trip_date DESC, t.start_time
        """,
        (g.user["id"],),
    ).fetchall()
    joined = database.execute(
        """
        SELECT t.*, tp.status AS participation_status, oa.name AS origin_area,
               da.name AS destination_area, u.display_name AS publisher_name
        FROM trip_participants tp
        JOIN trips t ON t.id = tp.trip_id
        JOIN users u ON u.id = t.publisher_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE tp.user_id = ? ORDER BY t.trip_date DESC, t.start_time
        """,
        (g.user["id"],),
    ).fetchall()
    request_history = database.execute(
        """
        SELECT mr.*, t.trip_date, t.start_time, oa.name AS origin_area,
               da.name AS destination_area,
               (SELECT tp.status FROM trip_participants tp
                WHERE tp.request_id = mr.id ORDER BY tp.id DESC LIMIT 1)
                AS participation_status
        FROM match_requests mr JOIN trips t ON t.id = mr.trip_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE mr.requester_id = ?
        ORDER BY mr.created_at DESC
        """,
        (g.user["id"],),
    ).fetchall()
    return render_template("trips/mine.html", published=published, joined=joined,
                           request_history=request_history)


@bp.route("/requests")
@login_required
def requests_dashboard():
    received = get_db().execute(
        """
        SELECT mr.*, t.trip_date, t.start_time, t.end_time,
               u.display_name AS requester_name, oa.name AS origin_area,
               da.name AS destination_area
        FROM match_requests mr
        JOIN trips t ON t.id = mr.trip_id
        JOIN users u ON u.id = mr.requester_id
        JOIN location_areas oa ON oa.id = t.origin_area_id
        JOIN location_areas da ON da.id = t.destination_area_id
        WHERE t.publisher_id = ?
        ORDER BY CASE mr.status WHEN 'Pending' THEN 0 ELSE 1 END, mr.created_at DESC
        """,
        (g.user["id"],),
    ).fetchall()
    return render_template("trips/requests.html", received=received)


def eligible_review_targets(trip_id, user_id):
    database = get_db()
    trip = database.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    if trip is None:
        abort(404)
    is_active_participant = database.execute(
        """SELECT 1 FROM trip_participants
           WHERE trip_id = ? AND user_id = ? AND status = 'Active'""",
        (trip_id, user_id),
    ).fetchone()
    if trip["status"] != "Completed" or (trip["publisher_id"] != user_id and not is_active_participant):
        return trip, []
    return trip, database.execute(
        """
        SELECT u.id, u.display_name
        FROM users u
        WHERE u.id <> ? AND (
            u.id = ? OR u.id IN (
                SELECT user_id FROM trip_participants WHERE trip_id = ? AND status = 'Active'
            )
        )
        ORDER BY u.display_name
        """,
        (user_id, trip["publisher_id"], trip_id),
    ).fetchall()


@bp.route("/<int:trip_id>/review", methods=("GET", "POST"))
@login_required
def review(trip_id):
    trip, targets = eligible_review_targets(trip_id, g.user["id"])
    target_ids = {target["id"] for target in targets}
    if not target_ids:
        flash("Only actual participants of a completed trip can review each other.", "error")
        return redirect(url_for("trips.detail", trip_id=trip_id))
    if request.method == "POST":
        try:
            reviewee_id = int(request.form.get("reviewee_id", ""))
            rating = int(request.form.get("rating", ""))
        except ValueError:
            reviewee_id, rating = 0, 0
        comment = request.form.get("comment", "").strip() or None
        if reviewee_id not in target_ids:
            flash("Choose an eligible participant.", "error")
        elif not 1 <= rating <= 5:
            flash("Rating must be between 1 and 5.", "error")
        elif len(comment or "") > 1000:
            flash("Comment must not exceed 1000 characters.", "error")
        else:
            try:
                database = get_db()
                database.execute(
                    """INSERT INTO reviews (trip_id, reviewer_id, reviewee_id, rating, comment)
                       VALUES (?, ?, ?, ?, ?)""",
                    (trip_id, g.user["id"], reviewee_id, rating, comment),
                )
                database.commit()
            except sqlite3.IntegrityError:
                flash("You already reviewed this user for this trip.", "error")
            else:
                flash("Review submitted.", "success")
                return redirect(url_for("trips.detail", trip_id=trip_id))
    return render_template("trips/review.html", trip=trip, targets=targets)
