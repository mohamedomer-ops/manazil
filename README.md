# Manazil | منازل

Manazil is a Sudan-focused property rental marketplace. Stage 2B adds an
internal property creation form to the existing application and Property model.

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
│   ├── admin.py             # Internal property creation routes
│   ├── property_forms.py    # Form parsing and validation
│   ├── templates/admin/property_form.html
│   ├── templates/index.html
│   └── static/
│       ├── css/style.css
│       └── js/app.js
├── migrations/             # Alembic environment and versioned migrations
├── tests/
│   ├── test_app.py
│   ├── test_properties.py
│   └── test_property_creation.py
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

## Internal property creation (Stage 2B)

Arabic is the permanent default (`lang="ar" dir="rtl"`). English is selected
explicitly (`?lang=en`); no browser-language detection or saved language
preference is used. An unqualified new visit always returns to Arabic. Both
pages extend `base.html`, with Home, List Your Property, and language controls.

The mobile-first interface uses subtle Sudan-inspired red actions, green
accents, charcoal text, and light backgrounds. Shared styling provides large
inputs, visible keyboard focus, rounded form sections, a two-step progress
indicator, and responsive RTL/LTR layouts. Typography uses a local
Arabic-compatible sans-serif font stack without external font services.

The Arabic form step shows title, description, city, and area in Arabic. Next
opens the English step for those four translations. The other language's values
are carried as hidden fields, and shared property/contact fields appear only
once per form and retain their values across steps. Language buttons submit
the current entries without saving or requiring completed fields. Only the
final Save creates a record, after validating both languages and shared fields.
Switching works without JavaScript. Validation messages, options, navigation,
and connection labels are translated, and direction follows the active language.

Open http://localhost:5000/admin/properties/new to enter a property. The form
posts to `/admin/properties`, validates on the server, and saves through
SQLAlchemy. Every new property is forced to `draft`, regardless of submitted
publication status. Amenities are entered one per line; blank lines are ignored.
Successful saves redirect back with the new property ID in a confirmation.
Validation errors preserve entries and show field errors (HTTP 422). Database
failures roll back and redisplay the form with a retry message (HTTP 503).

These are local internal development routes without authentication. The form
uses a CSRF token, and requests with a missing or invalid token are rejected.
The success message uses Flask's signed session cookie. `SECRET_KEY` can optionally
be supplied through the environment; otherwise a random process-local key is
generated, so pending messages do not survive an application restart.

Creation tests reuse Stage 2A's isolated PostgreSQL migration fixture. They
cover validation, draft enforcement, stored amenities, successful redirects,
HTML escaping, and rollback after a failed commit. No schema change or new
migration was required for the initial Stage 2B workflow.

The state/date update uses the approved 10 Sudanese states as a fixed dropdown.
The selected state's canonical English and Arabic names are stored in `city_en`
and `city_ar`; arbitrary state text is rejected. Existing city data is retained.
Availability timing is separate from the existing `available` / `rented`
status: Available Now stores a null `available_from_date`, while Available
From a Date requires today or a future date using Sudan's timezone. Apply
`flask --app run db upgrade` in the web container to install migration
`0002_available_from_date`, which adds only this nullable date column.

## Intentionally deferred

Authentication, users, admin tools, listing management, property pages and
listings, search, photos and uploads, WhatsApp, tracking and analytics,
payments, maps, reviews, ratings, notifications, AI, chat, favorites, and
saved searches are not implemented. Azure deployment and the complete UI
are also deferred. No listing UI or additional application tables are added.
This project stops at Stage 2B.
