import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
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

    from app.routes import main

    app.register_blueprint(main)
    return app
