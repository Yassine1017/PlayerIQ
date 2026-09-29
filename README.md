# PlayerIQ

PlayerIQ is a football GPS performance platform. This repository currently contains **Phase 1 only**: a Python backend foundation, a versioned registry for the reviewed Activity Report PDF, deterministic extraction and validation, private-schema database models/migrations, and tests. There is no frontend, upload endpoint, authentication, player linking, analytics API, or AI integration yet.

The architecture and source metric decisions are in [SPEC.md](docs/SPEC.md) and [GPS_DATA_MODEL.md](docs/GPS_DATA_MODEL.md). The ingestion boundary is explained in [INGESTION.md](docs/INGESTION.md).

## Backend setup (Python 3.12)

Run in PowerShell from the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
python -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

Then visit `http://127.0.0.1:8000/healthz` and `/readyz`. Readiness currently reports `database: not_checked`; it does not claim that PostgreSQL is connected.

## Environment and database

Set `DATABASE_URL` in `.env` to a PostgreSQL connection string. The migrations expect a Supabase-compatible `auth.users` table to exist and create a private `playeriq` schema. They enable row level security with no access policies yet. Use a privileged migration role to apply them; the eventual application and worker roles must be separately restricted and granted policies before authenticated features are added. The other values in `.env.example` are placeholders or review thresholds. Keep `.env` and credentials out of Git.

```powershell
$env:PYTHONPATH = "apps/api"
python -m alembic upgrade head
python -m alembic current
```

There is no PostgreSQL service bundled with this repository. Offline migration SQL can be checked with `python -m alembic upgrade head --sql`, but a successful live migration requires a real database with `auth.users`.

## Tests and local GPS report

```powershell
python -m pytest -q
python -m ruff check apps/api db/migrations
python -m ruff format --check apps/api db/migrations
python -m mypy apps/api/app
```

Tests generate an anonymized PDF in memory. To additionally run the optional real-report test without committing the PDF:

```powershell
$env:PLAYERIQ_LOCAL_REPORT = "C:\path\to\private-report.pdf"
python -m pytest -q
```

You may place the private PDF in `sample-data/`; that folder ignores everything except its README. The supplied original remains outside the repository. Do not commit athlete names, report pages, or raw report bytes.

## Current API

`GET /healthz` checks that the process responds. `GET /readyz` states that database readiness has not been checked. Ingestion is a Python service/repository boundary for now; it is intentionally not exposed over HTTP before authentication and ownership checks exist.
