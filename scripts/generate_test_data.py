"""Create reproducible, business-consistent synthetic data in a NEW database."""

import argparse
import random
import sqlite3
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED = 5003


def generate_database(database_path, trip_count, user_count=100, *, seed=DEFAULT_SEED, as_of=None):
    """Never overwrite a file or write inside the application's instance directory."""
    path = Path(database_path).resolve()
    if path.is_relative_to((ROOT / "instance").resolve()):
        raise ValueError("Evaluation databases must be outside the application instance directory.")
    if trip_count < 1 or user_count < 6:
        raise ValueError("Use at least one trip and six users.")
    as_of = date.fromisoformat(as_of) if isinstance(as_of, str) else (as_of or date.today())
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also rejects accidental reuse of a demo/business database.
    with path.open("xb"):
        pass
    rng = random.Random(seed)
    bookings = defaultdict(list)
    connection = sqlite3.connect(path)
    try:
        connection.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
        connection.executemany(
            """INSERT INTO users(username,password_hash,display_name,email,created_at)
               VALUES (?, 'evaluation-only', ?, ?, ?)""",
            [(f"user{i}", f"Synthetic User {i}", f"user{i}@example.test",
              f"{as_of - timedelta(days=90)} 00:00:00") for i in range(1, user_count + 1)],
        )
        connection.executemany("INSERT INTO location_areas(name) VALUES (?)",
                               [(f"Evaluation Area {i:02d}",) for i in range(1, 21)])

        def free(user, day, start, end):
            return all(end < a or start > b for a, b in bookings[(user, day)])

        def request(trip, user, state, stamp):
            return connection.execute(
                """INSERT INTO match_requests(trip_id,requester_id,status,created_at,updated_at)
                   VALUES (?,?,?,?,?)""", (trip, user, state, stamp, stamp)
            ).lastrowid

        for _ in range(trip_count):
            status = rng.choices(["Open", "Full", "Completed", "Cancelled"], [55, 15, 22, 8])[0]
            capacity = rng.randint(1, min(4, user_count - 2))
            active = (capacity if status == "Full" else
                      rng.randint(1, capacity) if status == "Completed" else
                      rng.randrange(capacity) if status == "Open" else 0)
            # Reject overlapping assignments, without changing schema or query semantics.
            for attempt in range(10000):
                offset = rng.randint(1, 30) * (-1 if status == "Completed" else 1)
                day = as_of + timedelta(days=offset)
                start = rng.choice([7, 9, 12, 15, 18, 20]) * 60 + rng.choice([0, 10, 20])
                end = start + rng.choice([45, 60, 90])
                available = [u for u in range(1, user_count + 1) if free(u, day, start, end)]
                if len(available) >= active + 2:
                    break
            else:
                raise ValueError("Requested workload exceeds the synthetic calendar's capacity.")
            publisher = rng.choice(available)
            candidates = [u for u in available if u != publisher]
            participants = rng.sample(candidates, active)
            origin = rng.choices(range(1, 21), [4] * 5 + [1] * 15)[0]
            destination = rng.choice([a for a in range(1, 21) if a != origin])
            hhmm = lambda minute: f"{minute // 60:02d}:{minute % 60:02d}"
            created = min(datetime.combine(day, time(0)) - timedelta(days=3),
                          datetime.combine(as_of, time(0)) - timedelta(days=1))
            created -= timedelta(seconds=rng.randrange(86400))
            stamp = created.isoformat(sep=" ")
            joined = (created + timedelta(hours=1)).isoformat(sep=" ")
            ended = (created + timedelta(hours=2)).isoformat(sep=" ")
            trip = connection.execute(
                """INSERT INTO trips(publisher_id,trip_date,origin_area_id,origin_detail,
                   destination_area_id,destination_detail,start_time,end_time,publisher_party_size,
                   seat_capacity,available_seats,status,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (publisher, day.isoformat(), origin, f"Pickup point {rng.randint(1, 4)}",
                 destination, f"Meeting point {rng.randint(1, 4)}", hhmm(start), hhmm(end),
                 rng.randint(1, 3), capacity, capacity - active, status, stamp, stamp),
            ).lastrowid
            if status != "Cancelled":
                for user in [publisher] + participants:
                    bookings[(user, day)].append((start, end))
            for user in participants:
                req = request(trip, user, "Accepted", joined)
                connection.execute(
                    """INSERT INTO trip_participants(trip_id,user_id,request_id,joined_at)
                       VALUES (?,?,?,?)""", (trip, user, req, joined))
                connection.execute(
                    """INSERT INTO notifications(user_id,event_type,trip_id,request_id,created_at)
                       VALUES (?,'RequestAccepted',?,?,?)""", (user, trip, req, joined))
                if status == "Completed" and rng.random() < 0.8:
                    review_time = (datetime.combine(day, time(0)) +
                                   timedelta(minutes=end, hours=2)).isoformat(sep=" ")
                    for reviewer, reviewee in [(user, publisher), (publisher, user)]:
                        connection.execute(
                            """INSERT INTO reviews(trip_id,reviewer_id,reviewee_id,rating,comment,created_at)
                               VALUES (?,?,?,?,?,?)""",
                            (trip, reviewer, reviewee, rng.choices(range(1, 6), [5, 10, 20, 35, 30])[0],
                             "Synthetic evaluation review", review_time))
            others = [u for u in candidates if u not in participants]
            rng.shuffle(others)
            for user in others[:rng.randint(0, min(3, len(others)))]:
                state = rng.choice(["Pending", "Rejected", "Cancelled"]) if status in ("Open", "Full") else rng.choice(["Rejected", "Cancelled"])
                req = request(trip, user, state, joined)
                if state == "Pending":
                    connection.execute(
                        """INSERT INTO notifications(user_id,event_type,trip_id,request_id,created_at)
                           VALUES (?,'RequestSubmitted',?,?,?)""", (publisher, trip, req, joined))
                elif state == "Cancelled" and rng.random() < 0.5:
                    history = "TripCancelled" if status == "Cancelled" else rng.choice(["Left", "Removed"])
                    connection.execute(
                        """INSERT INTO trip_participants(trip_id,user_id,request_id,status,joined_at,ended_at)
                           VALUES (?,?,?,?,?,?)""", (trip, user, req, history, joined, ended))
        connection.commit()
    finally:
        connection.close()
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trips", type=int, default=5000)
    parser.add_argument("--users", type=int, default=100)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--database", type=Path, required=True, help="NEW path outside instance/")
    args = parser.parse_args()
    try:
        path = generate_database(args.database, args.trips, args.users, seed=args.seed, as_of=args.as_of)
    except (ValueError, FileExistsError) as error:
        parser.error(str(error))
    print(f"Generated {args.trips} trips and {args.users} users in {path}")


if __name__ == "__main__":
    main()
