"""Facebook avatars are optional, private, and never override a manual choice."""
import io

import pytest
from flask import current_app
from PIL import Image

from app import db
from app.avatar_storage import AvatarError, MAX_DOWNLOAD_BYTES, fetch_facebook_avatar
from app.models import User
from app.photo_storage import LocalPhotoStorage, PhotoError, photo_storage
from test_auth import client, csrf
from test_facebook_auth import complete_facebook_profile
from test_meta_facebook_auth import callback, meta_client, mock_meta, start
from test_production_config import FakeContainer
from test_properties import migrated_connection

PICTURE_URL = 'https://scontent.xx.fbcdn.net/avatar.jpg'


def image_bytes(color='green'):
    output = io.BytesIO()
    Image.new('RGB', (40, 40), color).save(output, format='JPEG')
    return output.getvalue()


class PictureResponse:
    def __init__(self, payload, content_type='image/jpeg', size=None):
        self.payload = payload
        self.headers = {'Content-Type': content_type,
                        'Content-Length': str(len(payload) if size is None else size)}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.payload[:limit]


def profile_with_picture(picture_url=PICTURE_URL, silhouette=False):
    return {'id': '987654321', 'name': 'Meta Member',
            'picture': {'data': {'url': picture_url, 'is_silhouette': silhouette}}}


@pytest.fixture
def avatar_client(meta_client, monkeypatch, tmp_path):
    current_app.config['PHOTO_STORAGE_ROOT'] = str(tmp_path)
    monkeypatch.setattr('app.avatar_storage._open_picture',
                        lambda request: PictureResponse(image_bytes()))
    return meta_client


def facebook_login(client):
    _, state = start(client)
    response = callback(client, state)
    assert response.status_code == 303
    if response.location.startswith('/auth/complete-profile'):
        complete_facebook_profile(client)
    return db.session.query(User).one()


def test_new_facebook_user_avatar_is_stored_and_served_privately(avatar_client, monkeypatch):
    mock_meta(monkeypatch, profile=profile_with_picture())
    user = facebook_login(avatar_client)
    assert user.avatar_source == 'facebook'
    assert user.avatar_storage_key.startswith(f'avatars/{user.id}/')
    assert photo_storage().path(user.avatar_storage_key).is_file()
    page = avatar_client.get('/account?lang=en')
    assert '<img class="account-avatar account-avatar-image" src="/account/avatar"' in page.text
    picture = avatar_client.get('/account/avatar')
    assert picture.status_code == 200 and picture.mimetype == 'image/webp'
    with Image.open(io.BytesIO(picture.data)) as image:
        assert image.size == (40, 40)
    assert picture.headers['Cache-Control'] == 'private, no-store'
    avatar_client.post('/logout', data={'csrf_token': csrf(page)})
    assert avatar_client.get('/account/avatar').status_code == 302


def test_existing_facebook_user_without_avatar_gets_one(avatar_client, monkeypatch):
    mock_meta(monkeypatch)
    user = facebook_login(avatar_client)
    assert user.avatar_storage_key is None and user.avatar_source is None
    mock_meta(monkeypatch, profile=profile_with_picture())
    facebook_login(avatar_client)
    assert user.avatar_source == 'facebook' and user.avatar_storage_key


def test_facebook_avatar_refresh_replaces_and_removes_old_file(avatar_client, monkeypatch):
    mock_meta(monkeypatch, profile=profile_with_picture())
    user = facebook_login(avatar_client)
    old_key = user.avatar_storage_key
    monkeypatch.setattr('app.avatar_storage._open_picture',
                        lambda request: PictureResponse(image_bytes('blue')))
    facebook_login(avatar_client)
    assert user.avatar_storage_key != old_key
    assert not photo_storage().path(old_key).exists()
    assert photo_storage().path(user.avatar_storage_key).is_file()


def test_manual_avatar_is_never_replaced_or_downloaded(avatar_client, monkeypatch):
    mock_meta(monkeypatch)
    user = facebook_login(avatar_client)
    storage = photo_storage()
    manual_key = storage.save_avatar(user.id, image_bytes())
    user.avatar_storage_key = manual_key
    user.avatar_source = 'manual'
    db.session.commit()
    monkeypatch.setattr('app.avatar_storage._open_picture',
                        lambda request: pytest.fail('Manual avatar must not trigger a fetch'))
    mock_meta(monkeypatch, profile=profile_with_picture())
    facebook_login(avatar_client)
    assert user.avatar_storage_key == manual_key and user.avatar_source == 'manual'
    assert storage.path(manual_key).is_file()


@pytest.mark.parametrize('picture', [None, {'data': {'is_silhouette': True, 'url': PICTURE_URL}},
                                       {'data': {'is_silhouette': False}}])
def test_missing_or_silhouette_picture_preserves_avatar(avatar_client, monkeypatch, picture):
    mock_meta(monkeypatch, profile=profile_with_picture())
    user = facebook_login(avatar_client)
    old_key = user.avatar_storage_key
    profile = {'id': '987654321', 'name': 'Meta Member'}
    if picture is not None:
        profile['picture'] = picture
    mock_meta(monkeypatch, profile=profile)
    facebook_login(avatar_client)
    assert user.avatar_storage_key == old_key and photo_storage().path(old_key).is_file()


@pytest.mark.parametrize('failure', ['timeout', 'invalid', 'oversized', 'wrong_type', 'storage'])
def test_avatar_failure_does_not_block_login_or_replace_existing(avatar_client, monkeypatch, failure):
    mock_meta(monkeypatch, profile=profile_with_picture())
    user = facebook_login(avatar_client)
    old_key = user.avatar_storage_key
    if failure == 'timeout':
        def fail(request):
            raise TimeoutError('private network detail')
        monkeypatch.setattr('app.avatar_storage._open_picture', fail)
    elif failure == 'storage':
        def fail(self, user_id, payload):
            raise OSError('private storage detail')
        monkeypatch.setattr(LocalPhotoStorage, 'save_avatar', fail)
    else:
        payload = (b'not an image' if failure == 'invalid' else
                   b'x' * (MAX_DOWNLOAD_BYTES + 1) if failure == 'oversized' else image_bytes())
        content_type = 'text/html' if failure == 'wrong_type' else 'image/jpeg'
        monkeypatch.setattr('app.avatar_storage._open_picture',
                            lambda request: PictureResponse(payload, content_type))
    facebook_login(avatar_client)
    assert user.avatar_storage_key == old_key and user.avatar_source == 'facebook'
    assert photo_storage().path(old_key).is_file()


def test_url_validation_rejects_untrusted_hosts_and_redirects(monkeypatch):
    for url in ('http://scontent.xx.fbcdn.net/avatar.jpg', 'https://evil.example/avatar.jpg',
                'https://scontent.xx.fbcdn.net.evil.example/avatar.jpg',
                'https://scontent.xx.fbcdn.net/avatar.jpg?access_token=private'):
        with pytest.raises(AvatarError):
            fetch_facebook_avatar(url)
    monkeypatch.setattr('app.avatar_storage._open_picture',
                        lambda request: (_ for _ in ()).throw(AvatarError('redirect')))
    with pytest.raises(AvatarError):
        fetch_facebook_avatar(PICTURE_URL)


def test_azure_avatar_storage_and_refresh_use_private_container(avatar_client, monkeypatch):
    container = FakeContainer()
    current_app.config.update(PHOTO_STORAGE_BACKEND='azure_blob', AZURE_BLOB_CONTAINER_CLIENT=container)
    mock_meta(monkeypatch, profile=profile_with_picture())
    user = facebook_login(avatar_client)
    first_key = user.avatar_storage_key
    assert container.types[first_key] == 'image/webp'
    assert avatar_client.get('/account/avatar').status_code == 200
    facebook_login(avatar_client)
    assert first_key not in container.data
    assert user.avatar_storage_key in container.data


def test_avatar_route_rejects_missing_or_invalid_key(avatar_client, monkeypatch):
    mock_meta(monkeypatch)
    user = facebook_login(avatar_client)
    assert avatar_client.get('/account/avatar').status_code == 404
    user.avatar_storage_key = '../outside.webp'
    user.avatar_source = 'manual'
    db.session.commit()
    assert avatar_client.get('/account/avatar').status_code == 404
    with pytest.raises(PhotoError):
        photo_storage().delete_avatar('../outside.webp', user.id)
    other_key = photo_storage().save_avatar(user.id + 1, image_bytes())
    user.avatar_storage_key = other_key
    db.session.commit()
    assert avatar_client.get('/account/avatar').status_code == 404
    with pytest.raises(PhotoError):
        photo_storage().delete_avatar(other_key, user.id)


@pytest.mark.parametrize('language', ['ar', 'en'])
@pytest.mark.parametrize('route', ['/login', '/signup'])
def test_facebook_button_is_not_public(client, route, language):
    current_app.config['PUBLIC_FACEBOOK_LOGIN_ENABLED'] = True
    page = client.get(route + '?lang=' + language).text
    assert 'src="/static/images/facebook-f.svg"' not in page
    assert 'Continue with Facebook' not in page and 'المتابعة باستخدام فيسبوك' not in page


def test_fallback_initial_for_account_without_avatar(avatar_client, monkeypatch):
    mock_meta(monkeypatch)
    facebook_login(avatar_client)
    page = avatar_client.get('/account?lang=en').text
    assert '<span class="account-avatar" aria-hidden="true">M</span>' in page
    assert 'src="/account/avatar"' not in page
