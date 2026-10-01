"""Owner photo management uses the posting validator and existing photo records."""
import io
import re

import pytest
from sqlalchemy import select

from app import db
from app.models import Property, PropertyPhoto, User
from app.photo_storage import LocalPhotoStorage
from test_photo_review import photo_client, image_file
from test_property_creation import client, form_data
from test_properties import migrated_connection, values


def tokens(response):
    page = response.get_data(as_text=True)
    return {
        'csrf_token': re.search(r'name="csrf_token" value="([^"]+)"', page).group(1),
        '_photo_token': re.search(r'name="_photo_token" value="([^"]+)"', page).group(1),
    }


def create_with_photos(client, form_data, count):
    if count:
        response = client.post('/admin/properties', data=form_data | {
            '_action': 'upload', 'photos': [image_file(f'{index}.jpg') for index in range(count)]})
        assert response.status_code == 200
    assert client.post('/admin/properties', data=form_data).status_code == 303
    return db.session.scalar(select(Property))


def edit_data(client, property, form_data, language='en'):
    page = client.get(f'/properties/{property.id}/edit?lang={language}')
    assert page.status_code == 200
    return page, form_data | tokens(page) | {'_language': language}


@pytest.mark.parametrize('language,primary,add', [
    ('en', 'Primary photo', 'Add photos'),
    ('ar', 'الصورة الرئيسية', 'إضافة الصور'),
])
def test_edit_photo_ui_and_language(photo_client, form_data, language, primary, add):
    property = create_with_photos(photo_client, form_data, 2)
    page, _ = edit_data(photo_client, property, form_data, language)
    assert ('>2</span> of 20 photos' if language == 'en' else '>2</span> من 20 صورة') in page.text
    assert page.text.count('/my-properties/photos/') == 2
    assert primary in page.text and add in page.text
    assert f'value="delete_existing_{property.photos[0].id}"' in page.text
    assert f'value="primary_existing_{property.photos[1].id}"' in page.text
    assert 'id="selected-photo-previews"' in page.text


def test_upload_then_save_updates_public_carousel_and_details(photo_client, form_data):
    property = create_with_photos(photo_client, form_data, 1)
    owner_id, publication, availability = property.owner_id, property.publication_status, property.availability_status
    page, data = edit_data(photo_client, property, form_data)
    staged = photo_client.post(f'/properties/{property.id}/edit', data=data | {
        '_action': 'upload', 'photos': image_file('added.jpg')})
    assert staged.status_code == 200 and '>2</span> of 20 photos' in staged.text
    assert 'New photos' in staged.text
    assert photo_client.post(f'/properties/{property.id}/edit', data=data | tokens(staged)).status_code == 303
    db.session.expire_all()
    property = db.session.get(Property, property.id)
    assert len(property.photos) == 2
    assert [photo.display_order for photo in property.photos] == [0, 1]
    assert sum(photo.is_primary for photo in property.photos) == 1
    assert (property.owner_id, property.publication_status, property.availability_status) == (
        owner_id, publication, availability)
    assert '<span class="market-photo-current">1</span> / <span>2</span>' in photo_client.get('/properties?lang=en').text
    details = photo_client.get(f'/properties/{property.id}?lang=en').text
    assert all(f'/properties/photos/{photo.id}' in details for photo in property.photos)
    assert all(LocalPhotoStorage().path(photo.storage_key).is_file() for photo in property.photos)


def test_direct_save_with_selected_upload_and_invalid_content(photo_client, form_data):
    property = create_with_photos(photo_client, form_data, 0)
    _, data = edit_data(photo_client, property, form_data)
    route = f'/properties/{property.id}/edit'
    invalid = photo_client.post(route, data=data | {
        '_action': 'upload', 'photos': (io.BytesIO(b'not an image'), 'bad.jpg', 'image/jpeg')})
    assert invalid.status_code == 422 and 'image content is invalid' in invalid.text
    assert not property.photos
    saved = photo_client.post(route, data=data | {'photos': image_file('first.jpg')})
    assert saved.status_code == 303
    db.session.expire_all()
    property = db.session.get(Property, property.id)
    assert len(property.photos) == 1 and property.photos[0].is_primary


def test_total_limit_counts_existing_and_staged(photo_client, form_data):
    property = create_with_photos(photo_client, form_data, 19)
    _, data = edit_data(photo_client, property, form_data)
    route = f'/properties/{property.id}/edit'
    response = photo_client.post(route, data=data | {
        '_action': 'upload', 'photos': [image_file('extra1.jpg'), image_file('extra2.jpg')]})
    assert response.status_code == 422 and 'at most 20 photos' in response.text
    assert len(property.photos) == 19
    staged = photo_client.post(route, data=data | {'_action': 'upload', 'photos': image_file('last.jpg')})
    assert staged.status_code == 200 and '>20</span> of 20 photos' in staged.text
    assert photo_client.post(route, data=data | tokens(staged) | {
        '_action': 'upload', 'photos': image_file('too-many.jpg')}).status_code == 422
    assert photo_client.post(route, data=data | tokens(staged)).status_code == 303
    db.session.expire_all()
    assert len(db.session.get(Property, property.id).photos) == 20


def test_delete_primary_reassigns_and_removes_file(photo_client, form_data):
    property = create_with_photos(photo_client, form_data, 2)
    primary, other = property.photos
    key, photo_id = primary.storage_key, primary.id
    _, data = edit_data(photo_client, property, form_data)
    route = f'/properties/{property.id}/edit'
    response = photo_client.post(route, data=data | {'_action': f'delete_existing_{photo_id}'})
    assert response.status_code == 200
    db.session.expire_all()
    property = db.session.get(Property, property.id)
    assert [photo.id for photo in property.photos] == [other.id]
    assert property.photos[0].is_primary and property.photos[0].display_order == 0
    assert not LocalPhotoStorage().path(key).exists()
    assert photo_client.get(f'/properties/photos/{photo_id}').status_code == 404
    assert f'/properties/photos/{photo_id}' not in photo_client.get('/properties').text
    assert f'/properties/photos/{other.id}' in photo_client.get('/properties').text
    assert f'/properties/photos/{photo_id}' not in photo_client.get(f'/properties/{property.id}').text
    assert photo_client.post(route, data=data | {'_action': f'delete_existing_{other.id}'}).status_code == 200
    db.session.expire_all()
    assert db.session.get(Property, property.id).photos == []
    assert 'No photo available' in photo_client.get('/properties?lang=en').text
    assert 'No photo available' in photo_client.get(f'/properties/{property.id}?lang=en').text


def test_photo_change_keeps_rented_property_private(photo_client, form_data):
    property = create_with_photos(photo_client, form_data, 2)
    property.availability_status = 'rented'
    db.session.commit()
    owner_id, remaining_id = property.owner_id, property.photos[1].id
    _, data = edit_data(photo_client, property, form_data)
    assert photo_client.post(f'/properties/{property.id}/edit', data=data | {
        '_action': f'delete_existing_{remaining_id}'}).status_code == 200
    db.session.expire_all()
    property = db.session.get(Property, property.id)
    assert property.owner_id == owner_id
    assert property.publication_status == 'published' and property.availability_status == 'rented'
    assert len(property.photos) == 1
    assert photo_client.get(f'/properties/{property.id}').status_code == 404
    assert photo_client.get(f'/properties/photos/{property.photos[0].id}').status_code == 404


def test_set_primary_and_reorder_existing_photos(photo_client, form_data):
    property = create_with_photos(photo_client, form_data, 3)
    first, second, third = property.photos
    _, data = edit_data(photo_client, property, form_data)
    route = f'/properties/{property.id}/edit'
    assert photo_client.post(route, data=data | {'_action': f'up_existing_{third.id}'}).status_code == 200
    db.session.expire_all()
    assert [photo.id for photo in db.session.get(Property, property.id).photos] == [first.id, third.id, second.id]
    assert photo_client.post(route, data=data | {'_action': f'primary_existing_{third.id}'}).status_code == 200
    db.session.expire_all()
    property = db.session.get(Property, property.id)
    assert [photo.id for photo in property.photos if photo.is_primary] == [third.id]
    assert f'src="/properties/photos/{third.id}"' in photo_client.get('/properties?lang=en').text
    assert f'src="/properties/photos/{third.id}"' in photo_client.get(f'/properties/{property.id}?lang=en').text


def test_new_photo_can_become_primary_and_staged_order_is_saved(photo_client, form_data):
    property = create_with_photos(photo_client, form_data, 1)
    old_primary = property.photos[0].id
    _, data = edit_data(photo_client, property, form_data)
    route = f'/properties/{property.id}/edit'
    staged = photo_client.post(route, data=data | {
        '_action': 'upload', 'photos': [image_file('new-a.jpg'), image_file('new-b.jpg')]})
    assert staged.status_code == 200
    ids = re.findall(r'value="delete_([0-9a-f]{32})"', staged.text)
    assert len(ids) == 2
    moved = photo_client.post(route, data=data | tokens(staged) | {'_action': f'up_{ids[1]}'})
    assert moved.status_code == 200
    selected = photo_client.post(route, data=data | tokens(moved) | {'_action': f'primary_{ids[1]}'})
    assert selected.status_code == 200
    assert photo_client.post(route, data=data | tokens(selected)).status_code == 303
    db.session.expire_all()
    property = db.session.get(Property, property.id)
    assert [photo.original_filename for photo in property.photos] == ['0.jpg', 'new-b.jpg', 'new-a.jpg']
    assert [photo.id for photo in property.photos if photo.is_primary] == [property.photos[1].id]
    assert property.photos[0].id == old_primary
    assert f'src="/properties/photos/{property.photos[1].id}"' in photo_client.get('/properties?lang=en').text


def test_photo_actions_are_owner_only_post_and_csrf_protected(photo_client, form_data, values):
    property = create_with_photos(photo_client, form_data, 1)
    photo_id = property.photos[0].id
    route = f'/properties/{property.id}/edit'
    _, data = edit_data(photo_client, property, form_data)
    assert photo_client.get(route + f'?_action=delete_existing_{photo_id}').status_code == 200
    assert db.session.get(PropertyPhoto, photo_id) is not None
    assert photo_client.post(route, data={'_action': f'delete_existing_{photo_id}'}).status_code == 400
    assert photo_client.post(route, data=data | {'_action': 'delete_existing_999999'}).status_code == 404
    second = Property(**(values | {'owner_id': property.owner_id, 'publication_status': 'published'}))
    db.session.add(second)
    db.session.commit()
    assert photo_client.post(f'/properties/{second.id}/edit', data=data | {
        '_action': f'delete_existing_{photo_id}'}).status_code == 404
    other = User(phone_number='+249911111111', is_verified=True)
    db.session.add(other)
    db.session.commit()
    with photo_client.session_transaction() as session:
        session['user_id'] = other.id
    assert photo_client.post(route, data=data | {
        '_action': f'delete_existing_{photo_id}'}).status_code == 404
    with photo_client.session_transaction() as session:
        session.pop('user_id', None)
    assert photo_client.post(route, data=data | {'_action': f'delete_existing_{photo_id}'}).status_code == 302
    assert db.session.get(PropertyPhoto, photo_id) is not None
