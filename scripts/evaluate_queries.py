"""Benchmark actual application SQL; save auditable raw data in a new run directory."""

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import random
import shutil
import sqlite3
import statistics
import tempfile
import time
from collections import defaultdict
from contextlib import ExitStack, closing
from datetime import date, datetime, timezone
from pathlib import Path

from generate_test_data import generate_database, ROOT, DEFAULT_SEED
from evaluation_workload import (build_workload, index_inventory, remove_performance_indexes,
                                 result_signature, order_keys, validate_dataset, PERFORMANCE_INDEXES)


def write_csv(path, rows):
    if not rows:
        raise ValueError(f"No results for {path}")
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(round_rows, group_fields):
    grouped = defaultdict(list)
    for row in round_rows:
        grouped[tuple(row[k] for k in group_fields)].append(row["ms"])
    result = []
    for key, values in sorted(grouped.items()):
        result.append(dict(zip(group_fields, key), rounds=len(values),
                           median_ms=statistics.median(values), p25_ms=percentile(values, .25),
                           p75_ms=percentile(values, .75), p95_ms=percentile(values, .95),
                           min_ms=min(values), max_ms=max(values)))
    return result


def run_experiment(output, sizes=(100, 1000, 5000), *, users=100, seed=DEFAULT_SEED,
                   as_of=None, rounds=8, repetitions=30, warmups=3, automatic_index=True):
    if min(sizes) < 1 or users < 6 or rounds < 2 or rounds % 2 or repetitions < 2 or warmups < 1:
        raise ValueError("Positive sizes; users>=6; even rounds>=2; repetitions>=2; warmups>=1 required.")
    as_of = str(as_of or date.today())
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"Refusing to replace existing run: {output}")
    output.mkdir(parents=True)
    started = datetime.now(timezone.utc).isoformat()
    source_paths = ["schema.sql", "campusride/trips.py", "scripts/generate_test_data.py",
                    "scripts/evaluate_queries.py", "scripts/evaluation_workload.py"]
    metadata = {
        "started_utc": started, "as_of_local": as_of, "seed": seed, "sizes": list(sizes),
        "users": users, "rounds": rounds, "repetitions_per_case_round": repetitions,
        "warmups_per_case_round": warmups, "automatic_index": automatic_index,
        "removed_non_unique_indexes": list(PERFORMANCE_INDEXES),
        "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "flask": importlib.metadata.version("flask"), "os": platform.platform(),
        "processor": platform.processor(), "logical_cpus": os.cpu_count(),
        "timer": "perf_counter_ns; execute plus fetchall with sqlite3.Row; milliseconds",
        "summary": "Median across rounds of the arithmetic mean of per-case medians; IQR across rounds",
        "statistics_policy": "No ANALYZE, matching the current application setup; same automatic_index in both conditions",
        "order_policy": "Shuffle cases per round; alternate condition order by round for each case, exactly balanced",
        "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in source_paths},
    }
    raw, plans, workloads, validation, case_rounds, family_rounds, inventories = [], [], [], [], [], [], []
    with tempfile.TemporaryDirectory(prefix="campusride-benchmark-") as directory:
        for size in sizes:
            base = generate_database(Path(directory) / f"base-{size}.sqlite", size, users, seed=seed, as_of=as_of)
            with ExitStack() as stack:
                connections = {}
                for condition in ("full", "reduced"):
                    copy = Path(directory) / f"{condition}-{size}.sqlite"
                    shutil.copyfile(base, copy)
                    connection = stack.enter_context(closing(sqlite3.connect(copy)))
                    connection.row_factory = sqlite3.Row
                    connection.execute("PRAGMA foreign_keys = ON")
                    connection.execute(f"PRAGMA automatic_index = {int(automatic_index)}")
                    if condition == "reduced":
                        remove_performance_indexes(connection)
                    connections[condition] = connection
                    checked = validate_dataset(connection, as_of)
                    validation.append({"size": size, "condition": condition, **checked})
                    inventories.append({"size": size, "condition": condition, "indexes": index_inventory(connection),
                                        "page_size": connection.execute("PRAGMA page_size").fetchone()[0],
                                        "cache_size": connection.execute("PRAGMA cache_size").fetchone()[0],
                                        "journal_mode": connection.execute("PRAGMA journal_mode").fetchone()[0]})
                if validation[-1]["logical_sha256"] != validation[-2]["logical_sha256"]:
                    raise AssertionError("Index removal changed dataset contents")
                workload = build_workload(connections["full"], as_of)
                expected = {}
                for item in workload:
                    key = (item["query"], item["case"])
                    baseline = connections["full"].execute(item["sql"], item["parameters"]).fetchall()
                    reduced = connections["reduced"].execute(item["sql"], item["parameters"]).fetchall()
                    signature = result_signature(baseline)
                    if not baseline or signature != result_signature(reduced) or order_keys(item["query"], baseline) != order_keys(item["query"], reduced):
                        raise AssertionError(f"Empty or different result: {size}/{key}")
                    expected[key] = (len(baseline), signature, order_keys(item["query"], baseline))
                    workloads.append({"size": size, **item, "result_rows": len(baseline), "result_sha256": signature})
                    for condition, connection in connections.items():
                        for plan in connection.execute("EXPLAIN QUERY PLAN " + item["sql"], item["parameters"]):
                            plans.append({"size": size, "condition": condition, "query": key[0], "case": key[1],
                                          "id": plan[0], "parent": plan[1], "detail": plan[3]})
                for round_id in range(rounds):
                    rng = random.Random(seed + size * 100 + round_id)
                    order = list(enumerate(workload))
                    rng.shuffle(order)
                    family_values = defaultdict(list)
                    for position, (case_index, item) in enumerate(order):
                        conditions = ["full", "reduced"] if (round_id + case_index) % 2 == 0 else ["reduced", "full"]
                        for condition_position, condition in enumerate(conditions):
                            connection = connections[condition]
                            for _ in range(warmups):
                                connection.execute(item["sql"], item["parameters"]).fetchall()
                            samples = []
                            for repetition in range(repetitions):
                                start = time.perf_counter_ns()
                                rows = connection.execute(item["sql"], item["parameters"]).fetchall()
                                elapsed = (time.perf_counter_ns() - start) / 1_000_000
                                samples.append(elapsed)
                                raw.append({"size": size, "condition": condition, "query": item["query"], "case": item["case"],
                                            "round": round_id + 1, "case_order": position + 1,
                                            "condition_order": condition_position + 1, "repetition": repetition + 1,
                                            "result_rows": len(rows), "elapsed_ms": elapsed})
                            count, signature, keys = expected[(item["query"], item["case"])]
                            if len(rows) != count or result_signature(rows) != signature or order_keys(item["query"], rows) != keys:
                                raise AssertionError("Result changed during benchmark")
                            median = statistics.median(samples)
                            case_rounds.append({"size": size, "condition": condition, "query": item["query"],
                                                "case": item["case"], "round": round_id + 1, "ms": median})
                            family_values[(condition, item["query"])].append(median)
                    for (condition, name), values in family_values.items():
                        family_rounds.append({"size": size, "condition": condition, "query": name,
                                              "round": round_id + 1, "cases": len(values), "ms": statistics.mean(values)})
                print(f"Validated and measured {size} trips; {len(workload)} non-empty parameter cases", flush=True)
    write_csv(output / "raw_measurements.csv", raw)
    write_csv(output / "query_plans.csv", plans)
    write_csv(output / "case_rounds.csv", case_rounds)
    write_csv(output / "workload_rounds.csv", family_rounds)
    summary = summarize(family_rounds, ["size", "condition", "query"])
    write_csv(output / "summary.csv", summary)
    write_csv(output / "case_summary.csv", summarize(case_rounds, ["size", "condition", "query", "case"]))
    write_csv(output / "dataset_counts.csv", [{"size": v["size"], **v["counts"], "participant_users": v["participant_users"]}
                                             for v in validation if v["condition"] == "full"])
    for name, data in (("workload.json", workloads), ("validation.json", validation), ("indexes.json", inventories)):
        (output / name).write_text(json.dumps(data, indent=2), encoding="utf-8")
    sql_text = []
    for item in workloads:
        sql_text.extend([f"-- size={item['size']}; query={item['query']}; case={item['case']}",
                         "-- Bound parameters: " + json.dumps(item["parameters"]), item["sql"] + ";", ""])
    (output / "queries.sql").write_text("\n".join(sql_text), encoding="utf-8")
    metadata["finished_utc"] = datetime.now(timezone.utc).isoformat()
    metadata["raw_measurement_count"] = len(raw)
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Saved {len(raw)} timed executions to {output}")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[100, 1000, 5000])
    parser.add_argument("--users", type=int, default=100)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--rounds", type=int, default=8)
    parser.add_argument("--repetitions", type=int, default=30)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--automatic-index", choices=["on", "off"], default="on")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "evaluation" / datetime.now().strftime("run-%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    run_experiment(args.output, args.sizes, users=args.users, seed=args.seed, as_of=args.as_of,
                   rounds=args.rounds, repetitions=args.repetitions, warmups=args.warmups,
                   automatic_index=args.automatic_index == "on")


if __name__ == "__main__":
    main()
