import os
from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError

from app import create_app, db
from test_auth import client
from test_properties import migrated_connection


@pytest.fixture
def app():
    return create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": os.environ.get(
            "DATABASE_URL", "postgresql+psycopg://manazil@localhost:5432/manazil"
        ),
    })


def test_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "منازل" in response.get_data(as_text=True)


def test_health_returns_json(app):
    response = app.test_client().get("/api/health")
    assert response.is_json
    assert response.json["service"] == "Manazil"
    assert (response.status_code, response.json["status"], response.json["database"]) in {
        (200, "ok", "connected"),
        (503, "error", "unavailable"),
    }


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="Requires PostgreSQL")
def test_live_database_connection(app):
    response = app.test_client().get("/api/health")
    assert response.status_code == 200
    assert response.json["database"] == "connected"


def test_health_database_unavailable(app):
    with app.app_context():
        with patch.object(db.engine, "connect", side_effect=OperationalError("SELECT 1", {}, Exception())):
            response = app.test_client().get("/api/health")
    assert response.status_code == 503
    assert response.json == {"status": "error", "service": "Manazil", "database": "unavailable"}
