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
    from app.admin import admin
    from app.languages import template_language

    app.register_blueprint(main)
    app.register_blueprint(admin)
    app.context_processor(template_language)
    return app
