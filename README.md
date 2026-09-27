# Manazil | منازل

Manazil is a Sudan-focused property rental marketplace. Stage 1 establishes
the local application and database foundation only.

## Stack

Python 3, Flask, Flask-SQLAlchemy / SQLAlchemy, psycopg, PostgreSQL 17,
server-rendered Jinja2 HTML, CSS, vanilla JavaScript, Docker Compose, and pytest.
Git and VS Code can be used for development. No cloud services are required.

## Structure

```text
Manazil/
├── app/
│   ├── __init__.py          # Application factory and database configuration
│   ├── routes.py            # Homepage and database health probe
│   ├── templates/index.html
│   └── static/
│       ├── css/style.css
│       └── js/app.js
├── tests/test_app.py
├── .dockerignore
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
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
docker compose exec web python -m pytest -q
```

Tests cover the homepage, the health JSON contract, a live PostgreSQL
connection, and a simulated database outage. No tables are created.

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
There are no application models, migrations, or property tables at this stage.

## Intentionally deferred

Authentication, users, admin tools, listing management, property models and
listings, search, photos and uploads, WhatsApp, tracking and analytics,
payments, maps, reviews, ratings, notifications, AI, chat, favorites, and
saved searches are not implemented. Azure deployment and the complete UI
are also deferred. This project stops at Stage 1.
