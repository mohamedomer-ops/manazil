from datetime import date
from decimal import Decimal

import pytest

from app import routes
from test_properties import migrated_connection, values
from test_property_creation import client
from test_public_properties import add_property


def test_published_available_property_details_in_both_languages(client, values):
    property = add_property(
        values, publication_status="published", property_type="villa",
        size=Decimal("120.5"), furnished=True, amenities=["Parking", "Kitchen"],
        contact_role="owner", whatsapp="+249 123 456 780",
    )
    for path, title, city, area, description, other_title, type_name, furnished in (
        (f"/properties/{property.id}", values["title_ar"], values["city_ar"], values["area_ar"], values["description_ar"], values["title_en"], "فيلا", "مفروش"),
        (f"/properties/{property.id}?lang=en", values["title_en"], values["city_en"], values["area_en"], values["description_en"], values["title_ar"], "Villa", "Furnished"),
    ):
        response = client.get(path)
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert title in html and city in html and area in html and description in html
        assert other_title not in html
        assert f'<dd>{type_name}</dd>' in html
        assert furnished in html
        assert "125,000.5 SDG" in html
        assert "120.5" in html
        assert "Parking" in html and "Kitchen" in html
        assert values["contact_name"] in html
        assert values["phone"] in html
        assert 'href="tel:+249123456789"' in html
        assert 'href="https://wa.me/249123456780"' in html
        assert 'class="detail-gallery"' in html or 'class="photo-gallery detail-gallery"' in html
        assert 'class="detail-contact-action"' in html
        assert html.index('id="facts-heading"') < html.index('id="contact-heading"')
        assert html.index('id="description-heading"') < html.index('id="facts-heading"')
    assert '<html lang="ar" dir="rtl">' in client.get(f"/properties/{property.id}").get_data(as_text=True)
    assert '<html lang="en" dir="ltr">' in client.get(f"/properties/{property.id}?lang=en").get_data(as_text=True)


@pytest.mark.parametrize("publication,availability", [
    ("draft", "available"), ("published", "rented"),
])
def test_non_public_property_details_return_404(client, values, publication, availability):
    property = add_property(values, publication_status=publication, availability_status=availability)
    for suffix in ("", "?lang=en&publication_status=published&availability_status=available"):
        response = client.get(f"/properties/{property.id}{suffix}")
        assert response.status_code == 404
        assert values["title_en"] not in response.get_data(as_text=True)
        assert values["title_ar"] not in response.get_data(as_text=True)


def test_nonexistent_and_invalid_ids_return_404(client):
    assert client.get("/properties/999999").status_code == 404
    assert client.get("/properties/not-an-id").status_code == 404


@pytest.mark.parametrize("available_date,english,arabic", [
    (None, "Available Now", "متاح الآن"),
    (date(2026, 10, 1), "Available Now", "متاح الآن"),
    (date(2026, 9, 30), "Available Now", "متاح الآن"),
    (date(2026, 10, 15), "Available from October 15, 2026", "متاح من 15 أكتوبر 2026"),
])
def test_detail_availability_uses_listing_logic(client, values, monkeypatch, available_date, english, arabic):
    monkeypatch.setattr(routes, "sudan_today", lambda: date(2026, 10, 1))
    property = add_property(values, publication_status="published", available_from_date=available_date)
    for suffix, expected in (("?lang=en", english), ("", arabic)):
        html = client.get(f"/properties/{property.id}{suffix}").get_data(as_text=True)
        assert expected in html


@pytest.mark.parametrize("role,english,arabic", [
    ("owner", "Contact Owner", "تواصل مع المالك"),
    ("broker", "Contact Broker", "تواصل مع الوسيط"),
])
def test_contact_role_and_action_are_localized(client, values, role, english, arabic):
    property = add_property(values, publication_status="published", contact_role=role)
    en = client.get(f"/properties/{property.id}?lang=en").get_data(as_text=True)
    ar = client.get(f"/properties/{property.id}").get_data(as_text=True)
    assert english in en and ("Owner" if role == "owner" else "Broker") in en
    assert arabic in ar and ("مالك" if role == "owner" else "وسيط") in ar
    assert "WhatsApp" not in en and "واتساب" not in ar


def test_contact_links_reject_unsafe_numbers_and_user_content_is_escaped(client, values):
    property = add_property(
        values, publication_status="published", phone="javascript:alert(1)",
        whatsapp="<script>unsafe</script>", description_en="<script>unsafe</script>",
    )
    html = client.get(f"/properties/{property.id}?lang=en").get_data(as_text=True)
    assert 'href="javascript:' not in html
    assert 'href="https://wa.me/' not in html
    assert 'class="detail-contact-action" type="button" disabled' in html
    assert "<script>unsafe</script>" not in html
    assert "&lt;script&gt;unsafe&lt;/script&gt;" in html


def test_listing_links_to_correct_details_page_and_keeps_language(client, values):
    first = add_property(values, publication_status="published", title_en="First home")
    second = add_property(values, publication_status="published", title_en="Second home")
    for suffix in ("", "?lang=en"):
        html = client.get("/properties" + suffix).get_data(as_text=True)
        assert f'href="/properties/{first.id}{suffix}"' in html
        assert f'href="/properties/{second.id}{suffix}"' in html
        assert 'type="button" disabled' not in html
        assert client.get(f"/properties/{first.id}{suffix}").status_code == 200


def test_detail_language_switch_stays_on_same_property(client, values):
    property = add_property(values, publication_status="published")
    arabic = client.get(f"/properties/{property.id}").get_data(as_text=True)
    english = client.get(f"/properties/{property.id}?lang=en").get_data(as_text=True)
    assert f'href="/properties/{property.id}?lang=en" lang="en"' in arabic
    assert f'href="/properties/{property.id}" lang="ar"' in english


def test_optional_size_and_amenities_sections_are_omitted(client, values):
    property = add_property(values, publication_status="published")
    html = client.get(f"/properties/{property.id}?lang=en").get_data(as_text=True)
    assert 'id="amenities-heading"' not in html
    assert "Size in square meters" not in html
