from datetime import timedelta

import pytest
from sqlalchemy import select

from app import db
from app.models import DRAFT_OPTIONAL_TEXT_FIELDS, Property
from app.property_forms import sudan_today
from test_properties import migrated_connection, values
from test_property_creation import client, form_data, property_count
from test_property_languages import FormHTML


def submit(client, page, action, **updates):
    data = FormHTML(page).values | updates | {"_action": action}
    return client.post("/admin/properties", data=data)


def test_wizard_next_back_preserves_entries_and_validates_only_current_step(client):
    first = client.get("/admin/properties/new")
    assert 'name="_step" value="1"' in first.get_data(as_text=True)
    missing = submit(client, first, "next")
    assert missing.status_code == 422
    assert 'id="title_ar-error"' in missing.get_data(as_text=True)
    second = submit(client, first, "next", title_ar="شقة مريحة",
                    description_ar="وصف العقار", property_type="apartment")
    assert second.status_code == 200
    assert FormHTML(second).values["_step"] == "2"
    # Contact details are still empty, but Step 1 can advance.
    back = submit(client, second, "back")
    parsed = FormHTML(back)
    assert parsed.values["_step"] == "1"
    assert parsed.values["title_ar"] == "شقة مريحة"
    assert property_count() == 0


@pytest.mark.parametrize("language", ["ar", "en"])
def test_wizard_language_switch_and_location(client, language):
    first = client.get("/admin/properties/new")
    location = submit(client, first, "switch_" + language, _step="2")
    html = location.get_data(as_text=True)
    assert f'<html lang="{language}" dir="{"rtl" if language == "ar" else "ltr"}">' in html
    name = f"state_{language}"
    assert f'<select id="{name}" name="{name}"' in html
    assert 'name="city_ar"' in html
    assert 'name="area_ar"' in html
    assert 'name="title_en"' not in html
    assert property_count() == 0


def test_invalid_state_and_past_date_cannot_advance(client, form_data):
    page = client.get("/admin/properties/new?lang=en")
    location = submit(client, page, "switch_en", _step="2")
    rejected = submit(client, location, "next", state_en="North Darfur",
                      city_ar="الخرطوم", area_ar="الوسط")
    assert rejected.status_code == 422
    assert 'id="state_en-error"' in rejected.get_data(as_text=True)
    price = submit(client, page, "switch_en", _step="4")
    past = submit(client, price, "next", monthly_rent="100",
                  currency="SDG", availability_mode="date",
                  available_from_date=(sudan_today() - timedelta(days=1)).isoformat())
    assert past.status_code == 422
    assert 'id="available_from_date-error"' in past.get_data(as_text=True)
    future = submit(client, price, "next", monthly_rent="100",
                    currency="SDG", availability_mode="date",
                    available_from_date=(sudan_today() + timedelta(days=1)).isoformat())
    assert future.status_code == 200
    assert FormHTML(future).values["_step"] == "5"


def test_review_edit_and_submit_creates_one_pending_property(client, form_data):
    first = client.get("/admin/properties/new?lang=en")
    page = first
    for step in range(1, 7):
        data = FormHTML(page).values | {key: value for key, value in form_data.items() if key not in DRAFT_OPTIONAL_TEXT_FIELDS} | {"_wizard": "1", "_step": str(step), "_action": "next"}
        page = client.post("/admin/properties", data=data)
        assert page.status_code == 200
        assert FormHTML(page).values["_step"] == str(step + 1)
        assert property_count() == 0
    html = page.get_data(as_text=True)
    assert form_data["title_ar"] in html
    assert "No photos added." in html
    assert 'value="go_2"' in html
    edited = submit(client, page, "go_2")
    assert FormHTML(edited).values["_step"] == "2"
    result = submit(client, page, "submit", publication_status="published")
    assert result.status_code == 303
    assert property_count() == 1
    saved = db.session.scalar(select(Property))
    assert saved.publication_status == "pending"
    assert saved.state_en == "Khartoum"
    assert saved.title_en == saved.description_en == saved.city_en == saved.area_en == ""


@pytest.mark.parametrize("token", [None, "invalid"])
def test_wizard_csrf_rejects_missing_or_invalid_token(client, token):
    page = client.get("/admin/properties/new")
    data = FormHTML(page).values | {"_action": "next", "title_ar": "عنوان"}
    if token is None:
        data.pop("csrf_token")
    else:
        data["csrf_token"] = token
    response = client.post("/admin/properties", data=data)
    assert response.status_code == 400
    assert property_count() == 0
