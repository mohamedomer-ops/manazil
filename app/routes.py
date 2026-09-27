from flask import Blueprint, current_app, jsonify, render_template
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import db


main = Blueprint("main", __name__)


@main.get("/")
def index():
    return render_template("index.html")


@main.get("/api/health")
def health():
    try:
        with db.engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
    except SQLAlchemyError:
        current_app.logger.warning("Database health check failed.")
        return jsonify(status="error", service="Manazil", database="unavailable"), 503
    return jsonify(status="ok", service="Manazil", database="connected")
