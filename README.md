# Manazil | منازل

Manazil is a Sudan-focused property rental marketplace with a staged property
submission, local photo storage, internal review, and public listings.

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

The mobile-first interface uses green actions, charcoal text, and light
backgrounds. Shared styling provides large inputs, visible keyboard focus,
rounded form sections, a seven-step progress indicator, and responsive
RTL/LTR layouts. Typography uses a local
Arabic-compatible sans-serif font stack without external font services.

The wizard stages Basic Information, Location, Property Details, Price &
Availability, Photos, Contact, and Review. Each Next validates only the current step.
Back and language switching preserve entries without saving. The form asks for
Arabic title, description, city, and area only; English switches the interface
language without asking for duplicate property text. Review shows the entered
information and provides section edit actions. The final Submit for Review
creates one pending record after validating the entered fields. English text
columns may remain empty; public English pages fall back to the Arabic values.
Switching works without JavaScript. Validation messages, options, navigation,
and connection labels are translated, and direction follows the active language.

Open http://localhost:5000/admin/properties/new to enter a property. The form
posts to `/admin/properties`, validates on the server, and saves through
SQLAlchemy. Wizard submissions are forced to `pending`, regardless of submitted
publication status. Amenities are entered one per line; blank lines are ignored.
Successful submissions redirect with a confirmation.
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
State is stored in `state_en` and `state_ar`, separately from city. Migration
`0003_property_states` copies existing city values to state, preserving
existing records. Arbitrary or excluded state names are rejected on submission.
Availability timing is separate from the existing `available` / `rented`
status: Available Now stores a null `available_from_date`, while Available
From a Date requires today or a future date using Sudan's timezone. Apply
`flask --app run db upgrade` in the web container to install the latest migration.

Step 5 accepts optional JPEG, PNG, or WebP photos in seven categories, up to
four per category and 5 MB per file. Images are decoded and re-encoded before
storage. A signed wizard token carries temporary photo state between steps;
the final submission copies files into persistent local storage and records
metadata in `property_photos`. Docker Compose mounts `photo_data` at
`/app/instance/property_photos`. Set `PHOTO_STORAGE_ROOT` to use another
local location. `LocalPhotoStorage` isolates filesystem operations so a future
storage backend can replace it. Abandoned temporary uploads currently need
periodic cleanup.

The internal queue is at `/admin/properties/pending`. Reviewers can inspect a
pending property, approve it to `published`, or return it to `draft`.
Approval does not change availability: only published and available properties
are public. These admin routes intentionally have no authentication or owner
permissions in this stage; deploy them only behind an external access control
until those features are implemented.

## Public property listings (Stage 2C.1)

Open `/properties` to browse properties marked both `published` and `available`.
The page is public and displays bilingual card details in the selected language.
Properties with a future `available_from_date` remain listed with a localized
availability date; null, current, and past dates display Available Now. Cards
omit descriptions, contact details, and internal status fields. View Property
links to the public details page.

## Public property details (Stage 2C.2)

`/properties/<property_id>` returns details only for properties marked both
`published` and `available`; all other IDs return 404. The selected language
controls title, location, description, labels, and availability dates. The page
shows property facts, optional amenities, and contact information. Phone and
WhatsApp links are built only from valid phone numbers. When present, the
primary photo and categorized gallery are shown. Inquiry backend is deferred.

## Intentionally deferred

Authentication, users, listing management, search, WhatsApp integration,
tracking and analytics,
payments, maps, reviews, ratings, notifications, AI, chat, favorites, and
saved searches are not implemented. Azure Blob Storage and deployment are
deferred.
# Development phone login

The local Docker Compose web service enables the development OTP provider. After
requesting a code on `/login`, retrieve it from the container with:

```sh
docker compose exec web flask --app run dev-otp +249912345678
```

Use the phone number entered on the login page (the command accepts Sudanese
local format too). This command and the provider's local code file are disabled
unless `OTP_DEVELOPMENT_MODE=1` (or the app is in testing mode). Do not enable
that setting in a production deployment. Configure a production delivery
provider through `OTP_DELIVERY_PROVIDER` before offering phone login there.

## Development Facebook authentication

Local Docker Compose explicitly sets `MANAZIL_ENV=development` and
`FACEBOOK_DEVELOPMENT_MODE=1`. The authentication cards offer Continue with
Facebook and a clearly labeled simulation confirmation page. No Meta API,
Facebook credentials, email matching or automatic account linking is used.
The fake account ID is stable (`development-facebook-user`); optional server
configuration `FACEBOOK_DEVELOPMENT_USER_ID` and
`FACEBOOK_DEVELOPMENT_DISPLAY_NAME` selects a different test identity.
Never expose this development deployment to untrusted users: all visitors
can authenticate as the configured fake account.

The default environment is production, where the simulation routes and UI
are absent even if `FACEBOOK_DEVELOPMENT_MODE=1`. Explicit `TESTING=True`
also enables the simulation for isolated tests. Debug mode and the OTP
development flag alone do not enable Facebook authentication. Real Meta
authentication is not implemented; production Facebook login fails closed.

`FacebookAuthProvider` defines authorization URL and identity authentication
methods. Future Meta delivery can implement that boundary while reusing the
identity lookup and session logic. Provider identities use a unique composite
key `(provider, provider_user_id)`; names are not account identifiers.
Facebook-only accounts have no verified phone, WhatsApp or contact role.
The existing phone/contact requirements for posting remain in place for this
stage; account linking and property-specific contact verification are deferred.
Phone/OTP login remains available independently. Both login methods preserve
safe local `next` destinations and never automatically save a property.
