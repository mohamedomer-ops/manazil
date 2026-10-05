"""Production wiring never connects to Neon or Azure in tests."""
import io
import os
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest
from azure.core.exceptions import AzureError, ResourceNotFoundError
from PIL import Image
from flask import request
from werkzeug.datastructures import FileStorage

from app import create_app
from app import db
from app.azure_photo_storage import AzureBlobPhotoStorage
from app.otp import DevelopmentOTPProvider, provider
from app.photo_storage import LocalPhotoStorage, PhotoError, photo_storage
from app.models import Property, PropertyPhoto
from test_auth import client
from test_properties import migrated_connection, values

LOCAL_DATABASE = os.environ.get('DATABASE_URL', 'postgresql+psycopg://manazil@localhost:5432/manazil')
NEON_EXAMPLE = 'postgresql://account:example-password@ep-example.aws.neon.tech/neondb?sslmode=require'


class FakeBlob:
    def __init__(self, container, key):
        self.container, self.key = container, key

    def upload_blob(self, payload, *, overwrite=False, content_settings=None):
        if self.container.fail:
            raise AzureError('fake storage failure')
        if self.key in self.container.data and not overwrite:
            raise AzureError('already exists')
        self.container.data[self.key] = bytes(payload)
        self.container.types[self.key] = content_settings.content_type

    def get_blob_properties(self):
        if self.key not in self.container.data:
            raise ResourceNotFoundError('missing')
        return SimpleNamespace(size=len(self.container.data[self.key]))

    def download_blob(self, *, offset=0, length=None):
        if self.container.fail:
            raise AzureError('fake storage failure')
        if self.key not in self.container.data:
            raise ResourceNotFoundError('missing')
        return SimpleNamespace(readall=lambda: self.container.data[self.key][offset:offset + length])

    def delete_blob(self, **kwargs):
        if self.container.fail:
            raise AzureError('fake storage failure')
        if self.key not in self.container.data:
            raise ResourceNotFoundError('missing')
        del self.container.data[self.key]

    def exists(self):
        if self.container.fail:
            raise AzureError('fake storage failure')
        return self.key in self.container.data


class FakeContainer:
    def __init__(self):
        self.data, self.types, self.fail = {}, {}, False

    def get_blob_client(self, key):
        return FakeBlob(self, key)


def upload():
    image = Image.new('RGB', (8, 8), 'green')
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG')
    buffer.seek(0)
    return FileStorage(stream=buffer, filename='room.jpg', content_type='image/jpeg')


def production_config(**overrides):
    return {
        'TESTING': True, 'ENVIRONMENT': 'production',
        'SQLALCHEMY_DATABASE_URI': NEON_EXAMPLE,
        'SECRET_KEY': 'production-test-secret-that-is-long-enough',
        'DATA_DELETION_CONTACT_EMAIL': 'privacy@example.test',
        'PHOTO_STORAGE_BACKEND': 'azure_blob',
        'AZURE_BLOB_CONTAINER_CLIENT': FakeContainer(),
        'OTP_DEVELOPMENT_MODE': False,
        'PUBLIC_GOOGLE_LOGIN_ENABLED': False,
    } | overrides


def test_local_defaults_and_neon_url_normalization():
    app = create_app({'TESTING': True, 'ENVIRONMENT': 'testing', 'SQLALCHEMY_DATABASE_URI': LOCAL_DATABASE})
    assert app.config['PHOTO_STORAGE_BACKEND'] == 'local'
    assert not app.config['SESSION_COOKIE_SECURE']
    assert app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql+psycopg://')
    production = create_app(production_config())
    assert production.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql+psycopg://')
    assert 'example-password' in production.config['SQLALCHEMY_DATABASE_URI']
    assert production.config['SQLALCHEMY_DATABASE_URI'].endswith('sslmode=require')
    assert production.config['SESSION_COOKIE_SECURE'] and not production.debug


def test_production_fails_closed_for_missing_security_configuration():
    for changes in ({'SECRET_KEY': None}, {'SECRET_KEY': 'short'},
                    {'DATA_DELETION_CONTACT_EMAIL': None},
                    {'DATA_DELETION_CONTACT_EMAIL': 'not-an-email'},
                    {'PHOTO_STORAGE_BACKEND': 'local'},
                    {'AZURE_BLOB_CONTAINER_CLIENT': None, 'AZURE_STORAGE_CONNECTION_STRING': None},
                    {'SQLALCHEMY_DATABASE_URI': NEON_EXAMPLE.replace('?sslmode=require', '')},
                    {'OTP_DEVELOPMENT_MODE': True}):
        with pytest.raises(ValueError):
            create_app(production_config(**changes))


def test_migration_cli_skips_only_unrelated_blob_credentials(monkeypatch):
    monkeypatch.setenv('MANAZIL_MIGRATION_ONLY', '1')
    monkeypatch.setattr(sys, 'argv', ['flask', '--app', 'run', 'db', 'upgrade'])
    migration = production_config(AZURE_BLOB_CONTAINER_CLIENT=None,
                                  AZURE_STORAGE_CONNECTION_STRING=None,
                                  AZURE_STORAGE_CONTAINER=None)
    app = create_app(migration)
    assert app.config['ENVIRONMENT'] == 'production'
    assert app.config['PHOTO_STORAGE_BACKEND'] == 'azure_blob'
    for invalid in ({'SECRET_KEY': 'short'},
                    {'SQLALCHEMY_DATABASE_URI': NEON_EXAMPLE.replace('?sslmode=require', '')},
                    {'OTP_DEVELOPMENT_MODE': True}):
        with pytest.raises(ValueError):
            create_app(migration | invalid)
    monkeypatch.setattr(sys, 'argv', ['gunicorn', 'run:app'])
    with pytest.raises(ValueError):
        create_app(migration)


def test_production_authentication_fails_closed_for_development_otp():
    app = create_app(production_config(DEBUG=True))
    assert not app.debug and app.config['SESSION_COOKIE_SECURE']
    with app.app_context():
        with pytest.raises(RuntimeError):
            provider()
        with pytest.raises(RuntimeError):
            DevelopmentOTPProvider().send('+249912345678', '123456')


def test_unconfigured_production_otp_returns_safe_service_error():
    app = create_app(production_config())
    app.add_url_rule('/_otp-check', view_func=provider)
    response = app.test_client().get('/_otp-check?lang=en',
                                     base_url='https://manazil-prod.azurewebsites.net')
    assert response.status_code == 503
    assert b'Authentication is temporarily unavailable.' in response.data
    assert b'Production OTP delivery is not configured' not in response.data


def test_forwarded_scheme_is_trusted_only_when_explicitly_enabled():
    for trusted, expected in ((False, 'http'), (True, 'https')):
        app = create_app(production_config(TRUST_PROXY_HEADERS=trusted))
        app.add_url_rule('/_scheme-check', view_func=lambda: request.scheme)
        result = app.test_client().get('/_scheme-check', base_url='http://manazil-prod.azurewebsites.net',
                                       headers={'X-Forwarded-Proto': 'https'})
        assert result.text == expected


def test_production_trusts_exact_custom_and_azure_hosts_without_opening_other_hosts():
    app = create_app(production_config(TRUSTED_HOSTS=['manazil-prod.azurewebsites.net']))
    app.add_url_rule('/_host-check', view_func=lambda: 'ok')
    client = app.test_client()
    assert app.config['TRUSTED_HOSTS'] == [
        'manazilelsaudan.com', 'www.manazilelsaudan.com', 'manazil-prod.azurewebsites.net']
    for host in app.config['TRUSTED_HOSTS']:
        expected = 308 if host == 'manazilelsaudan.com' else 200
        assert client.get('/_host-check', base_url=f'https://{host}').status_code == expected
    for host in ('localhost', 'other.azurewebsites.net', 'fake.manazilelsaudan.com'):
        assert client.get('/_host-check', base_url=f'https://{host}').status_code == 400


def test_production_keeps_additional_explicit_hosts_and_development_is_unchanged():
    production = create_app(production_config(TRUSTED_HOSTS=['existing.example']))
    production.add_url_rule('/_host-check', view_func=lambda: 'ok')
    assert production.test_client().get('/_host-check', base_url='https://existing.example').status_code == 200
    assert production.test_client().get('/_host-check', base_url='https://unlisted.example').status_code == 400
    local = create_app({'TESTING': True, 'ENVIRONMENT': 'development',
                        'SQLALCHEMY_DATABASE_URI': LOCAL_DATABASE, 'TRUSTED_HOSTS': None})
    local.add_url_rule('/_host-check', view_func=lambda: 'ok')
    assert local.test_client().get('/_host-check', base_url='http://localhost').status_code == 200


def test_apex_redirects_to_www_before_any_production_route_runs():
    app = create_app(production_config())
    app.add_url_rule('/_host-check', view_func=lambda: 'ok')
    browser = app.test_client()
    for path in ('/properties?state=khartoum&lang=en', '/auth?next=%2Fproperties%2Fnew',
                 '/auth/google/callback?state=example'):
        result = browser.get(path, base_url='https://manazilelsaudan.com')
        assert result.status_code == 308
        assert result.location == 'https://www.manazilelsaudan.com' + path
    assert browser.get('/_host-check', base_url='http://manazilelsaudan.com').location == 'https://www.manazilelsaudan.com/_host-check'
    assert browser.get('/_host-check', base_url='https://www.manazilelsaudan.com').status_code == 200
    assert browser.get('/_host-check', base_url='https://manazil-prod.azurewebsites.net').status_code == 200
    assert browser.get('/_host-check', base_url='https://other.example').status_code == 400


def test_local_storage_contract_remains_operational(tmp_path):
    app = create_app({'TESTING': True, 'ENVIRONMENT': 'testing', 'SQLALCHEMY_DATABASE_URI': LOCAL_DATABASE,
                      'PHOTO_STORAGE_ROOT': str(tmp_path), 'PHOTO_STORAGE_BACKEND': 'local'})
    with app.app_context():
        storage = photo_storage()
        assert isinstance(storage, LocalPhotoStorage)
        token = storage.new_token()
        staged = storage.add(token, 'other', [upload()])
        key = staged[0]['storage_key']
        assert storage.path(key).is_file()
        published, copied = storage.prepare_property_photos(token, 42)
        assert storage.path(copied[0]).is_file()
        with app.test_request_context('/photos'):
            assert storage.send(published[0]['storage_key'], 'image/jpeg').status_code == 200
        storage.mark_submitted(token, 42)
        assert not storage.path(key).exists()
        storage.remove_keys(copied)
        assert not storage.path(copied[0]).exists()


def test_private_azure_storage_contract_with_fake_client():
    container = FakeContainer()
    app = create_app({'TESTING': True, 'ENVIRONMENT': 'testing', 'SQLALCHEMY_DATABASE_URI': LOCAL_DATABASE,
                      'PHOTO_STORAGE_BACKEND': 'azure_blob', 'AZURE_BLOB_CONTAINER_CLIENT': container})
    with app.app_context():
        storage = photo_storage()
        assert isinstance(storage, AzureBlobPhotoStorage)
        token = storage.new_token()
        staged = storage.add(token, 'other', [upload()])
        key = staged[0]['storage_key']
        assert container.types[key] == 'image/jpeg'
        assert storage.read(token)['photos'][0]['storage_key'] == key
        published, copied = storage.prepare_property_photos(token, 42)
        assert copied[0].startswith('properties/42/')
        assert container.data[key] == container.data[copied[0]]
        with app.test_request_context('/photos'):
            response = storage.send(copied[0], 'image/jpeg')
            assert response.status_code == 200 and response.mimetype == 'image/jpeg'
        storage.mark_submitted(token, 42)
        assert key not in container.data
        storage.remove_keys(copied)
        assert copied[0] not in container.data
        with pytest.raises(PhotoError):
            storage.send('../secret', 'image/jpeg')
        with pytest.raises(PhotoError):
            storage.send(copied[0], 'image/jpeg')
        container.fail = True
        with pytest.raises(PhotoError):
            storage.read(token)


def test_public_photo_route_uses_private_blob_backend_and_visibility(client, values):
    from flask import current_app

    container = FakeContainer()
    current_app.config.update(PHOTO_STORAGE_BACKEND='azure_blob', AZURE_BLOB_CONTAINER_CLIENT=container)
    listing = Property(**(values | {'publication_status': 'published'}))
    db.session.add(listing)
    db.session.flush()
    key = f'properties/{listing.id}/{uuid4().hex}.jpg'
    payload = upload().stream.read()
    container.data[key] = payload
    photo = PropertyPhoto(property_id=listing.id, category='other', storage_key=key,
                          original_filename='room.jpg', content_type='image/jpeg',
                          file_size=len(payload), display_order=0, is_primary=True)
    db.session.add(photo)
    db.session.commit()
    response = client.get(f'/properties/photos/{photo.id}')
    assert response.status_code == 200 and response.data == payload
    listing.availability_status = 'rented'
    db.session.commit()
    assert client.get(f'/properties/photos/{photo.id}').status_code == 404
