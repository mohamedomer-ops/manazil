import re
from datetime import date

import pytest
from flask import current_app
from sqlalchemy import select

from app import db
from app.models import Property, PropertyPhoto, User
from app.photo_storage import LocalPhotoStorage
from test_properties import migrated_connection, values
from test_property_creation import client, form_data
from test_photo_review import image_file


def token(page):
    return re.search(r'name="csrf_token" value="([^"]+)"', page.get_data(as_text=True)).group(1)


def listing(values, **changes):
    owner = db.session.scalar(select(User))
    property = Property(**(values | {'owner_id': owner.id, 'phone': '+249912345678',
        'neighborhood_ar': 'Neighborhood', 'publication_status': 'published'} | changes))
    db.session.add(property)
    db.session.commit()
    return property


@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
def test_my_properties_empty_and_languages(client, language, direction):
    page = client.get('/my-properties?lang=' + language)
    assert page.status_code == 200
    assert f'<html lang="{language}" dir="{direction}">' in page.text
    assert '/properties/new' in page.text
    assert 'no-store' in page.headers['Cache-Control']


def test_my_properties_only_owner_and_all_statuses(client, values):
    own = listing(values, title_ar='Owner listing', title_en='Owner listing')
    rented = listing(values, title_ar='Rented listing', title_en='Rented listing', availability_status='rented')
    draft = listing(values, title_ar='Draft listing', title_en='Draft listing', publication_status='draft')
    other_user = User(phone_number='+249911111111', is_verified=True)
    db.session.add(other_user)
    db.session.commit()
    listing(values, owner_id=other_user.id, title_ar='Other private listing', title_en='Other private listing')
    listing(values, owner_id=None, title_ar='Unowned listing', title_en='Unowned listing')
    page = client.get('/my-properties?lang=en').text
    assert 'Owner listing' in page and 'Rented listing' in page and 'Draft listing' in page
    assert 'Other private listing' not in page and 'Unowned listing' not in page
    assert 'Published' in page and 'Rented' in page and 'Draft' in page
    assert 'Khartoum' in page and 'Neighborhood' in page and '125,000.5' in page
    assert 'Apartment' in page and 'No photo available' in page
    assert f'href="/properties/{own.id}?lang=en"' in page
    assert f'href="/properties/{rented.id}?lang=en"' not in page
    assert f'href="/properties/{draft.id}?lang=en"' not in page
    for property in (own, rented, draft):
        assert f'/properties/{property.id}/edit?lang=en' in page


@pytest.mark.parametrize('method', ['get', 'post'])
def test_management_requires_login(client, values, method):
    property = listing(values)
    csrf = token(client.get('/account'))
    client.post('/logout', data={'csrf_token': csrf})
    if method == 'get':
        response = client.get('/my-properties')
        assert response.status_code == 302 and 'next=/my-properties' in response.location
    response = getattr(client, method)(f'/properties/{property.id}/edit', **({'data': {'csrf_token': csrf}} if method == 'post' else {}))
    assert response.status_code == 302 and '/auth?' in response.location


def test_other_owner_and_missing_cannot_edit(client, values):
    other = User(phone_number='+249911111111', is_verified=True)
    db.session.add(other)
    db.session.commit()
    property = listing(values, owner_id=other.id)
    csrf = token(client.get('/account'))
    for property_id in (property.id, property.id + 1000):
        assert client.get(f'/properties/{property_id}/edit').status_code == 404
        assert client.post(f'/properties/{property_id}/edit', data={'csrf_token': csrf, 'title_ar': 'Intrusion'}).status_code == 404
    db.session.refresh(property)
    assert property.title_ar == values['title_ar']


def test_edit_prefills_and_updates_only_existing_property(client, values, form_data):
    property = listing(values, availability_status='rented', available_from_date=date(2030, 1, 1))
    other_property = listing(values, whatsapp='+249913333333', phone='+249913333333')
    user = db.session.get(User, property.owner_id)
    profile = (user.contact_name, user.phone_number, user.whatsapp, user.contact_role)
    page = client.get(f'/properties/{property.id}/edit?lang=en')
    assert page.status_code == 200
    assert f'action="/properties/{property.id}/edit"' in page.text
    assert 'Edit Property' in page.text and 'Save Changes' in page.text
    assert 'name="phone"' not in page.text and page.text.count('name="whatsapp"') == 1
    assert 'value="125000.50"' in page.text and 'Neighborhood' in page.text
    data = form_data | {'csrf_token': token(page), 'title_ar': 'Updated listing', 'price': '500',
        'contact_name': 'Property contact', 'owner_id': '999', 'publication_status': 'draft',
        'availability_status': 'available', 'phone': '0911111111', 'whatsapp': '0912222222', 'agent': 'yes'}
    response = client.post(f'/properties/{property.id}/edit', data=data)
    assert response.status_code == 303 and response.location.startswith('/my-properties?')
    db.session.refresh(property)
    db.session.refresh(user)
    assert db.session.query(Property).count() == 2
    assert property.title_ar == 'Updated listing' and property.price == 500
    assert property.owner_id == user.id and property.publication_status == 'published'
    assert property.availability_status == 'rented' and property.available_from_date == date(2030, 1, 1)
    assert property.title_en == values['title_en'] and property.city_en == values['city_en']
    assert property.contact_name == 'Property contact' and property.contact_role == 'broker'
    assert property.phone == '+249912222222' and property.whatsapp == '+249912222222'
    assert (user.contact_name, user.phone_number, user.whatsapp, user.contact_role) == profile
    db.session.refresh(other_property)
    assert other_property.phone == other_property.whatsapp == '+249913333333'


def test_edit_validation_csrf_and_language_switch(client, values, form_data):
    property = listing(values, publication_status='draft')
    route = f'/properties/{property.id}/edit'
    assert client.post(route, data=form_data | {'csrf_token': ''}).status_code == 400
    response = client.post(route, data=form_data | {'price': '-1', 'title_ar': 'Unsaved'})
    assert response.status_code == 422 and 'Unsaved' in response.text
    db.session.refresh(property)
    assert property.price == values['monthly_rent'] and property.publication_status == 'draft'
    response = client.post(route, data=form_data | {'_action': 'switch_ar', 'title_ar': 'Keep this'})
    assert response.status_code == 200 and '<html lang="ar" dir="rtl">' in response.text
    assert 'Keep this' in response.text and f'action="{route}"' in response.text
    response = client.post(route, data=form_data)
    assert response.status_code == 303
    db.session.refresh(property)
    assert property.publication_status == 'draft'


def test_primary_photo_and_private_access_and_edit_preserves_photos(client, form_data, tmp_path):
    current_app.config['PHOTO_STORAGE_ROOT'] = str(tmp_path)
    assert client.post('/admin/properties', data=form_data | {'_action': 'upload', 'photos': image_file()}).status_code == 200
    assert client.post('/admin/properties', data=form_data).status_code == 303
    property = db.session.scalar(select(Property))
    photo = db.session.scalar(select(PropertyPhoto))
    identity, key = photo.id, photo.storage_key
    property.availability_status = 'rented'
    db.session.commit()
    page = client.get('/my-properties').text
    assert f'/my-properties/photos/{identity}' in page
    response = client.get(f'/my-properties/photos/{identity}')
    assert response.status_code == 200 and response.mimetype == 'image/jpeg'
    assert 'no-store' in response.headers['Cache-Control']
    assert client.get(f'/properties/photos/{identity}').status_code == 404
    edit = client.get(f'/properties/{property.id}/edit?lang=en')
    assert f'/my-properties/photos/{identity}' in edit.text
    edit_token = re.search(r'name="_photo_token" value="([^"]+)"', edit.text).group(1)
    assert client.post(f'/properties/{property.id}/edit', data=form_data | {
        'csrf_token': token(edit), '_photo_token': edit_token}).status_code == 303
    db.session.refresh(photo)
    assert photo.id == identity and photo.storage_key == key and LocalPhotoStorage().path(key).is_file()
    other = User(phone_number='+249911111111', is_verified=True)
    db.session.add(other)
    db.session.commit()
    with client.session_transaction() as auth_session:
        auth_session['user_id'] = other.id
    assert client.get(f'/my-properties/photos/{identity}').status_code == 404
    assert client.get(f'/admin/property-photos/{identity}').status_code == 404
    assert client.get(f'/properties/{property.id}/edit').status_code == 404


@pytest.mark.parametrize('language', ['ar', 'en'])
def test_owner_availability_round_trip_and_public_visibility(client, values, language):
    from app.languages import translate
    property = listing(values, title_ar='Availability test property', title_en='Availability test property')
    page = client.get('/my-properties?lang=' + language)
    assert translate('Mark as Rented', language) in page.text
    assert f'action="/properties/{property.id}/mark-rented"' in page.text
    assert 'method="post"' in page.text
    assert 'Availability test property' in client.get('/properties').text
    assert client.get(f'/properties/{property.id}').status_code == 200
    response = client.post(f'/properties/{property.id}/mark-rented', data={
        'csrf_token': token(page), '_language': language, 'owner_id': '999', 'publication_status': 'draft'})
    assert response.status_code == 303
    assert response.location == '/my-properties' + ('?lang=en' if language == 'en' else '')
    db.session.refresh(property)
    assert property.availability_status == 'rented' and property.publication_status == 'published'
    assert property.owner_id == db.session.scalar(select(User)).id
    page = client.get(response.location)
    assert 'Availability test property' in page.text and translate('Rented', language) in page.text
    assert translate('Make Available', language) in page.text
    assert translate('Mark as Rented', language) not in page.text
    assert f'href="/properties/{property.id}' + ('?lang=en' if language == 'en' else '') + '"' not in page.text
    assert 'Availability test property' not in client.get('/properties').text
    assert client.get(f'/properties/{property.id}').status_code == 404
    response = client.post(f'/properties/{property.id}/make-available', data={
        'csrf_token': token(page), '_language': language})
    assert response.status_code == 303
    db.session.refresh(property)
    assert property.availability_status == 'available'
    assert 'Availability test property' in client.get('/properties').text
    assert client.get(f'/properties/{property.id}').status_code == 200
    assert translate('Mark as Rented', language) in client.get(response.location).text


@pytest.mark.parametrize('action,status', [('mark-rented', 'available'), ('make-available', 'rented')])
def test_availability_post_only_csrf_and_authentication(client, values, action, status):
    property = listing(values, availability_status=status)
    route = f'/properties/{property.id}/{action}'
    assert client.get(route).status_code == 405
    assert client.post(route).status_code == 400
    assert client.post(route, data={'csrf_token': 'invalid'}).status_code == 400
    db.session.refresh(property)
    assert property.availability_status == status
    csrf = token(client.get('/my-properties'))
    client.post('/logout', data={'csrf_token': csrf})
    response = client.post(route, data={'csrf_token': csrf})
    assert response.status_code == 302 and '/auth?' in response.location
    db.session.refresh(property)
    assert property.availability_status == status


@pytest.mark.parametrize('action,status', [('mark-rented', 'available'), ('make-available', 'rented')])
def test_availability_other_owner_and_missing_are_404(client, values, action, status):
    other = User(phone_number='+249911111111', is_verified=True)
    db.session.add(other)
    db.session.commit()
    property = listing(values, owner_id=other.id, availability_status=status)
    csrf = token(client.get('/my-properties?lang=en'))
    for property_id in (property.id, property.id + 1000):
        response = client.post(f'/properties/{property_id}/{action}', data={
            'csrf_token': csrf, 'owner_id': db.session.scalar(select(User).order_by(User.id)).id})
        assert response.status_code == 404
    db.session.refresh(property)
    assert property.availability_status == status and property.owner_id == other.id


def test_make_available_does_not_publish_draft(client, values):
    property = listing(values, publication_status='draft', availability_status='rented',
                       title_ar='Private draft', title_en='Private draft')
    response = client.post(f'/properties/{property.id}/make-available', data={
        'csrf_token': token(client.get('/my-properties'))})
    assert response.status_code == 303
    db.session.refresh(property)
    assert property.availability_status == 'available' and property.publication_status == 'draft'
    assert 'Private draft' in client.get('/my-properties?lang=en').text
    assert 'Private draft' not in client.get('/properties?lang=en').text
    assert client.get(f'/properties/{property.id}').status_code == 404
