# Campus Ride Match ER Diagram

This diagram represents the tables and columns in `schema.sql`. Partial unique indexes and detailed checks are described in [DATABASE_DESIGN.md](DATABASE_DESIGN.md).

```mermaid
erDiagram
    USERS {
        INTEGER id PK
        TEXT username UK
        TEXT password_hash
        TEXT display_name
        TEXT email UK
        TEXT phone
        TEXT created_at
    }
    LOCATION_AREAS {
        INTEGER id PK
        TEXT name UK
        INTEGER is_active
    }
    TRIPS {
        INTEGER id PK
        INTEGER publisher_id FK
        TEXT trip_date
        INTEGER origin_area_id FK
        TEXT origin_detail
        INTEGER destination_area_id FK
        TEXT destination_detail
        TEXT start_time
        TEXT end_time
        INTEGER publisher_party_size
        INTEGER seat_capacity
        INTEGER available_seats
        TEXT status
        TEXT created_at
        TEXT updated_at
    }
    MATCH_REQUESTS {
        INTEGER id PK
        INTEGER trip_id FK
        INTEGER requester_id FK
        TEXT status
        TEXT created_at
        TEXT updated_at
    }
    TRIP_PARTICIPANTS {
        INTEGER id PK
        INTEGER trip_id FK
        INTEGER user_id FK
        INTEGER request_id FK_UK
        TEXT status
        TEXT joined_at
        TEXT ended_at
    }
    NOTIFICATIONS {
        INTEGER id PK
        INTEGER user_id FK
        TEXT event_type
        INTEGER trip_id FK
        INTEGER request_id FK
        TEXT created_at
        TEXT read_at
    }
    REVIEWS {
        INTEGER id PK
        INTEGER trip_id FK
        INTEGER reviewer_id FK
        INTEGER reviewee_id FK
        INTEGER rating
        TEXT comment
        TEXT created_at
    }

    USERS ||--o{ TRIPS : publishes
    LOCATION_AREAS ||--o{ TRIPS : origin_for
    LOCATION_AREAS ||--o{ TRIPS : destination_for
    USERS ||--o{ MATCH_REQUESTS : submits
    TRIPS ||--o{ MATCH_REQUESTS : receives
    USERS ||--o{ TRIP_PARTICIPANTS : joins
    TRIPS ||--o{ TRIP_PARTICIPANTS : has
    MATCH_REQUESTS ||--o| TRIP_PARTICIPANTS : creates_when_accepted
    USERS ||--o{ NOTIFICATIONS : receives
    TRIPS o|--o{ NOTIFICATIONS : concerns
    MATCH_REQUESTS o|--o{ NOTIFICATIONS : concerns
    TRIPS ||--o{ REVIEWS : contextualizes
    USERS ||--o{ REVIEWS : writes_as_reviewer
    USERS ||--o{ REVIEWS : receives_as_reviewee
```

The `USERS`–`TRIPS` many-to-many participation relationship is resolved by `TRIP_PARTICIPANTS`. `MATCH_REQUESTS` preserves application history, while `TRIP_PARTICIPANTS` records the participation produced by an accepted request. A trip publisher is not duplicated in `TRIP_PARTICIPANTS`.
