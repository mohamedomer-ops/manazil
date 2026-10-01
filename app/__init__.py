import os
import secrets

from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect


db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        PHOTO_STORAGE_ROOT=os.environ.get("PHOTO_STORAGE_ROOT") or os.path.join(app.instance_path, "property_photos"),
        MAX_CONTENT_LENGTH=102 * 1024 * 1024,
        OTP_DEVELOPMENT_MODE=os.environ.get('OTP_DEVELOPMENT_MODE') == '1',
        ENVIRONMENT=os.environ.get('MANAZIL_ENV', 'production'),
        FACEBOOK_DEVELOPMENT_MODE=os.environ.get('FACEBOOK_DEVELOPMENT_MODE') == '1',
        FACEBOOK_DEVELOPMENT_USER_ID=os.environ.get('FACEBOOK_DEVELOPMENT_USER_ID', 'development-facebook-user'),
        FACEBOOK_DEVELOPMENT_DISPLAY_NAME=os.environ.get('FACEBOOK_DEVELOPMENT_DISPLAY_NAME', 'Development Facebook User'),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SQLALCHEMY_ENGINE_OPTIONS={
            "pool_pre_ping": True,
            "connect_args": {"connect_timeout": 3},
        },
    )
    if test_config:
        app.config.update(test_config)
    database_url = app.config["SQLALCHEMY_DATABASE_URI"]
    if not database_url or not database_url.startswith("postgresql+psycopg://"):
        raise ValueError("Set DATABASE_URL to a postgresql+psycopg:// connection URL.")
    db.init_app(app)
    csrf.init_app(app)

    from app import models

    migrate.init_app(app, db, render_as_batch=False)

    from app.routes import main
    from app.admin import admin, new_property
    from app.auth import auth
    from app.ownership import ownership
    from app.saved import saved
    from app.languages import template_language

    app.register_blueprint(main)
    app.register_blueprint(admin)
    app.register_blueprint(auth)
    app.register_blueprint(ownership)
    app.register_blueprint(saved)
    from app.facebook_provider import configure_facebook
    configure_facebook(app)
    app.add_url_rule("/properties/new", endpoint="property_new", view_func=new_property, methods=["GET"])
    app.context_processor(template_language)
    @app.cli.command('dev-otp')
    @__import__('click').argument('phone')
    def dev_otp(phone):
        """Read a code in an explicitly configured development environment."""
        if not (app.config['OTP_DEVELOPMENT_MODE'] or app.testing):
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
