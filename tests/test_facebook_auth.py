import re
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import current_app
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app import create_app, db
from app.facebook_provider import DevelopmentFacebookAuthProvider, development_enabled
from app.languages import translate
from app.models import SavedProperty, User, UserIdentity
from test_auth import client, csrf, login
from test_properties import migrated_connection, values
from test_public_properties import add_property


def begin(client, destination='/account', language='en'):
    page = client.get('/login', query_string={'next': destination, 'lang': language})
    response = client.post('/auth/facebook', data={
        'csrf_token': csrf(page), 'next': destination, '_language': language})
    assert response.status_code == 303
    page = client.get(response.location)
    assert page.status_code == 200
    state = re.search(r'name="state" value="([^"]+)"', page.text).group(1)
    return page, state


def facebook_login(client, destination='/account', language='en', **extra):
    page, state = begin(client, destination, language)
    return client.post('/auth/facebook/callback', data={
        'csrf_token': csrf(page), 'state': state, **extra})


def complete_facebook_profile(client, phone='0912222222', language='en'):
    page = client.get('/auth/complete-profile?lang=' + language)
    assert page.status_code == 200
    return client.post('/auth/complete-profile', data={
        'csrf_token': csrf(page), '_language': language, 'whatsapp': phone})


@pytest.mark.parametrize('environment,testing,enabled,debug,expected', [
    ('production', False, False, False, False),
    ('production', False, True, True, False),
    ('development', False, False, True, False),
    ('development', False, True, False, True),
    ('production', True, False, False, False),
])
def test_provider_configuration_fails_closed(environment, testing, enabled, debug, expected):
    config = {'ENVIRONMENT': environment, 'TESTING': testing,
              'FACEBOOK_DEVELOPMENT_MODE': enabled, 'DEBUG': debug,
              'OTP_DEVELOPMENT_MODE': environment != 'production'}
    assert development_enabled(config) == expected
    if environment == 'production':
        config.update(SECRET_KEY='production-test-secret-that-is-long-enough',
                      DATA_DELETION_CONTACT_EMAIL='privacy@example.test',
                      SQLALCHEMY_DATABASE_URI='postgresql://account:example@ep-example.aws.neon.tech/neondb?sslmode=require',
                      PHOTO_STORAGE_BACKEND='azure_blob', AZURE_BLOB_CONTAINER_CLIENT=object())
        if enabled:
            with pytest.raises(ValueError, match='Development authentication'):
                create_app(config)
            return
    app = create_app(config)
    assert bool(app.extensions.get('facebook_auth_provider')) == expected
    routes = {rule.rule for rule in app.url_map.iter_rules()}
    assert ('/auth/facebook' in routes) == expected
    if not expected:
        browser = app.test_client()
        base_url = 'https://www.manazilelsaudan.com' if environment == 'production' else 'http://localhost'
        page = browser.get('/auth?lang=en', base_url=base_url)
        assert 'Continue with Facebook' not in page.text
        token = csrf(browser.get('/login', base_url=base_url))
        for path in ('/auth/facebook', '/auth/facebook/development', '/auth/facebook/callback'):
            assert browser.get(path, base_url=base_url).status_code == 404
            assert browser.post(path, base_url=base_url, data={'csrf_token': token}).status_code == 404
        with app.test_request_context():
            with pytest.raises(RuntimeError, match='disabled'):
                DevelopmentFacebookAuthProvider().authenticate({})


@pytest.mark.parametrize('destination', ['/properties/new', '/account', '//evil.example', 'https://evil.example'])
def test_first_login_session_and_safe_destination(client, destination):
    response = facebook_login(client, destination, provider_user_id='browser-forgery', display_name='Untrusted')
    assert response.status_code == 303
    assert response.location == '/auth/complete-profile?lang=en'
    expected = destination if destination.startswith('/') and not destination.startswith('//') else '/'
    with client.session_transaction() as auth_session:
        assert auth_session['profile_next'] == expected
    user = db.session.query(User).one()
    identity = db.session.query(UserIdentity).one()
    assert identity.provider == 'facebook'
    assert identity.provider_user_id == 'development-facebook-user'
    assert identity.user_id == user.id
    assert identity.display_name == 'Development Facebook User'
    assert user.phone_number is None and not user.is_verified
    assert user.whatsapp is None and user.contact_role is None
    assert user.last_login_at and user.is_active and not user.contact_complete
    with client.session_transaction() as auth_session:
        assert auth_session['user_id'] == user.id
        assert 'facebook_auth' not in auth_session
    assert client.get('/account?lang=en').location == '/auth/complete-profile?lang=en'
    assert client.get('/properties/new').location == '/auth/complete-profile'
    assert complete_facebook_profile(client).location == ('/?lang=en' if expected == '/' else expected)
    assert user.phone_number == user.whatsapp == '+249912222222' and not user.is_verified


def test_returning_identity_same_user_and_profile_logout(client):
    facebook_login(client)
    complete_facebook_profile(client)
    user = db.session.query(User).one()
    original_id = user.id
    user.contact_name = 'Saved Name'
    user.contact_role = 'broker'
    db.session.commit()
    page = client.get('/account')
    assert client.post('/logout', data={'csrf_token': csrf(page)}).status_code == 303
    assert client.get('/account').status_code == 302
    current_app.config['FACEBOOK_DEVELOPMENT_DISPLAY_NAME'] = 'Changed Provider Name'
    assert facebook_login(client).status_code == 303
    assert db.session.query(User).count() == 1
    assert db.session.query(UserIdentity).count() == 1
    user = db.session.query(User).one()
    assert user.id == original_id and user.contact_name == 'Saved Name'
    assert user.whatsapp == '+249912222222' and user.contact_role == 'broker'


def test_facebook_profile_contact_allows_posting_after_completion(client):
    facebook_login(client)
    complete_facebook_profile(client)
    page = client.get('/account?lang=en')
    response = client.post('/account', data={'csrf_token': csrf(page), '_language': 'en',
        'contact_name': 'Facebook Member', 'whatsapp': '0912222222', 'contact_role': 'owner'})
    assert response.status_code == 200
    user = db.session.query(User).one()
    assert user.contact_complete and user.phone_number == '+249912222222' and not user.is_verified
    listing = client.get('/properties/new?lang=en')
    assert listing.status_code == 200
    assert 'name="whatsapp" type="tel" value="+249912222222"' in listing.text
    assert 'name="phone"' not in listing.text


def test_unique_identity_database_and_names_not_identifiers(client):
    facebook_login(client)
    identity = db.session.query(UserIdentity).one()
    assert inspect(db.session.get_bind()).get_pk_constraint('user_identities')['constrained_columns'] == ['provider', 'provider_user_id']
    with pytest.raises(IntegrityError):
        with db.session.begin_nested():
            db.session.execute(UserIdentity.__table__.insert().values(
                provider='facebook', provider_user_id=identity.provider_user_id,
                user_id=identity.user_id, display_name='Same identity'))
    current_app.config['FACEBOOK_DEVELOPMENT_USER_ID'] = 'development-second-user'
    facebook_login(client)
    assert db.session.query(User).count() == 2  # Same name, different stable IDs.
    assert db.session.query(UserIdentity).count() == 2


def test_existing_phone_login_coexists_without_automatic_linking(client):
    phone_user = User(phone_number='+249912345678', is_verified=True,
                      contact_name='Development Facebook User', whatsapp='+249911111111', contact_role='owner')
    db.session.add(phone_user)
    db.session.commit()
    facebook_login(client)
    complete_facebook_profile(client)
    facebook_user = db.session.query(UserIdentity).one().user
    assert facebook_user.id != phone_user.id
    page = client.get('/account')
    client.post('/logout', data={'csrf_token': csrf(page)})
    assert login(client, destination='/properties/new').location == '/properties/new'
    with client.session_transaction() as auth_session:
        assert auth_session['user_id'] == phone_user.id
    assert client.get('/properties/new').status_code == 200
    assert phone_user.contact_name == 'Development Facebook User' and phone_user.is_verified
    assert db.session.query(User).count() == 2


@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
def test_auth_cards_and_simulation_languages(client, language, direction):
    current_app.config['PUBLIC_FACEBOOK_LOGIN_ENABLED'] = True
    for route in ('/auth', '/login', '/signup'):
        page = client.get(route, query_string={'next': '/properties/new', 'lang': language})
        assert f'<html lang="{language}" dir="{direction}">' in page.text
        assert translate('Continue with Facebook', language) in page.text
        assert translate('Development simulation only. No connection to Facebook.', language) in page.text
        assert 'class="form-page auth-page"' in page.text
        assert 'name="next" value="/properties/new"' in page.text
    page, state = begin(client, '/properties/new', language)
    assert f'<html lang="{language}" dir="{direction}">' in page.text
    assert translate('Development Facebook Login', language) in page.text
    assert translate('Cancel', language) in page.text
    assert 'no-store' in page.headers['Cache-Control']


def test_property_return_no_auto_save_and_account_scoped_lists(client, values):
    other = User(phone_number='+249911111111', is_verified=True)
    db.session.add(other)
    db.session.flush()
    theirs = add_property(values, owner_id=other.id, publication_status='published',
                          title_en='Other account property', title_ar='Other account property')
    db.session.add(SavedProperty(user_id=other.id, property_id=theirs.id))
    db.session.commit()
    destination = f'/properties/{theirs.id}?lang=en'
    assert client.get('/properties').status_code == 200
    page = client.get(destination)
    assert page.status_code == 200
    response = client.post(f'/properties/{theirs.id}/save', data={'csrf_token': csrf(client.get('/login')), '_language': 'en'})
    assert parse_qs(urlsplit(response.location).query)['next'] == [destination]
    assert facebook_login(client, destination).location == '/auth/complete-profile?lang=en'
    assert complete_facebook_profile(client).location == destination
    assert client.get(destination).status_code == 200
    user = db.session.query(UserIdentity).one().user
    assert db.session.get(SavedProperty, (user.id, theirs.id)) is None
    for route in ('/my-properties', '/saved-properties'):
        page = client.get(route + '?lang=en&user_id=' + str(other.id))
        assert page.status_code == 200
        content = page.text.split('<main', 1)[1]
        assert 'Other account property' not in content
    mine = add_property(values, owner_id=user.id, publication_status='published',
                        title_en='Facebook account property', title_ar='Facebook account property')
    assert 'Facebook account property' in client.get('/my-properties?lang=en').text
    page = client.get(destination)
    assert client.post(f'/properties/{theirs.id}/save', data={'csrf_token': csrf(page)}).status_code == 303
    assert db.session.get(SavedProperty, (user.id, theirs.id))
    assert db.session.get(SavedProperty, (other.id, theirs.id))
    assert client.get(f'/properties/{theirs.id}/edit').status_code == 404
    current_app.config['FACEBOOK_DEVELOPMENT_USER_ID'] = 'development-another-account'
    facebook_login(client)
    complete_facebook_profile(client, '0913333333')
    for route in ('/my-properties', '/saved-properties'):
        content = client.get(route + '?lang=en').text.split('<main', 1)[1]
        assert 'Facebook account property' not in content and 'Other account property' not in content


def test_state_session_bound_expired_single_use_and_csrf(client):
    assert client.get('/auth/facebook').status_code == 405
    assert client.get('/auth/facebook/callback').status_code == 405
    assert client.post('/auth/facebook').status_code == 400
    page, state = begin(client)
    assert client.post('/auth/facebook/callback', data={'state': state}).status_code == 400
    assert current_app.test_client().get('/auth/facebook/development?state=' + state).status_code == 400
    assert client.post('/auth/facebook/callback', data={'csrf_token': csrf(page), 'state': 'خطأ'}).status_code == 400
    assert db.session.query(User).count() == 0
    page, state = begin(client)
    with client.session_transaction() as auth_session:
        pending = auth_session['facebook_auth']
        pending['issued_at'] = time.time() - 301
        auth_session['facebook_auth'] = pending
    assert client.get('/auth/facebook/development?state=' + state).status_code == 400
    assert client.post('/auth/facebook/callback', data={'csrf_token': csrf(page), 'state': state}).status_code == 400
    page, state = begin(client)
    assert client.post('/auth/facebook/callback', data={'csrf_token': csrf(page), 'state': state}).status_code == 303
    assert client.post('/auth/facebook/callback', data={'csrf_token': csrf(page), 'state': state}).status_code == 400
    assert db.session.query(User).count() == 1


def test_disabled_runtime_and_inactive_account_fail_closed(client):
    facebook_login(client)
    user = db.session.query(User).one()
    user.is_active = False
    db.session.commit()
    assert client.get('/account').status_code == 302
    assert facebook_login(client).status_code == 403
    assert db.session.query(User).count() == 1
    with client.session_transaction() as auth_session:
        assert 'user_id' not in auth_session
    current_app.config.update(TESTING=False, ENVIRONMENT='production')
    assert client.get('/auth/facebook/development').status_code == 404
