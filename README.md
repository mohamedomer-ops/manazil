# Manazil | منازل

Manazil is a Sudan-focused property rental marketplace. Stage 2A adds the
Property model and database migrations to the working Stage 1 foundation.

## Stack

Python 3, Flask, Flask-SQLAlchemy / SQLAlchemy, Flask-Migrate / Alembic, psycopg, PostgreSQL 17,
server-rendered Jinja2 HTML, CSS, vanilla JavaScript, Docker Compose, and pytest.
Git and VS Code can be used for development. No cloud services are required.

## Structure

```text
Manazil/
├── app/
│   ├── __init__.py          # Application factory and database configuration
│   ├── routes.py            # Homepage and database health probe
│   ├── models.py            # Property model and validation
│   ├── templates/index.html
│   └── static/
│       ├── css/style.css
│       └── js/app.js
├── migrations/             # Alembic environment and versioned migrations
├── tests/
│   ├── test_app.py
│   └── test_properties.py
├── .dockerignore
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── pytest.ini
├── run.py
└── README.md
```

## Start locally

Install and start Docker Desktop with Linux containers and Docker Compose.
From the project directory, copy the example configuration:

```powershell
Copy-Item .env.example .env
```

On macOS/Linux, use `cp .env.example .env` instead. Edit `.env` and replace
the example password in both variables with the same local password.
URL-encode special characters in the password used inside `DATABASE_URL`.
The real `.env` is ignored by Git and excluded from the Docker build context.

```sh
docker compose up --build
```

Open http://localhost:5000. The page displays API and database status on load
and refreshes it every 15 seconds. Flask's development server is intentional
for this local stage; deployment configuration belongs to a later stage.
Source is copied into the image; rerun the build after editing files.

To run in the background, use `docker compose up --build -d`.
After the containers start, apply the database migration (also required on a fresh database):

```sh
docker compose exec web flask --app run db upgrade
```

Application startup does not create or modify tables. To verify the migration:

```sh
docker compose exec web flask --app run db current
docker compose exec web flask --app run db check
docker compose exec db psql -U manazil -d manazil -c "\dt"
```

To view logs, use `docker compose logs web db`.

## Stop

```sh
docker compose down
```

The named PostgreSQL volume persists across stops and container rebuilds.
`docker compose down --volumes` deletes database data; use it only when an
intentional local database reset is needed.

## Health and tests

Open http://localhost:5000/api/health, or run:

```powershell
Invoke-RestMethod http://localhost:5000/api/health
```

With curl: `curl http://localhost:5000/api/health`.
Each request executes `SELECT 1` against PostgreSQL. A successful connection
returns HTTP 200 with `status: ok`, `service: Manazil`, and
`database: connected`. Connection failure returns HTTP 503 with
`status: error` and `database: unavailable`, without exposing credentials.
An API that responds with a database failure still appears reachable in the UI.

With Compose running:

```sh
docker compose exec web pytest
```

The original four tests cover the homepage, health JSON contract, live PostgreSQL
connection, and a simulated database outage. Property tests cover defaults,
validation, saving and retrieval, timestamps, and database constraints.
Each database test applies the actual migration to a fresh, isolated PostgreSQL
schema inside a transaction. Test records, tables, and schemas are rolled back
afterward; existing application data is never deleted. Tests require the
configured PostgreSQL database and permission to create schemas (provided by
the local Compose database owner). SQLite is not used.

## Database configuration

Compose runs PostgreSQL with database and username `manazil`. Its password
comes from `POSTGRES_PASSWORD` in `.env`. The web service receives
`DATABASE_URL` through its environment; the hostname `db` resolves to the
PostgreSQL service on the private Compose network, using port 5432.
The database port is not exposed to the host. Only localhost port 5000 is published.

Compose waits for `pg_isready` before starting Flask. SQLAlchemy opens
connections on demand with a three-second connection timeout and checks
pooled connections before reuse. The homepage can render during an outage;
the health endpoint reports failure and can recover when PostgreSQL returns.

PostgreSQL initializes credentials only when the volume is first created.
Changing `.env` alone does not change a password in an existing database.
The initial migration `0001_properties` creates `properties`, the only
application table. Alembic also maintains its internal `alembic_version` table.
Applying an already-applied migration is safe and does not recreate the table.

## Property foundation

Import the model with `from app.models import Property`. It stores bilingual
titles, descriptions, city and area; property type, monthly rent, currency,
bedrooms, bathrooms, optional size in square meters, furnished status,
amenities, contact details, and separate publication and availability statuses.

Required text rejects null, empty, and whitespace-only values. Rent and size
use PostgreSQL NUMERIC / Python Decimal without an arbitrary precision limit;
they must be finite and nonnegative. Bedrooms and bathrooms must be nonnegative
integers. Size and WhatsApp are optional. Property type must be nonempty; the
example types are not treated as a closed list.

Defaults are `SDG`, `furnished=False`, an independent empty amenities list,
`contact_role=owner`, `publication_status=draft`, and
`availability_status=available`. Defaults exist on both the model and database.
Amenities use JSONB and must be a list of strings; in-place list edits are tracked.

Contact role accepts only `owner` (Owner / مالك) or `broker` (Broker / وسيط).
It describes the contact shown to renters, not a future user or staff role.
Publication status accepts `draft`, `pending`, `published`, or `archived`;
availability accepts `available` or `rented`. Model validation and named database
constraints enforce required values, nonnegative numbers, and allowed statuses.

Timezone-aware `created_at` and `updated_at` are populated on insert.
SQLAlchemy automatically updates `updated_at` on model changes. Direct SQL
updates outside SQLAlchemy must explicitly set that timestamp; no database
trigger is installed.

## Intentionally deferred

Authentication, users, admin tools, listing management, property pages and
listings, search, photos and uploads, WhatsApp, tracking and analytics,
payments, maps, reviews, ratings, notifications, AI, chat, favorites, and
saved searches are not implemented. Azure deployment and the complete UI
are also deferred. No listing UI or additional application tables are added.
This project stops at Stage 2A.
