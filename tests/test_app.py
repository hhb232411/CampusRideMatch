import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from campusride import create_app
from campusride.db import get_db, init_db


class CampusRideTestCase(unittest.TestCase):
    def setUp(self):
        # Keep the original same-day scenarios independent of the wall-clock hour.
        clock = patch("campusride.trips.datetime", wraps=datetime)
        self.clock = clock.start()
        self.clock.now.return_value = datetime.combine(date.today(), datetime.min.time())
        self.addCleanup(clock.stop)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.temp_dir.name) / "test.sqlite")
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE": self.database_path,
        })
        with self.app.app_context():
            init_db(with_seed=True)
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def login(self, username, password="password123"):
        return self.client.post(
            "/auth/login",
            data={"username": username, "password": password},
            follow_redirects=True,
        )

    def logout(self):
        return self.client.post("/auth/logout", follow_redirects=True)

    def publish(self, seats=2, trip_date=None, start="12:20", end="14:10", party_size=2):
        trip_date = trip_date or date.today().isoformat()
        response = self.client.post(
            "/trips/publish",
            data={
                "trip_date": trip_date,
                "origin_area_id": "1",
                "origin_detail": "CityU Main Entrance",
                "destination_area_id": "2",
                "destination_detail": "Langham Place",
                "start_time": start,
                "end_time": end,
                "publisher_party_size": str(party_size),
                "seat_capacity": str(seats),
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        return int(response.headers["Location"].rstrip("/").split("/")[-1])

    def database_row(self, sql, parameters=()):
        with self.app.app_context():
            return get_db().execute(sql, parameters).fetchone()

    def _database_rows(self, sql, parameters=()):
        with self.app.app_context():
            return get_db().execute(sql, parameters).fetchall()

    def test_registration_login_and_profile(self):
        response = self.client.post(
            "/auth/register",
            data={
                "username": "david",
                "display_name": "David Ho",
                "email": "david@example.com",
                "phone": "9456 7890",
                "password": "safe-password",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Account created", response.data)
        stored = self.database_row("SELECT * FROM users WHERE username = 'david'")
        self.assertNotEqual(stored["password_hash"], "safe-password")
        self.assertIn(b"Incorrect username", self.login("david", "wrong-pass").data)
        self.assertIn(b"Share campus journeys", self.login("david", "safe-password").data)
        response = self.client.post(
            "/auth/profile",
            data={"display_name": "David H.", "email": "david2@example.com", "phone": "9000"},
            follow_redirects=True,
        )
        self.assertIn(b"Profile updated", response.data)

    def test_search_uses_overlap_and_ignores_specific_locations(self):
        self.login("alice")
        future = (date.today() + timedelta(days=2)).isoformat()
        trip_id = self.publish(trip_date=future)
        path = (f"/trips/search?trip_date={future}&origin_area_id=1&destination_area_id=2"
                "&start_time=12:00&end_time=12:20")
        response = self.client.get(path)
        self.assertIn(f"/trips/{trip_id}".encode(), response.data)

        no_overlap = self.client.get(
            f"/trips/search?trip_date={future}&origin_area_id=1&destination_area_id=2"
            "&start_time=14:11&end_time=15:00"
        )
        self.assertNotIn(f"/trips/{trip_id}".encode(), no_overlap.data)
        wrong_route = self.client.get(
            f"/trips/search?trip_date={future}&origin_area_id=1&destination_area_id=3"
            "&start_time=12:30&end_time=13:00"
        )
        self.assertNotIn(f"/trips/{trip_id}".encode(), wrong_route.data)

        all_trips = self.client.get("/trips/search")
        self.assertIn(f"/trips/{trip_id}".encode(), all_trips.data)

        origin_only = self.client.get("/trips/search?origin_area_id=1")
        self.assertIn(f"/trips/{trip_id}".encode(), origin_only.data)

    def test_bilingual_location_catalog_and_search_controls(self):
        response = self.client.get("/trips/search")
        self.assertIn("Kowloon Tong 九龙塘".encode("utf-8"), response.data)
        self.assertIn("Pok Fu Lam 薄扶林".encode("utf-8"), response.data)
        self.assertIn("University Station 大学站".encode("utf-8"), response.data)
        self.assertNotIn(b"(CityU)", response.data)
        self.assertIn(b'class="searchable-area-select"', response.data)
        self.assertIn(b'data-search-placeholder=', response.data)
        self.assertIn(b'>All destinations<', response.data)
        area_count = self.database_row("SELECT COUNT(*) FROM location_areas")[0]
        self.assertGreaterEqual(area_count, 40)

    def test_language_switch_and_twenty_demo_trips(self):
        trip_count = self.database_row("SELECT COUNT(*) FROM trips")[0]
        self.assertEqual(trip_count, 20)
        status_counts = {
            row["status"]: row["total"]
            for row in self._database_rows(
                "SELECT status, COUNT(*) AS total FROM trips GROUP BY status"
            )
        }
        self.assertGreater(status_counts.get("Open", 0), 0)
        self.assertGreater(status_counts.get("Full", 0), 0)
        self.assertGreater(status_counts.get("Completed", 0), 0)
        self.assertGreater(status_counts.get("Cancelled", 0), 0)
        self.assertGreater(
            self.database_row(
                "SELECT COUNT(*) FROM match_requests WHERE status = 'Pending'"
            )[0],
            0,
        )

        switched = self.client.post(
            "/language/zh", data={"next": "/trips/search"}, follow_redirects=True
        )
        self.assertIn("搜索行程".encode("utf-8"), switched.data)
        self.assertIn("匹配行程".encode("utf-8"), switched.data)
        self.assertIn("当前人数".encode("utf-8"), switched.data)
        self.assertIn("剩余座位".encode("utf-8"), switched.data)
        self.assertIn(b">EN<", switched.data)
        english = self.client.post(
            "/language/en", data={"next": "/auth/login"}, follow_redirects=True
        )
        self.assertIn(b"Welcome back", english.data)

    def test_database_insights_and_sample_queries(self):
        response = self.client.get("/trips/insights")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Database insights", response.data)
        self.assertIn(b"Popular routes", response.data)
        self.assertIn(b"Average rating", response.data)

        sample_queries = Path(__file__).resolve().parents[1] / "sql" / "sample_queries.sql"
        with self.app.app_context():
            get_db().executescript(sample_queries.read_text(encoding="utf-8"))

    def test_additional_database_check_and_unique_constraints(self):
        with self.app.app_context():
            database = get_db()
            invalid_rows = (
                """INSERT INTO trips
                   (publisher_id, trip_date, origin_area_id, destination_area_id,
                    start_time, end_time, seat_capacity, available_seats)
                   VALUES (1, '2099-01-01', 1, 2, '12:00', '11:00', 1, 1)""",
                """INSERT INTO trips
                   (publisher_id, trip_date, origin_area_id, destination_area_id,
                    start_time, end_time, seat_capacity, available_seats)
                   VALUES (1, '2099-01-01', 1, 2, '12:00', '13:00', 1, -1)""",
                """INSERT INTO trip_participants
                   (trip_id, user_id, request_id, status, ended_at)
                   SELECT trip_id, requester_id, id, 'Active', CURRENT_TIMESTAMP
                   FROM match_requests WHERE status = 'Pending' LIMIT 1""",
            )
            for sql in invalid_rows:
                with self.assertRaises(sqlite3.IntegrityError):
                    database.execute(sql)
                database.rollback()

    def test_request_accept_contact_edit_lock_complete_and_review(self):
        self.login("alice")
        trip_id = self.publish(seats=1, party_size=3)
        self.logout()

        self.login("bob")
        before = self.client.get(f"/trips/{trip_id}")
        self.assertNotIn(b"alice@example.com", before.data)
        self.client.post(f"/trips/{trip_id}/request")
        duplicate = self.client.post(f"/trips/{trip_id}/request", follow_redirects=True)
        self.assertIn(b"already requested", duplicate.data)
        request_id = self.database_row(
            "SELECT id FROM match_requests WHERE trip_id = ? AND requester_id = 2", (trip_id,)
        )["id"]
        self.logout()

        self.login("alice")
        accepted = self.client.post(f"/trips/requests/{request_id}/accept", follow_redirects=True)
        self.assertIn(b"participant added", accepted.data)
        trip = self.database_row("SELECT * FROM trips WHERE id = ?", (trip_id,))
        self.assertEqual((trip["available_seats"], trip["status"]), (0, "Full"))
        self.assertEqual(trip["publisher_party_size"], 3)
        participant = self.database_row("SELECT * FROM trip_participants WHERE request_id = ?", (request_id,))
        self.assertEqual(participant["status"], "Active")
        full_search = self.client.get(
            f"/trips/search?trip_date={date.today().isoformat()}&origin_area_id=1"
            "&destination_area_id=2&start_time=12:00&end_time=13:00&include_full=1"
        )
        self.assertIn(f"/trips/{trip_id}".encode(), full_search.data)
        self.assertIn(b">Full<", full_search.data)
        self.assertIn(b"Cannot join", full_search.data)
        self.assertIn(b"4</strong> people currently", full_search.data)
        self.logout()
        self.login("carol")
        blocked_request = self.client.post(f"/trips/{trip_id}/request", follow_redirects=True)
        self.assertIn(b"not available", blocked_request.data)
        self.assertIsNone(self.database_row(
            "SELECT id FROM match_requests WHERE trip_id = ? AND requester_id = 3", (trip_id,)
        ))
        self.logout()
        self.login("alice")
        publisher_view = self.client.get(f"/trips/{trip_id}")
        self.assertIn(b"bob@example.com", publisher_view.data)

        edit = self.client.post(
            f"/trips/{trip_id}/edit",
            data={"origin_detail": "New pickup", "destination_detail": "New drop-off",
                  "trip_date": "2099-01-01", "origin_area_id": "3", "destination_area_id": "4",
                  "start_time": "01:00", "end_time": "02:00", "seat_capacity": "9",
                  "publisher_party_size": "9"},
            follow_redirects=True,
        )
        self.assertIn(b"Matching fields are locked", edit.data)
        unchanged = self.database_row("SELECT * FROM trips WHERE id = ?", (trip_id,))
        self.assertEqual(unchanged["origin_area_id"], 1)
        self.assertEqual(unchanged["seat_capacity"], 1)
        self.assertEqual(unchanged["publisher_party_size"], 3)

        self.client.post(f"/trips/{trip_id}/complete", follow_redirects=True)
        self.assertEqual(self.database_row("SELECT status FROM trips WHERE id = ?", (trip_id,))[0], "Completed")
        self.logout()

        self.login("bob")
        participant_view = self.client.get(f"/trips/{trip_id}")
        self.assertIn(b"alice@example.com", participant_view.data)
        review = self.client.post(
            f"/trips/{trip_id}/review",
            data={"reviewee_id": "1", "rating": "5", "comment": "Reliable ride partner"},
            follow_redirects=True,
        )
        self.assertIn(b"Review submitted", review.data)
        duplicate_review = self.client.post(
            f"/trips/{trip_id}/review",
            data={"reviewee_id": "1", "rating": "4", "comment": "Again"},
            follow_redirects=True,
        )
        self.assertIn(b"already reviewed", duplicate_review.data)
        self.logout()

        self.login("carol")
        blocked = self.client.get(f"/trips/{trip_id}/review", follow_redirects=True)
        self.assertIn(b"Only actual participants", blocked.data)

    def test_no_seat_acceptance_rolls_back_then_withdraw_restores(self):
        self.login("alice")
        trip_id = self.publish(seats=1, trip_date=(date.today() + timedelta(days=1)).isoformat())
        self.logout()
        for user in ("bob", "carol"):
            self.login(user)
            self.client.post(f"/trips/{trip_id}/request")
            self.logout()
        bob_request = self.database_row(
            "SELECT id FROM match_requests WHERE trip_id = ? AND requester_id = 2", (trip_id,)
        )["id"]
        carol_request = self.database_row(
            "SELECT id FROM match_requests WHERE trip_id = ? AND requester_id = 3", (trip_id,)
        )["id"]

        self.login("alice")
        self.client.post(f"/trips/requests/{bob_request}/accept")
        self.logout()
        self.login("bob")
        premature_review = self.client.get(f"/trips/{trip_id}/review", follow_redirects=True)
        self.assertIn(b"Only actual participants of a completed trip", premature_review.data)
        failed = self.client.post(f"/trips/requests/{carol_request}/accept", follow_redirects=True)
        self.assertEqual(failed.status_code, 403)
        self.logout()
        self.login("alice")
        failed = self.client.post(f"/trips/requests/{carol_request}/accept", follow_redirects=True)
        self.assertIn(b"no available seats", failed.data)
        carol_state = self.database_row("SELECT status FROM match_requests WHERE id = ?", (carol_request,))[0]
        self.assertEqual(carol_state, "Pending")
        self.assertIsNone(self.database_row("SELECT id FROM trip_participants WHERE request_id = ?", (carol_request,)))
        self.logout()

        self.login("bob")
        participant_id = self.database_row(
            "SELECT id FROM trip_participants WHERE request_id = ?", (bob_request,)
        )["id"]
        self.client.post(f"/trips/participants/{participant_id}/leave")
        restored = self.database_row("SELECT available_seats, status FROM trips WHERE id = ?", (trip_id,))
        self.assertEqual((restored["available_seats"], restored["status"]), (1, "Open"))
        self.logout()

        self.login("alice")
        self.client.post(f"/trips/requests/{carol_request}/accept")
        self.assertEqual(self.database_row("SELECT status FROM match_requests WHERE id = ?", (carol_request,))[0], "Accepted")

    def test_cancel_reject_and_database_constraints(self):
        self.login("alice")
        trip_id = self.publish(trip_date=(date.today() + timedelta(days=1)).isoformat())
        self.logout()
        self.login("bob")
        self.client.post(f"/trips/{trip_id}/request")
        request_id = self.database_row("SELECT id FROM match_requests WHERE trip_id = ?", (trip_id,))["id"]
        self.client.post(f"/trips/requests/{request_id}/cancel")
        self.assertEqual(self.database_row("SELECT status FROM match_requests WHERE id = ?", (request_id,))[0], "Cancelled")

        with self.app.app_context():
            database = get_db()
            with self.assertRaises(sqlite3.IntegrityError):
                database.execute(
                    "UPDATE trips SET status = 'Unknown' WHERE id = ?", (trip_id,)
                )
            database.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                database.execute(
                    "INSERT INTO match_requests (trip_id, requester_id) VALUES (99999, 2)"
                )
            database.rollback()

    def test_reject_remove_and_cancel_trip_preserve_history(self):
        self.login("alice")
        future = (date.today() + timedelta(days=1)).isoformat()
        trip_id = self.publish(seats=2, trip_date=future)
        self.logout()

        self.login("bob")
        self.client.post(f"/trips/{trip_id}/request")
        bob_request = self.database_row(
            "SELECT id FROM match_requests WHERE trip_id = ? AND requester_id = 2", (trip_id,)
        )["id"]
        self.logout()
        self.login("alice")
        self.client.post(f"/trips/requests/{bob_request}/reject")
        self.assertEqual(self.database_row("SELECT status FROM match_requests WHERE id = ?", (bob_request,))[0], "Rejected")

        second_trip = self.publish(seats=1, trip_date=future, start="15:00", end="16:00")
        self.logout()
        self.login("carol")
        self.client.post(f"/trips/{second_trip}/request")
        carol_request = self.database_row(
            "SELECT id FROM match_requests WHERE trip_id = ? AND requester_id = 3", (second_trip,)
        )["id"]
        self.logout()
        self.login("alice")
        self.client.post(f"/trips/requests/{carol_request}/accept")
        participant_id = self.database_row(
            "SELECT id FROM trip_participants WHERE request_id = ?", (carol_request,)
        )["id"]
        self.client.post(f"/trips/participants/{participant_id}/remove")
        participation = self.database_row("SELECT * FROM trip_participants WHERE id = ?", (participant_id,))
        restored = self.database_row("SELECT * FROM trips WHERE id = ?", (second_trip,))
        self.assertEqual(participation["status"], "Removed")
        self.assertIsNotNone(participation["ended_at"])
        self.assertEqual((restored["available_seats"], restored["status"]), (1, "Open"))

        third_trip = self.publish(seats=2, trip_date=future, start="17:00", end="18:00")
        self.logout()
        self.login("bob")
        self.client.post(f"/trips/{third_trip}/request")
        pending_id = self.database_row(
            "SELECT id FROM match_requests WHERE trip_id = ? AND requester_id = 2", (third_trip,)
        )["id"]
        self.logout()
        self.login("alice")
        self.client.post(f"/trips/{third_trip}/cancel")
        self.assertEqual(self.database_row("SELECT status FROM trips WHERE id = ?", (third_trip,))[0], "Cancelled")
        self.assertEqual(self.database_row("SELECT status FROM match_requests WHERE id = ?", (pending_id,))[0], "Cancelled")

    def test_leave_then_reapply_preserves_history_and_seats(self):
        future = (date.today() + timedelta(days=60)).isoformat()
        self.login("alice")
        trip_id = self.publish(seats=1, trip_date=future, start="08:00", end="09:00")
        self.logout()
        self.login("bob")
        self.client.post(f"/trips/{trip_id}/request")
        first_request = self.database_row(
            "SELECT id FROM match_requests WHERE trip_id = ? AND requester_id = 2", (trip_id,)
        )["id"]
        self.logout()
        self.login("alice")
        self.client.post(f"/trips/requests/{first_request}/accept")
        self.logout()
        self.login("bob")
        participant_id = self.database_row(
            "SELECT id FROM trip_participants WHERE request_id = ?", (first_request,)
        )["id"]
        self.client.post(f"/trips/participants/{participant_id}/leave")
        detail = self.client.get(f"/trips/{trip_id}")
        self.assertIn(b"Request to join", detail.data)
        self.client.post(f"/trips/{trip_id}/request")
        requests = self._database_rows(
            "SELECT * FROM match_requests WHERE trip_id = ? AND requester_id = 2 ORDER BY id",
            (trip_id,),
        )
        self.assertEqual([row["status"] for row in requests], ["Cancelled", "Pending"])
        self.logout()
        self.login("alice")
        self.client.post(f"/trips/requests/{requests[-1]['id']}/accept")
        self.assertEqual(self.database_row(
            "SELECT COUNT(*) FROM trip_participants WHERE trip_id = ?", (trip_id,)
        )[0], 2)
        self.assertEqual(self.database_row(
            "SELECT available_seats FROM trips WHERE id = ?", (trip_id,)
        )[0], 0)

    def test_conflict_is_rechecked_when_request_is_accepted(self):
        future = (date.today() + timedelta(days=70)).isoformat()
        self.login("alice")
        target = self.publish(seats=2, trip_date=future, start="10:00", end="11:00")
        self.logout()
        self.login("bob")
        self.client.post(f"/trips/{target}/request")
        request_id = self.database_row(
            "SELECT id FROM match_requests WHERE trip_id = ? AND requester_id = 2", (target,)
        )["id"]
        own_trip = self.publish(seats=1, trip_date=future, start="10:30", end="11:30")
        self.assertIsNotNone(own_trip)
        self.logout()
        self.login("alice")
        response = self.client.post(
            f"/trips/requests/{request_id}/accept", follow_redirects=True
        )
        self.assertIn(b"Schedule conflict", response.data)
        self.assertEqual(self.database_row(
            "SELECT status FROM match_requests WHERE id = ?", (request_id,)
        )[0], "Pending")
        self.assertEqual(self.database_row(
            "SELECT available_seats FROM trips WHERE id = ?", (target,)
        )[0], 2)

    def test_notifications_and_cancelled_participant_state(self):
        future = (date.today() + timedelta(days=80)).isoformat()
        self.login("alice")
        trip_id = self.publish(seats=1, trip_date=future, start="13:00", end="14:00")
        self.logout()
        self.login("bob")
        self.client.post(f"/trips/{trip_id}/request")
        self.logout()
        self.login("alice")
        self.assertIn(b'notification-badge', self.client.get("/").data)
        request_id = self.database_row(
            "SELECT id FROM match_requests WHERE trip_id = ? AND requester_id = 2", (trip_id,)
        )["id"]
        self.client.post(f"/trips/requests/{request_id}/accept")
        self.client.post(f"/trips/{trip_id}/cancel")
        participant = self.database_row(
            "SELECT * FROM trip_participants WHERE request_id = ?", (request_id,)
        )
        self.assertEqual(participant["status"], "TripCancelled")
        self.assertIsNotNone(participant["ended_at"])
        self.assertEqual(self.database_row(
            "SELECT status FROM match_requests WHERE id = ?", (request_id,)
        )[0], "Cancelled")
        self.logout()
        self.login("bob")
        self.assertGreaterEqual(self.database_row(
            "SELECT COUNT(*) FROM notifications WHERE user_id = 2 AND read_at IS NULL"
        )[0], 2)
        self.assertNotIn(b"alice@example.com", self.client.get(f"/trips/{trip_id}").data)

    def test_csrf_rejects_missing_token_when_enabled(self):
        self.app.config.update(TESTING=False, CSRF_ENABLED=True)
        response = self.client.post(
            "/auth/login", data={"username": "alice", "password": "password123"}
        )
        self.assertEqual(response.status_code, 400)

    def test_publish_overlap_boundaries_and_adjacent_interval(self):
        future = (date.today() + timedelta(days=90)).isoformat()
        self.login("alice")
        first = self.publish(seats=1, trip_date=future, start="10:00", end="11:00")
        overlap = self.client.post(
            "/trips/publish",
            data={"trip_date": future, "origin_area_id": "3", "destination_area_id": "4",
                  "origin_detail": "A", "destination_detail": "B", "start_time": "11:00",
                  "end_time": "12:00", "publisher_party_size": "1", "seat_capacity": "1"},
            follow_redirects=True,
        )
        self.assertIn(b"Schedule conflict", overlap.data)
        adjacent = self.client.post(
            "/trips/publish",
            data={"trip_date": future, "origin_area_id": "3", "destination_area_id": "4",
                  "origin_detail": "A", "destination_detail": "B", "start_time": "11:01",
                  "end_time": "12:00", "publisher_party_size": "1", "seat_capacity": "1"},
            follow_redirects=False,
        )
        self.assertEqual(adjacent.status_code, 302)
        self.assertIsNotNone(first)

    def test_expired_open_trip_is_not_searchable(self):
        with self.app.app_context():
            database = get_db()
            past = (date.today() - timedelta(days=1)).isoformat()
            cursor = database.execute(
                """INSERT INTO trips
                   (publisher_id, trip_date, origin_area_id, destination_area_id,
                    start_time, end_time, publisher_party_size, seat_capacity, available_seats)
                   VALUES (1, ?, 1, 2, '09:00', '10:00', 1, 1, 1)""",
                (past,),
            )
            trip_id = cursor.lastrowid
            database.commit()
        response = self.client.get("/trips/search?origin_area_id=1&destination_area_id=2")
        self.assertNotIn(f"/trips/{trip_id}".encode(), response.data)

    def test_notification_mark_read_is_owner_only(self):
        future = (date.today() + timedelta(days=100)).isoformat()
        self.login("alice")
        trip_id = self.publish(seats=1, trip_date=future, start="07:00", end="08:00")
        self.logout()
        self.login("bob")
        self.client.post(f"/trips/{trip_id}/request")
        notification_id = self.database_row(
            "SELECT id FROM notifications WHERE user_id = 1 ORDER BY id DESC"
        )["id"]
        forbidden = self.client.post(f"/notifications/{notification_id}/read")
        self.assertEqual(forbidden.status_code, 403)
        self.logout()
        self.login("alice")
        self.client.post(f"/notifications/{notification_id}/read")
        self.assertIsNotNone(self.database_row(
            "SELECT read_at FROM notifications WHERE id = ?", (notification_id,)
        )["read_at"])

    def test_removed_user_can_reapply(self):
        future = (date.today() + timedelta(days=110)).isoformat()
        self.login("alice")
        trip_id = self.publish(seats=1, trip_date=future, start="16:00", end="17:00")
        self.logout()
        self.login("carol")
        self.client.post(f"/trips/{trip_id}/request")
        request_id = self.database_row(
            "SELECT id FROM match_requests WHERE trip_id = ? AND requester_id = 3", (trip_id,)
        )["id"]
        self.logout()
        self.login("alice")
        self.client.post(f"/trips/requests/{request_id}/accept")
        participant_id = self.database_row(
            "SELECT id FROM trip_participants WHERE request_id = ?", (request_id,)
        )["id"]
        self.client.post(f"/trips/participants/{participant_id}/remove")
        self.logout()
        self.login("carol")
        self.assertIn(b"Request to join", self.client.get(f"/trips/{trip_id}").data)
        self.client.post(f"/trips/{trip_id}/request")
        self.assertEqual(self.database_row(
            """SELECT COUNT(*) FROM match_requests
               WHERE trip_id = ? AND requester_id = 3""", (trip_id,)
        )[0], 2)


if __name__ == "__main__":
    unittest.main()
