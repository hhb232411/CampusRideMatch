"""Checks for experimental validity, SQL parity and safe database generation."""

import csv
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from flask import session
from campusride import create_app
from campusride.db import get_db

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from generate_test_data import generate_database
from evaluation_workload import (build_workload, validate_dataset, index_inventory,
                                 remove_performance_indexes, result_signature, order_keys)
from evaluate_queries import run_experiment
from plot_evaluation import verify_run


class EvaluationTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = generate_database(self.root / "data.sqlite", 100, as_of="2026-11-10")

    def connect(self, path=None):
        connection = sqlite3.connect(path or self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def test_deterministic_data_satisfies_business_rules(self):
        other = generate_database(self.root / "repeat.sqlite", 100, as_of="2026-11-10")
        with closing(self.connect()) as a, closing(self.connect(other)) as b:
            first, second = validate_dataset(a, "2026-11-10"), validate_dataset(b, "2026-11-10")
            self.assertEqual(first, second)
            self.assertEqual(set(first["trip_statuses"]), {"Open", "Full", "Completed", "Cancelled"})
            self.assertEqual(set(first["ratings"]), {"1", "2", "3", "4", "5"})
            self.assertGreater(first["participant_users"], 50)

    def test_generator_refuses_existing_files_and_application_directory(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        with self.assertRaises(FileExistsError):
            generate_database(self.path, 100)
        with self.assertRaises(ValueError):
            generate_database(ROOT / "instance" / "campusride.sqlite", 100)
        self.assertEqual(before, hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_index_ablation_preserves_constraints_and_results(self):
        with closing(self.connect()) as connection:
            workload = build_workload(connection, "2026-11-10")
            rows = [connection.execute(w["sql"], w["parameters"]).fetchall() for w in workload]
            self.assertTrue(all(rows))
            unique_before = [r for r in index_inventory(connection) if r["unique"]]
            remove_performance_indexes(connection)
            self.assertEqual([r for r in index_inventory(connection) if r["unique"]], unique_before)
            for w, before in zip(workload, rows):
                after = connection.execute(w["sql"], w["parameters"]).fetchall()
                self.assertEqual(result_signature(before), result_signature(after))
                self.assertEqual(order_keys(w["query"], before), order_keys(w["query"], after))
            trip, user = connection.execute("SELECT trip_id,requester_id FROM match_requests WHERE status IN ('Pending','Accepted') LIMIT 1").fetchone()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO match_requests(trip_id,requester_id) VALUES (?,?)", (trip, user))
            connection.rollback()
            validate_dataset(connection, "2026-11-10")

    def test_benchmark_sql_matches_actual_flask_routes(self):
        app = create_app({"TESTING": True, "SECRET_KEY": "evaluation-test", "DATABASE": str(self.path)})
        seen = []
        @app.before_request
        def trace_queries():
            get_db().set_trace_callback(seen.append)
        client = app.test_client()
        with closing(self.connect()) as connection:
            workload = build_workload(connection, "2026-11-10")
            for item in workload:
                if item["query"] == "trip_search":
                    p = item["parameters"]
                    path = f"/trips/search?trip_date={p[3]}&origin_area_id={p[4]}&destination_area_id={p[5]}&end_time={p[6]}&start_time={p[7]}"
                    marker = "COUNT(tp.id)"
                elif item["query"] == "browse_open":
                    path, marker = "/trips/search", "COUNT(tp.id)"
                elif item["query"] == "my_joined_trips":
                    path, marker = "/trips/mine", "tp.status AS participation_status"
                elif item["query"] == "incoming_requests":
                    path, marker = "/trips/requests", "requester_name"
                else:
                    path, marker = "/trips/insights", "oa.name AS origin_area"
                with client.session_transaction() as state:
                    state["user_id"] = item["parameters"][0] if item["query"] in ("my_joined_trips", "incoming_requests") else 1
                seen.clear()
                with patch("campusride.trips.datetime", wraps=datetime) as clock:
                    clock.now.return_value = datetime(2026, 11, 10, 12)
                    response = client.get(path)
                self.assertEqual(response.status_code, 200)
                actual = [sql for sql in seen if marker in sql]
                expanded = []
                connection.set_trace_callback(expanded.append)
                connection.execute(item["sql"], item["parameters"]).fetchall()
                connection.set_trace_callback(None)
                normalize = lambda sql: " ".join(sql.split())
                self.assertIn(normalize(expanded[-1]), [normalize(sql) for sql in actual], item["query"])

    def test_small_experiment_saves_balanced_nonempty_measurements(self):
        output = self.root / "run"
        run_experiment(output, [100], as_of="2026-11-10", rounds=2, repetitions=2, warmups=1)
        with (output / "raw_measurements.csv").open(newline="", encoding="utf-8") as handle:
            raw = list(csv.DictReader(handle))
        workload = json.loads((output / "workload.json").read_text())
        self.assertEqual(len(raw), len(workload) * 2 * 2 * 2)
        self.assertTrue(all(int(r["result_rows"]) > 0 and float(r["elapsed_ms"]) > 0 for r in raw))
        for w in workload:
            for condition in ("full", "reduced"):
                positions = [int(r["condition_order"]) for r in raw if r["query"] == w["query"] and r["case"] == w["case"] and r["condition"] == condition]
                self.assertEqual(positions.count(1), positions.count(2))
        verify_run(output)
        validation = json.loads((output / "validation.json").read_text())
        self.assertEqual(validation[0]["logical_sha256"], validation[1]["logical_sha256"])
        with self.assertRaises(FileExistsError):
            run_experiment(output, [100], as_of="2026-11-10", rounds=2, repetitions=2, warmups=1)


if __name__ == "__main__":
    unittest.main()
