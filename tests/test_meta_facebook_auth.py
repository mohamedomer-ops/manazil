"""Real Facebook OAuth boundary tests; every Meta HTTP response is mocked."""
import json
import logging
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import current_app

from app import create_app, db
from app.facebook_provider import DevelopmentFacebookAuthProvider
from app.languages import translate
from app.meta_facebook_provider import (
    GRAPH_VERSION, MetaFacebookAuthProvider, MetaProviderError,
)
from app.models import User, UserIdentity
from test_auth import client, csrf, login
from test_facebook_auth import complete_facebook_profile
from test_properties import migrated_connection

CALLBACK = 'https://manazilelsaudan.com/auth/facebook/callback'
APP_ID = '1234567890'
APP_SECRET = 'test-only-meta-secret-never-real'


class FakeResponse:
    def __init__(self, value):
        self.payload = json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.payload[:limit]


@pytest.fixture
def meta_client(client):
    current_app.extensions['facebook_auth_provider'] = MetaFacebookAuthProvider(APP_ID, APP_SECRET, CALLBACK)
    return client


def mock_meta(monkeypatch, *, token=None, profile=None, failure=None):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        if failure and len(calls) == failure[0]:
            raise failure[1]
        token_payload = token if token is not None else {
            'access_token': 'test-only-access-token', 'token_type': 'bearer'}
        profile_payload = profile if profile is not None else {'id': '987654321', 'name': 'Meta Member'}
        return FakeResponse(token_payload if len(calls) % 2 else profile_payload)

    monkeypatch.setattr('app.meta_facebook_provider.urlopen', fake_urlopen)
    return calls


def start(client, destination='/account', language='en'):
    page = client.get('/auth', query_string={'next': destination, 'lang': language})
    response = client.post('/auth/facebook', data={
        'csrf_token': csrf(page), 'next': destination, '_language': language})
    assert response.status_code == 303
    return response, parse_qs(urlsplit(response.location).query)['state'][0]


def callback(client, state, code='test-only-code'):
    return client.get('/auth/facebook/callback', query_string={'state': state, 'code': code})


def production_config(**changes):
    return dict(ENVIRONMENT='production', SECRET_KEY='test-only-production-secret-long-enough',
                SQLALCHEMY_DATABASE_URI='postgresql://user:example@neon.example/db?sslmode=require',
                PHOTO_STORAGE_BACKEND='azure_blob', AZURE_BLOB_CONTAINER_CLIENT=object(),
                DATA_DELETION_CONTACT_EMAIL='privacy@example.test',
                OTP_DEVELOPMENT_MODE=False, FACEBOOK_DEVELOPMENT_MODE=False,
                FACEBOOK_AUTH_PROVIDER='meta', FACEBOOK_APP_ID=APP_ID,
                FACEBOOK_APP_SECRET=APP_SECRET, FACEBOOK_REDIRECT_URI=CALLBACK) | changes


@pytest.mark.parametrize('change', [
    {'FACEBOOK_APP_ID': None}, {'FACEBOOK_APP_ID': 'not-numeric'},
    {'FACEBOOK_APP_SECRET': None}, {'FACEBOOK_APP_SECRET': 'short'},
    {'FACEBOOK_REDIRECT_URI': None},
    {'FACEBOOK_REDIRECT_URI': 'http://manazilelsaudan.com/auth/facebook/callback'},
    {'FACEBOOK_REDIRECT_URI': 'https://www.manazilelsaudan.com/auth/facebook/callback'},
    {'FACEBOOK_REDIRECT_URI': 'https://elsewhere.example/auth/facebook/callback'},
    {'FACEBOOK_REDIRECT_URI': CALLBACK + '?next=/account'},
    {'FACEBOOK_DEVELOPMENT_MODE': True},
])
def test_production_meta_configuration_fails_closed(change):
    with pytest.raises(ValueError):
        create_app(production_config(**change))


def test_provider_selection_is_explicit_and_never_falls_back():
    app = create_app(production_config(FACEBOOK_AUTH_PROVIDER=None))
    assert 'facebook_auth_provider' not in app.extensions
    assert '/auth/facebook' not in {rule.rule for rule in app.url_map.iter_rules()}
    assert isinstance(create_app(production_config()).extensions['facebook_auth_provider'], MetaFacebookAuthProvider)
    with pytest.raises(ValueError):
        create_app(production_config(FACEBOOK_AUTH_PROVIDER='development'))
    with pytest.raises(ValueError):
        create_app(production_config(FACEBOOK_AUTH_PROVIDER='unknown'))
    with pytest.raises(ValueError, match='Development authentication'):
        create_app(production_config(FACEBOOK_AUTH_PROVIDER=None, FACEBOOK_DEVELOPMENT_MODE=True))


def test_legacy_azure_callback_allows_startup_but_disables_facebook_login(caplog, monkeypatch):
    legacy = 'https://manazil-prod.azurewebsites.net/auth/facebook/callback'
    # Alembic's logging setup can disable an existing app logger in earlier tests.
    monkeypatch.setattr(logging.getLogger('app'), 'disabled', False)
    caplog.set_level('WARNING', logger='app')
    app = create_app(production_config(FACEBOOK_REDIRECT_URI=legacy))
    assert 'facebook_auth_provider' not in app.extensions
    assert '/auth/facebook' not in {rule.rule for rule in app.url_map.iter_rules()}
    browser = app.test_client()
    assert browser.get('/auth?lang=en', base_url='https://manazilelsaudan.com').status_code == 200
    page = browser.get('/login?lang=en', base_url='https://manazilelsaudan.com')
    assert 'Continue with Facebook' not in page.text
    assert 'Phone number' in page.text
    assert browser.get('/auth/facebook/callback', base_url='https://manazilelsaudan.com').status_code == 404
    assert 'Facebook Login is disabled until the canonical callback is configured.' in caplog.text
    assert legacy not in caplog.text
    assert APP_SECRET not in caplog.text

    ready = create_app(production_config())
    assert isinstance(ready.extensions['facebook_auth_provider'], MetaFacebookAuthProvider)
    assert '/auth/facebook' in {rule.rule for rule in ready.url_map.iter_rules()}


def test_authorization_url_scope_callback_csrf_and_language(meta_client):
    assert meta_client.post('/auth/facebook').status_code == 400
    response, state = start(meta_client, '/properties/new', 'ar')
    parsed = urlsplit(response.location)
    params = parse_qs(parsed.query)
    assert parsed.scheme == 'https' and parsed.netloc == 'www.facebook.com'
    assert parsed.path == f'/{GRAPH_VERSION}/dialog/oauth'
    assert params == {'client_id': [APP_ID], 'redirect_uri': [CALLBACK],
                      'response_type': ['code'], 'scope': ['public_profile'], 'state': [state]}
    assert APP_SECRET not in response.location
    with meta_client.session_transaction() as stored:
        assert stored['facebook_auth']['next'] == '/properties/new'
        assert stored['facebook_auth']['language'] == 'ar'
    page = meta_client.get('/auth?lang=ar')
    assert meta_client.post('/auth/facebook/callback', data={
        'csrf_token': csrf(page), 'state': state}).status_code == 405
    assert meta_client.get('/auth/facebook/development', query_string={'state': state}).status_code == 404


def test_production_oauth_starts_on_apex_after_www_redirect():
    app = create_app(production_config())
    browser = app.test_client()
    from_www = browser.get('/auth?lang=en&next=%2Fproperties%2Fnew',
                           base_url='https://www.manazilelsaudan.com')
    assert from_www.status_code == 308
    assert from_www.location == 'https://manazilelsaudan.com/auth?lang=en&next=%2Fproperties%2Fnew'
    page = browser.get('/auth?lang=en&next=%2Fproperties%2Fnew',
                       base_url='https://manazilelsaudan.com')
    assert page.status_code == 200
    response = browser.post('/auth/facebook', base_url='https://manazilelsaudan.com',
                            headers={'Referer': 'https://manazilelsaudan.com/auth?lang=en'}, data={
        'csrf_token': csrf(page), 'next': '/properties/new', '_language': 'en'})
    assert response.status_code == 303
    parameters = parse_qs(urlsplit(response.location).query)
    assert parameters['redirect_uri'] == [CALLBACK]
    denied = browser.get('/auth/facebook/callback', base_url='https://manazilelsaudan.com',
                         query_string={'state': parameters['state'][0], 'error': 'access_denied'})
    assert denied.status_code == 400
    assert 'Facebook sign-in was cancelled.' in denied.text


def test_code_exchange_first_signup_and_returning_account(meta_client, monkeypatch):
    calls = mock_meta(monkeypatch)
    _, state = start(meta_client, '/account', 'en')
    response = callback(meta_client, state)
    assert response.status_code == 303 and response.location == '/auth/complete-profile?lang=en'
    assert len(calls) == 2 and all(timeout == 5 for _, timeout in calls)
    token_request = calls[0][0]
    assert token_request.full_url == f'https://graph.facebook.com/{GRAPH_VERSION}/oauth/access_token'
    assert token_request.get_method() == 'POST'
    token_form = parse_qs(token_request.data.decode())
    assert token_form == {'client_id': [APP_ID], 'client_secret': [APP_SECRET],
                          'redirect_uri': [CALLBACK], 'code': ['test-only-code']}
    profile_request = calls[1][0]
    assert profile_request.full_url == (
        f'https://graph.facebook.com/{GRAPH_VERSION}/me?fields=id%2Cname%2Cpicture.type(square).width(256).height(256)')
    assert profile_request.get_header('Authorization') == 'Bearer test-only-access-token'
    user = db.session.query(User).one()
    identity = db.session.query(UserIdentity).one()
    assert identity.provider == 'facebook' and identity.provider_user_id == '987654321'
    assert identity.user_id == user.id and user.role == 'user'
    assert user.phone_number is None and not user.is_verified and user.is_active
    assert user.contact_name == 'Meta Member'
    with meta_client.session_transaction() as auth_session:
        assert auth_session['user_id'] == user.id and 'facebook_auth' not in auth_session
        assert 'access_token' not in str(auth_session)
    assert complete_facebook_profile(meta_client).location == '/account'
    account = meta_client.get('/account?lang=en')
    assert 'Facebook login' in account.text and 'Development simulation' not in account.text
    user.contact_name = 'Edited Name'
    user.contact_role = 'broker'
    db.session.commit()
    meta_client.post('/logout', data={'csrf_token': csrf(account)})
    _, state = start(meta_client)
    assert callback(meta_client, state).location == '/account'
    assert db.session.query(User).count() == 1 and db.session.query(UserIdentity).count() == 1
    assert db.session.query(User).one().contact_name == 'Edited Name'
    assert db.session.query(User).one().whatsapp == '+249912222222'


@pytest.mark.parametrize('destination,expected', [
    ('/properties/new', '/properties/new'), ('/properties/25?lang=en', '/properties/25?lang=en'),
    ('//evil.example', '/?lang=en'), ('https://evil.example', '/?lang=en'),
])
def test_safe_next_destination(meta_client, monkeypatch, destination, expected):
    mock_meta(monkeypatch)
    _, state = start(meta_client, destination)
    assert callback(meta_client, state).location == '/auth/complete-profile?lang=en'
    assert complete_facebook_profile(meta_client).location == expected


@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
def test_real_meta_ui_language_and_no_simulation_label(meta_client, monkeypatch, language, direction):
    for route in ('/auth', '/login', '/signup'):
        page = meta_client.get(route, query_string={'lang': language, 'next': '/account'})
        assert f'<html lang="{language}" dir="{direction}">' in page.text
        assert translate('Continue with Facebook', language) in page.text
        assert 'Development simulation only.' not in page.text
    mock_meta(monkeypatch)
    _, state = start(meta_client, language=language)
    assert callback(meta_client, state).status_code == 303
    complete_facebook_profile(meta_client, language=language)
    account = meta_client.get('/account?lang=' + language)
    assert translate('Facebook login', language) in account.text
    assert translate('Development simulation', language) not in account.text


@pytest.mark.parametrize('problem', ['denied', 'missing', 'wrong_state', 'expired', 'replay'])
def test_denial_missing_code_and_invalid_state_never_create_user(meta_client, monkeypatch, problem):
    calls = mock_meta(monkeypatch)
    _, state = start(meta_client)
    if problem == 'denied':
        response = meta_client.get('/auth/facebook/callback', query_string={'state': state, 'error': 'access_denied'})
    elif problem == 'missing':
        response = meta_client.get('/auth/facebook/callback', query_string={'state': state})
    elif problem == 'wrong_state':
        response = callback(meta_client, 'incorrect')
    elif problem == 'expired':
        with meta_client.session_transaction() as stored:
            pending = stored['facebook_auth']
            pending['issued_at'] = time.time() - 301
            stored['facebook_auth'] = pending
        response = callback(meta_client, state)
    else:
        response = callback(meta_client, state)
        assert response.status_code == 303
        response = callback(meta_client, state)
    assert response.status_code == 400
    assert len(calls) == (2 if problem == 'replay' else 0)
    assert db.session.query(User).count() == (1 if problem == 'replay' else 0)


@pytest.mark.parametrize('token,profile,failure', [
    ({'error': {'message': 'private'}}, None, None),
    ({'access_token': None}, None, None),
    ({'access_token': 'token', 'token_type': 5}, None, None),
    (None, {'id': 'not-a-meta-id', 'name': 'Person'}, None),
    (None, {'id': '42', 'name': ''}, None),
    (None, {'id': '42', 'name': 'Person', 'error': {'message': 'private'}}, None),
    (None, None, (1, TimeoutError('private timeout'))),
    (None, None, (2, TimeoutError('private timeout'))),
])
def test_provider_failures_are_generic_and_create_no_user(meta_client, monkeypatch, token, profile, failure):
    calls = mock_meta(monkeypatch, token=token, profile=profile, failure=failure)
    _, state = start(meta_client, language='ar')
    response = callback(meta_client, state)
    assert response.status_code == 502
    assert translate('Facebook sign-in could not be completed. Please try again.', 'ar') in response.text
    assert 'private' not in response.text
    assert db.session.query(User).count() == 0 and db.session.query(UserIdentity).count() == 0
    assert len(calls) >= 1


def test_suspended_identity_and_phone_account_remain_separate(meta_client, monkeypatch):
    phone_user = User(phone_number='+249912345678', is_verified=True,
                      contact_name='Meta Member', role='admin')
    db.session.add(phone_user)
    db.session.commit()
    mock_meta(monkeypatch)
    _, state = start(meta_client)
    assert callback(meta_client, state).status_code == 303
    complete_facebook_profile(meta_client)
    facebook_user = db.session.query(UserIdentity).one().user
    assert facebook_user.id != phone_user.id and facebook_user.role == 'user'
    meta_client.post('/logout', data={'csrf_token': csrf(meta_client.get('/account'))})
    facebook_user.is_active = False
    db.session.commit()
    _, state = start(meta_client)
    assert callback(meta_client, state).status_code == 403
    assert db.session.query(User).count() == 2
    with meta_client.session_transaction() as stored:
        assert 'user_id' not in stored
    assert login(meta_client, phone='0912345678').location == '/account'
    with meta_client.session_transaction() as stored:
        assert stored['user_id'] == phone_user.id


def test_development_provider_remains_guarded(client):
    assert isinstance(current_app.extensions['facebook_auth_provider'], DevelopmentFacebookAuthProvider)
    page = client.get('/auth?lang=en')
    assert 'Development simulation only.' in page.text
    assert client.get('/auth/facebook/callback').status_code == 405
