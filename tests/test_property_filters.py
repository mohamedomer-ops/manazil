import re
from html import unescape
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import event

from app import db
from app.languages import PROPERTY_TYPE_NAMES, translate
from app.models import PropertyPhoto, SavedProperty
from app.property_filters import STATE_OPTIONS
from test_auth import client, csrf
from test_public_properties import add_property
from test_saved_properties import sign_in
from test_properties import migrated_connection, values


def listing(values, title, **changes):
    return add_property(values, title_en=title, title_ar=title,
                        publication_status='published', **changes)


def result_titles(page):
    return re.findall(r'<div class="market-result-info">\s*<h2>(.*?)</h2>', page.text)


def test_default_results_and_visibility(client, values):
    listing(values, 'Public rent')
    listing(values, 'Public sale', transaction_type='sale', rent_period=None)
    add_property(values, title_en='Draft secret', title_ar='Draft secret', publication_status='draft')
    listing(values, 'Rented secret', availability_status='rented')
    page = client.get('/properties?lang=en')
    assert page.status_code == 200
    assert result_titles(page) == ['Public sale', 'Public rent']
    assert 'Draft secret' not in page.text and 'Rented secret' not in page.text
    assert 'class="market-filters" method="get"' in page.text
    assert 'name="transaction"' in page.text
    assert 'name="state"' in page.text
    assert 'name="bedrooms"' in page.text
    assert 'name="seller"' in page.text
    assert 'name="property_type"' in page.text
    assert 'class="market-result-link"' in page.text
    assert 'class="properties-grid"' not in page.text
    assert 'href="/properties/1?lang=en"' in page.text


@pytest.mark.parametrize('transaction,expected', [('rent', 'Rent home'), ('sale', 'Sale home')])
def test_transaction_filter(client, values, transaction, expected):
    listing(values, 'Rent home')
    listing(values, 'Sale home', transaction_type='sale', rent_period=None)
    page = client.get('/properties', query_string={'transaction': transaction, 'lang': 'en'})
    assert result_titles(page) == [expected]
    assert f'<option value="{transaction}" selected>' in page.text


@pytest.mark.parametrize('slug,english,arabic', STATE_OPTIONS)
def test_each_approved_state_filter(client, values, slug, english, arabic):
    listing(values, 'Matching state', state_en=english, state_ar=arabic)
    other = STATE_OPTIONS[0] if slug != STATE_OPTIONS[0][0] else STATE_OPTIONS[1]
    listing(values, 'Other state', state_en=other[1], state_ar=other[2])
    page = client.get('/properties', query_string={'state': slug, 'lang': 'en'})
    assert result_titles(page) == ['Matching state']
    assert f'<option value="{slug}" selected>{english}</option>' in page.text
    assert page.text.count('<option value="') >= 10
    assert 'name="city"' not in page.text


@pytest.mark.parametrize('bedrooms,expected', [('1', ['Five rooms', 'Two rooms', 'One room']),
                                                ('2', ['Five rooms', 'Two rooms']),
                                                ('5', ['Five rooms'])])
def test_bedroom_minimum(client, values, bedrooms, expected):
    listing(values, 'One room', bedrooms=1)
    listing(values, 'Two rooms', bedrooms=2)
    listing(values, 'Five rooms', bedrooms=5)
    assert result_titles(client.get('/properties', query_string={'bedrooms': bedrooms})) == expected


@pytest.mark.parametrize('seller,expected', [('owner', 'Owner home'), ('broker', 'Broker home')])
def test_seller_filter(client, values, seller, expected):
    listing(values, 'Owner home', contact_role='owner')
    listing(values, 'Broker home', contact_role='broker')
    page = client.get('/properties', query_string={'seller': seller})
    assert result_titles(page) == [expected]
    assert f'<option value="{seller}" selected>' in page.text


@pytest.mark.parametrize('property_type', PROPERTY_TYPE_NAMES)
def test_property_type_filter(client, values, property_type):
    listing(values, 'Matching type', property_type=property_type)
    other = 'house' if property_type != 'house' else 'apartment'
    listing(values, 'Other type', property_type=other)
    page = client.get('/properties', query_string={'property_type': property_type, 'lang': 'en'})
    assert result_titles(page) == ['Matching type']
    assert f'<option value="{property_type}" selected>' in page.text


@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
def test_combined_filters_language_switch_reset_and_empty(client, values, language, direction):
    target = dict(transaction_type='sale', rent_period=None, state_en='Khartoum',
                  state_ar='الخرطوم', bedrooms=3, contact_role='owner', property_type='villa')
    listing(values, 'Exact match', **target)
    for title, change in [('Rent decoy', {'transaction_type': 'rent', 'rent_period': 'monthly'}),
                          ('State decoy', {'state_en': 'Sennar', 'state_ar': 'سنار'}),
                          ('Bedroom decoy', {'bedrooms': 2}),
                          ('Seller decoy', {'contact_role': 'broker'}),
                          ('Type decoy', {'property_type': 'house'}),
                          ('Rented decoy', {'availability_status': 'rented'}),
                          ('Draft decoy', {'publication_status': 'draft'})]:
        listing(values, title, **(target | change)) if title != 'Draft decoy' else add_property(
            values, title_en=title, title_ar=title, **(target | change))
    filters = {'transaction': 'sale', 'state': 'khartoum', 'bedrooms': '3',
               'seller': 'owner', 'property_type': 'villa'}
    page = client.get('/properties', query_string=filters | {'lang': language})
    assert page.status_code == 200
    assert f'<html lang="{language}" dir="{direction}">' in page.text
    assert result_titles(page) == ['Exact match']
    for key, value in filters.items():
        assert f'name="{key}"' in page.text
        assert f'<option value="{value}" selected>' in page.text
    assert translate('Filters', language) in page.text
    assert translate('Seller Type', language) in page.text
    assert translate('Clear Filters', language) in page.text
    reset_url = '/properties?lang=en' if language == 'en' else '/properties'
    assert f'href="{reset_url}"' in page.text
    language_link = re.search(r'<a href="([^"]+)" lang="en"', page.text)
    assert parse_qs(urlsplit(unescape(language_link.group(1))).query)['transaction'] == ['sale']
    empty = client.get('/properties', query_string=filters | {'bedrooms': '5', 'lang': language})
    assert translate('No properties match your filters.', language) in empty.text
    assert result_titles(empty) == []
    assert len(result_titles(client.get('/properties'))) == 6


def test_invalid_filter_values_are_ignored_safely(client, values):
    listing(values, 'Safe listing')
    page = client.get('/properties', query_string={
        'transaction': "rent' OR 1=1 --", 'state': 'not-a-state', 'bedrooms': '-2',
        'seller': 'agent', 'property_type': '<script>', 'publication_status': 'draft'})
    assert page.status_code == 200
    assert result_titles(page) == ['Safe listing']
    assert 'value="<script>"' not in page.text
    assert 'selected' not in page.text.split('class="market-filters"', 1)[1].split('</form>', 1)[0]


def test_logged_out_save_uses_detail_destination_and_card_link_is_separate(client, values):
    property = listing(values, 'Save candidate')
    page = client.get('/properties?lang=en')
    article = page.text.split('class="market-result"', 1)[1].split('</article>', 1)[0]
    assert f'class="market-result-link" href="/properties/{property.id}?lang=en"' in article
    assert '<a href="/auth?next=' in article
    save_url = unescape(re.search(r'<a href="([^"]+)"><span aria-hidden="true">♡', article).group(1))
    assert parse_qs(urlsplit(save_url).query)['next'] == [f'/properties/{property.id}?lang=en']
    assert client.get(save_url).status_code == 200
    assert db.session.query(SavedProperty).count() == 0


def test_listing_save_unsave_post_csrf_and_filter_return(client, values):
    user = sign_in(client)
    property = listing(values, 'Save candidate')
    other = listing(values, 'Different transaction', transaction_type='sale', rent_period=None)
    page = client.get('/properties?transaction=rent&lang=en')
    assert result_titles(page) == ['Save candidate']
    assert f'action="/properties/{property.id}/save"' in page.text
    assert client.post(f'/properties/{property.id}/save', data={'return_to': 'listing'}).status_code == 400
    response = client.post(f'/properties/{property.id}/save', data={
        'csrf_token': csrf(page), '_language': 'en', 'return_to': 'listing', 'transaction': 'rent'})
    assert response.status_code == 303 and response.location == '/properties?transaction=rent&lang=en'
    assert db.session.get(SavedProperty, (user.id, property.id))
    page = client.get(response.location)
    assert f'action="/properties/{property.id}/unsave"' in page.text
    assert 'aria-label="Remove from Saved"' in page.text
    response = client.post(f'/properties/{property.id}/unsave', data={
        'csrf_token': csrf(page), '_language': 'en', 'return_to': 'listing', 'transaction': 'rent'})
    assert response.status_code == 303 and response.location == '/properties?transaction=rent&lang=en'
    assert db.session.get(SavedProperty, (user.id, property.id)) is None
    assert f'action="/properties/{property.id}/save"' in client.get(response.location).text
    assert other.title_en not in client.get(response.location).text


def test_photo_eager_loading_and_secure_photo_route(client, values):
    for index in range(4):
        property = listing(values, f'Photo home {index}')
        db.session.add(PropertyPhoto(property_id=property.id, category='exterior',
            storage_key=f'properties/{property.id}/{index:032x}.jpg',
            original_filename='photo.jpg', content_type='image/jpeg', file_size=1,
            display_order=0, is_primary=True))
    db.session.commit()
    statements = []
    def record(connection, cursor, statement, parameters, context, executemany):
        if 'property_photos' in statement.lower() and statement.lstrip().lower().startswith('select'):
            statements.append(statement)
    event.listen(db.engine, 'before_cursor_execute', record)
    try:
        page = client.get('/properties?lang=en')
    finally:
        event.remove(db.engine, 'before_cursor_execute', record)
    assert len(statements) == 1
    assert page.text.count('class="property-card-image"') == 4
    photo = db.session.query(PropertyPhoto).first()
    photo.property.availability_status = 'rented'
    db.session.commit()
    assert client.get(f'/properties/photos/{photo.id}').status_code == 404
