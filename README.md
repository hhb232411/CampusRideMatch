# Campus Ride Match

A CityU DSC5003 **Track 1: Database Application Development** project. Campus Ride Match helps campus community members find compatible journeys, request participation and coordinate after a publisher accepts. The focus is relational design, SQL, transactional consistency and measured query performance.

## Key Features

- Registration, login, profiles and English/Chinese pages.
- Publish and edit trips; search fixed areas, dates and overlapping time intervals.
- Request, accept, reject, withdraw and remove participation, with consistent seat counts.
- Cancel/complete trips while preserving history; review actual members of completed trips.
- Personal trip/request histories, in-app notifications and SQL-based Insights.

A seat is **one additional participant**, separate from the publisher's party size. Notifications stay inside the application; automatic email is not implemented. Expiry uses server-local time, with the end minute inclusive. This is a local course prototype, not a production transport service.

## Technology Stack

Python **3.10+** (clean reproduction verified on **3.12.2**), Flask 3.1.x, Werkzeug, SQLite via Python's standard library, Jinja, HTML/CSS and minimal JavaScript. No ORM or separate frontend build is required. Dependencies are in [requirements.txt](requirements.txt); optional charting dependencies are in [requirements-evaluation.txt](requirements-evaluation.txt).

## Project Structure

```text
campusride/             Flask routes, SQL, templates and static assets
schema.sql             Seven tables, constraints and indexes
seed.sql               Fictional accounts and areas
sql/sample_queries.sql Eight teaching SELECT examples
tests/                 34 integration, correctness and evaluation tests
scripts/               Data generation, benchmarking and figure tools
docs/                  Design, ER model, evaluation and delivery status
docs/evaluation/       Two original runs: SQL, plans, raw CSVs and figures
instance/.gitkeep      Runtime database directory; no database is shipped
app.py / run.py        Application entry points
```

## Installation and Setup

Clone the public repository and enter the project directory. Alternatively, extract the supplied source ZIP and enter the directory containing `app.py`.

```text
git clone https://github.com/hhb232411/CampusRideMatch.git
cd CampusRideMatch
```

Create a clean virtual environment:

```text
python -m venv .venv
```

Activate it using the command for your shell:

```powershell
# Windows PowerShell; if script activation is restricted, use .venv/Scripts/python.exe directly
.venv/Scripts/Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Install the application dependencies:

```text
python -m pip install -r requirements.txt
```

No external database server, API key or `.env` file is required. A local session secret is generated in `instance/.secret_key` on first use. Do not commit that file or local databases. The application can alternatively read `CAMPUSRIDE_SECRET_KEY`; never put a real value in the repository.

## Database Initialization

**Run only in a fresh extracted/cloned project with no data to preserve:**

```text
python -m flask --app app init-db --with-seed
python -m flask --app app audit-db
```

Initialization replaces the local database at `instance/campusride.sqlite`. It loads fictional accounts, the fixed-area catalog and 20 example trips using dates relative to initialization. Repeating `init-db` destroys that local database's current records. For an existing database that needs a schema upgrade, use `python -m flask --app app migrate-db` instead; do not use initialization as a migration.

Seed-only accounts: `alice`, `bob`, `carol`; all use **`password123`**. Names, example-domain emails and phone strings are fictional fixtures, not real contact information. Use them only in a local classroom demonstration. The separate video sandbox uses different credentials, documented in its recording guide.

## Running the Application

```text
python -m flask --app app --no-debug run --host 127.0.0.1 --port 5000
```

Open **http://127.0.0.1:5000/**. Keep this terminal running; Ctrl+C stops the server. This command keeps debug mode off. Log in, open Search, Publish, My trips, Requests, Notifications and Insights. The initial database includes completed and full trips as well as open ones; use an open future trip for requests.

## Running Tests

```text
python -m unittest discover -s tests -v
```

The suite contains **34 tests**: 18 application tests, 11 correctness regressions and 5 evaluation tests. Database writes occur in isolated temporary/in-memory databases. The evaluation tests include a tiny 88-timing smoke fixture; they do not overwrite or rerun the two saved full experiments. Final clean-copy results are summarized in [validation notes](docs/VALIDATION.md).

For database checking, `audit-db` includes foreign-key and cross-table business checks. SQLite's structural check can also be run locally:

```text
python -c "import sqlite3; c=sqlite3.connect('file:instance/campusride.sqlite?mode=ro',uri=True); print(c.execute('PRAGMA integrity_check').fetchall()); print(c.execute('PRAGMA foreign_key_check').fetchall()); c.close()"
```

Expected output is `ok` for integrity and an empty foreign-key result. An audit detects defined inconsistencies; it is not proof of every possible business rule.

## Database Design and SQL

The seven tables are `users`, `location_areas`, `trips`, `match_requests`, `trip_participants`, `notifications` and `reviews`. The schema declares 14 foreign keys, eight non-unique performance indexes and two partial unique indexes; SQLite also retains its ordinary unique/primary-key access paths.

`BEGIN IMMEDIATE`, state rechecks, conditional updates and rollback protect multi-table lifecycle writes. Database constraints, application checks and the audit have distinct responsibilities. See:

- [Database design and normalization](docs/DATABASE_DESIGN.md)
- [ER model with all attributes](docs/ER_DIAGRAM.md) and [report ER figure](docs/figures/er-model.png)
- [Technical design](docs/TECHNICAL_DESIGN.md) and [architecture figure](docs/figures/architecture.png)
- [Teaching SQL examples](sql/sample_queries.sql) and actual route queries in [trips.py](campusride/trips.py)

The teaching queries use illustrative IDs and filters, so result counts depend on the dataset. They are not the benchmark workload.

## Performance Evaluation

The saved experiment uses **100, 1,000 and 5,000 trips** and actual application SQL. Two runs contain **31,680 timed executions**, with warmups, repeated rounds and balanced condition order. The reduced condition removes eight specified non-unique indexes, retaining integrity indexes and automatic indexing.

At 5,000 trips, primary-run reduced/full time ratios are **3.06** for filtered search and **2.36** for incoming requests. Browse performance does **not** improve consistently across runs. Measurements cover warmed SELECT execution and fetching, not whole-site latency or concurrent capacity.

Read [Evaluation and Results](docs/EVALUATION.md), the [primary evidence](docs/evaluation/main-2026-11-10/), [repeat evidence](docs/evaluation/repeat-2026-11-10/) and [figures](docs/evaluation/figures/). No rerun is needed to inspect them. Tool usage can be inspected without timing an experiment:

```text
python scripts/evaluate_queries.py --help
python scripts/generate_test_data.py --help
```

Chart generation additionally requires `python -m pip install -r requirements-evaluation.txt`. Reproduction commands and safeguards are documented in EVALUATION.md; use new output directories, never the saved evidence directories.

## Links to Report and Video

- **Report:** `CampusRideMatch-report.pdf` is supplied separately in the final delivery with editable LaTeX. Team/contribution/link placeholders remain; it is not yet a submission-ready PDF.
- The source repository is publicly available on [GitHub](https://github.com/hhb232411/CampusRideMatch).
- **Video:** **TO BE COMPLETED — recording, upload and accessible URL pending.**
- [Deliverable status and recording handoff](docs/DELIVERABLES.md)

The recording materials are distributed separately to keep the repository compact. Copy the supplied `VIDEO_HANDOFF` directory into this project root before using its commands; it runs a protected, independent demo database. Do not copy an existing business database or secret into this source tree.
