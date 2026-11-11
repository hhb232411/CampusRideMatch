"""Deterministic transaction, expiry, audit and migration regressions.

Every database is temporary. Concurrency tests pause real Flask requests at a
SQL checkpoint, verify the write reservation with an independent connection,
then let a competing request attempt BEGIN IMMEDIATE before releasing the first.
No sleeps or probabilistic scheduling are used.
"""

import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

from click.testing import CliRunner
from flask import g, session
from flask.cli import ScriptInfo, cli

from campusride import create_app
from campusride.db import apply_migrations, audit_checks, get_db, init_db
from tests import test_app


class CorrectnessTestCase(unittest.TestCase):
    setUp = test_app.CampusRideTestCase.setUp
    tearDown = test_app.CampusRideTestCase.tearDown
    login = test_app.CampusRideTestCase.login
    logout = test_app.CampusRideTestCase.logout
    database_row = test_app.CampusRideTestCase.database_row

    def connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def make_trip(self, day=None, start="10:00", end="11:00", publisher=1):
        day = day or (date.today() + timedelta(days=180)).isoformat()
        with closing(self.connect()) as connection, connection:
            return connection.execute(
                """INSERT INTO trips (publisher_id, trip_date, origin_area_id,
                   destination_area_id, start_time, end_time, seat_capacity, available_seats)
                   VALUES (?, ?, 1, 2, ?, ?, 1, 1)""",
                (publisher, day, start, end),
            ).lastrowid

    def make_request(self, trip_id, requester=2):
        with closing(self.connect()) as connection, connection:
            return connection.execute(
                "INSERT INTO match_requests (trip_id, requester_id) VALUES (?, ?)",
                (trip_id, requester),
            ).lastrowid

    def form(self, day=None, start="12:00", end="13:00"):
        return {
            "trip_date": day or (date.today() + timedelta(days=180)).isoformat(),
            "origin_area_id": "1", "destination_area_id": "2",
            "start_time": start, "end_time": end,
            "seat_capacity": "1", "publisher_party_size": "1",
            "origin_detail": "Updated meeting point", "destination_detail": "Destination",
        }

    def assert_clean(self):
        with closing(self.connect()) as connection:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertFalse(any(audit_checks(connection).values()), audit_checks(connection))

    def snapshot(self):
        with closing(self.connect()) as connection:
            return {
                table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY id")]
                for table in ("users", "location_areas", "trips", "match_requests",
                              "trip_participants", "notifications", "reviews")
            }

    def run_interleaving(self, first, second, checkpoint):
        """Requests are (path, form, user_id); both connections load before locking."""
        ready = [threading.Event(), threading.Event()]
        start = [threading.Event(), threading.Event()]
        checked = threading.Event()
        release = threading.Event()
        second_attempt = threading.Event()
        responses, failures = {}, {}
        owner = self

        class ObservedConnection:
            def __init__(self, connection, role):
                self.connection, self.role = connection, role
                self.paused = False

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def execute(self, sql, parameters=()):
                normalized = " ".join(sql.split())
                if self.role == 1 and normalized == "BEGIN IMMEDIATE":
                    second_attempt.set()
                result = self.connection.execute(sql, parameters)
                if self.role == 0 and not self.paused and checkpoint in normalized:
                    self.paused = True
                    try:
                        owner.assertTrue(self.connection.in_transaction,
                                         "Business state was read before acquiring the write lock")
                        with closing(sqlite3.connect(owner.database_path, timeout=0)) as probe:
                            with owner.assertRaises(sqlite3.OperationalError) as blocked:
                                probe.execute("BEGIN IMMEDIATE")
                            owner.assertIn("locked", str(blocked.exception))
                    finally:
                        checked.set()
                    if not release.wait(10):
                        raise AssertionError("Timed out releasing SQL checkpoint")
                return result

        def worker(role, operation):
            path, data, user_id = operation
            try:
                with self.app.test_request_context(path, method="POST", data=data):
                    session["user_id"] = user_id
                    self.app.preprocess_request()
                    g.db = ObservedConnection(get_db(), role)
                    ready[role].set()
                    if not start[role].wait(10):
                        raise AssertionError("Timed out starting request")
                    response = self.app.make_response(self.app.dispatch_request())
                    responses[role] = (response.status_code, response.get_data(as_text=True))
            except BaseException as error:
                failures[role] = error
                ready[role].set()
                if role == 0:
                    checked.set()

        threads = [threading.Thread(target=worker, args=(i, operation), daemon=True)
                   for i, operation in enumerate((first, second))]
        for thread in threads:
            thread.start()
        try:
            for event in ready:
                self.assertTrue(event.wait(10), "Database connection preparation timed out")
            self.assertFalse(failures, failures)
            start[0].set()
            self.assertTrue(checked.wait(10), "First request did not reach its SQL checkpoint")
            self.assertFalse(failures, failures)
            start[1].set()
            self.assertTrue(second_attempt.wait(10), "Competing request did not attempt its transaction")
        finally:
            release.set()
            for event in start:
                event.set()
            for thread in threads:
                thread.join(10)
        self.assertFalse(any(thread.is_alive() for thread in threads), "Request thread leaked")
        self.assertFalse(failures, failures)
        self.assertEqual(set(responses), {0, 1})
        self.assert_clean()
        return responses

    def test_edit_and_accept_are_serialized_in_both_orders(self):
        for offset, edit_first in enumerate((True, False)):
            with self.subTest(edit_first=edit_first):
                day = (date.today() + timedelta(days=180 + offset)).isoformat()
                trip_id = self.make_trip(day)
                request_id = self.make_request(trip_id)
                edit = (f"/trips/{trip_id}/edit", self.form(day), 1)
                accept = (f"/trips/requests/{request_id}/accept", {}, 1)
                responses = self.run_interleaving(
                    edit if edit_first else accept, accept if edit_first else edit,
                    "SELECT COUNT(*) FROM trip_participants" if edit_first
                    else "SELECT mr.*, t.publisher_id",
                )
                self.assertEqual([responses[i][0] for i in (0, 1)], [302, 302])
                trip = self.database_row("SELECT * FROM trips WHERE id = ?", (trip_id,))
                self.assertEqual((trip["available_seats"], trip["status"]), (0, "Full"))
                self.assertEqual(trip["start_time"], "12:00" if edit_first else "10:00")
                self.assertEqual(self.database_row(
                    "SELECT COUNT(*) FROM trip_participants WHERE trip_id = ? AND status = 'Active'",
                    (trip_id,),
                )[0], 1)

    def test_complete_and_cancel_preserve_first_terminal_state(self):
        for offset, first_action in enumerate(("complete", "cancel")):
            with self.subTest(first_action=first_action):
                trip_id = self.make_trip(date.today().isoformat(), f"0{offset}:00", f"0{offset}:30")
                request_id = self.make_request(trip_id)
                # Preserve a real accepted participant through completion, or end it on cancellation.
                with closing(self.connect()) as connection, connection:
                    connection.execute("UPDATE match_requests SET status='Accepted' WHERE id=?", (request_id,))
                    connection.execute("INSERT INTO trip_participants(trip_id,user_id,request_id) VALUES(?,2,?)",
                                       (trip_id, request_id))
                    connection.execute("UPDATE trips SET status='Full',available_seats=0 WHERE id=?", (trip_id,))
                second_action = "cancel" if first_action == "complete" else "complete"
                self.run_interleaving(
                    (f"/trips/{trip_id}/{first_action}", {}, 1),
                    (f"/trips/{trip_id}/{second_action}", {}, 1), "SELECT t.*, p.display_name",
                )
                self.assertEqual(self.database_row("SELECT status FROM trips WHERE id=?", (trip_id,))[0],
                                 "Completed" if first_action == "complete" else "Cancelled")
                self.assertEqual(self.database_row("SELECT status FROM trip_participants WHERE request_id=?",
                                                   (request_id,))[0],
                                 "Active" if first_action == "complete" else "TripCancelled")

    def test_simultaneous_overlapping_publishes_create_only_one_trip(self):
        data = self.form()
        responses = self.run_interleaving(
            ("/trips/publish", data, 1), ("/trips/publish", data, 1), "SELECT DISTINCT t.id",
        )
        self.assertEqual((responses[0][0], responses[1][0]), (302, 200))
        self.assertIn("Schedule conflict", responses[1][1])
        self.assertEqual(self.database_row("SELECT COUNT(*) FROM trips WHERE trip_date=?",
                                           (data["trip_date"],))[0], 1)

    def test_publish_and_accept_recheck_the_same_users_schedule(self):
        for offset, publish_first in enumerate((True, False)):
            with self.subTest(publish_first=publish_first):
                day = (date.today() + timedelta(days=190 + offset)).isoformat()
                trip_id = self.make_trip(day)
                request_id = self.make_request(trip_id)
                publish = ("/trips/publish", self.form(day, "10:30", "11:30"), 2)
                accept = (f"/trips/requests/{request_id}/accept", {}, 1)
                self.run_interleaving(publish if publish_first else accept,
                                      accept if publish_first else publish, "SELECT DISTINCT t.id")
                self.assertEqual(self.database_row("SELECT status FROM match_requests WHERE id=?",
                                                   (request_id,))[0],
                                 "Pending" if publish_first else "Accepted")
                self.assertEqual(self.database_row("SELECT COUNT(*) FROM trips WHERE publisher_id=2 AND trip_date=?",
                                                   (day,))[0], 1 if publish_first else 0)

    def test_expiry_is_consistent_for_post_search_and_detail(self):
        today = date.today()
        self.clock.now.return_value = datetime.combine(today, datetime.min.time()).replace(
            hour=10, minute=30, second=59)
        cases = ((today - timedelta(days=1), "11:00", True),
                 (today, "10:29", True), (today, "10:30", False),
                 (today, "11:00", False), (today + timedelta(days=1), "11:00", False))
        for day, end, expired in cases:
            with self.subTest(day=day, end=end):
                with self.app.app_context():
                    init_db(with_seed=True)
                trip_id = self.make_trip(day.isoformat(), "10:00", end)
                self.logout()
                self.login("bob")
                search = self.client.get("/trips/search")
                detail = self.client.get(f"/trips/{trip_id}")
                self.assertEqual(f"/trips/{trip_id}".encode() in search.data, not expired)
                self.assertEqual(b"Request to join" in detail.data, not expired)
                self.client.post(f"/trips/{trip_id}/request")
                pending = self.database_row("SELECT id FROM match_requests WHERE trip_id=?", (trip_id,))
                if expired:
                    self.assertIsNone(pending)
                    request_id = self.make_request(trip_id)  # A request submitted before expiry.
                else:
                    self.assertIsNotNone(pending)
                    request_id = pending[0]
                self.logout()
                self.login("alice")
                before = self.snapshot()
                result = self.client.post(f"/trips/requests/{request_id}/accept", follow_redirects=True)
                if expired:
                    self.assertIn(b"has expired", result.data)
                    self.assertEqual(self.snapshot(), before)
                else:
                    self.assertEqual(self.database_row("SELECT status FROM match_requests WHERE id=?",
                                                       (request_id,))[0], "Accepted")
                self.assert_clean()

    def test_accept_reads_updated_expiry_after_waiting_for_edit(self):
        self.clock.now.return_value = datetime.combine(date.today(), datetime.min.time()).replace(hour=11)
        trip_id = self.make_trip()
        request_id = self.make_request(trip_id)
        self.run_interleaving(
            (f"/trips/{trip_id}/edit", self.form(date.today().isoformat(), "09:00", "10:00"), 1),
            (f"/trips/requests/{request_id}/accept", {}, 1), "SELECT COUNT(*) FROM trip_participants",
        )
        self.assertEqual(self.database_row("SELECT status FROM match_requests WHERE id=?", (request_id,))[0], "Pending")
        self.assertEqual(self.database_row("SELECT available_seats FROM trips WHERE id=?", (trip_id,))[0], 1)

    def test_mid_acceptance_failure_rolls_back_all_tables(self):
        trip_id = self.make_trip()
        request_id = self.make_request(trip_id)
        self.login("alice")
        for table, condition in (("trip_participants", "1"),
                                 ("notifications", "NEW.event_type = 'RequestAccepted'")):
            with self.subTest(failure_at=table):
                before = self.snapshot()
                with closing(self.connect()) as connection, connection:
                    connection.execute(f"""CREATE TRIGGER audit_injected_failure BEFORE INSERT ON {table}
                        WHEN {condition} BEGIN SELECT RAISE(ABORT, 'injected failure'); END""")
                try:
                    with self.assertRaisesRegex(sqlite3.IntegrityError, "injected failure"):
                        self.client.post(f"/trips/requests/{request_id}/accept")
                    self.assertEqual(self.snapshot(), before)
                    self.assert_clean()
                finally:
                    with closing(self.connect()) as connection, connection:
                        connection.execute("DROP TRIGGER audit_injected_failure")
        # The connection/transaction is usable after each failure.
        self.client.post(f"/trips/requests/{request_id}/accept")
        self.assertEqual(self.database_row("SELECT status FROM match_requests WHERE id=?", (request_id,))[0], "Accepted")
        self.assert_clean()

    def test_audit_detects_relational_and_lifecycle_corruption(self):
        self.assert_clean()
        corruptions = (
            ("participant_request_identity_mismatch", "UPDATE trip_participants SET user_id=3 WHERE id=1"),
            ("participant_request_identity_mismatch", "UPDATE trip_participants SET trip_id=1 WHERE id=1"),
            ("active_participant_without_accepted_request", "UPDATE match_requests SET status='Pending' WHERE id=(SELECT request_id FROM trip_participants WHERE id=1)"),
            ("ended_participant_without_cancelled_request", "UPDATE trip_participants SET status='Left',ended_at=CURRENT_TIMESTAMP WHERE id=1"),
            ("publisher_request", "INSERT INTO match_requests(trip_id,requester_id) VALUES(1,1)"),
            ("publisher_participation", "UPDATE trip_participants SET user_id=1 WHERE id=1"),
            ("terminal_trip_request_mismatch", "UPDATE trips SET status='Completed' WHERE id=1"),
            ("cancelled_trip_participation_mismatch", "UPDATE trips SET status='Cancelled' WHERE id=(SELECT trip_id FROM trip_participants WHERE id=1)"),
            ("ineligible_review", "UPDATE reviews SET trip_id=1 WHERE id=1"),
            ("seat_mismatch", "UPDATE trips SET available_seats=1,status='Open' WHERE id=(SELECT trip_id FROM trip_participants WHERE id=1)"),
        )
        with closing(self.connect()) as connection:
            for key, sql in corruptions:
                with self.subTest(check=key, sql=sql):
                    connection.execute("SAVEPOINT corruption")
                    try:
                        connection.execute(sql)
                        self.assertGreater(audit_checks(connection)[key], 0)
                    finally:
                        connection.execute("ROLLBACK TO corruption")
                        connection.execute("RELEASE corruption")
        clean = CliRunner().invoke(cli, ["audit-db"], obj=ScriptInfo(create_app=lambda: self.app))
        self.assertEqual(clean.exit_code, 0, clean.output)
        with closing(self.connect()) as connection, connection:
            connection.execute("UPDATE trip_participants SET user_id=3 WHERE id=1")
        before = self.snapshot()
        failed = CliRunner().invoke(cli, ["audit-db"], obj=ScriptInfo(create_app=lambda: self.app))
        self.assertNotEqual(failed.exit_code, 0)
        self.assertIn("participant_request_identity_mismatch: 1", failed.output)
        self.assertEqual(self.snapshot(), before, "Audit must not repair records silently")

    def test_withdrawal_refuses_inconsistent_request_link(self):
        trip_id = self.make_trip()
        request_id = self.make_request(trip_id)
        self.login("alice")
        self.client.post(f"/trips/requests/{request_id}/accept")
        participant_id = self.database_row("SELECT id FROM trip_participants WHERE request_id=?", (request_id,))[0]
        with closing(self.connect()) as connection, connection:
            connection.execute("UPDATE match_requests SET requester_id=3 WHERE id=?", (request_id,))
        before = self.snapshot()
        result = self.client.post(f"/trips/participants/{participant_id}/remove", follow_redirects=True)
        self.assertIn(b"data is inconsistent", result.data)
        self.assertEqual(self.snapshot(), before)

    def test_fresh_initialization_and_current_migration_are_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fresh.sqlite"
            app = create_app({"TESTING": True, "SECRET_KEY": "test", "DATABASE": str(path)})
            runner = CliRunner()
            for args in (["init-db", "--with-seed"], ["migrate-db"], ["migrate-db"], ["audit-db"]):
                result = runner.invoke(cli, args, obj=ScriptInfo(create_app=lambda: app))
                self.assertEqual(result.exit_code, 0, (result.output, result.exception))
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM trips").fetchone()[0], 20)
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        before = self.snapshot()
        with self.app.app_context():
            apply_migrations(get_db())
            apply_migrations(get_db())
        self.assertEqual(self.snapshot(), before)
        self.assert_clean()

    def test_legacy_request_history_migration_preserves_rows(self):
        # Reconstruct the legacy variants that apply_migrations explicitly supports.
        schema = (Path(__file__).resolve().parents[1] / "schema.sql").read_text(encoding="utf-8")
        schema = schema.replace("    publisher_party_size INTEGER NOT NULL DEFAULT 1\n        CHECK (publisher_party_size BETWEEN 1 AND 20),\n", "")
        schema = schema.replace("updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP\n);\n\nCREATE UNIQUE INDEX uq_requests_active\n    ON match_requests(trip_id, requester_id)\n    WHERE status IN ('Pending', 'Accepted');",
                                "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,\n    UNIQUE (trip_id, requester_id)\n);")
        self.assertIn("UNIQUE (trip_id, requester_id)", schema)
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.row_factory = sqlite3.Row
            connection.executescript(schema)
            connection.executescript("""
                INSERT INTO users(username,password_hash,display_name,email) VALUES
                    ('owner','test','Owner','owner@example.test'),
                    ('guest','test','Guest','guest@example.test'),
                    ('former','test','Former','former@example.test');
                INSERT INTO location_areas(name) VALUES ('A'),('B');
                INSERT INTO trips(publisher_id,trip_date,origin_area_id,destination_area_id,
                    start_time,end_time,seat_capacity,available_seats) VALUES
                    (1,'2099-01-01',1,2,'10:00','11:00',2,1);
                INSERT INTO match_requests(trip_id,requester_id,status) VALUES
                    (1,2,'Accepted'),(1,3,'Accepted');
                INSERT INTO trip_participants(trip_id,user_id,request_id,status,ended_at) VALUES
                    (1,2,1,'Active',NULL),(1,3,2,'Left','2026-01-01 00:00:00');
                INSERT INTO notifications(user_id,event_type,trip_id,request_id)
                    VALUES(2,'RequestAccepted',1,1);
            """)
            for _ in range(2):
                apply_migrations(connection)
                self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertFalse(any(audit_checks(connection).values()), audit_checks(connection))
            self.assertEqual(connection.execute("SELECT publisher_party_size FROM trips").fetchone()[0], 1)
            self.assertEqual([row[0] for row in connection.execute("SELECT status FROM match_requests ORDER BY id")],
                             ["Accepted", "Cancelled"])
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM trip_participants").fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT request_id FROM notifications").fetchone()[0], 1)
            connection.execute("INSERT INTO match_requests(trip_id,requester_id) VALUES(1,3)")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO match_requests(trip_id,requester_id) VALUES(1,3)")


if __name__ == "__main__":
    unittest.main()
