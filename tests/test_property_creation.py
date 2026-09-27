import re
from unittest.mock import patch

from flask import current_app
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import scoped_session, sessionmaker

from app import db
from app.models import DRAFT_OPTIONAL_TEXT_FIELDS, Property
from app.property_forms import FORM_FIELDS, TEXT_FIELDS
from test_properties import migrated_connection, values


@pytest.fixture
def client(migrated_connection, monkeypatch):
    # Reuse Stage 2A's real migration and rolled-back PostgreSQL schema.
    sessions = scoped_session(sessionmaker(
        bind=migrated_connection, join_transaction_mode="create_savepoint",
    ))
    monkeypatch.setattr(db, "session", sessions)
    try:
        yield current_app.test_client()
    finally:
        sessions.remove()


@pytest.fixture
def form_data(values, client):
    response = client.get("/admin/properties/new?lang=en")
    token = re.search(r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True))
    assert token is not None
    return {key: str(value) for key, value in values.items()} | {
        "csrf_token": token.group(1),
        "_language": "en",
        "availability_mode": "now", "available_from_date": "",
        "currency": "SDG", "contact_role": "broker", "availability_status": "rented",
        "size": "120.5", "furnished": "on", "whatsapp": "+249123456789",
        "amenities": " Air conditioning \r\n\nParking\n Kitchen \nBalcony\n",
    }


def property_count():
    return db.session.scalar(select(func.count()).select_from(Property))


def test_creation_form(client):
    response = client.get("/admin/properties/new?lang=en")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    for name in FORM_FIELDS:
        if name in DRAFT_OPTIONAL_TEXT_FIELDS:
            assert f'name="{name}"' not in html
            continue
        assert f'name="{name}"' in html
    for section in ("Basic Information", "Location", "Property Details", "Photos", "Contact Information", "Review"):
        assert section in html
    assert 'name="publication_status"' not in html
    assert 'name="_wizard" value="1"' in html
    assert 'value="SDG"' in html
    assert 'lang="en" dir="ltr"' in html


def test_valid_csrf_token_allows_property_creation(client, form_data):
    response = client.post("/admin/properties", data=form_data)
    assert response.status_code == 303
    assert property_count() == 1


def test_missing_csrf_token_rejected(client, form_data):
    form_data.pop("csrf_token")
    response = client.post("/admin/properties", data=form_data)
    assert response.status_code == 400
    assert "The form could not be submitted." in response.get_data(as_text=True)
    assert property_count() == 0


def test_invalid_csrf_token_rejected_in_arabic(client, form_data):
    response = client.post("/admin/properties", data=form_data | {
        "csrf_token": "invalid", "_language": "ar",
    })
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert '<html lang="ar" dir="rtl">' in html
    assert "تعذّر إرسال النموذج." in html
    assert property_count() == 0


@pytest.mark.parametrize("role", ["owner", "broker"])
@pytest.mark.parametrize("availability", ["available", "rented"])
def test_valid_post_creates_draft(client, form_data, role, availability):
    response = client.post("/admin/properties", data=form_data | {
        "contact_role": role, "availability_status": availability,
        "publication_status": "published", "id": "9999",
    })
    assert response.status_code == 303
    assert response.location.endswith("/admin/properties/new?lang=en")
    assert property_count() == 1
    saved = db.session.scalar(select(Property))
    assert saved.publication_status == "draft"
    assert saved.id != 9999
    assert saved.contact_role == role
    assert saved.availability_status == availability
    assert saved.amenities == ["Air conditioning", "Parking", "Kitchen", "Balcony"]
    assert saved.title_ar == form_data["title_ar"]
    assert str(saved.monthly_rent) == form_data["monthly_rent"]
    assert saved.furnished is True
    assert saved.whatsapp == form_data["whatsapp"]
    success = client.get(response.location)
    assert f"Property #{saved.id} was saved as Draft." in success.get_data(as_text=True)
    client.get(response.location)
    assert property_count() == 1


@pytest.mark.parametrize("field", (*(field for field in TEXT_FIELDS if field not in DRAFT_OPTIONAL_TEXT_FIELDS), "monthly_rent", "bedrooms", "bathrooms"))
@pytest.mark.parametrize("value", [None, "", " \t\n"])
def test_required_fields_rejected(client, form_data, field, value):
    if field in ("city_ar", "city_en", "state_ar", "state_en"):
        form_data["_language"] = field[-2:]
    if value is None:
        form_data.pop(field)
    else:
        form_data[field] = value
    response = client.post("/admin/properties", data=form_data)
    assert response.status_code == 422
    assert f'id="{field}-error"' in response.get_data(as_text=True)
    assert property_count() == 0


@pytest.mark.parametrize("field,value", [
    ("monthly_rent", "-1"), ("bedrooms", "-1"), ("bathrooms", "-1"), ("size", "-1"),
    ("contact_role", "admin"), ("availability_status", "pending"),
    ("monthly_rent", "abc"), ("bedrooms", "abc"), ("bathrooms", "abc"), ("size", "abc"),
    ("monthly_rent", "NaN"), ("size", "Infinity"), ("monthly_rent", "1e999999"),
    ("bedrooms", "2.5"), ("bathrooms", "1.5"), ("bedrooms", "2147483648"),
    ("furnished", "invalid"), ("phone", "bad\x00number"),
    ("amenities", "bad\x00amenity"), ("whatsapp", "bad\x00number"),
])
def test_invalid_values_do_not_save(client, form_data, field, value):
    response = client.post("/admin/properties", data=form_data | {field: value})
    assert response.status_code == 422
    html = response.get_data(as_text=True)
    assert f'id="{field}-error"' in html
    assert form_data["title_ar"] in html
    assert form_data["description_ar"] in html
    assert property_count() == 0


def test_empty_optional_fields_and_zero_numbers(client, form_data):
    for key in ("size", "whatsapp", "amenities", "furnished"):
        form_data.pop(key)
    form_data.update(monthly_rent="0", bedrooms="0", bathrooms="0")
    assert client.post("/admin/properties", data=form_data).status_code == 303
    saved = db.session.scalar(select(Property))
    assert saved.size is None
    assert saved.whatsapp is None
    assert saved.amenities == []
    assert saved.furnished is False
    assert saved.monthly_rent == 0
    assert saved.bedrooms == saved.bathrooms == 0


def test_redisplayed_values_are_escaped(client, form_data):
    form_data.update(title_ar='<script>alert("x")</script>', monthly_rent="invalid")
    response = client.post("/admin/properties", data=form_data)
    assert response.status_code == 422
    html = response.get_data(as_text=True)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert property_count() == 0


def test_database_failure_rolls_back_flushed_record(client, form_data):
    session = db.session()
    with patch.object(session, "commit", side_effect=SQLAlchemyError("private database details")):
        with patch.object(session, "rollback", wraps=session.rollback) as rollback:
            response = client.post("/admin/properties", data=form_data)
            rollback.assert_called_once()
    assert response.status_code == 503
    html = response.get_data(as_text=True)
    assert "could not be saved" in html
    assert form_data["title_ar"] in html
    assert "private database details" not in html
    assert property_count() == 0
    assert client.post("/admin/properties", data=form_data).status_code == 303
    assert property_count() == 1
