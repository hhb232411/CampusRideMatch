"""Application SQL extraction, timing-independent workload selection and validation."""

import ast
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from campusride.db import audit_checks

PERFORMANCE_INDEXES = (
    "idx_trips_search", "idx_trips_publisher", "idx_requests_trip_status",
    "idx_requests_user_status", "idx_participants_trip_status", "idx_participants_user_status",
    "idx_notifications_user_unread", "idx_reviews_reviewee",
)
TABLES = ("users", "location_areas", "trips", "match_requests", "trip_participants", "reviews", "notifications")


def application_sql(function, marker, clauses=None):
    """Read SELECT text from the application without changing/importing its routes.

    Only search() has a dynamic SQL fragment: the known parameterized WHERE list.
    Refuse unknown dynamic expressions rather than silently changing the workload.
    """
    tree = ast.parse((ROOT / "campusride" / "trips.py").read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
    matches = []
    for call in ast.walk(node):
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute) or call.func.attr != "execute" or not call.args:
            continue
        arg = call.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            sql = arg.value
        elif isinstance(arg, ast.JoinedStr) and function == "search":
            pieces = []
            for value in arg.values:
                if isinstance(value, ast.Constant):
                    pieces.append(value.value)
                elif isinstance(value, ast.FormattedValue) and ast.unparse(value.value) == "' AND '.join(clauses)":
                    pieces.append(" AND ".join(clauses))
                else:
                    raise ValueError("Unsupported dynamic application SQL")
            sql = "".join(pieces)
        else:
            continue
        if marker in sql:
            matches.append(sql.strip())
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one application query for {function}/{marker}")
    return matches[0]


def quantile_rows(rows):
    if not rows:
        raise ValueError("No eligible non-empty workload; increase the dataset size.")
    return [rows[i] for i in sorted({round((len(rows) - 1) * q) for q in (0.25, 0.5, 0.75)})]


def build_workload(connection, as_of):
    base = ["(t.trip_date > ? OR (t.trip_date = ? AND t.end_time >= ?))",
            "t.status = 'Open'", "t.available_seats > 0"]
    search_sql = application_sql("search", "COUNT(tp.id)", base + [
        "t.trip_date = ?", "t.origin_area_id = ?", "t.destination_area_id = ?",
        "t.start_time <= ?", "t.end_time >= ?"])
    workload = []
    candidates = connection.execute(
        """SELECT trip_date,origin_area_id,destination_area_id,start_time,end_time,id
           FROM trips WHERE status='Open' AND available_seats>0 AND trip_date>=?
           ORDER BY id""", (as_of,)).fetchall()
    for i, row in enumerate(quantile_rows(candidates), 1):
        workload.append({"query": "trip_search", "case": f"q{i}", "sql": search_sql,
                         "parameters": [as_of, as_of, "12:00", row[0], str(row[1]), str(row[2]), row[4], row[3]],
                         "selection": f"Open-trip ID quartile; source trip {row[5]}"})
    workload.append({"query": "browse_open", "case": "all", "sql": application_sql("search", "COUNT(tp.id)", base),
                     "parameters": [as_of, as_of, "12:00"], "selection": "All currently available trips; no optional filters"})
    for name, function, marker, candidates_sql in (
        ("my_joined_trips", "my_trips", "tp.status AS participation_status",
         "SELECT user_id,COUNT(*) n FROM trip_participants GROUP BY user_id ORDER BY n,user_id"),
        ("incoming_requests", "requests_dashboard", "requester_name",
         "SELECT t.publisher_id,COUNT(*) n FROM match_requests mr JOIN trips t ON t.id=mr.trip_id GROUP BY t.publisher_id ORDER BY n,t.publisher_id"),
    ):
        for i, row in enumerate(quantile_rows(connection.execute(candidates_sql).fetchall()), 1):
            workload.append({"query": name, "case": f"q{i}", "sql": application_sql(function, marker),
                             "parameters": [row[0]], "selection": f"Non-empty user-count quartile; user {row[0]}, {row[1]} records"})
    workload.append({"query": "popular_routes", "case": "all",
                     "sql": application_sql("insights", "oa.name AS origin_area"),
                     "parameters": [], "selection": "Application top-five route aggregation"})
    return workload


def index_inventory(connection):
    rows = []
    for table in TABLES:
        for index in connection.execute(f'PRAGMA index_list("{table}")'):
            rows.append({"table": table, "name": index[1], "unique": bool(index[2]),
                         "origin": index[3], "partial": bool(index[4])})
    return sorted(rows, key=lambda row: row["name"])


def remove_performance_indexes(connection):
    inventory = {row["name"]: row for row in index_inventory(connection)}
    for name in PERFORMANCE_INDEXES:
        if name not in inventory or inventory[name]["unique"]:
            raise ValueError(f"Missing or constraint-bearing index: {name}")
        connection.execute(f'DROP INDEX "{name}"')
    connection.commit()


def result_signature(rows):
    # ORDER BY ties may legitimately differ. Retain duplicates in the row multiset.
    values = sorted(json.dumps(list(row), ensure_ascii=True, separators=(",", ":")) for row in rows)
    return hashlib.sha256("\n".join(values).encode()).hexdigest()


def order_keys(query, rows):
    if query in ("trip_search", "browse_open"):
        return [(0 if r["status"] == "Open" else 1, r["trip_date"], r["start_time"], r["created_at"]) for r in rows]
    if query == "my_joined_trips":
        return [(r["trip_date"], r["start_time"]) for r in rows]
    if query == "incoming_requests":
        return [(0 if r["status"] == "Pending" else 1, r["created_at"]) for r in rows]
    return [(r["trip_count"], r["origin_area"], r["destination_area"]) for r in rows]


def validate_dataset(connection, as_of):
    checks = audit_checks(connection)
    checks["future_completed"] = connection.execute("SELECT COUNT(*) FROM trips WHERE status='Completed' AND trip_date>?", (as_of,)).fetchone()[0]
    checks["expired_active_trip"] = connection.execute("SELECT COUNT(*) FROM trips WHERE status IN ('Open','Full') AND trip_date<?", (as_of,)).fetchone()[0]
    checks["schedule_conflicts"] = connection.execute("""
        WITH members AS (
            SELECT id trip_id,publisher_id user_id FROM trips WHERE status<>'Cancelled'
            UNION SELECT tp.trip_id,tp.user_id FROM trip_participants tp
            JOIN trips t ON t.id=tp.trip_id WHERE tp.status='Active' AND t.status<>'Cancelled'
        )
        SELECT COUNT(*) FROM members a JOIN members b ON a.user_id=b.user_id AND a.trip_id<b.trip_id
        JOIN trips ta ON ta.id=a.trip_id JOIN trips tb ON tb.id=b.trip_id
        WHERE ta.trip_date=tb.trip_date AND ta.start_time<=tb.end_time AND ta.end_time>=tb.start_time
    """).fetchone()[0]
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok" or any(checks.values()):
        raise ValueError(f"Invalid evaluation data: {integrity}, {checks}")
    counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in TABLES}
    statuses = {r[0]: r[1] for r in connection.execute("SELECT status,COUNT(*) FROM trips GROUP BY status")}
    ratings = {str(r[0]): r[1] for r in connection.execute("SELECT rating,COUNT(*) FROM reviews GROUP BY rating")}
    digest = hashlib.sha256()
    for table in TABLES:
        for row in connection.execute(f"SELECT * FROM {table} ORDER BY id"):
            digest.update(json.dumps([table, list(row)], ensure_ascii=True).encode())
    return {"counts": counts, "trip_statuses": statuses, "ratings": ratings,
            "participant_users": connection.execute("SELECT COUNT(DISTINCT user_id) FROM trip_participants").fetchone()[0],
            "checks": checks, "integrity_check": integrity, "logical_sha256": digest.hexdigest()}
