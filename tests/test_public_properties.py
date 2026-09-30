from datetime import date

import pytest

from app import db, routes
from app.models import Property, PropertyPhoto
from test_properties import migrated_connection, values
from test_property_creation import client


def add_property(values, **overrides):
    property = Property(**(values | overrides))
    db.session.add(property)
    db.session.commit()
    return property


@pytest.mark.parametrize("language,empty_message,direction", [
    ("ar", "لا توجد عقارات متاحة حالياً.", "rtl"),
    ("en", "No properties are currently available.", "ltr"),
])
def test_public_page_empty_state_and_language(client, language, empty_message, direction):
    suffix = "?lang=en" if language == "en" else ""
    response = client.get("/properties" + suffix)
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert f'<html lang="{language}" dir="{direction}">' in html
    assert empty_message in html
    assert f'href="/properties{suffix}"' in html
    assert 'aria-current="page"' in html
    assert 'href="/properties?lang=en"' in html


def test_only_published_available_properties_appear(client, values):
    cases = [
        ("published", "available", "Public home"),
        ("draft", "available", "Draft secret"),
        ("published", "rented", "Rented secret"),
    ]
    for publication, availability, title in cases:
        add_property(values, title_en=title, publication_status=publication, availability_status=availability)
    for path in ("/properties?lang=en", "/properties?lang=en&publication_status=draft&availability_status=rented"):
        html = client.get(path).get_data(as_text=True)
        assert "Public home" in html
        assert all(title not in html for _, _, title in cases[1:])
        assert html.count('class="property-card"') == 1


@pytest.mark.parametrize("available_date,english,arabic", [
    (None, "Available Now", "متاح الآن"),
    (date(2026, 10, 1), "Available Now", "متاح الآن"),
    (date(2026, 9, 30), "Available Now", "متاح الآن"),
    (date(2026, 10, 15), "Available from October 15, 2026", "متاح من 15 أكتوبر 2026"),
])
def test_availability_dates_keep_property_visible(client, values, monkeypatch, available_date, english, arabic):
    monkeypatch.setattr(routes, "sudan_today", lambda: date(2026, 10, 1))
    add_property(values, publication_status="published", available_from_date=available_date)
    for path, expected in (("/properties?lang=en", english), ("/properties", arabic)):
        html = client.get(path).get_data(as_text=True)
        title = "Apartment in Khartoum" if "lang=en" in path else "شقة في الخرطوم"
        assert title in html
        assert '<span class="availability-dot" aria-hidden="true"></span>' in html
        assert f'<span class="availability-text">{expected}</span>' in html


@pytest.mark.parametrize("property_type,english,arabic", [
    ("apartment", "Apartment", "شقة"),
    ("house", "House", "منزل"),
    ("villa", "Villa", "فيلا"),
    ("office", "Office", "مكتب"),
    ("shop", "Shop", "محل"),
    ("land", "Land", "أرض"),
])
def test_property_type_is_localized(client, values, property_type, english, arabic):
    add_property(values, publication_status="published", property_type=property_type)
    assert f'class="property-card-type">{english}</p>' in client.get("/properties?lang=en").get_data(as_text=True)
    assert f'class="property-card-type">{arabic}</p>' in client.get("/properties").get_data(as_text=True)


@pytest.mark.parametrize("furnished,english,arabic", [
    (True, "Furnished", "مفروش"),
    (False, "Unfurnished", "غير مفروش"),
])
def test_card_language_and_safe_fields(client, values, furnished, english, arabic):
    add_property(
        values, publication_status="published", furnished=furnished,
        description_en="PRIVATE DESCRIPTION", description_ar="وصف خاص",
        contact_name="PRIVATE CONTACT", phone="PRIVATE PHONE", whatsapp="PRIVATE WHATSAPP",
    )
    english_html = client.get("/properties?lang=en").get_data(as_text=True)
    arabic_html = client.get("/properties").get_data(as_text=True)
    for html, expected, title, city, area, other_title in (
        (english_html, english, values["title_en"], values["city_en"], values["area_en"], values["title_ar"]),
        (arabic_html, arabic, values["title_ar"], values["city_ar"], values["area_ar"], values["title_en"]),
    ):
        assert title in html and city in html and area in html
        assert other_title not in html
        assert expected in html
        assert "125,000.5 SDG" in html
        assert 'class="property-card-action" href="/properties/' in html
        for secret in ("PRIVATE DESCRIPTION", "وصف خاص", "PRIVATE CONTACT", "PRIVATE PHONE", "PRIVATE WHATSAPP"):
            assert secret not in html
    assert "Bedrooms" in english_html and "Bathrooms" in english_html
    assert "غرف النوم" in arabic_html and "الحمامات" in arabic_html
    assert ">View Property</a>" in english_html
    assert ">عرض العقار</a>" in arabic_html


def test_user_content_is_escaped(client, values):
    add_property(values, publication_status="published", title_en="<script>unsafe</script>")
    html = client.get("/properties?lang=en").get_data(as_text=True)
    assert "<script>unsafe</script>" not in html
    assert "&lt;script&gt;unsafe&lt;/script&gt;" in html


@pytest.mark.parametrize("count", [0, 1, 2, 5])
def test_card_photo_primary_count_and_languages(client, values, count):
    property = add_property(values, publication_status="published")
    for index in range(count):
        db.session.add(PropertyPhoto(
            property_id=property.id, category="exterior",
            storage_key=f"properties/{property.id}/{index:032x}.jpg",
            original_filename=f"{index}.jpg", content_type="image/jpeg",
            file_size=1, display_order=index, is_primary=index == count - 1,
        ))
    db.session.commit()
    for suffix, language, title in (("", "ar", values["title_ar"]), ("?lang=en", "en", values["title_en"])):
        html = client.get("/properties" + suffix).get_data(as_text=True)
        assert f'<html lang="{language}" dir="{"rtl" if language == "ar" else "ltr"}">' in html
        assert 'class="property-card-media"' in html
        assert 'class="property-card-image-placeholder" role="img"' in html
        if count:
            primary = property.photos[-1]
            assert f'src="/properties/photos/{primary.id}" alt="{title}" loading="lazy" decoding="async"' in html
            assert "onerror=\"this.previousElementSibling.removeAttribute('aria-hidden');this.hidden=true\"" in html
        else:
            assert 'class="property-card-image"' not in html
        assert ('class="property-card-photo-count"' in html) == (count > 1)
        if count > 1:
            assert f'<span>{count}</span>' in html
