from datetime import date, timedelta
from html.parser import HTMLParser
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import MetaData, Table, insert, select, text
from sqlalchemy.schema import CreateSchema

from app import create_app, db
from app.models import Property
from app.property_forms import sudan_today
from test_properties import migrated_connection, values
from test_property_creation import client, form_data, property_count
from test_property_languages import FormHTML


EXPECTED_STATES = (
    ("Khartoum", "الخرطوم"), ("Al Jazirah", "الجزيرة"),
    ("Red Sea", "البحر الأحمر"), ("Kassala", "كسلا"),
    ("Gedaref", "القضارف"), ("Sennar", "سنار"),
    ("Blue Nile", "النيل الأزرق"), ("White Nile", "النيل الأبيض"),
    ("Northern", "الشمالية"), ("River Nile", "نهر النيل"),
)

EXCLUDED_STATES = (
    ("North Kordofan", "شمال كردفان"), ("South Kordofan", "جنوب كردفان"),
    ("West Kordofan", "غرب كردفان"), ("North Darfur", "شمال دارفور"),
    ("South Darfur", "جنوب دارفور"), ("West Darfur", "غرب دارفور"),
    ("Central Darfur", "وسط دارفور"), ("East Darfur", "شرق دارفور"),
)


class SelectOptions(HTMLParser):
    def __init__(self, html, name):
        super().__init__()
        self.name = name
        self.in_select = False
        self.option = None
        self.options = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "select":
            self.in_select = attrs.get("name") == self.name
        if tag == "option" and self.in_select:
            self.option = attrs.get("value", "")
            self.options[self.option] = ""

    def handle_data(self, data):
        if self.option is not None:
            self.options[self.option] += data

    def handle_endtag(self, tag):
        if tag == "option":
            self.option = None
        if tag == "select":
            self.in_select = False


@pytest.mark.parametrize("language,index", [("ar", 1), ("en", 0)])
def test_all_10_states_are_localized_dropdown_options(client, language, index):
    response = client.get(f"/admin/properties/new?lang={language}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    options = SelectOptions(html, f"city_{language}").options
    options.pop("")
    assert len(options) == 10
    assert options == {state[index]: state[index] for state in EXPECTED_STATES}
    heading = "المعلومات الأساسية" if language == "ar" else "Basic Information"
    assert f"<legend>{heading}</legend>" in html
    assert f"<legend>{heading} —" not in html


@pytest.mark.parametrize("language,index", [("ar", 1), ("en", 0)])
@pytest.mark.parametrize("state", EXPECTED_STATES)
def test_each_state_saves_its_canonical_bilingual_names(client, form_data, state, language, index):
    response = client.post("/admin/properties", data=form_data | {
        "_language": language, f"city_{language}": state[index],
    })
    assert response.status_code == 303
    assert property_count() == 1
    saved = db.session.scalar(select(Property))
    assert (saved.city_en, saved.city_ar) == state
    assert saved.publication_status == "draft"


@pytest.mark.parametrize("field", ["city_ar", "city_en"])
@pytest.mark.parametrize("value", ["Atlantis", "Port Sudan", "not-a-state"])
def test_arbitrary_state_rejected_in_visible_or_hidden_field(client, form_data, field, value):
    response = client.post("/admin/properties", data=form_data | {field: value})
    assert response.status_code == 422
    assert f'id="{field}-error"' in response.get_data(as_text=True)
    assert property_count() == 0


@pytest.mark.parametrize("language,index", [("ar", 1), ("en", 0)])
@pytest.mark.parametrize("state", EXCLUDED_STATES)
def test_excluded_state_cannot_be_submitted(client, form_data, state, language, index):
    field = f"city_{language}"
    response = client.post("/admin/properties", data=form_data | {
        "_language": language, field: state[index],
    })
    assert response.status_code == 422
    assert f'id="{field}-error"' in response.get_data(as_text=True)
    assert property_count() == 0


def test_state_selection_survives_switching_and_updates_other_translation(client, form_data):
    english = client.post("/admin/properties", data=form_data | {
        "_language": "ar", "city_ar": "البحر الأحمر", "_action": "switch_en",
    })
    carried = FormHTML(english).values
    assert carried["city_en"] == "Red Sea"
    assert carried["city_ar"] == "البحر الأحمر"
    arabic = client.post("/admin/properties", data=carried | {
        "city_en": "Northern", "_action": "switch_ar",
    })
    returned = FormHTML(arabic).values
    assert returned["city_ar"] == "الشمالية"
    assert returned["city_en"] == "Northern"
    assert property_count() == 0


@pytest.mark.parametrize("date_value", [None, "", "not-a-date", "2000-01-01"])
def test_available_now_stores_null_without_requiring_date(client, form_data, date_value):
    form_data["availability_status"] = "available"
    if date_value is None:
        form_data.pop("available_from_date")
    else:
        form_data["available_from_date"] = date_value
    response = client.post("/admin/properties", data=form_data)
    assert response.status_code == 303
    saved = db.session.scalar(select(Property))
    assert saved.available_from_date is None
    assert saved.availability_status == "available"


@pytest.mark.parametrize("date_value", [None, "", " \t", "yesterday", "2026-02-30", "20260101", "2026-01-01T12:00:00"])
def test_future_availability_requires_valid_date(client, form_data, date_value):
    form_data["availability_mode"] = "date"
    if date_value is None:
        form_data.pop("available_from_date")
    else:
        form_data["available_from_date"] = date_value
    response = client.post("/admin/properties", data=form_data)
    assert response.status_code == 422
    assert 'id="available_from_date-error"' in response.get_data(as_text=True)
    assert property_count() == 0


@pytest.mark.parametrize("language", ["ar", "en"])
def test_past_date_rejected_in_each_language(client, form_data, language):
    yesterday = (sudan_today() - timedelta(days=1)).isoformat()
    response = client.post("/admin/properties", data=form_data | {
        "_language": language, "availability_mode": "date", "available_from_date": yesterday,
    })
    assert response.status_code == 422
    html = response.get_data(as_text=True)
    assert ("اختر تاريخ اليوم أو تاريخًا في المستقبل." if language == "ar" else "Choose today or a future date.") in html
    assert f'value="{yesterday}"' in html
    assert property_count() == 0


@pytest.mark.parametrize("days_ahead", [0, 1, 90])
def test_today_or_future_date_persists_in_postgresql(client, form_data, days_ahead):
    available_date = sudan_today() + timedelta(days=days_ahead)
    response = client.post("/admin/properties", data=form_data | {
        "availability_status": "available", "availability_mode": "date", "available_from_date": available_date.isoformat(),
    })
    assert response.status_code == 303
    saved = db.session.scalar(select(Property))
    assert saved.available_from_date == available_date
    assert saved.availability_status == "available"
    assert saved.publication_status == "draft"


def test_date_and_mode_survive_language_switch(client, form_data):
    future_date = (sudan_today() + timedelta(days=30)).isoformat()
    response = client.post("/admin/properties", data=form_data | {
        "availability_mode": "date", "available_from_date": future_date, "_action": "switch_ar",
    })
    parsed = FormHTML(response)
    assert parsed.values["availability_mode"] == "date"
    assert parsed.values["available_from_date"] == future_date
    date_control = next(attrs for _, attrs in parsed.controls if attrs["name"] == "available_from_date")
    assert date_control["type"] == "date"
    assert date_control["min"] == sudan_today().isoformat()
    assert "required" in date_control
    assert property_count() == 0


def test_invalid_availability_mode_rejected(client, form_data):
    response = client.post("/admin/properties", data=form_data | {"availability_mode": "someday"})
    assert response.status_code == 422
    assert 'id="availability_mode-error"' in response.get_data(as_text=True)
    assert property_count() == 0


def test_date_migration_preserves_existing_property(values):
    with create_app({"TESTING": True}).app_context(), db.engine.connect() as connection:
        transaction = connection.begin()
        try:
            schema = f"test_availability_{uuid4().hex}"
            connection.execute(CreateSchema(schema))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            config = Config("migrations/alembic.ini")
            config.set_main_option("script_location", "migrations")
            config.attributes["connection"] = connection
            command.upgrade(config, "0001_properties")
            old_table = Table("properties", MetaData(), autoload_with=connection)
            old_values = values | {"city_en": "Port Sudan", "city_ar": "بورتسودان", "availability_status": "rented"}
            old_record = connection.execute(insert(old_table).values(**old_values).returning(old_table)).mappings().one()
            command.upgrade(config, "head")
            new_table = Table("properties", MetaData(), autoload_with=connection)
            saved = connection.execute(select(new_table)).mappings().one()
            assert saved["available_from_date"] is None
            assert all(saved[key] == value for key, value in old_record.items())
        finally:
            transaction.rollback()
