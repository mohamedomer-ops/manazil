"""Listing currency is selected and displayed without changing the price."""
import re

import pytest
from sqlalchemy import select

from app import db
from app.models import Property, SavedProperty, User
from test_property_creation import client, form_data
from test_properties import migrated_connection


@pytest.mark.parametrize('language,labels', [
    ('ar', ('الجنيه السوداني (SDG)', 'الدولار الأمريكي (USD)')),
    ('en', ('Sudanese Pound (SDG)', 'US Dollar (USD)')),
])
def test_currency_options_and_new_property_default(client, language, labels):
    page = client.get('/properties/new' + ('?lang=en' if language == 'en' else ''))
    assert page.status_code == 200
    assert f'<html lang="{language}" dir="{"rtl" if language == "ar" else "ltr"}">' in page.text
    assert 'name="currency" required' in page.text
    assert '<option value="SDG" selected>' in page.text
    assert '<option value="USD" >' in page.text
    assert page.text.index('name="price"') < page.text.index('name="currency"')
    for label in labels:
        assert label in page.text


@pytest.mark.parametrize('transaction,period,currency', [
    ('rent', 'monthly', 'SDG'),
    ('rent', 'weekly', 'USD'),
    ('sale', '', 'SDG'),
    ('sale', '', 'USD'),
])
def test_posting_accepts_only_selected_listing_currency(client, form_data, transaction, period, currency):
    response = client.post('/admin/properties', data=form_data | {
        'transaction_type': transaction, 'rent_period': period, 'currency': currency, 'price': '500',
    })
    assert response.status_code == 303
    property = db.session.scalar(select(Property).order_by(Property.id.desc()))
    assert property.currency == currency and property.price == 500
    assert property.transaction_type == transaction
    assert property.rent_period == (period or None)
    detail = client.get(f'/properties/{property.id}?lang=en')
    assert f'500 {currency}' in detail.text
    assert '500 EUR' not in detail.text
    results = client.get('/properties?lang=en').text
    assert f'500 {currency}' in results
    assert ('Sale price' if transaction == 'sale' else 'Weekly rent' if period == 'weekly' else 'Monthly rent') in results
    if transaction == 'sale':
        assert 'Monthly rent' not in results and 'Weekly rent' not in results


@pytest.mark.parametrize('currency', ['', 'EUR', 'USD ', 'usd'])
def test_unsupported_or_missing_currency_is_rejected(client, form_data, currency):
    response = client.post('/admin/properties', data=form_data | {'currency': currency})
    assert response.status_code == 422
    assert 'Choose SDG or USD.' in response.text
    assert db.session.scalar(select(Property.id)) is None


@pytest.mark.parametrize('initial,target', [('SDG', 'USD'), ('USD', 'SDG')])
def test_edit_prefills_and_changes_currency_without_conversion(client, form_data, initial, target):
    assert client.post('/admin/properties', data=form_data | {
        'currency': initial, 'price': '500',
    }).status_code == 303
    property = db.session.scalar(select(Property))
    edit_url = f'/properties/{property.id}/edit'
    page = client.get(edit_url + '?lang=en')
    assert f'<option value="{initial}" selected>' in page.text
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    photo_token = re.search(r'name="_photo_token" value="([^"]+)"', page.text).group(1)
    response = client.post(edit_url, data=form_data | {
        'csrf_token': csrf, '_photo_token': photo_token,
        'currency': target, 'price': '500',
    })
    assert response.status_code == 303
    db.session.refresh(property)
    assert property.currency == target and property.price == 500
    assert f'<option value="{target}" selected>' in client.get(edit_url + '?lang=en').text
    assert f'500 {target}' in client.get(f'/properties/{property.id}?lang=en').text


def test_edit_rejects_tampered_currency_and_preserves_listing(client, form_data):
    assert client.post('/admin/properties', data=form_data | {'currency': 'USD'}).status_code == 303
    property = db.session.scalar(select(Property))
    edit_url = f'/properties/{property.id}/edit'
    page = client.get(edit_url + '?lang=en')
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    photo_token = re.search(r'name="_photo_token" value="([^"]+)"', page.text).group(1)
    response = client.post(edit_url, data=form_data | {
        'csrf_token': csrf, '_photo_token': photo_token, 'currency': 'EUR',
    })
    assert response.status_code == 422
    db.session.refresh(property)
    assert property.currency == 'USD' and property.price == 125000


def test_usd_price_is_shown_on_all_property_surfaces(client, form_data):
    assert client.post('/admin/properties', data=form_data | {
        'currency': 'USD', 'price': '500',
    }).status_code == 303
    property = db.session.scalar(select(Property))
    user = db.session.scalar(select(User))
    db.session.add(SavedProperty(user_id=user.id, property_id=property.id))
    db.session.commit()
    for url in ('/', '/properties', f'/properties/{property.id}',
                '/my-properties', '/saved-properties'):
        for suffix in ('', '?lang=en'):
            page = client.get(url + suffix)
            assert page.status_code == 200
            assert '500 USD' in page.text
            assert '500 SDG' not in page.text


def test_existing_sdg_default_and_model_rejects_other_codes(client, form_data):
    assert client.post('/admin/properties', data=form_data).status_code == 303
    property = db.session.scalar(select(Property))
    assert property.currency == 'SDG'
    assert '125,000 SDG' in client.get('/properties?lang=en').text
    with pytest.raises(ValueError):
        property.currency = 'EUR'
    assert property.currency == 'SDG'
