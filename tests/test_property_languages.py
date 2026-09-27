from collections import Counter
from html.parser import HTMLParser

import pytest
from sqlalchemy import select

from app import db
from app.models import DRAFT_OPTIONAL_TEXT_FIELDS, Property
from app.property_forms import FORM_FIELDS
from test_properties import migrated_connection, values
from test_property_creation import client, form_data, property_count


class FormHTML(HTMLParser):
    def __init__(self, response):
        super().__init__()
        self.controls = []
        self.values = {}
        self.active = None
        self.links = []
        self.root = {}
        self.feed(response.get_data(as_text=True))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "html":
            self.root = attrs
        if tag == "a":
            self.links.append(attrs.get("href"))
        name = attrs.get("name")
        if tag in ("input", "textarea", "select") and name:
            self.controls.append((tag, attrs))
            if tag == "input":
                if attrs.get("type") != "checkbox" or "checked" in attrs:
                    self.values[name] = attrs.get("value", "on" if attrs.get("type") == "checkbox" else "")
            else:
                self.active = (tag, name)
                self.values[name] = ""
        if tag == "option" and self.active and "selected" in attrs:
            self.values[self.active[1]] = attrs.get("value", "")

    def handle_data(self, data):
        if self.active and self.active[0] == "textarea":
            self.values[self.active[1]] += data

    def handle_endtag(self, tag):
        if self.active and tag == self.active[0]:
            self.active = None


def assert_single_language(response, language, step=1):
    parsed = FormHTML(response)
    assert parsed.root["lang"] == language
    assert parsed.root["dir"] == ("rtl" if language == "ar" else "ltr")
    assert parsed.values["_step"] == str(step)
    counts = Counter(attrs["name"] for _, attrs in parsed.controls)
    for name in FORM_FIELDS:
        if name in DRAFT_OPTIONAL_TEXT_FIELDS:
            assert counts[name] == 0
            continue
        assert counts[name] == 1
    for key in ("title_ar", "description_ar", "city_ar", "area_ar"):
        control = next(attrs for _, attrs in parsed.controls if attrs["name"] == key)
        assert (control.get("type") == "hidden") == (key not in ("title_ar", "description_ar"))
    assert "publication_status" not in parsed.values
    return parsed


@pytest.mark.parametrize("path", ["/", "/admin/properties/new"])
def test_arabic_default_ignores_browser_language_and_prior_switch(client, path):
    response = client.get(path, headers={"Accept-Language": "en-US,en;q=0.9"})
    assert '<html lang="ar" dir="rtl">' in response.get_data(as_text=True)
    assert '<html lang="en" dir="ltr">' in client.get(path + "?lang=en").get_data(as_text=True)
    assert '<html lang="ar" dir="rtl">' in client.get(path).get_data(as_text=True)


@pytest.mark.parametrize("language", ["ar", "en"])
def test_only_one_visible_language_and_one_copy_of_fields(client, language):
    page = client.get(f"/admin/properties/new?lang={language}")
    parsed = assert_single_language(page, language)
    assert next(attrs for _, attrs in parsed.controls if attrs["name"] == "title_ar").get("type") != "hidden"
    assert 'aria-current="step"' in page.get_data(as_text=True)


@pytest.mark.parametrize("language", ["ar", "en"])
def test_navigation_and_homepage_cta(client, language):
    suffix = "?lang=en" if language == "en" else ""
    response = client.get("/" + suffix)
    parsed = FormHTML(response)
    assert "/" + suffix in parsed.links
    assert parsed.links.count("/admin/properties/new" + suffix) == 2
    assert "/properties" + suffix in parsed.links


def test_switching_preserves_partial_and_invalid_entries_without_saving(client, form_data):
    first = assert_single_language(client.get("/admin/properties/new"), "ar")
    first.values.update(title_ar="عنوان جزئي", monthly_rent="not a number")
    english = client.post("/admin/properties", data=first.values | {"_action": "switch_en"})
    carried = assert_single_language(english, "en")
    assert carried.values["title_ar"] == "عنوان جزئي"
    assert carried.values["monthly_rent"] == "not a number"
    assert property_count() == 0


def test_review_submits_arabic_only_property(client, form_data):
    page = client.get("/admin/properties/new?lang=en")
    data = FormHTML(page).values | {key: value for key, value in form_data.items() if key not in DRAFT_OPTIONAL_TEXT_FIELDS} | {"_wizard": "1", "_step": "7", "_action": "submit", "publication_status": "published"}
    response = client.post("/admin/properties", data=data)
    assert response.status_code == 303
    assert property_count() == 1
    saved = db.session.scalar(select(Property))
    for key in ("title", "description", "city", "area"):
        assert getattr(saved, f"{key}_ar") == form_data[f"{key}_ar"]
        assert getattr(saved, f"{key}_en") == ""
    assert (saved.state_en, saved.state_ar) == (form_data["state_en"], form_data["state_ar"])
    assert saved.publication_status == "pending"


def test_final_save_checks_hidden_arabic_fields(client, form_data):
    response = client.post("/admin/properties", data=form_data | {
        "_wizard": "1", "_step": "7", "_action": "submit", "title_ar": "",
    })
    assert response.status_code == 422
    assert_single_language(response, "ar", 1)
    assert 'id="title_ar-error"' in response.get_data(as_text=True)
    assert property_count() == 0


def test_arabic_confirmation_remains_translated(client, form_data):
    response = client.post("/admin/properties", data=form_data | {
        "_wizard": "1", "_step": "7", "_action": "submit", "_language": "ar",
    }, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<html lang="ar" dir="rtl">' in html
    assert "تم إرسال العقار للمراجعة بنجاح." in html
    assert property_count() == 1
