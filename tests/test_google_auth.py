"""Google OIDC is mocked; these tests never contact Google."""
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import current_app
from sqlalchemy import select

from app import create_app, db
from app.avatar_storage import AvatarError, fetch_google_avatar
from app.google_provider import GoogleAuthProvider, GoogleIdentity, GoogleProviderError
from app.models import User, UserIdentity
from app.photo_storage import photo_storage
from test_auth import client, csrf, signup
from test_meta_facebook_auth import production_config
from test_facebook_avatar import PictureResponse, image_bytes
from test_properties import migrated_connection

CLIENT_ID = 'test-client.apps.googleusercontent.com'
CLIENT_SECRET = 'test-only-google-secret-never-real'
CALLBACK = 'http://localhost:5000/auth/google/callback'
PRODUCTION_CALLBACK = 'https://www.manazilelsaudan.com/auth/google/callback'


@pytest.fixture
def google_client(client):
    assert 'google' in current_app.blueprints
    assert current_app.extensions['google_auth_provider'].redirect_uri == CALLBACK
    return client


@pytest.fixture(autouse=True)
def isolated_google_environment(monkeypatch):
    monkeypatch.setenv('PUBLIC_GOOGLE_LOGIN_ENABLED', '1')
    monkeypatch.setenv('GOOGLE_CLIENT_ID', CLIENT_ID)
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET', CLIENT_SECRET)
    monkeypatch.setenv('GOOGLE_REDIRECT_URI', CALLBACK)


def begin(client, destination='/', language='en'):
    page = client.get('/login', query_string={'next': destination, 'lang': language})
    result = client.post('/auth/google', data={'csrf_token': csrf(page), 'next': destination,
                                               '_language': language})
    assert result.status_code == 303
    query = parse_qs(urlsplit(result.location).query)
    return result, query['state'][0]


def fake_identity(monkeypatch, subject='stable-sub', name='Google Member', picture=None):
    def authenticate(self, code, nonce, verifier):
        assert code == 'mock-code' and nonce and verifier
        return GoogleIdentity(subject, name, picture)
    monkeypatch.setattr(GoogleAuthProvider, 'authenticate', authenticate)


def complete(client, phone='0912222222', language='en'):
    page = client.get('/auth/complete-profile?lang=' + language)
    assert page.status_code == 200
    return client.post('/auth/complete-profile', data={'csrf_token': csrf(page),
                       'whatsapp': phone, '_language': language})


def test_configuration_disabled_and_production_fails_closed():
    app = create_app(production_config(FACEBOOK_AUTH_PROVIDER='disabled'))
    assert 'google_auth_provider' not in app.extensions
    assert '/auth/google' not in {rule.rule for rule in app.url_map.iter_rules()}
    required = dict(PUBLIC_GOOGLE_LOGIN_ENABLED=True, GOOGLE_CLIENT_ID=CLIENT_ID,
                    GOOGLE_CLIENT_SECRET=CLIENT_SECRET, GOOGLE_REDIRECT_URI=PRODUCTION_CALLBACK)
    ready = create_app(production_config(FACEBOOK_AUTH_PROVIDER='disabled', **required))
    assert ready.extensions['google_auth_provider'].redirect_uri == PRODUCTION_CALLBACK
    for key, value in [('GOOGLE_CLIENT_ID', None), ('GOOGLE_CLIENT_SECRET', None),
                       ('GOOGLE_REDIRECT_URI', None), ('GOOGLE_REDIRECT_URI', CALLBACK),
                       ('GOOGLE_REDIRECT_URI', 'https://evil.example/auth/google/callback')]:
        with pytest.raises(ValueError):
            create_app(production_config(FACEBOOK_AUTH_PROVIDER='disabled', **(required | {key: value})))


@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
def test_public_ui_and_authorization_url(google_client, language, direction):
    for path in ('/auth', '/login', '/signup'):
        page = google_client.get(path + '?lang=' + language)
        assert f'<html lang="{language}" dir="{direction}">' in page.text
        assert 'action="/auth/google"' in page.text
        assert 'action="/auth/facebook"' not in page.text
        assert '/static/images/google-g.svg' in page.text
        assert ('المتابعة باستخدام جوجل' if language == 'ar' else 'Continue with Google') in page.text
    result, state = begin(google_client, language=language)
    query = parse_qs(urlsplit(result.location).query)
    assert result.location.startswith('https://accounts.google.com/o/oauth2/v2/auth?')
    assert query['scope'] == ['openid email profile']
    assert query['redirect_uri'] == [CALLBACK]
    assert query['state'] == [state]
    assert query['nonce'][0] and query['code_challenge_method'] == ['S256']


def test_start_is_csrf_protected_and_disabled_flag_fails_closed(google_client):
    assert google_client.post('/auth/google').status_code == 400
    current_app.config['PUBLIC_GOOGLE_LOGIN_ENABLED'] = False
    page = google_client.get('/login')
    assert 'Continue with Google' not in page.text
    assert google_client.post('/auth/google', data={'csrf_token': csrf(page)}).status_code == 404


def test_new_identity_profile_completion_and_returning_login(google_client, monkeypatch):
    fake_identity(monkeypatch)
    _, state = begin(google_client, '/properties/new')
    result = google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'mock-code'})
    assert result.location == '/auth/complete-profile?lang=en'
    identity = db.session.get(UserIdentity, ('google', 'stable-sub'))
    assert identity and identity.user.role == 'user' and not identity.user.is_verified
    assert identity.user.phone_number is None and identity.user.password_hash is None
    assert complete(google_client).location == '/properties/new'
    assert identity.user.phone_number == '+249912222222' and not identity.user.is_verified
    first_id = identity.user.id
    identity.user.contact_name = 'Edited Manazil Name'
    db.session.commit()
    logout = google_client.post('/logout', data={'csrf_token': csrf(google_client.get('/account'))})
    assert logout.status_code == 303
    _, state = begin(google_client)
    assert google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'mock-code'}).location == '/?lang=en'
    assert db.session.get(UserIdentity, ('google', 'stable-sub')).user_id == first_id
    assert identity.user.contact_name == 'Edited Manazil Name'
    assert db.session.query(UserIdentity).filter_by(provider='google').count() == 1


def test_google_never_merges_with_phone_or_facebook_accounts(google_client, monkeypatch):
    signup(google_client, phone='0912345678')
    manual = db.session.scalar(select(User).where(User.phone_number == '+249912345678'))
    google_client.post('/logout', data={'csrf_token': csrf(google_client.get('/account'))})
    fake_identity(monkeypatch, subject='different-id', name=manual.contact_name)
    _, state = begin(google_client)
    google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'mock-code'})
    identity = db.session.get(UserIdentity, ('google', 'different-id'))
    assert identity.user_id != manual.id
    assert identity.user.role == 'user'
    result = complete(google_client, '0912345678')
    assert result.status_code == 422
    assert identity.user.phone_number is None and manual.password_hash


@pytest.mark.parametrize('callback', [
    {'state': 'wrong', 'code': 'mock-code'}, {'code': 'mock-code'},
])
def test_invalid_state_is_rejected_before_exchange(google_client, monkeypatch, callback):
    fake_identity(monkeypatch)
    _, state = begin(google_client)
    assert google_client.get('/auth/google/callback', query_string=callback).status_code == 400
    assert google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'mock-code'}).status_code == 400
    assert db.session.query(UserIdentity).filter_by(provider='google').count() == 0


def test_expired_state_denial_missing_code_and_replay(google_client, monkeypatch):
    fake_identity(monkeypatch)
    _, state = begin(google_client)
    with google_client.session_transaction() as stored:
        stored['google_auth'] = stored['google_auth'] | {'issued_at': time.time() - 301}
    assert google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'mock-code'}).status_code == 400
    _, state = begin(google_client)
    assert google_client.get('/auth/google/callback', query_string={'state': state, 'error': 'access_denied'}).status_code == 400
    _, state = begin(google_client)
    assert google_client.get('/auth/google/callback', query_string={'state': state}).status_code == 400
    _, state = begin(google_client)
    assert google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'mock-code'}).status_code == 303
    assert google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'mock-code'}).status_code == 400


def test_unsafe_next_and_incomplete_user_on_return(google_client, monkeypatch):
    fake_identity(monkeypatch)
    _, state = begin(google_client, 'https://evil.example/')
    assert google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'mock-code'}).location == '/auth/complete-profile?lang=en'
    google_client.post('/logout', data={'csrf_token': csrf(google_client.get('/auth/complete-profile'))})
    _, state = begin(google_client)
    assert google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'mock-code'}).location == '/auth/complete-profile?lang=en'
    assert complete(google_client).location == '/?lang=en'


def test_suspended_user_is_rejected(google_client, monkeypatch):
    fake_identity(monkeypatch)
    _, state = begin(google_client)
    google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'mock-code'})
    user = db.session.get(UserIdentity, ('google', 'stable-sub')).user
    user.is_active = False
    db.session.commit()
    _, state = begin(google_client)
    assert google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'mock-code'}).status_code == 403


class FakeResponse:
    def __init__(self, data):
        self.data = json.dumps(data).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, count):
        return self.data[:count]


def test_provider_validates_signed_claims_and_network_failures(monkeypatch):
    provider = GoogleAuthProvider(CLIENT_ID, CLIENT_SECRET, CALLBACK)
    monkeypatch.setattr('app.google_provider.urlopen', lambda *args, **kwargs: FakeResponse({'id_token': 'mock-id-token'}))
    claims = {'iss': 'https://accounts.google.com', 'aud': CLIENT_ID, 'sub': 'stable-id',
              'email': 'member@example.test', 'email_verified': True, 'name': 'Member',
              'nonce': 'nonce', 'exp': time.time() + 3600}
    monkeypatch.setattr('app.google_provider.id_token.verify_oauth2_token', lambda *args: claims.copy())
    assert provider.authenticate('mock-code', 'nonce', 'verifier').provider_user_id == 'stable-id'
    monkeypatch.setattr('app.google_provider.urlopen', lambda *args, **kwargs: FakeResponse({}))
    with pytest.raises(GoogleProviderError):
        provider.authenticate('mock-code', 'nonce', 'verifier')


@pytest.mark.parametrize('change,category', [
    ({'aud': 'wrong-client'}, 'audience_validation_failure'),
    ({'iss': 'https://evil.example'}, 'issuer_validation_failure'),
    ({'exp': 0}, 'expiration_validation_failure'),
    ({'nonce': 'wrong'}, 'nonce_validation_failure'),
    ({'email': None}, 'missing_email'),
    ({'email_verified': False}, 'email_verified_failure'),
    ({'sub': ''}, 'malformed_required_claims'),
    ({'email': 'invalid'}, 'malformed_required_claims'),
])
def test_provider_reports_fixed_claim_failure_categories(monkeypatch, change, category):
    provider = GoogleAuthProvider(CLIENT_ID, CLIENT_SECRET, CALLBACK)
    monkeypatch.setattr('app.google_provider.urlopen', lambda *args, **kwargs: FakeResponse({'id_token': 'mock-id-token'}))
    claims = {'iss': 'https://accounts.google.com', 'aud': CLIENT_ID, 'sub': 'stable-id',
              'email': 'member@example.test', 'email_verified': True,
              'nonce': 'nonce', 'exp': time.time() + 3600}
    with pytest.raises(GoogleProviderError) as caught:
        _with_claims(provider, claims | change)
    assert caught.value.category == category


@pytest.mark.parametrize('reason,category', [
    ('Token has wrong audience: sensitive-value', 'audience_validation_failure'),
    ('Wrong issuer: sensitive-value', 'issuer_validation_failure'),
    ('Token expired: sensitive-value', 'expiration_validation_failure'),
    ('Invalid signature: sensitive-value', 'id_token_verification_failure'),
])
def test_verifier_errors_are_classified_without_exposing_details(monkeypatch, reason, category):
    provider = GoogleAuthProvider(CLIENT_ID, CLIENT_SECRET, CALLBACK)
    monkeypatch.setattr('app.google_provider.urlopen', lambda *args, **kwargs: FakeResponse({'id_token': 'mock-id-token'}))
    def reject(*args):
        raise ValueError(reason)
    monkeypatch.setattr('app.google_provider.id_token.verify_oauth2_token', reject)
    with pytest.raises(GoogleProviderError) as caught:
        provider.authenticate('mock-code', 'nonce', 'verifier')
    assert caught.value.category == category
    assert 'sensitive-value' not in str(caught.value)


def test_exchange_failures_have_distinct_categories(monkeypatch):
    provider = GoogleAuthProvider(CLIENT_ID, CLIENT_SECRET, CALLBACK)
    def http_failure(*args, **kwargs):
        raise HTTPError('https://oauth2.googleapis.com/token', 400, 'sensitive-response', {}, None)
    monkeypatch.setattr('app.google_provider.urlopen', http_failure)
    with pytest.raises(GoogleProviderError) as caught:
        provider.authenticate('secret-code', 'nonce', 'verifier')
    assert (caught.value.category, caught.value.http_status) == ('token_exchange_http_status', 400)
    monkeypatch.setattr('app.google_provider.urlopen', lambda *args, **kwargs: (_ for _ in ()).throw(URLError('sensitive-network-detail')))
    with pytest.raises(GoogleProviderError) as caught:
        provider.authenticate('secret-code', 'nonce', 'verifier')
    assert caught.value.category == 'authorization_code_exchange_failure'
    monkeypatch.setattr('app.google_provider.urlopen', lambda *args, **kwargs: FakeResponse({'wrong': 'response'}))
    with pytest.raises(GoogleProviderError) as caught:
        provider.authenticate('secret-code', 'nonce', 'verifier')
    assert caught.value.category == 'malformed_provider_response'


@pytest.mark.parametrize('unexpected', [False, True])
def test_callback_logs_only_sanitized_failure_category(google_client, monkeypatch, unexpected):
    records = []
    monkeypatch.setattr(current_app.logger, 'warning', lambda format, *args: records.append(format % args))
    def reject(*args):
        if unexpected:
            raise RuntimeError('secret-code sensitive-token member@example.test')
        raise GoogleProviderError('token_exchange_http_status', 400)
    monkeypatch.setattr(GoogleAuthProvider, 'authenticate', reject)
    _, state = begin(google_client)
    response = google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'secret-code'})
    assert response.status_code == 502
    assert records == [f'GOOGLE_AUTH_DIAGNOSTIC category={"unexpected_provider_error" if unexpected else "token_exchange_http_status"} http_status={"none" if unexpected else "400"}']
    assert all(value not in records[0] for value in (state, 'secret-code', 'sensitive-token', 'member@example.test'))


def test_local_access_log_omits_google_callback_query(monkeypatch):
    from run import LocalRequestHandler
    recorded = []
    monkeypatch.setattr(LocalRequestHandler, 'log', lambda self, level, format, *args: recorded.append(format % args))
    handler = object.__new__(LocalRequestHandler)
    handler.path = '/auth/google/callback?state=secret-state&code=secret-code'
    handler.command = 'GET'
    handler.request_version = 'HTTP/1.1'
    handler.log_request(502, '-')
    assert handler.path.endswith('code=secret-code')
    assert '/auth/google/callback' in recorded[0]
    assert 'secret-state' not in recorded[0] and 'secret-code' not in recorded[0]


def _with_claims(provider, claims):
    from unittest.mock import patch
    with patch('app.google_provider.id_token.verify_oauth2_token', return_value=claims):
        return provider.authenticate('mock-code', 'nonce', 'verifier')


def test_google_avatar_import_refresh_and_manual_precedence(google_client, monkeypatch, tmp_path):
    current_app.config['PHOTO_STORAGE_ROOT'] = str(tmp_path)
    monkeypatch.setattr('app.avatar_storage._open_picture', lambda request: PictureResponse(image_bytes()))
    fake_identity(monkeypatch, picture='https://lh3.googleusercontent.com/avatar')
    _, state = begin(google_client)
    google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'mock-code'})
    user = db.session.get(UserIdentity, ('google', 'stable-sub')).user
    assert user.avatar_source == 'google'
    first = user.avatar_storage_key
    assert photo_storage().path(first).is_file()
    complete(google_client)
    assert google_client.get('/account/avatar').status_code == 200
    _, state = begin(google_client)
    google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'mock-code'})
    assert user.avatar_storage_key != first and not photo_storage().path(first).exists()
    manual = photo_storage().save_avatar(user.id, image_bytes('blue'))
    user.avatar_storage_key = manual
    user.avatar_source = 'manual'
    db.session.commit()
    monkeypatch.setattr('app.avatar_storage._open_picture', lambda request: pytest.fail('Manual avatar fetched'))
    _, state = begin(google_client)
    google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'mock-code'})
    assert user.avatar_storage_key == manual and user.avatar_source == 'manual'


def test_google_avatar_url_is_restricted_and_import_failure_does_not_block_login(google_client, monkeypatch):
    for url in ('http://lh3.googleusercontent.com/avatar', 'https://evil.example/avatar',
                'https://lh3.googleusercontent.com.evil.example/avatar'):
        with pytest.raises(AvatarError):
            fetch_google_avatar(url)
    fake_identity(monkeypatch, picture='https://evil.example/avatar')
    _, state = begin(google_client)
    assert google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'mock-code'}).status_code == 303
    user = db.session.get(UserIdentity, ('google', 'stable-sub')).user
    assert user.avatar_storage_key is None
    fake_identity(monkeypatch, picture=None)
    _, state = begin(google_client)
    assert google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'mock-code'}).status_code == 303
    assert user.avatar_storage_key is None
