"""Verify saved measurements and render two English, report-ready figures."""

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from evaluate_queries import percentile, write_csv

LABELS = {
    "trip_search": "Filtered trip search", "browse_open": "Browse all open trips",
    "my_joined_trips": "My joined trips", "incoming_requests": "Incoming requests",
    "popular_routes": "Popular routes",
}
COLORS = {"full": "#176B87", "reduced": "#CA6532"}
CONDITIONS = {"full": "Full indexes", "reduced": "8 non-unique indexes removed"}


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def verify_run(directory):
    directory = Path(directory)
    metadata = json.loads((directory / "metadata.json").read_text())
    raw = read_csv(directory / "raw_measurements.csv")
    assert len(raw) == metadata["raw_measurement_count"]
    grouped = defaultdict(list)
    first_conditions = defaultdict(list)
    for row in raw:
        key = (int(row["size"]), row["condition"], row["query"], row["case"], int(row["round"]))
        assert int(row["result_rows"]) > 0 and float(row["elapsed_ms"]) > 0
        grouped[key].append(float(row["elapsed_ms"]))
        if int(row["repetition"]) == 1:
            first_conditions[key[:-1]].append(int(row["condition_order"]))
    for positions in first_conditions.values():
        assert positions.count(1) == positions.count(2) == metadata["rounds"] // 2
    case_medians = {}
    for key, values in grouped.items():
        assert len(values) == metadata["repetitions_per_case_round"]
        case_medians[key] = statistics.median(values)
    for row in read_csv(directory / "case_rounds.csv"):
        key = (int(row["size"]), row["condition"], row["query"], row["case"], int(row["round"]))
        assert math.isclose(float(row["ms"]), case_medians[key], rel_tol=1e-12)
    case_groups = defaultdict(list)
    for key, value in case_medians.items():
        case_groups[key[:-1]].append(value)
    for row in read_csv(directory / "case_summary.csv"):
        values = case_groups[int(row["size"]), row["condition"], row["query"], row["case"]]
        for metric, value in (("median_ms", statistics.median(values)), ("p25_ms", percentile(values,.25)),
                              ("p75_ms", percentile(values,.75)), ("p95_ms", percentile(values,.95))):
            assert math.isclose(float(row[metric]), value, rel_tol=1e-12)
    family_rounds = defaultdict(list)
    for (size, condition, query, case, round_id), median in case_medians.items():
        family_rounds[(size, condition, query, round_id)].append(median)
    for row in read_csv(directory / "workload_rounds.csv"):
        values = family_rounds[int(row["size"]), row["condition"], row["query"], int(row["round"])]
        assert math.isclose(float(row["ms"]), statistics.mean(values), rel_tol=1e-12)
    families = defaultdict(list)
    for (size, condition, query, round_id), medians in family_rounds.items():
        families[(size, condition, query)].append(statistics.mean(medians))
    summary = read_csv(directory / "summary.csv")
    for row in summary:
        key = (int(row["size"]), row["condition"], row["query"])
        values = families[key]
        assert len(values) == metadata["rounds"]
        expected = {"median_ms": statistics.median(values), "p25_ms": percentile(values, .25),
                    "p75_ms": percentile(values, .75), "p95_ms": percentile(values, .95),
                    "min_ms": min(values), "max_ms": max(values)}
        for metric, value in expected.items():
            assert math.isclose(float(row[metric]), value, rel_tol=1e-12), (key, metric)
    assert len(summary) == len(families)
    validation = json.loads((directory / "validation.json").read_text())
    assert all(v["integrity_check"] == "ok" and not any(v["checks"].values()) for v in validation)
    for size in metadata["sizes"]:
        hashes = {v["logical_sha256"] for v in validation if v["size"] == size}
        assert len(hashes) == 1
    return summary, metadata, validation


def render(run, repeat, output):
    primary, metadata, valid = verify_run(run)
    second, repeat_metadata, repeat_valid = verify_run(repeat)
    assert valid == repeat_valid, "Regenerated datasets differ"
    for key in ("seed", "sizes", "users", "rounds", "repetitions_per_case_round", "warmups_per_case_round", "as_of_local", "automatic_index", "source_sha256"):
        assert metadata[key] == repeat_metadata[key], key
    assert (Path(run) / "workload.json").read_bytes() == (Path(repeat) / "workload.json").read_bytes()
    assert (Path(run) / "query_plans.csv").read_bytes() == (Path(repeat) / "query_plans.csv").read_bytes()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    lookup = lambda rows: {(int(r["size"]), r["condition"], r["query"]): r for r in rows}
    a, b = lookup(primary), lookup(second)
    comparison = []
    for key, row in a.items():
        first, other = float(row["median_ms"]), float(b[key]["median_ms"])
        comparison.append({"size": key[0], "condition": key[1], "query": key[2],
                           "main_median_ms": first, "main_p25_ms": float(row["p25_ms"]),
                           "main_p75_ms": float(row["p75_ms"]), "repeat_median_ms": other,
                           "repeat_change_percent": 100 * (other / first - 1)})
    write_csv(output / "figure_data.csv", comparison)
    write_csv(output / "index_ratios.csv", [
        {"size": size, "query": name,
         "main_reduced_over_full": float(a[size,"reduced",name]["median_ms"]) / float(a[size,"full",name]["median_ms"]),
         "repeat_reduced_over_full": float(b[size,"reduced",name]["median_ms"]) / float(b[size,"full",name]["median_ms"])}
        for size in metadata["sizes"] for name in LABELS])
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "svg.fonttype": "none", "savefig.facecolor": "white"})
    size = max(metadata["sizes"])
    fig, ax = plt.subplots(figsize=(9.4, 4.9))
    for index, query in enumerate(LABELS):
        for offset, condition in ((-.13, "full"), (.13, "reduced")):
            row = a[size,condition,query]
            median, low, high = [float(row[k]) for k in ("median_ms", "p25_ms", "p75_ms")]
            ax.errorbar(median, index + offset, xerr=[[median - low], [high - median]],
                        fmt="o", color=COLORS[condition], capsize=4, markersize=6, linewidth=1.8)
            ax.plot(float(b[size,condition,query]["median_ms"]), index + offset, marker="D",
                    markerfacecolor="white", markeredgecolor=COLORS[condition], markersize=5, linestyle="none")
    ax.set_yticks(range(len(LABELS)), LABELS.values())
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlim(.1, 30)
    ax.set_xticks([.1, .2, .5, 1, 2, 5, 10, 20], ["0.1", "0.2", "0.5", "1", "2", "5", "10", "20"])
    ax.set_xlabel("SQL execution + full fetch (ms, logarithmic scale)")
    ax.grid(axis="x", alpha=.18)
    fig.suptitle(f"Index comparison at {size:,} trips", x=.035, ha="left", fontsize=16, fontweight="bold")
    fig.text(.035, .91, "Filled circles: primary run median and IQR  |  Hollow diamonds: independent rerun median", fontsize=9)
    handles = [Line2D([0], [0], color=COLORS[c], marker="o", label=CONDITIONS[c]) for c in COLORS]
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=9)
    fig.text(.035, .025, "Primary keys and all unique indexes retained. SQLite automatic indexes enabled in both conditions.", fontsize=8.5)
    fig.subplots_adjust(left=.26, right=.97, top=.84, bottom=.17)
    for extension in ("png", "svg"):
        fig.savefig(output / f"index_comparison.{extension}", dpi=300)
    plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(10.5, 6.1))
    sizes = metadata["sizes"]
    for ax, (query, label) in zip(axes.flat, LABELS.items()):
        for condition in COLORS:
            rows = [a[n,condition,query] for n in sizes]
            medians = [float(r["median_ms"]) for r in rows]
            ax.plot(sizes, medians, marker="o", color=COLORS[condition], linewidth=1.8, markersize=4)
            ax.fill_between(sizes, [float(r["p25_ms"]) for r in rows],
                            [float(r["p75_ms"]) for r in rows], color=COLORS[condition], alpha=.15)
        ax.set_title(label, loc="left", fontsize=10, fontweight="bold")
        ax.set_xscale("log")
        ax.set_xticks(sizes, [f"{n:,}" for n in sizes])
        ax.minorticks_off()
        ax.set_ylim(bottom=0)
        ax.set_ylabel("Time (ms)", fontsize=9)
        ax.set_xlabel("Trips", fontsize=9)
        ax.grid(axis="y", alpha=.18)
        ax.tick_params(labelsize=9)
    axes.flat[-1].axis("off")
    axes.flat[-1].text(.05,.8,"Measurement notes",fontweight="bold",fontsize=11)
    axes.flat[-1].text(.05,.66,"8 rounds per configuration\n30 repeats per case\n3 warmups per block\nShading: round-level IQR\nIndependent vertical scales\nFixed cohort: 100 users",va="top",fontsize=10,linespacing=1.6)
    fig.suptitle("Query time as the trip dataset grows", x=.04, ha="left", fontsize=16, fontweight="bold")
    fig.text(.04,.915,"Primary run; medians across balanced workload rounds. SELECT results are fully fetched.",fontsize=9)
    fig.legend(handles=handles,loc="lower center",ncol=2,frameon=False,fontsize=9,bbox_to_anchor=(.5,.005))
    fig.subplots_adjust(left=.075,right=.98,top=.83,bottom=.13,hspace=.65,wspace=.45)
    for extension in ("png", "svg"):
        fig.savefig(output / f"query_scaling.{extension}", dpi=300)
    plt.close(fig)
    checks = {"raw_summary_recomputed": True, "balanced_order": True,
              "datasets_identical_across_conditions_and_runs": True,
              "workload_and_plans_identical_across_runs": True,
              "timed_executions_per_run": metadata["raw_measurement_count"],
              "matplotlib": matplotlib.__version__,
              "input_sha256": {str(Path(p).as_posix()): hashlib.sha256(Path(p).read_bytes()).hexdigest()
                               for p in [Path(run)/"summary.csv", Path(repeat)/"summary.csv"]},
              "figures_sha256": {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.glob("*.png")}}
    (output / "verification.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print("Verified both runs against raw samples and exported figures to", output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--repeat", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.run, args.repeat, args.output)
