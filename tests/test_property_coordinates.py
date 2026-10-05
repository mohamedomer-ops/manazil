"""Optional owner-selected coordinates stay private and survive property edits."""
import re
from decimal import Decimal

import pytest
from sqlalchemy import select

from app import db
from app.models import Property
from test_property_creation import client, form_data
from test_properties import migrated_connection


def latest_property():
    return db.session.scalar(select(Property).order_by(Property.id.desc()))


def test_property_without_map_selection_stores_null_coordinates(client, form_data):
    assert client.post('/admin/properties', data=form_data).status_code == 303
    property = latest_property()
    assert property.latitude is None and property.longitude is None
    assert 'name="latitude"' not in client.get(f'/properties/{property.id}').text


def test_selected_coordinates_persist_and_are_not_public(client, form_data):
    assert client.post('/admin/properties', data=form_data | {
        'latitude': '15.500001', 'longitude': '32.550002'}).status_code == 303
    property = latest_property()
    assert property.latitude == Decimal('15.500001')
    assert property.longitude == Decimal('32.550002')
    public_page = client.get(f'/properties/{property.id}').text
    assert '15.500001' not in public_page and '32.550002' not in public_page


@pytest.mark.parametrize('coordinates', [
    {'latitude': '91', 'longitude': '32'},
    {'latitude': '-91', 'longitude': '32'},
    {'latitude': '15', 'longitude': '181'},
    {'latitude': '15', 'longitude': '-181'},
    {'latitude': 'NaN', 'longitude': '32'},
    {'latitude': 'abc', 'longitude': '32'},
    {'latitude': '15', 'longitude': ''},
    {'latitude': '', 'longitude': '32'},
])
def test_invalid_or_partial_coordinates_are_rejected(client, form_data, coordinates):
    response = client.post('/admin/properties', data=form_data | coordinates)
    assert response.status_code == 422
    assert latest_property() is None
    assert 'name="latitude"' in response.text and 'name="longitude"' in response.text


def test_edit_preserves_and_updates_selected_map_location(client, form_data):
    assert client.post('/admin/properties', data=form_data | {
        'latitude': '15.500001', 'longitude': '32.550002'}).status_code == 303
    property = latest_property()
    route = f'/properties/{property.id}/edit?lang=en'
    page = client.get(route)
    assert page.status_code == 200
    assert 'name="latitude" value="15.500001"' in page.text
    assert 'name="longitude" value="32.550002"' in page.text
    tokens = {name: re.search(fr'name="{name}" value="([^"]+)"', page.text).group(1)
              for name in ('csrf_token', '_photo_token')}
    edit_form = form_data | tokens
    assert client.post(route, data=edit_form).status_code == 303
    db.session.refresh(property)
    assert (property.latitude, property.longitude) == (Decimal('15.500001'), Decimal('32.550002'))
    assert client.post(route, data=edit_form | {'latitude': '16.111111', 'longitude': '33.222222'}).status_code == 303
    db.session.refresh(property)
    assert (property.latitude, property.longitude) == (Decimal('16.111111'), Decimal('33.222222'))


@pytest.mark.parametrize('language,direction,label', [
    ('ar', 'rtl', 'موقع العقار على الخريطة (اختياري)'),
    ('en', 'ltr', 'Property location on map (optional)'),
])
def test_posting_form_map_is_optional_and_localized(client, language, direction, label):
    page = client.get('/admin/properties/new' + ('?lang=en' if language == 'en' else ''))
    assert page.status_code == 200
    assert f'<html lang="{language}" dir="{direction}">' in page.text
    assert label in page.text
    assert 'id="property-location-map"' in page.text
    assert '/static/vendor/leaflet/leaflet.js' in page.text
    assert 'images/property-posting-house.svg' in page.text
    assert page.text.count('id="property-form"') == 1
    assert 'name="_step"' not in page.text


def test_map_fields_do_not_bypass_csrf(client, form_data):
    response = client.post('/admin/properties', data=form_data | {
        'csrf_token': 'invalid', 'latitude': '15', 'longitude': '32'})
    assert response.status_code == 400
    assert latest_property() is None
