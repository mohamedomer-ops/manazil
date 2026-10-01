from test_properties import migrated_connection
import io
import re
from PIL import Image
import pytest
from sqlalchemy import select
from app import db
from app.models import Property, PropertyPhoto
from app.photo_storage import MAX_PHOTO_BYTES
from test_property_creation import client, form_data

@pytest.fixture
def photo_client(client, tmp_path, monkeypatch):
    from flask import current_app
    current_app.config['PHOTO_STORAGE_ROOT'] = str(tmp_path)
    return client

def image_file(name='room.jpg'):
    image = Image.new('RGB', (8, 8), 'green')
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG')
    buffer.seek(0)
    return (buffer, name, 'image/jpeg')

def staged(page):
    return re.findall(r'name="_action" value="(primary|delete|up|down)_([0-9a-f]{32})"', page)

def test_upload_twenty_and_reject_twenty_first(photo_client, form_data):
    for i in range(20):
        response = photo_client.post('/admin/properties', data=form_data | {'_action':'upload','photos':image_file(f'{i}.jpg')})
        assert response.status_code == 200, (i, response.get_data(as_text=True)[-1000:])
    page = response.get_data(as_text=True)
    assert '>20</span> of 20 photos' in page
    response = photo_client.post('/admin/properties', data=form_data | {'_action':'upload','photos':image_file('extra.jpg')})
    assert response.status_code == 422
    assert '20 photos' in response.get_data(as_text=True)
    submit = photo_client.post('/admin/properties', data=form_data | {'_action':'submit'})
    assert submit.status_code == 303
    saved = db.session.scalar(select(Property).order_by(Property.id.desc()))
    assert len(saved.photos) == 20
    assert all(photo.category == 'other' for photo in saved.photos)

def test_photo_preview_delete_reorder_primary(photo_client, form_data):
    for i in range(2):
        response = photo_client.post('/admin/properties', data=form_data | {'_action':'upload','photos':image_file(f'{i}.jpg')})
        assert response.status_code == 200
    page = response.get_data(as_text=True)
    ids = list(dict.fromkeys(re.findall(r'value="delete_([0-9a-f]{32})"', page)))
    assert len(ids) == 2
    assert photo_client.get(f'/admin/properties/staged-photos/{form_data["_photo_token"]}/{ids[0]}').status_code == 200
    assert photo_client.post('/admin/properties', data=form_data | {'_action':f'primary_{ids[1]}'}).status_code == 200
    assert photo_client.post('/admin/properties', data=form_data | {'_action':f'up_{ids[1]}'}).status_code == 200
    assert photo_client.post('/admin/properties', data=form_data | {'_action':f'delete_{ids[0]}'}).status_code == 200

def test_invalid_file_rejected(photo_client, form_data):
    response = photo_client.post('/admin/properties', data=form_data | {'_action':'upload','photos':(io.BytesIO(b'bad'),'bad.jpg','image/jpeg')})
    assert response.status_code == 422
