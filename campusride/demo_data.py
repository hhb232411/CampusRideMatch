"""Idempotent demonstration data for classroom demos and screenshots."""

from datetime import date, timedelta


DEMO_TRIPS = (
    ("alice", 30, "Kowloon Tong 九龙塘", "CityU main entrance", "Mong Kok 旺角", "Langham Place", "17:30", "19:00", 3, "Open"),
    ("bob", 1, "Pok Fu Lam 薄扶林", "HKU station exit A", "Central 中环", "Exchange Square", "08:00", "09:15", 2, "Open"),
    ("carol", 2, "University Station 大学站", "MTR station exit B", "Sha Tin 沙田", "New Town Plaza", "17:20", "18:40", 3, "Open"),
    ("alice", 3, "Clear Water Bay 清水湾", "University north gate", "Hang Hau 坑口", "Hang Hau MTR", "16:30", "18:00", 1, "Full"),
    ("bob", 4, "Hung Hom 红磡", "Station concourse", "Tsim Sha Tsui 尖沙咀", "Harbour City", "12:00", "13:10", 2, "Open"),
    ("carol", 5, "Tuen Mun 屯门", "Town centre", "Central 中环", "Hong Kong Station", "07:15", "08:45", 3, "Open"),
    ("alice", 6, "Tai Po 大埔", "Tai Po Market Station", "Kowloon Tong 九龙塘", "Festival Walk", "09:00", "10:30", 2, "Open"),
    ("bob", 7, "Ho Man Tin 何文田", "MTR exit A", "Mong Kok 旺角", "MOKO", "14:00", "15:15", 2, "Open"),
    ("carol", 8, "Braemar Hill 宝马山", "Campus entrance", "Causeway Bay 铜锣湾", "Times Square", "18:00", "19:20", 2, "Open"),
    ("alice", 9, "Siu Lek Yuen 小沥源", "Siu Lek Yuen Road", "Sha Tin 沙田", "Sha Tin Station", "11:30", "12:30", 3, "Open"),
    ("bob", 10, "Tseung Kwan O 将军澳", "PopCorn mall", "Kwun Tong 观塘", "apm", "17:00", "18:30", 1, "Full"),
    ("carol", 11, "Tsuen Wan 荃湾", "Tsuen Wan Station", "Kwai Fong 葵芳", "Metroplaza", "13:15", "14:15", 2, "Open"),
    ("alice", 12, "Wan Chai 湾仔", "Convention Centre", "Central 中环", "IFC", "18:10", "19:10", 2, "Open"),
    ("bob", 13, "Chai Wan 柴湾", "Chai Wan Station", "Quarry Bay 鲗鱼涌", "Taikoo Place", "08:20", "09:20", 3, "Open"),
    ("carol", 14, "Yuen Long 元朗", "YOHO Mall", "Tuen Mun 屯门", "Tuen Mun Station", "15:00", "16:20", 2, "Open"),
    ("alice", 15, "Tin Shui Wai 天水围", "Tin Shui Wai Station", "Yuen Long 元朗", "Yuen Long Station", "10:00", "11:00", 3, "Open"),
    ("bob", -1, "Kowloon Tong 九龙塘", "Festival Walk", "Hung Hom 红磡", "PolyU entrance", "10:30", "11:30", 2, "Completed"),
    ("carol", -2, "Pok Fu Lam 薄扶林", "Pok Fu Lam Road", "Central 中环", "Central Pier", "14:00", "15:30", 2, "Completed"),
    ("alice", -3, "Sha Tin 沙田", "Sha Tin Station", "University Station 大学站", "University Station", "08:30", "09:30", 2, "Completed"),
    ("bob", 20, "Hong Kong International Airport 香港国际机场", "Terminal 1", "Tung Chung 东涌", "Citygate", "20:00", "21:00", 2, "Cancelled"),
)


def seed_demo_trips(connection):
    """Ensure the 20 demo trips exist; return the number newly inserted."""
    users = {
        row["username"]: row["id"]
        for row in connection.execute("SELECT id, username FROM users")
    }
    areas = {
        row["name"]: row["id"]
        for row in connection.execute("SELECT id, name FROM location_areas WHERE is_active = 1")
    }
    required_users = {"alice", "bob", "carol"}
    if not required_users.issubset(users):
        raise RuntimeError("Demo accounts are missing. Initialize with --with-seed first.")

    created = 0
    demo_trip_ids = []
    user_order = (users["alice"], users["bob"], users["carol"])
    today = date.today()
    for index, (username, day_offset, origin, origin_detail, destination, destination_detail,
                start_time, end_time, capacity, status) in enumerate(DEMO_TRIPS):
        if origin not in areas or destination not in areas:
            raise RuntimeError(f"Demo area is missing: {origin} or {destination}")
        publisher_id = users[username]
        trip_date = (today + timedelta(days=day_offset)).isoformat()
        existing = connection.execute(
            """
            SELECT id FROM trips
            WHERE publisher_id = ? AND trip_date = ? AND origin_area_id = ?
              AND destination_area_id = ? AND start_time = ? AND end_time = ?
            """,
            (publisher_id, trip_date, areas[origin], areas[destination], start_time, end_time),
        ).fetchone()
        # Recognize the original one-row seed even if SQLite UTC and local dates differed.
        if not existing and index == 0:
            existing = connection.execute(
                """
                SELECT id FROM trips
                WHERE publisher_id = ? AND origin_area_id = ? AND destination_area_id = ?
                  AND start_time = ? AND end_time = ? AND status = 'Open'
                """,
                (publisher_id, areas[origin], areas[destination], start_time, end_time),
            ).fetchone()
        if existing:
            demo_trip_ids.append(existing["id"])
            connection.execute(
                "UPDATE trips SET publisher_party_size = ? WHERE id = ?",
                (1 + (index % 3), existing["id"]),
            )
            continue

        available_seats = 0 if status == "Full" else capacity
        if status == "Completed":
            available_seats = capacity - 1
        cursor = connection.execute(
            """
            INSERT INTO trips (
                publisher_id, trip_date, origin_area_id, origin_detail,
                destination_area_id, destination_detail, start_time, end_time,
                publisher_party_size, seat_capacity, available_seats, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (publisher_id, trip_date, areas[origin], origin_detail,
             areas[destination], destination_detail, start_time, end_time,
             1 + (index % 3), capacity, available_seats, status),
        )
        trip_id = cursor.lastrowid
        demo_trip_ids.append(trip_id)
        created += 1

        if status in ("Full", "Completed"):
            publisher_index = user_order.index(publisher_id)
            participant_id = user_order[(publisher_index + 1) % len(user_order)]
            request_cursor = connection.execute(
                """INSERT INTO match_requests (trip_id, requester_id, status)
                   VALUES (?, ?, 'Accepted')""",
                (trip_id, participant_id),
            )
            connection.execute(
                """INSERT INTO trip_participants (trip_id, user_id, request_id)
                   VALUES (?, ?, ?)""",
                (trip_id, participant_id, request_cursor.lastrowid),
            )
            if status == "Completed":
                connection.execute(
                    """INSERT INTO reviews (trip_id, reviewer_id, reviewee_id, rating, comment)
                       VALUES (?, ?, ?, 5, ?)""",
                    (trip_id, participant_id, publisher_id, "Reliable and easy to coordinate with."),
                )

    # Keep one realistic pending request so the request-management JOIN can be
    # demonstrated immediately after a fresh seeded initialization.
    connection.execute(
        """INSERT OR IGNORE INTO match_requests (trip_id, requester_id, status)
           VALUES (?, ?, 'Pending')""",
        (demo_trip_ids[0], users["bob"]),
    )

    return created
