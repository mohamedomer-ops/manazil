# Manazil

Manazil is a Sudan-focused property marketplace for rent and sale, available at <https://www.manazilelsaudan.com>. Visitors can browse, search, and view listings without an account. Accounts support property posting and management, saved properties, and contact profiles. Arabic is the default language, with an English switch and RTL/LTR layouts.

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
  facebook_auth.py, facebook_provider.py, meta_facebook_provider.py
                          Development simulator and real Meta OAuth
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
.github/workflows/        Container image build and GHCR publishing
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

The homepage has a Sudan-focused hero image slideshow with a Post Property action. Its filter form sits under Find What Fits You, followed by the newest four public properties. Search uses the same GET filters as `/properties`.

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

`/auth` offers Sign In and Sign Up. The public forms use a calling-code selector (Sudan +249 by default) and a local phone number. Manual Sign Up collects a full name, WhatsApp/mobile number, and password; it normalizes the combined number, stores a password hash, and signs the user in without OTP. The number is not marked verified. Password login uses the same normalized number. Facebook and phone OTP authentication remain implemented but are hidden from the public auth UI while their providers are being prepared. Authentication preserves a safe local `next` destination, such as `/properties/new` or a property detail URL. Logout ends the session.

The current OTP delivery is a **development provider**. It stores the code locally for development; it does **not** send a real WhatsApp message. OTP codes are hashed in the database and protected by expiry, attempt limits, single use, and request throttling. After requesting a code locally, inspect it with:

```powershell
docker compose exec web flask --app run dev-otp +249912345678
```

Manazil also retains Facebook authentication behind a provider setting for existing linked accounts. Local Compose uses a **simulated development provider** with a stable fake identity; it does not contact Meta. Selecting `FACEBOOK_AUTH_PROVIDER=meta` enables the real authorization-code provider only when its app ID, secret, and HTTPS callback are configured. Facebook is not presented in the public authentication UI. Production never falls back to the simulator. Phone OTP remains available internally. A Facebook-only account can complete its contact profile and post without a verified OTP-login phone; its WhatsApp contact number is separate from authentication identity.
Google Sign-In is the public social-login option when `PUBLIC_GOOGLE_LOGIN_ENABLED=1` and a Google OAuth web client is configured. It uses OpenID Connect authorization code, signed ID-token verification, and the stable Google account ID. Google users complete a contact number using the existing social-profile page; their number is not marked OTP-verified. Existing Facebook-linked accounts and backend routes remain available, but Facebook is not shown on the public Sign In or Sign Up pages. Social identities are never automatically merged with phone/password accounts.

`/account` displays account identity and contact information. Users can edit contact name, WhatsApp number, and Owner/Broker role; the account phone is read-only in Account & Security, with verification indicated only when OTP has actually verified it. The page links to Saved Properties and Post Property. My Properties remains available in authenticated navigation. Arabic interface text is the default on each request; the language switch selects English (`lang=en`) or Arabic, with RTL Arabic and LTR English. Optional English property title/description fall back to Arabic content when absent.

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

## Production deployment

Production runs the Docker image on **Azure Container Apps** (`manazil-container` in `manazil-container-env`, resource group `rg-manazil-prod`). The container starts Flask through Gunicorn on port **5000**. The app connects to **Neon PostgreSQL** and stores property photos in a **private Azure Blob Storage** container. Container Apps scales from **0 to 2 replicas**. Azure Container Apps managed certificates provide HTTPS for both custom domains. Local development remains Docker Compose with its own PostgreSQL `db` service and local photo storage; it does not use Neon or Azure Blob Storage.

<https://www.manazilelsaudan.com> is canonical. In production, requests to <https://manazilelsaudan.com> receive an HTTP **308** redirect to the equivalent `www` URL, retaining path and query string. Both hosts are trusted by the application. The production health endpoint is <https://www.manazilelsaudan.com/api/health>; it checks database connectivity without exposing credentials.

### Container image and updates

The [GitHub Actions workflow](.github/workflows/container-image.yml) builds the repository's Dockerfile on pushes to `main` and by manual dispatch. It logs in to GHCR using GitHub Actions' `GITHUB_TOKEN` and publishes `ghcr.io/mohamedomer-ops/manazil` with `latest` and commit-SHA tags. The Dockerfile runs Gunicorn on port 5000 with two workers; its access log omits query strings so OAuth callback codes are not logged. Local Compose overrides this with `python run.py`.

For an update: run the full test suite, push the reviewed change to `main` or dispatch the workflow, confirm its image build succeeds, and deploy the immutable commit-SHA tag to the existing Container App (with its existing GHCR registry access):

```powershell
$commitSha = (git rev-parse HEAD).Trim()
az containerapp update --name manazil-container --resource-group rg-manazil-prod --image "ghcr.io/mohamedomer-ops/manazil:$commitSha"
Invoke-RestMethod https://www.manazilelsaudan.com/api/health
```

Check the new revision and application logs after updating. Keep the Container App ingress target port at **5000**. The image workflow publishes an image; it does not itself update the running Container App. Do not place registry credentials in this repository. [Azure Container Apps CLI reference](https://learn.microsoft.com/en-us/cli/azure/containerapp?view=azure-cli-latest) documents the image update command.

### Runtime settings and migrations

Configure runtime settings and secrets in Azure Container Apps, not in source control. These are the application variable **names**; obtain values from the appropriate secret store or service configuration:

| Variable | Purpose |
| --- | --- |
| `MANAZIL_ENV` | Select the production configuration. |
| `SECRET_KEY` | Stable Flask session/CSRF secret. |
| `DATABASE_URL` | Neon PostgreSQL connection URL with TLS required. |
| `PHOTO_STORAGE_BACKEND` | Select Azure Blob Storage. |
| `AZURE_STORAGE_CONNECTION_STRING` | Private Blob Storage credential. |
| `AZURE_STORAGE_CONTAINER` | Private property-photo container name. |
| `TRUST_PROXY_HEADERS` | Trust the configured HTTPS proxy hop. |
| `TRUSTED_HOSTS` | Optional additional exact hosts; both custom domains are already included in production code. |
| `FACEBOOK_AUTH_PROVIDER`, `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`, `FACEBOOK_REDIRECT_URI`, `PUBLIC_FACEBOOK_LOGIN_ENABLED` | Retained Meta provider configuration for existing linked users; the public Facebook button is no longer rendered. |
| `PUBLIC_GOOGLE_LOGIN_ENABLED`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` | Enable public Google Sign-In and configure its OAuth web client and exact callback. Production callback: `https://www.manazilelsaudan.com/auth/google/callback`; local callback: `http://localhost:5000/auth/google/callback`. |
| `DATA_DELETION_CONTACT_EMAIL` | Optional public deletion-request mailbox override. |
| `OTP_DEVELOPMENT_MODE`, `FACEBOOK_DEVELOPMENT_MODE` | Development providers; production rejects them when enabled. |

Production requires a strong secret, a TLS PostgreSQL URL, and Azure Blob configuration; it disables debug mode and uses secure, HTTP-only, SameSite=Lax session cookies. The private Blob container must remain nonpublic. Local photos are not copied to Azure automatically. The current phone OTP provider is development-only, including admin OTP login; manual password signup/login does not depend on it.

Schema changes use the existing Flask-Migrate/Alembic revisions. Run `flask --app run db upgrade` **once as a separate production process with production settings and access to Neon**, before activating a revision that requires the new schema. Never run migrations during HTTP requests or container startup. `MANAZIL_MIGRATION_ONLY` is reserved for the supported database-only Flask migration CLI path when Blob credentials are unavailable; do not set it on the web process. Local migrations continue to use `docker compose exec web flask --app run db upgrade`.

## Not yet implemented

The repository has no production WhatsApp/OTP delivery, Facebook-to-verified-phone linking, or per-property WhatsApp contact verification. Maps, payments, and AI features are not part of the current application.
