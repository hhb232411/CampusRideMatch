import sqlite3
from contextlib import contextmanager
from pathlib import Path

import click
from flask import current_app, g

from .area_catalog import sync_location_areas
from .demo_data import seed_demo_trips


LATEST_SCHEMA_VERSION = 2


@contextmanager
def immediate_transaction(connection):
    """Serialize business checks with their writes, including early returns."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        apply_migrations(g.db)
    return g.db


def apply_migrations(connection):
    """Upgrade existing databases in place while preserving historical rows."""
    trip_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(trips)")
    }
    if trip_columns and "publisher_party_size" not in trip_columns:
        connection.execute(
            """ALTER TABLE trips ADD COLUMN publisher_party_size INTEGER NOT NULL
               DEFAULT 1 CHECK (publisher_party_size BETWEEN 1 AND 20)"""
        )
        connection.commit()
    request_sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'match_requests'"
    ).fetchone()
    if request_sql and "UNIQUE (trip_id, requester_id)" in request_sql["sql"]:
        _migrate_request_history(connection)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            event_type TEXT NOT NULL CHECK (event_type IN (
                'RequestSubmitted', 'RequestAccepted', 'RequestRejected',
                'ParticipantRemoved', 'TripCancelled'
            )),
            trip_id INTEGER REFERENCES trips(id) ON DELETE RESTRICT,
            request_id INTEGER REFERENCES match_requests(id) ON DELETE RESTRICT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            read_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
            ON notifications(user_id, read_at, created_at DESC);
        """
    )
    connection.execute(f"PRAGMA user_version = {LATEST_SCHEMA_VERSION}")
    connection.commit()


def _migrate_request_history(connection):
    """Rebuild the two lifecycle tables so repeated historical attempts are possible."""
    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.executescript(
            """
            BEGIN IMMEDIATE;
            CREATE TABLE match_requests_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE RESTRICT,
                requester_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                status TEXT NOT NULL DEFAULT 'Pending'
                    CHECK (status IN ('Pending', 'Accepted', 'Rejected', 'Cancelled')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO match_requests_new
                SELECT id, trip_id, requester_id, status, created_at, updated_at
                FROM match_requests;

            CREATE TABLE trip_participants_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE RESTRICT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                request_id INTEGER NOT NULL UNIQUE REFERENCES match_requests_new(id) ON DELETE RESTRICT,
                status TEXT NOT NULL DEFAULT 'Active'
                    CHECK (status IN ('Active', 'Left', 'Removed', 'TripCancelled')),
                joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                ended_at TEXT,
                CHECK ((status = 'Active' AND ended_at IS NULL)
                    OR (status <> 'Active' AND ended_at IS NOT NULL))
            );
            INSERT INTO trip_participants_new
                SELECT id, trip_id, user_id, request_id, status, joined_at,
                       CASE WHEN status = 'Active' THEN NULL
                            ELSE COALESCE(ended_at, CURRENT_TIMESTAMP) END
                FROM trip_participants;

            UPDATE match_requests_new
               SET status = 'Cancelled', updated_at = CURRENT_TIMESTAMP
             WHERE status = 'Accepted'
               AND id NOT IN (
                   SELECT request_id FROM trip_participants_new WHERE status = 'Active'
               );

            DROP TABLE trip_participants;
            DROP TABLE match_requests;
            ALTER TABLE match_requests_new RENAME TO match_requests;
            ALTER TABLE trip_participants_new RENAME TO trip_participants;
            CREATE UNIQUE INDEX uq_requests_active
                ON match_requests(trip_id, requester_id)
                WHERE status IN ('Pending', 'Accepted');
            CREATE UNIQUE INDEX uq_participants_active
                ON trip_participants(trip_id, user_id)
                WHERE status = 'Active';
            CREATE INDEX idx_requests_trip_status ON match_requests(trip_id, status);
            CREATE INDEX idx_requests_user_status ON match_requests(requester_id, status);
            CREATE INDEX idx_participants_trip_status ON trip_participants(trip_id, status);
            CREATE INDEX idx_participants_user_status ON trip_participants(user_id, status);
            COMMIT;
            """
        )
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db(with_seed=False):
    connection = get_db()
    project_root = Path(current_app.root_path).parent
    connection.executescript((project_root / "schema.sql").read_text(encoding="utf-8"))
    if with_seed:
        connection.executescript((project_root / "seed.sql").read_text(encoding="utf-8"))
        seed_demo_trips(connection)
    connection.commit()


@click.command("migrate-db")
def migrate_db_command():
    """Safely upgrade an existing database without deleting its records."""
    apply_migrations(get_db())
    click.echo(f"Database schema is at version {LATEST_SCHEMA_VERSION}.")


def audit_checks(connection):
    """Count invariant violations without repairing or changing any records."""
    return {
        "foreign_keys": len(connection.execute("PRAGMA foreign_key_check").fetchall()),
        "seat_mismatch": connection.execute(
            """SELECT COUNT(*) FROM trips t
               WHERE available_seats <> seat_capacity - (
                   SELECT COUNT(*) FROM trip_participants tp
                   WHERE tp.trip_id = t.id AND tp.status = 'Active')"""
        ).fetchone()[0],
        "accepted_without_active_participant": connection.execute(
            """SELECT COUNT(*) FROM match_requests mr
               LEFT JOIN trip_participants tp
                 ON tp.request_id = mr.id AND tp.status = 'Active'
               WHERE mr.status = 'Accepted' AND tp.id IS NULL"""
        ).fetchone()[0],
        "ended_without_timestamp": connection.execute(
            """SELECT COUNT(*) FROM trip_participants
               WHERE status <> 'Active' AND ended_at IS NULL"""
        ).fetchone()[0],
        "trip_status_seat_mismatch": connection.execute(
            """SELECT COUNT(*) FROM trips
               WHERE (status = 'Full' AND available_seats <> 0)
                  OR (status = 'Open' AND available_seats <= 0)"""
        ).fetchone()[0],
        "participant_request_identity_mismatch": connection.execute(
            """SELECT COUNT(*) FROM trip_participants tp
               JOIN match_requests mr ON mr.id = tp.request_id
               WHERE tp.trip_id <> mr.trip_id OR tp.user_id <> mr.requester_id"""
        ).fetchone()[0],
        "active_participant_without_accepted_request": connection.execute(
            """SELECT COUNT(*) FROM trip_participants tp
               LEFT JOIN match_requests mr ON mr.id = tp.request_id
               WHERE tp.status = 'Active'
                 AND (mr.id IS NULL OR mr.status <> 'Accepted')"""
        ).fetchone()[0],
        "ended_participant_without_cancelled_request": connection.execute(
            """SELECT COUNT(*) FROM trip_participants tp
               JOIN match_requests mr ON mr.id = tp.request_id
               WHERE tp.status <> 'Active' AND mr.status <> 'Cancelled'"""
        ).fetchone()[0],
        "publisher_request": connection.execute(
            """SELECT COUNT(*) FROM match_requests mr
               JOIN trips t ON t.id = mr.trip_id
               WHERE mr.requester_id = t.publisher_id"""
        ).fetchone()[0],
        "publisher_participation": connection.execute(
            """SELECT COUNT(*) FROM trip_participants tp
               JOIN trips t ON t.id = tp.trip_id
               WHERE tp.user_id = t.publisher_id"""
        ).fetchone()[0],
        "terminal_trip_request_mismatch": connection.execute(
            """SELECT COUNT(*) FROM match_requests mr
               JOIN trips t ON t.id = mr.trip_id
               WHERE (t.status = 'Cancelled' AND mr.status IN ('Pending', 'Accepted'))
                  OR (t.status = 'Completed' AND mr.status = 'Pending')"""
        ).fetchone()[0],
        "cancelled_trip_participation_mismatch": connection.execute(
            """SELECT COUNT(*) FROM trip_participants tp
               JOIN trips t ON t.id = tp.trip_id
               WHERE (t.status = 'Cancelled' AND tp.status = 'Active')
                  OR (tp.status = 'TripCancelled' AND t.status <> 'Cancelled')"""
        ).fetchone()[0],
        "ineligible_review": connection.execute(
            """SELECT COUNT(*) FROM reviews r JOIN trips t ON t.id = r.trip_id
               WHERE t.status <> 'Completed'
                  OR (r.reviewer_id <> t.publisher_id AND NOT EXISTS (
                      SELECT 1 FROM trip_participants tp WHERE tp.trip_id = r.trip_id
                      AND tp.user_id = r.reviewer_id AND tp.status = 'Active'))
                  OR (r.reviewee_id <> t.publisher_id AND NOT EXISTS (
                      SELECT 1 FROM trip_participants tp WHERE tp.trip_id = r.trip_id
                      AND tp.user_id = r.reviewee_id AND tp.status = 'Active'))"""
        ).fetchone()[0],
    }


@click.command("audit-db")
def audit_db_command():
    """Report relational and lifecycle invariant violations from one snapshot."""
    connection = get_db()
    connection.execute("BEGIN")
    try:
        checks = audit_checks(connection)
    finally:
        connection.rollback()
    for name, count in checks.items():
        click.echo(f"{name}: {count}")
    if any(checks.values()):
        raise click.ClickException("Database audit found invariant violations.")
    click.echo("Database audit passed.")


@click.command("sync-areas")
def sync_areas_command():
    """Non-destructively add the current bilingual location catalog."""
    connection = get_db()
    sync_location_areas(connection)
    connection.commit()
    click.echo("Synchronized bilingual location areas.")


@click.command("seed-demo")
def seed_demo_command():
    """Non-destructively add the 20 demonstration trips."""
    connection = get_db()
    sync_location_areas(connection)
    created = seed_demo_trips(connection)
    connection.commit()
    click.echo(f"Demo data ready: {created} trips added, 20 demo trips defined.")


@click.command("init-db")
@click.option("--with-seed", is_flag=True, help="Load demonstration accounts and trips.")
def init_db_command(with_seed):
    init_db(with_seed=with_seed)
    click.echo("Initialized the database." + (" Seed data loaded." if with_seed else ""))


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(sync_areas_command)
    app.cli.add_command(seed_demo_command)
    app.cli.add_command(migrate_db_command)
    app.cli.add_command(audit_db_command)
