PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS reviews;
DROP TABLE IF EXISTS notifications;
DROP TABLE IF EXISTS trip_participants;
DROP TABLE IF EXISTS match_requests;
DROP TABLE IF EXISTS trips;
DROP TABLE IF EXISTS location_areas;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    phone TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(username)) BETWEEN 3 AND 30),
    CHECK (length(trim(display_name)) BETWEEN 1 AND 60),
    CHECK (length(trim(email)) >= 3)
);

CREATE TABLE location_areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publisher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    trip_date TEXT NOT NULL,
    origin_area_id INTEGER NOT NULL REFERENCES location_areas(id) ON DELETE RESTRICT,
    origin_detail TEXT,
    destination_area_id INTEGER NOT NULL REFERENCES location_areas(id) ON DELETE RESTRICT,
    destination_detail TEXT,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    publisher_party_size INTEGER NOT NULL DEFAULT 1
        CHECK (publisher_party_size BETWEEN 1 AND 20),
    seat_capacity INTEGER NOT NULL CHECK (seat_capacity BETWEEN 1 AND 20),
    available_seats INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'Open'
        CHECK (status IN ('Open', 'Full', 'Completed', 'Cancelled')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (trip_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    CHECK (start_time GLOB '[0-2][0-9]:[0-5][0-9]'),
    CHECK (end_time GLOB '[0-2][0-9]:[0-5][0-9]'),
    CHECK (CAST(substr(start_time, 1, 2) AS INTEGER) BETWEEN 0 AND 23),
    CHECK (CAST(substr(end_time, 1, 2) AS INTEGER) BETWEEN 0 AND 23),
    CHECK (start_time <= end_time),
    CHECK (available_seats BETWEEN 0 AND seat_capacity),
    CHECK ((status = 'Full' AND available_seats = 0)
        OR (status = 'Open' AND available_seats > 0)
        OR status IN ('Completed', 'Cancelled'))
);

CREATE TABLE match_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE RESTRICT,
    requester_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'Pending'
        CHECK (status IN ('Pending', 'Accepted', 'Rejected', 'Cancelled')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX uq_requests_active
    ON match_requests(trip_id, requester_id)
    WHERE status IN ('Pending', 'Accepted');

CREATE TABLE trip_participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE RESTRICT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    request_id INTEGER NOT NULL UNIQUE REFERENCES match_requests(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'Active'
        CHECK (status IN ('Active', 'Left', 'Removed', 'TripCancelled')),
    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TEXT,
    CHECK ((status = 'Active' AND ended_at IS NULL)
        OR (status <> 'Active' AND ended_at IS NOT NULL))
);

CREATE UNIQUE INDEX uq_participants_active
    ON trip_participants(trip_id, user_id)
    WHERE status = 'Active';

CREATE TABLE notifications (
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

CREATE TABLE reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE RESTRICT,
    reviewer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    reviewee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (reviewer_id <> reviewee_id),
    UNIQUE (trip_id, reviewer_id, reviewee_id)
);

CREATE INDEX idx_trips_search
    ON trips(trip_date, origin_area_id, destination_area_id, status, start_time, end_time);
CREATE INDEX idx_trips_publisher ON trips(publisher_id, status);
CREATE INDEX idx_requests_trip_status ON match_requests(trip_id, status);
CREATE INDEX idx_requests_user_status ON match_requests(requester_id, status);
CREATE INDEX idx_participants_trip_status ON trip_participants(trip_id, status);
CREATE INDEX idx_participants_user_status ON trip_participants(user_id, status);
CREATE INDEX idx_notifications_user_unread ON notifications(user_id, read_at, created_at DESC);
CREATE INDEX idx_reviews_reviewee ON reviews(reviewee_id);
