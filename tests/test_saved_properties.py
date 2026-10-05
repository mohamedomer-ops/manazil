import re
from html import unescape
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app import db
from app.languages import translate
from app.models import Property, SavedProperty, User
from test_properties import migrated_connection, values
from test_auth import client, csrf, login, signup
from test_public_properties import add_property


def public_listing(values, **changes):
    return add_property(values, publication_status='published', **changes)


def sign_in(client):
    user = User(phone_number='+249912345678', is_verified=True, contact_name='Account Name',
                whatsapp='+249911111111', contact_role='owner')
    db.session.add(user)
    db.session.commit()
    with client.session_transaction() as auth_session:
        auth_session['user_id'] = user.id
    return user


def save(client, property, **changes):
    page = client.get(f'/properties/{property.id}?lang=en')
    return client.post(f'/properties/{property.id}/save', data={
        'csrf_token': csrf(page), '_language': 'en', **changes})


@pytest.mark.parametrize('language', ['ar', 'en'])
def test_logged_out_browsing_save_destination_and_private_list(client, values, language):
    property = public_listing(values)
    suffix = '?lang=en' if language == 'en' else ''
    destination = f'/properties/{property.id}' + suffix
    assert client.get('/properties').status_code == 200
    page = client.get(destination)
    assert page.status_code == 200
    href, label = re.search(r'<a class="property-save-link" href="([^"]+)">([^<]+)</a>', page.text).groups()
    assert label == translate('Save Property', language)
    url = unescape(href)
    assert urlsplit(url).path == '/auth'
    assert parse_qs(urlsplit(url).query)['next'] == [destination]
    entry = client.get(url, follow_redirects=False)
    assert entry.status_code == 302 and urlsplit(entry.location).path == '/login'
    assert parse_qs(urlsplit(entry.location).query)['next'] == [destination]
    assert 'class="signin-main"' in client.get(entry.location).text
    response = client.post(f'/properties/{property.id}/save', data={
        'csrf_token': csrf(client.get('/login')), '_language': language})
    assert response.status_code == 303
    assert parse_qs(urlsplit(response.location).query)['next'] == [destination]
    assert db.session.query(SavedProperty).count() == 0
    response = client.get('/saved-properties')
    assert response.status_code == 302 and 'next=/saved-properties' in response.location
    navigation = page.text.split('<nav', 1)[1].split('</nav>', 1)[0]
    assert '/saved-properties' not in navigation


@pytest.mark.parametrize('flow', ['login', 'signup'])
def test_auth_returns_to_property_without_automatically_saving(client, values, flow):
    property = public_listing(values)
    destination = f'/properties/{property.id}'
    if flow == 'login':
        db.session.add(User(phone_number='+249912345678', is_verified=True, contact_name='Original Name'))
        db.session.commit()
    page = client.get(destination)
    assert 'next=' + destination in unescape(page.text)
    response = (login if flow == 'login' else signup)(client, destination=destination)
    assert response.status_code == 303 and response.location == destination
    assert client.get(response.location).status_code == 200
    assert db.session.query(SavedProperty).count() == 0
    assert save(client, property).status_code == 303
    assert db.session.query(SavedProperty).count() == 1


@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
def test_save_saved_state_list_and_unsave(client, values, language, direction):
    user = sign_in(client)
    property = public_listing(values)
    page = client.get('/saved-properties?lang=' + language)
    assert translate('Saved Properties', language) in page.text
    assert translate("You haven't saved any properties yet.", language) in unescape(page.text)
    assert translate('Browse Properties', language) in page.text
    assert save(client, property).status_code == 303
    assert save(client, property, user_id='999').status_code == 303
    assert db.session.query(SavedProperty).count() == 1
    assert db.session.get(SavedProperty, (user.id, property.id))
    db.session.expire_all()
    assert property in user.saved_properties and user in property.saved_by
    page = client.get(f'/properties/{property.id}?lang=' + language)
    assert '<span class="property-saved-state" role="status">' + translate('Saved', language) in page.text
    assert translate('Remove from Saved', language) in page.text
    saved_page = client.get('/saved-properties?lang=' + language)
    assert f'<html lang="{language}" dir="{direction}">' in saved_page.text
    assert 'no-store' in saved_page.headers['Cache-Control']
    assert (property.title_en if language == 'en' else property.title_ar) in saved_page.text
    assert '125,000.5 SDG' in saved_page.text
    assert f'/properties/{property.id}/unsave' in saved_page.text
    response = client.post(f'/properties/{property.id}/unsave', data={
        'csrf_token': csrf(page), '_language': language, 'return_to': 'detail'})
    assert response.status_code == 303
    assert response.location == f'/properties/{property.id}' + ('?lang=en' if language == 'en' else '')
    assert db.session.query(SavedProperty).count() == 0
    assert client.post(f'/properties/{property.id}/unsave', data={'csrf_token': csrf(page)}).status_code == 303


def test_saved_list_and_relationship_changes_are_account_scoped(client, values):
    first = sign_in(client)
    mine = public_listing(values, title_ar='My saved home', title_en='My saved home')
    theirs = public_listing(values, title_ar='Other saved home', title_en='Other saved home')
    save(client, mine)
    other = User(phone_number='+249911111111', is_verified=True)
    db.session.add(other)
    db.session.flush()
    db.session.add(SavedProperty(user_id=other.id, property_id=theirs.id))
    db.session.commit()
    page = client.get('/saved-properties?lang=en&user_id=' + str(other.id))
    assert 'My saved home' in page.text and 'Other saved home' not in page.text
    assert client.post(f'/properties/{theirs.id}/unsave', data={
        'csrf_token': csrf(page), 'user_id': other.id}).status_code == 303
    assert db.session.get(SavedProperty, (other.id, theirs.id))
    save(client, theirs, user_id=other.id)
    assert db.session.get(SavedProperty, (first.id, theirs.id))
    assert db.session.get(SavedProperty, (other.id, theirs.id))
    with client.session_transaction() as auth_session:
        auth_session['user_id'] = other.id
    page = client.get('/saved-properties?lang=en')
    assert 'Other saved home' in page.text and 'My saved home' not in page.text


@pytest.mark.parametrize('publication,availability', [('published', 'rented'), ('draft', 'available')])
def test_unavailable_saved_properties_retain_relationship_without_private_data(client, values, publication, availability):
    user = sign_in(client)
    property = public_listing(values, title_ar='Hidden private title', title_en='Hidden private title',
                              contact_name='Private owner name')
    save(client, property)
    property.publication_status = publication
    property.availability_status = availability
    db.session.commit()
    for language in ('ar', 'en'):
        page = client.get('/saved-properties?lang=' + language)
        content = page.text.split('<main', 1)[1].split('</main>', 1)[0]
        assert translate('No longer available', language) in content
        assert 'Hidden private title' not in content and 'Private owner name' not in content
        assert '125,000' not in content and 'Khartoum' not in content
        assert property.phone not in content
        assert f'href="/properties/{property.id}' not in content
        assert '/properties/photos/' not in content
        assert translate('Remove from Saved', language) in content
    assert db.session.get(SavedProperty, (user.id, property.id))
    assert client.get(f'/properties/{property.id}').status_code == 404
    assert client.post(f'/properties/{property.id}/save', data={'csrf_token': csrf(page)}).status_code == 404
    property.publication_status = 'published'
    property.availability_status = 'available'
    db.session.commit()
    assert 'Hidden private title' in client.get('/saved-properties?lang=en').text
    property.availability_status = 'rented'
    db.session.commit()
    assert client.post(f'/properties/{property.id}/unsave', data={'csrf_token': csrf(page)}).status_code == 303
    assert db.session.get(SavedProperty, (user.id, property.id)) is None


@pytest.mark.parametrize('action', ['save', 'unsave'])
def test_saved_operations_require_post_and_csrf(client, values, action):
    user = sign_in(client)
    property = public_listing(values)
    route = f'/properties/{property.id}/{action}'
    assert client.get(route).status_code == 405
    assert client.post(route).status_code == 400
    assert client.post(route, data={'csrf_token': 'invalid'}).status_code == 400
    assert db.session.query(SavedProperty).count() == 0
    page = client.get(f'/properties/{property.id}')
    client.post('/logout', data={'csrf_token': csrf(page)})
    response = client.post(route, data={'csrf_token': csrf(page)})
    assert response.status_code in (302, 303) and '/auth?' in response.location
    assert db.session.query(SavedProperty).count() == 0


def test_saved_database_unique_pair_and_cascade(client, values):
    user = sign_in(client)
    property = public_listing(values)
    save(client, property)
    assert inspect(db.session.get_bind()).get_pk_constraint('saved_properties')['constrained_columns'] == ['user_id', 'property_id']
    with pytest.raises(IntegrityError):
        with db.session.begin_nested():
            db.session.execute(SavedProperty.__table__.insert().values(user_id=user.id, property_id=property.id))
    db.session.execute(Property.__table__.delete().where(Property.id == property.id))
    db.session.commit()
    assert db.session.query(SavedProperty).count() == 0


def test_saved_survives_logout_and_login(client, values):
    user = sign_in(client)
    property = public_listing(values)
    save(client, property)
    page = client.get('/saved-properties')
    client.post('/logout', data={'csrf_token': csrf(page)})
    assert client.get('/saved-properties').status_code == 302
    assert login(client, destination='/saved-properties').location == '/saved-properties'
    assert db.session.get(SavedProperty, (user.id, property.id))
    assert property.title_ar in client.get('/saved-properties').text
