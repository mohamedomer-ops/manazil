# Manazil

Manazil is a Sudan-focused property marketplace for rent and sale. Visitors can browse, search, and view listings without an account. Accounts support property posting and management, saved properties, and contact profiles. Arabic is the default language, with an English switch and RTL/LTR layouts.

## Stack and structure

Manazil uses Python 3.13, Flask and Jinja2, HTML/CSS and vanilla JavaScript, Flask-SQLAlchemy/SQLAlchemy, Flask-Migrate/Alembic, PostgreSQL via psycopg, Pillow for image processing, Docker Compose, and pytest. Production support includes Gunicorn and the Azure Blob SDK.

```text
app/
  __init__.py             Application factory, configuration, extensions, CLI
  routes.py               Homepage, public properties, photo serving, health check
  admin.py                Current single-page property posting and staged uploads
  admin_portal.py         Staff login, authorization, dashboard, management, reports
  property_forms.py       Property form validation
  ownership.py            Owner-only property management and photo actions
  auth.py, otp.py, phone.py
                          Phone authentication, OTP, phone normalization
  facebook_auth.py, facebook_provider.py
                          Development Facebook authentication
  saved.py                Saved-property routes
  property_filters.py     Public listing filters
  models.py               Users, identities, properties, photos, OTPs, saves
  photo_storage.py        Image validation, local storage, backend selection
  azure_photo_storage.py  Private Azure Blob implementation
  states.py, languages.py Supported states and interface translations
  templates/              Jinja pages and reusable property components
  static/                 CSS, vanilla JavaScript, local images
migrations/versions/      Alembic schema revisions
tests/                    pytest coverage
run.py                    Flask entry point
docker-compose.yml        Web and PostgreSQL services
```

## Run locally

From the repository root in PowerShell, with Docker Compose available:

```powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose exec web flask --app run db upgrade
```

Open <http://127.0.0.1:5000>. Compose always connects the web service to its local `db` PostgreSQL service using `POSTGRES_PASSWORD` from `.env`; it does not pass a `DATABASE_URL` from `.env` to the web service. Keep Neon credentials in a separate, ignored environment file or your production secret store rather than the everyday local `.env`. If the Neon CLI has already added credentials to `.env`, leave them uncommitted; Compose will ignore its `DATABASE_URL`. Check services and logs with:

```powershell
docker compose ps
docker compose logs web db
```

Schema changes are managed by Flask-Migrate/Alembic. Apply all existing migrations with `docker compose exec web flask --app run db upgrade`; the repository contains revisions beyond the original property table, including users, OTP challenges, photos, saved-property relationships, and Facebook identities.

## Homepage and public browsing

The homepage has a Sudan-focused hero image slideshow with Search and Post Property actions. Its filter form sits under Find What Fits You, followed by the newest four public properties. Search uses the same GET filters as `/properties`.

`GET /properties` displays only **published and available** properties. Its validated query parameters are:

| Parameter | Values | Meaning |
| --- | --- | --- |
| `transaction` | `rent`, `sale` | Rent or sale |
| `state` | One of the supported state slugs, such as `khartoum` | State |
| `bedrooms` | `1` through `5` | Minimum bedroom count |
| `seller` | `owner`, `broker` | Contact role |
| `property_type` | `apartment`, `house`, `villa`, `office`, `shop`, `land` | Property type |

For example, `/properties?transaction=rent&state=khartoum&bedrooms=2&seller=owner` finds available published rentals matching all four filters. Results use responsive cards with price, bed and bath counts, and State · Neighborhood location. The photo carousel has independent previous/next controls and touch swipe; Save/Unsave is separate from opening a listing. Property type remains a filter, although it is not shown in result-card metadata.

`GET /properties/<property_id>` shows a public property's gallery, description, price, property details, amenities, location, and one listing-specific contact number with WhatsApp and Call actions. For older listings, a valid WhatsApp number takes priority; otherwise a valid phone number is used. Draft and rented listings are not publicly accessible through this route. Photos are served only according to the same public visibility rules; an owner can manage their own photos from the edit page.

## Properties and posting

A property records its Rent/Sale transaction, Rooms/Entire Property occupancy where applicable, property type, bedroom and bathroom counts, optional size, furnished status, amenities, price in the owner's selected currency (SDG or USD), optional rent period, state and neighborhood, listing contact name/WhatsApp number, and Owner/Broker role. The one listing contact number is used for WhatsApp and normal calls; Manazil does not verify that it has an active WhatsApp account. Manazil displays the selected currency without converting the numeric price. A property also has an owner, photos, and two distinct statuses:

- **Publication:** `draft` or `published`. A valid new submission is published directly.
- **Availability:** `available` or `rented`. A rented listing remains in its owner's management area but leaves public browsing.

The current posting form at `/properties/new` is one page, ordered as Category (Rent/Sale), rental occupancy, Photos, Property Details, Contact Details (including Owner/Broker), Location, then **Publish Property**. The form includes Arabic title and description, optional English content, the property details above, and an approved state plus Arabic neighborhood. City/Area columns remain for older records; they are not part of the current posting form. Posting requires authentication and a complete contact profile. The form prepopulates the WhatsApp contact number from the user's profile, but each property stores its own contact snapshot; editing a listing's contact does not edit the account.

The posting dropdown accepts these ten states from `app/states.py`: Khartoum, Al Jazirah, Red Sea, Kassala, Gedaref, Sennar, Blue Nile, White Nile, Northern, and River Nile. Other states are not currently accepted for new postings.

### Photos

Properties support up to **20 photos total**, with additional upload and individual deletion while editing. Accepted uploads are JPEG/JPG, PNG, and WebP, up to **5 MB per file**. The server checks the file type and image contents, processes images with Pillow, and stores them using generated safe names through a storage abstraction. Docker Compose persists local photos in the `photo_data` volume. The local storage root can be configured with `PHOTO_STORAGE_ROOT`.

An owner can set the primary photo, move photos in display order, and delete them. If the primary photo is deleted, another remaining photo becomes primary; with no photos, public cards use the existing placeholder. Public listings, the homepage carousel, and the details gallery use the current property photos.

## Accounts and authentication

`/auth` offers Login and Sign Up. Phone login verifies a normalized phone number by OTP and returns the same existing account; Sign Up collects name, the OTP login phone, and Owner/Broker role, then creates the account only after OTP verification. The verified phone initially fills the profile's WhatsApp contact number, which can later be edited independently. Authentication preserves a safe local `next` destination, such as `/properties/new` or a property detail URL. Logout ends the session.

The current OTP delivery is a **development provider**. It stores the code locally for development; it does **not** send a real WhatsApp message. OTP codes are hashed in the database and protected by expiry, attempt limits, single use, and request throttling. After requesting a code locally, inspect it with:

```powershell
docker compose exec web flask --app run dev-otp +249912345678
```

Manazil also has **simulated development Facebook authentication**. With the explicit development/test configuration in Compose, Continue with Facebook uses a stable fake provider identity, creates or reuses its associated Manazil account, and preserves `next`. It does not contact Meta, require Facebook credentials, or constitute production Facebook Login. The simulated endpoints are disabled outside configured development/testing mode. Phone OTP remains available independently. A Facebook-only account can complete its contact profile and post without a verified OTP-login phone; its WhatsApp contact number is separate from authentication identity.

`/account` displays account identity and contact information. Users can edit contact name, WhatsApp number, and Owner/Broker role; an OTP-login phone, when present, is read-only in Account & Security and remains separate from listing contact. The page links to Saved Properties and Post Property. My Properties remains available in authenticated navigation. Arabic interface text is the default on each request; the language switch selects English (`lang=en`) or Arabic, with RTL Arabic and LTR English. Optional English property title/description fall back to Arabic content when absent.

## Manage and save properties

`GET /my-properties` requires an account and lists only that user's properties. Owners can edit listing fields and photos, mark a property rented, or make it available again. Management changes use owner-protected POST actions. A published property becomes public again when made available unless administration has disabled it.

Browsing does not require an account; saving does. On a public detail page, a logged-out Save action enters Login/Sign Up and returns to that same detail URL after authentication, without saving automatically. Save and Unsave use POST actions. `GET /saved-properties` shows only the signed-in user's saves; the database prevents duplicate relationships. A saved relationship remains if a listing later becomes unavailable, but the saved page labels it **No longer available**, avoids exposing private listing details, and allows removal.

## Administration

The separate administration area starts at `http://127.0.0.1:5000/admin/login`. It uses the existing phone OTP service and a second admin-authenticated session check. An administrator must have an existing active account with a verified login phone. No account is promoted automatically. After applying migrations, grant the first administrator from the CLI:

```powershell
docker compose exec web flask --app run grant-admin +249912345678
```

Use an existing user's verified phone. `revoke-admin` takes the same argument, but refuses to remove the final active administrator. The admin dashboard, property and user management, reports, and admin-rights management are available only after admin OTP login. Moderation disables a listing's public visibility without deleting its data; restoring it makes a published, available listing public again. User suspension blocks authenticated access without deleting listings. The older `/admin/properties/new` owner-posting route remains available to ordinary authenticated users for compatibility.

## Security and tests

Flask-WTF CSRF protection covers state-changing forms. Server-side validation, SQLAlchemy queries, Jinja autoescaping, owner checks, safe local redirect handling, POST-only management/save actions, OTP protections, and image validation protect the current workflows. These controls do not by themselves constitute a production security review.

Run the complete suite with:

```powershell
docker compose exec web pytest
```

The tests cover authentication and redirects, account ownership, posting and editing, photos, public visibility and filters, saved properties, language rendering, and responsive template behavior. The full suite should pass before committing or deploying.

## Production Deployment

This repository is prepared for **Azure App Service → Flask/Gunicorn → Neon PostgreSQL + private Azure Blob Storage**. It does not provision or connect to those services. Local Docker Compose still runs Flask with its local PostgreSQL service and `PHOTO_STORAGE_BACKEND=local`.

Configure these App Service environment settings when infrastructure is provisioned:

| Setting | Production purpose |
| --- | --- |
| `MANAZIL_ENV=production` | Select strict production configuration (`APP_ENV` or `FLASK_ENV` is accepted when `MANAZIL_ENV` is absent). |
| `SECRET_KEY` | Stable, random secret of at least 32 characters, stored outside the repository. |
| `DATABASE_URL` | Neon connection string from Neon, including `sslmode=require` or stronger. `postgresql://` is converted to the installed psycopg driver without changing credentials. |
| `PHOTO_STORAGE_BACKEND=azure_blob` | Store staged and published photos in Blob Storage. |
| `AZURE_STORAGE_CONNECTION_STRING` | Private storage credential supplied as an App Service setting. |
| `AZURE_STORAGE_CONTAINER` | Name of an existing **private** blob container. |
| `TRUST_PROXY_HEADERS=1` | Trust one `X-Forwarded-Proto` hop only when behind the trusted App Service proxy. |
| `TRUSTED_HOSTS` | Optional comma-separated allowed App Service/custom hostnames. |

Production refuses a missing/short secret, a non-TLS database URL, local photo storage, missing Blob settings, and development authentication flags. It disables debug mode and uses secure, HTTP-only, SameSite=Lax session cookies. The database health check at `/api/health` remains lightweight and does not reveal credentials. Existing migrations are **not** run during HTTP requests; after configuring the production environment, run `flask --app run db upgrade` as a separate deployment step against the intended database.

For a Linux App Service **code deployment**, set the startup command to `gunicorn --bind=0.0.0.0:8000 --workers=2 --access-logfile=- --error-logfile=- run:app`. The Dockerfile also defaults to Gunicorn on port 5000 if a container deployment is chosen later; Compose overrides it with `python run.py` for local use. Configure HTTPS-only at App Service and set the trusted proxy option only for its proxy path.

Both storage backends retain the same generated `staging/...` and `properties/...` keys. Blob staging manifests live in the private container so different workers can handle successive form requests. Photos are served through the existing Flask public/owner/admin authorization routes; the Blob container should not allow anonymous public access. Existing local photo files are **not** copied to Azure automatically. If database records are ever moved between environments, copy their referenced files to the corresponding Blob keys separately. The Flask request cap is 102 MB for the current 20 × 5 MB photo limit plus form overhead; verify any App Service front-end upload limit before launch.

**Public-launch blocker:** The phone OTP provider is development-only and simulated Facebook Login is not Meta authentication. Development providers are disabled in production; a real delivery/authentication provider must be implemented and configured before public use, including administrator login. No Neon credentials, Blob credentials, or real photos have been used in this preparation stage.

## Not yet implemented

The repository has no real Meta Facebook Login, production WhatsApp/OTP delivery, Facebook-to-verified-phone linking, or per-property WhatsApp contact verification. Azure Blob support is implemented but no Azure resources or production deployment are configured. Maps, payments, and AI features are not part of the current application.
