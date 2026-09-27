from collections import Counter
from html.parser import HTMLParser

import pytest
from sqlalchemy import select

from app import db
from app.models import Property
from app.property_forms import FORM_FIELDS
from test_properties import migrated_connection, values
from test_property_creation import client, form_data, property_count


class FormHTML(HTMLParser):
    """Read real rendered controls, including values carried between steps."""

    def __init__(self, response):
        super().__init__()
        self.controls = []
        self.values = {}
        self.active = None
        self.option = None
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


def assert_single_language(response, language):
    parsed = FormHTML(response)
    other = "en" if language == "ar" else "ar"
    assert parsed.root["lang"] == language
    assert parsed.root["dir"] == ("rtl" if language == "ar" else "ltr")
    counts = Counter(attrs["name"] for _, attrs in parsed.controls)
    for name in FORM_FIELDS:
        assert counts[name] == 1
    for _, attrs in parsed.controls:
        if attrs["name"] in {f"{field}_{other}" for field in ("title", "description", "city", "area")}:
            assert attrs["type"] == "hidden"
        if attrs["name"] in {f"{field}_{language}" for field in ("title", "description", "city", "area")}:
            assert attrs.get("type") != "hidden"
    assert "publication_status" not in parsed.values
    return parsed


@pytest.mark.parametrize("path", ["/", "/admin/properties/new"])
def test_arabic_default_ignores_browser_language_and_prior_switch(client, path):
    response = client.get(path, headers={"Accept-Language": "en-US,en;q=0.9"})
    assert response.status_code == 200
    assert '<html lang="ar" dir="rtl">' in response.get_data(as_text=True)
    assert '<html lang="en" dir="ltr">' in client.get(path + "?lang=en").get_data(as_text=True)
    # An unqualified visit always starts in Arabic, even with the same cookies.
    assert '<html lang="ar" dir="rtl">' in client.get(path).get_data(as_text=True)
    assert '<html lang="ar" dir="rtl">' in client.get(path + "?lang=fr").get_data(as_text=True)


@pytest.mark.parametrize("language", ["ar", "en"])
def test_only_one_visible_language_and_one_copy_of_shared_fields(client, language):
    assert_single_language(client.get(f"/admin/properties/new?lang={language}"), language)


@pytest.mark.parametrize("language", ["ar", "en"])
def test_navigation_and_homepage_cta(client, language):
    suffix = "?lang=en" if language == "en" else ""
    response = client.get("/" + suffix)
    html = response.get_data(as_text=True)
    parsed = FormHTML(response)
    assert "/" + suffix in parsed.links
    assert parsed.links.count("/admin/properties/new" + suffix) == 2
    assert ("أضف عقارك" if language == "ar" else "List Your Property") in html
    assert ("الرئيسية" if language == "ar" else "Home") in html
    assert "العربية" in html and "English" in html
    assert not any(link.split("?")[0] == "/properties" for link in parsed.links)
    form = FormHTML(client.get("/admin/properties/new" + suffix))
    assert "/" + suffix in form.links
    assert "/admin/properties/new" + suffix in form.links


def test_switching_preserves_partial_and_invalid_entries_without_saving(client, form_data):
    form_data.update(_language="ar", title_ar="عنوان جزئي", title_en="", monthly_rent="not a number")
    english = client.post("/admin/properties", data=form_data | {"_action": "switch_en"})
    assert english.status_code == 200
    carried = assert_single_language(english, "en")
    assert carried.values["title_ar"] == "عنوان جزئي"
    assert carried.values["monthly_rent"] == "not a number"
    assert carried.values["furnished"] == "on"
    assert carried.values["amenities"] == form_data["amenities"]
    arabic = client.post("/admin/properties", data=carried.values | {"_action": "switch_ar"})
    assert arabic.status_code == 200
    returned = assert_single_language(arabic, "ar")
    for key in FORM_FIELDS:
        assert returned.values[key] == form_data[key]
    assert property_count() == 0


def test_two_steps_save_both_languages_in_one_draft(client, form_data):
    arabic_data = FormHTML(client.get("/admin/properties/new")).values
    arabic_data.update({key: value for key, value in form_data.items() if not key.endswith("_en") and key != "_language"})
    english = client.post("/admin/properties", data=arabic_data | {"_action": "next"})
    assert english.status_code == 200
    assert property_count() == 0
    final_data = assert_single_language(english, "en").values
    final_data.update({key: value for key, value in form_data.items() if key.endswith("_en")})
    result = client.post("/admin/properties", data=final_data | {"_action": "save", "publication_status": "published"})
    assert result.status_code == 303
    assert property_count() == 1
    saved = db.session.scalar(select(Property))
    for field in ("title", "description", "city", "area"):
        for language in ("ar", "en"):
            assert getattr(saved, f"{field}_{language}") == form_data[f"{field}_{language}"]
    for key in ("property_type", "currency", "contact_name", "phone", "whatsapp", "contact_role", "availability_status"):
        assert getattr(saved, key) == form_data[key]
    assert str(saved.monthly_rent) == form_data["monthly_rent"]
    assert saved.bedrooms == int(form_data["bedrooms"])
    assert saved.bathrooms == int(form_data["bathrooms"])
    assert str(saved.size) == form_data["size"]
    assert saved.furnished is True
    assert saved.amenities == ["Air conditioning", "Parking", "Kitchen", "Balcony"]
    assert saved.publication_status == "draft"


def test_arabic_validation_and_options(client, form_data):
    response = client.post("/admin/properties", data=form_data | {"_language": "ar", "_action": "next", "title_ar": " ", "monthly_rent": "-1"})
    assert response.status_code == 422
    html = response.get_data(as_text=True)
    assert "هذا الحقل مطلوب." in html
    assert "أدخل عددًا صالحًا ومحدودًا يساوي صفرًا أو أكثر." in html
    assert ">مالك</option>" in html and ">وسيط</option>" in html
    assert ">متاح الآن</option>" in html and ">متاح من تاريخ محدد</option>" in html
    assert ">شقة</option>" in html
    assert "This field is required." not in html
    assert property_count() == 0


def test_final_save_checks_hidden_arabic_fields(client, form_data):
    response = client.post("/admin/properties", data=form_data | {"_action": "save", "title_ar": ""})
    assert response.status_code == 422
    assert_single_language(response, "ar")
    assert "هذا الحقل مطلوب." in response.get_data(as_text=True)
    assert property_count() == 0


@pytest.mark.parametrize("language", ["ar", "en"])
def test_step_guidance_and_save_button(client, language):
    response = client.get(f"/admin/properties/new?lang={language}")
    html = response.get_data(as_text=True)
    assert 'aria-current="step"' in html
    assert 'id="main-content"' in html
    assert "Internal property creation" not in html
    assert "للاستخدام الداخلي" not in html
    if language == "ar":
        assert "التالي: English" in html
        assert 'value="save"' not in html
        assert "تظل التفاصيل المشتركة محفوظة" in html
    else:
        assert '>Save Property</button>' in html
        assert 'class="secondary-button"' in html


def test_arabic_confirmation_remains_translated(client, form_data):
    response = client.post("/admin/properties", data=form_data | {"_language": "ar", "_action": "save"}, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<html lang="ar" dir="rtl">' in html
    assert "حُفظ العقار رقم" in html
    assert "كمسودة" in html
    assert property_count() == 1
    assert db.session.scalar(select(Property)).publication_status == "draft"
