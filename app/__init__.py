import os
import re
import secrets
import sys

from flask import Flask, redirect, request
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.engine import make_url
from werkzeug.middleware.proxy_fix import ProxyFix


db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
PRODUCTION_TRUSTED_HOSTS = (
    'manazilelsaudan.com',
    'www.manazilelsaudan.com',
    'manazil-prod.azurewebsites.net',
)


def create_app(test_config=None):
    app = Flask(__name__)
    environment = (test_config or {}).get('ENVIRONMENT') or os.environ.get('MANAZIL_ENV') or os.environ.get('APP_ENV') or os.environ.get('FLASK_ENV') or ('testing' if (test_config or {}).get('TESTING') else 'production')
    if environment not in ('development', 'testing', 'production'):
        raise ValueError('MANAZIL_ENV must be development, testing, or production.')
    migration_only = os.environ.get('MANAZIL_MIGRATION_ONLY') == '1'
    if migration_only:
        cli_args = sys.argv[1:]
        if environment != 'production' or 'db' not in cli_args or cli_args[cli_args.index('db') + 1:][:1] not in (['upgrade'], ['current'], ['heads']):
            raise ValueError('MANAZIL_MIGRATION_ONLY is restricted to production Flask database CLI commands.')
    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith('postgresql://'):
        database_url = make_url(database_url).set(drivername='postgresql+psycopg').render_as_string(hide_password=False)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or (secrets.token_hex(32) if environment != 'production' else None),
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        PHOTO_STORAGE_ROOT=os.environ.get("PHOTO_STORAGE_ROOT") or os.path.join(app.instance_path, "property_photos"),
        PHOTO_STORAGE_BACKEND=os.environ.get('PHOTO_STORAGE_BACKEND', 'local' if environment != 'production' else 'azure_blob'),
        AZURE_STORAGE_CONNECTION_STRING=os.environ.get('AZURE_STORAGE_CONNECTION_STRING'),
        AZURE_STORAGE_CONTAINER=os.environ.get('AZURE_STORAGE_CONTAINER'),
        TRUST_PROXY_HEADERS=os.environ.get('TRUST_PROXY_HEADERS') == '1',
        TRUSTED_HOSTS=[host.strip() for host in os.environ.get('TRUSTED_HOSTS', '').split(',') if host.strip()] or None,
        MAX_CONTENT_LENGTH=102 * 1024 * 1024,
        OTP_DEVELOPMENT_MODE=os.environ.get('OTP_DEVELOPMENT_MODE') == '1',
        ENVIRONMENT=environment,
        FACEBOOK_DEVELOPMENT_MODE=os.environ.get('FACEBOOK_DEVELOPMENT_MODE') == '1',
        FACEBOOK_AUTH_PROVIDER=os.environ.get('FACEBOOK_AUTH_PROVIDER'),
        FACEBOOK_APP_ID=os.environ.get('FACEBOOK_APP_ID'),
        FACEBOOK_APP_SECRET=os.environ.get('FACEBOOK_APP_SECRET'),
        FACEBOOK_REDIRECT_URI=os.environ.get('FACEBOOK_REDIRECT_URI'),
        DATA_DELETION_CONTACT_EMAIL=os.environ.get('DATA_DELETION_CONTACT_EMAIL', 'support@manazilelsaudan.com'),
        FACEBOOK_DEVELOPMENT_USER_ID=os.environ.get('FACEBOOK_DEVELOPMENT_USER_ID', 'development-facebook-user'),
        FACEBOOK_DEVELOPMENT_DISPLAY_NAME=os.environ.get('FACEBOOK_DEVELOPMENT_DISPLAY_NAME', 'Development Facebook User'),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=environment == 'production',
        PREFERRED_URL_SCHEME='https' if environment == 'production' else 'http',
        DEBUG=False,
        SQLALCHEMY_ENGINE_OPTIONS={
            "pool_pre_ping": True,
            "pool_recycle": 300,
            "connect_args": {"connect_timeout": 10 if environment == 'production' else 3},
        },
    )
    if test_config:
        app.config.update(test_config)
    deletion_email = app.config.get('DATA_DELETION_CONTACT_EMAIL')
    if deletion_email and (not isinstance(deletion_email, str) or len(deletion_email) > 254 or
                           not re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', deletion_email)):
        raise ValueError('DATA_DELETION_CONTACT_EMAIL must be a valid email address.')
    if app.config['ENVIRONMENT'] == 'production':
        if not deletion_email:
            raise ValueError('Production requires a deletion contact mailbox.')
        app.config['TRUSTED_HOSTS'] = list(dict.fromkeys(
            (*PRODUCTION_TRUSTED_HOSTS, *(app.config['TRUSTED_HOSTS'] or []))))
        if not isinstance(app.config.get('SECRET_KEY'), str) or len(app.config['SECRET_KEY']) < 32:
            raise ValueError('Production requires a stable SECRET_KEY of at least 32 characters.')
        app.config['DEBUG'] = False
        app.config['SESSION_COOKIE_SECURE'] = True
        app.config['PREFERRED_URL_SCHEME'] = 'https'
        if app.config.get('OTP_DEVELOPMENT_MODE') or app.config.get('FACEBOOK_DEVELOPMENT_MODE'):
            raise ValueError('Development authentication modes are forbidden in production.')
    if app.config['PHOTO_STORAGE_BACKEND'] not in ('local', 'azure_blob'):
        raise ValueError('PHOTO_STORAGE_BACKEND must be local or azure_blob.')
    if app.config['ENVIRONMENT'] == 'production' and app.config['PHOTO_STORAGE_BACKEND'] != 'azure_blob':
        raise ValueError('Production requires azure_blob photo storage.')
    if app.config['PHOTO_STORAGE_BACKEND'] == 'azure_blob' and not migration_only and not app.config.get('AZURE_BLOB_CONTAINER_CLIENT'):
        if not app.config.get('AZURE_STORAGE_CONNECTION_STRING') or not app.config.get('AZURE_STORAGE_CONTAINER'):
            raise ValueError('Azure Blob storage requires its connection string and container name.')
    database_url = app.config["SQLALCHEMY_DATABASE_URI"]
    if database_url and database_url.startswith('postgresql://'):
        database_url = make_url(database_url).set(drivername='postgresql+psycopg').render_as_string(hide_password=False)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    if not database_url or not database_url.startswith("postgresql+psycopg://"):
        raise ValueError("Set DATABASE_URL to a postgresql+psycopg:// connection URL.")
    if app.config['ENVIRONMENT'] == 'production':
        if make_url(database_url).query.get('sslmode') not in ('require', 'verify-ca', 'verify-full'):
            raise ValueError('Production DATABASE_URL must require TLS (sslmode=require or stronger).')
    if app.config.get('TRUST_PROXY_HEADERS'):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)

    @app.before_request
    def canonical_production_host():
        if app.config['ENVIRONMENT'] == 'production' and request.host.split(':', 1)[0] == 'www.manazilelsaudan.com':
            path = request.path
            query = request.query_string.decode('latin-1')
            destination = f'https://manazilelsaudan.com{path}'
            if query:
                destination += f'?{query}'
            return redirect(destination, code=308)

    db.init_app(app)
    csrf.init_app(app)

    from app.otp import OTPProviderUnavailable

    @app.errorhandler(OTPProviderUnavailable)
    def unavailable_otp(error):
        from app.languages import current_language, translate
        app.logger.error('OTP delivery is unavailable.')
        return translate('Authentication is temporarily unavailable.', current_language()), 503

    from app import models

    migrate.init_app(app, db, render_as_batch=False)

    from app.routes import main
    from app.admin import admin, new_property
    from app.admin_portal import portal, register_cli
    from app.auth import auth
    from app.ownership import ownership
    from app.saved import saved
    from app.languages import template_language

    app.register_blueprint(main)
    app.register_blueprint(admin)
    app.register_blueprint(portal)
    app.register_blueprint(auth)
    app.register_blueprint(ownership)
    app.register_blueprint(saved)
    from app.facebook_provider import configure_facebook
    configure_facebook(app)
    app.add_url_rule("/properties/new", endpoint="property_new", view_func=new_property, methods=["GET"])
    register_cli(app)
    app.context_processor(template_language)
    @app.cli.command('dev-otp')
    @__import__('click').argument('phone')
    def dev_otp(phone):
        """Read a code in an explicitly configured development environment."""
        if app.config['ENVIRONMENT'] == 'production' or not (app.config['OTP_DEVELOPMENT_MODE'] or app.testing):
            raise __import__('click').ClickException('Development OTP access is disabled.')
        import hashlib
        from app.phone import normalize_phone
        from pathlib import Path
        normalized = normalize_phone(phone)
        path = Path(app.instance_path) / 'dev_otps' / hashlib.sha256(normalized.encode()).hexdigest()
        if not path.is_file():
            raise __import__('click').ClickException('No development OTP for that number.')
        __import__('click').echo(path.read_text())
    return app
