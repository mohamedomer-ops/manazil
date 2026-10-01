import re
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import scoped_session, sessionmaker

from app import db
from app.models import OTPChallenge, Property, User, utc_now
from app.otp import request_code
from app.phone import normalize_phone
from test_properties import migrated_connection


@pytest.fixture
def client(migrated_connection, monkeypatch):
    sessions = scoped_session(sessionmaker(bind=migrated_connection, join_transaction_mode='create_savepoint'))
    monkeypatch.setattr(db, 'session', sessions)
    try:
        yield __import__('flask').current_app.test_client()
    finally:
        sessions.remove()


def csrf(page):
    return re.search(r'name="csrf_token" value="([^"]+)"', page.get_data(as_text=True)).group(1)


def login(client, phone='0912345678', destination='/account'):
    page = client.get('/login?lang=en&next=' + destination)
    response = client.post('/auth/request-otp', data={'csrf_token': csrf(page), 'phone_number': phone,
                                                        'next': destination, '_language': 'en'})
    assert response.status_code == 303
    code = __import__('flask').current_app.extensions['development_otps'][normalize_phone(phone)]
    page = client.get('/auth/verify?lang=en')
    return client.post('/auth/verify', data={'csrf_token': csrf(page), 'code': code, '_language': 'en'})


def signup(client, phone='0912345678', destination='/account', role='owner'):
    page = client.get('/signup?lang=en&next=' + destination)
    response = client.post('/signup', data={'csrf_token': csrf(page), 'phone_number': phone,
        'contact_name': 'Mohamed Ahmed', 'whatsapp': '0911111111', 'contact_role': role,
        'next': destination, '_language': 'en'})
    assert response.status_code == 303
    assert db.session.query(User).count() == 0
    code = __import__('flask').current_app.extensions['development_otps'][normalize_phone(phone)]
    page = client.get('/auth/verify?lang=en')
    return client.post('/auth/verify', data={'csrf_token': csrf(page), 'code': code, '_language': 'en'})


def complete_account(client, role='owner'):
    page = client.get('/account?lang=en')
    return client.post('/account', data={'csrf_token': csrf(page), '_language': 'en',
        'contact_name': 'Mohamed Ahmed', 'whatsapp': '0911111111', 'contact_role': role})


def test_phone_normalization_and_login(client):
    assert normalize_phone('0912345678') == '+249912345678'
    assert normalize_phone('+249912345678') == '+249912345678'
    assert normalize_phone('00249912345678') == '+249912345678'
    assert signup(client).status_code == 303
    user = db.session.scalar(select(User).where(User.phone_number == '+249912345678'))
    assert user.is_verified and user.is_active and user.last_login_at
    assert client.get('/account').status_code == 200
    logout_response = client.post('/logout', data={'csrf_token': csrf(client.get('/account'))})
    assert logout_response.status_code == 303, logout_response.get_data(as_text=True)
    assert client.get('/account').status_code == 302
    for challenge in db.session.scalars(select(OTPChallenge)).all():
        challenge.created_at = utc_now() - timedelta(seconds=31)
    db.session.commit()
    assert login(client, '+249912345678').status_code == 303
    assert db.session.query(User).count() == 1


def test_protected_posting_and_public_access(client):
    assert client.get('/').status_code == 200
    assert client.get('/properties').status_code == 200
    response = client.get('/admin/properties/new')
    assert response.status_code == 302 and '/auth?' in response.location
    assert signup(client, destination='/admin/properties/new').location == '/admin/properties/new'
    assert client.get('/admin/properties/new').status_code == 200


def test_otp_security_attempts_expiry_and_reuse(client):
    page = client.get('/login')
    token = csrf(page)
    client.post('/auth/request-otp', data={'csrf_token': token, 'phone_number': '0912345678'})
    challenge = db.session.scalar(select(OTPChallenge))
    code = __import__('flask').current_app.extensions['development_otps']['+249912345678']
    assert len(code) == 6 and code.isdigit() and code not in challenge.otp_hash
    assert timedelta(minutes=4, seconds=50) < challenge.expires_at - challenge.created_at <= timedelta(minutes=5, seconds=10)
    verify_page = client.get('/auth/verify')
    for _ in range(5):
        assert client.post('/auth/verify', data={'csrf_token': csrf(verify_page), 'code': '999999' if code != '999999' else '888888'}).status_code == 422
    assert client.post('/auth/verify', data={'csrf_token': csrf(verify_page), 'code': code}).status_code == 422


def test_expired_and_inactive(client):
    page = client.get('/login')
    client.post('/auth/request-otp', data={'csrf_token': csrf(page), 'phone_number': '0912345678'})
    challenge = db.session.scalar(select(OTPChallenge))
    code = __import__('flask').current_app.extensions['development_otps']['+249912345678']
    challenge.expires_at = utc_now() - timedelta(seconds=1)
    db.session.commit()
    assert client.post('/auth/verify', data={'csrf_token': csrf(client.get('/auth/verify')), 'code': code}).status_code == 422
    user = User(phone_number='+249912345678', is_verified=True, is_active=False)
    db.session.add(user)
    db.session.commit()
    challenge.expires_at = utc_now() + timedelta(minutes=5)
    db.session.commit()
    assert client.post('/auth/verify', data={'csrf_token': csrf(client.get('/auth/verify')), 'code': code}).status_code == 403


def test_resend_rate_limit_and_invalidation(client):
    page = client.get('/login')
    token = csrf(page)
    client.post('/auth/request-otp', data={'csrf_token': token, 'phone_number': '0912345678'})
    first = db.session.scalar(select(OTPChallenge))
    first_code = __import__('flask').current_app.extensions['development_otps']['+249912345678']
    assert not request_code('+249912345678')
    first.created_at = utc_now() - timedelta(seconds=31)
    db.session.commit()
    assert request_code('+249912345678')
    assert first.consumed_at is not None
    second_code = __import__('flask').current_app.extensions['development_otps']['+249912345678']
    assert first_code != second_code or first.id != db.session.scalar(select(OTPChallenge).order_by(OTPChallenge.id.desc())).id
    assert db.session.query(OTPChallenge).count() == 2
    assert not request_code('+249912345678')


def test_language_and_no_code_in_html(client):
    assert '<html lang="ar" dir="rtl">' in client.get('/login').get_data(as_text=True)
    assert '<html lang="en" dir="ltr">' in client.get('/login?lang=en').get_data(as_text=True)
    page = client.get('/login')
    client.post('/auth/request-otp', data={'csrf_token': csrf(page), 'phone_number': '0912345678'})
    code = __import__('flask').current_app.extensions['development_otps']['+249912345678']
    assert code not in client.get('/auth/verify').get_data(as_text=True)


@pytest.mark.parametrize('role', ['owner', 'broker'])
def test_new_account_setup_and_listing_defaults(client, role):
    saved = signup(client, destination='/properties/new?lang=en', role=role)
    assert saved.status_code == 303 and saved.location == '/properties/new?lang=en'
    with client.session_transaction() as auth_session:
        assert 'user_id' in auth_session and 'pending_setup_user_id' not in auth_session
    user = db.session.scalar(select(User).where(User.phone_number == '+249912345678'))
    assert (user.contact_name, user.whatsapp, user.contact_role) == ('Mohamed Ahmed', '+249911111111', role)
    listing = client.get(saved.location).get_data(as_text=True)
    assert 'name="contact_name" type="text" value="Mohamed Ahmed"' in listing
    assert 'name="phone" type="tel" value="+249912345678"' in listing
    assert 'name="whatsapp" type="tel" value="+249911111111"' in listing
    assert f'name="agent" value="{"yes" if role == "broker" else "no"}" checked' in listing
    assert '<html lang="ar" dir="rtl">' in client.get('/account').get_data(as_text=True)


def test_existing_account_edit_and_verified_phone(client):
    signup(client)
    user = db.session.scalar(select(User).where(User.phone_number == '+249912345678'))
    client.post('/logout', data={'csrf_token': csrf(client.get('/account'))})
    for challenge in db.session.scalars(select(OTPChallenge)).all():
        challenge.created_at = utc_now() - timedelta(seconds=31)
    db.session.commit()
    assert login(client, destination='/admin/properties/new').location == '/admin/properties/new'
    page = client.get('/account?lang=en')
    changed = client.post('/account', data={'csrf_token': csrf(page), '_language': 'en',
        'contact_name': 'New Name', 'whatsapp': '0912222222', 'contact_role': 'broker',
        'phone_number': '+249999999999', 'is_verified': 'false'})
    assert changed.status_code == 200
    db.session.refresh(user)
    assert user.phone_number == '+249912345678' and user.is_verified
    assert (user.contact_name, user.whatsapp, user.contact_role) == ('New Name', '+249912222222', 'broker')
    assert 'Account information updated successfully' in changed.get_data(as_text=True)
    assert client.post('/account', data={'csrf_token': csrf(changed), 'contact_name': 'A',
        'whatsapp': 'bad', 'contact_role': 'owner'}).status_code == 422


def test_legacy_incomplete_account_must_complete_before_posting(client):
    user = User(phone_number='+249912345678', is_verified=True, is_active=True)
    db.session.add(user)
    db.session.commit()
    assert login(client, destination='/admin/properties/new').location == '/admin/properties/new'
    response = client.get('/admin/properties/new')
    assert response.status_code == 302 and '/account' in response.location
    assert client.post('/admin/properties', data={'csrf_token': csrf(client.get('/account'))}).status_code == 303
    assert complete_account(client).location == '/admin/properties/new'
    assert client.get('/admin/properties/new').status_code == 200


def test_choices_and_next_preserved(client):
    from urllib.parse import urlsplit, parse_qs
    response = client.get('/properties/new')
    assert urlsplit(response.location).path == '/auth'
    assert parse_qs(urlsplit(response.location).query)['next'] == ['/properties/new']
    page = client.get(response.location).get_data(as_text=True)
    assert '/login?next=/properties/new' in page and '/signup?next=/properties/new' in page
    for route in ('/login', '/signup'):
        page = client.get(route + '?next=/properties/new&lang=en').get_data(as_text=True)
        assert 'name="next" value="/properties/new"' in page
        assert 'next=/properties/new' in page and 'lang=ar' in page and 'lang=en' in page


def test_duplicate_and_returning_profile(client):
    signup(client, destination='/properties/new')
    user = db.session.scalar(select(User))
    identity = user.id
    profile = (user.contact_name, user.whatsapp, user.contact_role)
    client.post('/logout', data={'csrf_token': csrf(client.get('/account'))})
    page = client.get('/signup?next=/properties/new')
    response = client.post('/signup', data={'csrf_token': csrf(page), 'next': '/properties/new',
        'phone_number': '00249912345678', 'contact_name': 'Overwrite',
        'whatsapp': '0912222222', 'contact_role': 'broker', '_language': 'en'})
    assert response.status_code == 409
    assert 'already exists' in response.get_data(as_text=True)
    assert 'name="next" value="/properties/new"' in response.get_data(as_text=True)
    for challenge in db.session.scalars(select(OTPChallenge)):
        challenge.created_at = utc_now() - timedelta(seconds=31)
    db.session.commit()
    assert login(client, '+249912345678', '/properties/new').location == '/properties/new'
    db.session.refresh(user)
    assert db.session.query(User).count() == 1 and user.id == identity
    assert (user.contact_name, user.whatsapp, user.contact_role) == profile
    with client.session_transaction() as auth_session:
        assert auth_session['user_id'] == identity
    code = __import__('flask').current_app.extensions['development_otps'][user.phone_number]
    assert client.post('/auth/verify', data={'csrf_token': csrf(client.get('/account')), 'code': code}).status_code == 422


def test_login_unknown_does_not_create_user(client):
    response = login(client, destination='/properties/new')
    assert response.status_code == 422
    assert db.session.query(User).count() == 0
    assert '/signup?next=/properties/new' in response.get_data(as_text=True)


@pytest.mark.parametrize('field,value', [('contact_name', ''), ('phone_number', 'bad'), ('whatsapp', 'bad'), ('contact_role', 'staff')])
def test_signup_validation_before_challenge(client, field, value):
    data = {'csrf_token': csrf(client.get('/signup')), 'phone_number': '0912345678',
            'contact_name': 'Name', 'whatsapp': '0911111111', 'contact_role': 'owner', 'next': '/properties/new'}
    data[field] = value
    assert client.post('/signup', data=data).status_code == 422
    assert db.session.query(User).count() == db.session.query(OTPChallenge).count() == 0


def test_signup_otp_security_and_resend(client):
    page = client.get('/signup?next=/properties/new&lang=en')
    response = client.post('/signup', data={'csrf_token': csrf(page), 'next': '/properties/new',
        'phone_number': '0912345678', 'contact_name': 'Name',
        'whatsapp': '0911111111', 'contact_role': 'broker', '_language': 'en'})
    assert response.status_code == 303
    assert db.session.query(User).count() == 0
    with client.session_transaction() as auth_session:
        assert 'user_id' not in auth_session
    page = client.get('/auth/verify?lang=en')
    code = __import__('flask').current_app.extensions['development_otps']['+249912345678']
    assert code not in page.get_data(as_text=True)
    assert '/signup?next=/properties/new' in page.get_data(as_text=True)
    assert client.post('/auth/verify', data={'csrf_token': csrf(page), 'code': 'bad'}).status_code == 422
    challenge = db.session.scalar(select(OTPChallenge))
    challenge.expires_at = utc_now() - timedelta(seconds=1)
    challenge.created_at = utc_now() - timedelta(seconds=31)
    db.session.commit()
    assert client.post('/auth/verify', data={'csrf_token': csrf(page), 'code': code}).status_code == 422
    assert db.session.query(User).count() == 0
    assert client.post('/auth/resend', data={'csrf_token': csrf(page), '_language': 'en'}).status_code == 303
    assert db.session.query(OTPChallenge).count() == 2
    assert client.post('/auth/resend', data={'csrf_token': csrf(page)}).status_code == 303
    assert db.session.query(OTPChallenge).count() == 2
    with client.session_transaction() as auth_session:
        assert auth_session['auth_next'] == '/properties/new'
        assert auth_session['pending_signup']['contact_name'] == 'Name'
    code = __import__('flask').current_app.extensions['development_otps']['+249912345678']
    assert client.post('/auth/verify', data={'csrf_token': csrf(page), 'code': code}).location == '/properties/new'
    user = db.session.scalar(select(User))
    assert user.contact_name == 'Name' and user.contact_role == 'broker'
    assert client.post('/auth/verify', data={'csrf_token': csrf(page), 'code': code}).status_code == 422
    assert db.session.query(User).count() == 1


def test_signup_existing_phone_at_verification_does_not_overwrite(client):
    page = client.get('/signup')
    client.post('/signup', data={'csrf_token': csrf(page), 'next': '/properties/new',
        'phone_number': '0912345678', 'contact_name': 'Overwrite',
        'whatsapp': '0911111111', 'contact_role': 'broker'})
    existing = User(phone_number='+249912345678', contact_name='Original',
                    whatsapp='+249912222222', contact_role='owner', is_verified=True)
    db.session.add(existing)
    db.session.commit()
    code = __import__('flask').current_app.extensions['development_otps'][existing.phone_number]
    page = client.get('/auth/verify')
    assert client.post('/auth/verify', data={'csrf_token': csrf(page), 'code': code}).status_code == 409
    assert db.session.query(User).count() == 1
    db.session.refresh(existing)
    assert existing.contact_name == 'Original' and existing.contact_role == 'owner'
    with client.session_transaction() as auth_session:
        assert 'user_id' not in auth_session


def test_signup_csrf_and_safe_destination(client):
    assert client.post('/signup', data={'phone_number': '0912345678'}).status_code == 400
    page = client.get('/signup?next=https://example.com').get_data(as_text=True)
    assert 'name="next" value="/account"' in page


@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
def test_navigation_auth_entry_for_logged_out_users(client, language, direction):
    from app.languages import translate
    from html import unescape
    page = client.get('/?lang=' + language).get_data(as_text=True)
    assert f'<html lang="{language}" dir="{direction}">' in page
    navigation = re.search(r'<nav .*?</nav>', page, re.S).group(0)
    links = [(unescape(href), text) for href, text in re.findall(r'<a href="([^"]+)"[^>]*>([^<]+)</a>', navigation)]
    assert links == [(path + ('?lang=en' if language == 'en' else ''), translate(label, language))
                     for path, label in [('/', 'Home'), ('/properties', 'Properties'),
                                         ('/properties/new', 'Post Property'), ('/auth', 'Login / Sign Up')]]
    entry = client.get(links[-1][0]).get_data(as_text=True)
    assert translate('Already have an account?', language) in entry
    assert translate('New to Manazil?', language) in entry
    assert '/account' not in navigation and '/logout' not in navigation and '/my-properties' not in navigation and '/saved-properties' not in navigation


@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
def test_navigation_authenticated_users_unchanged(client, language, direction):
    from app.languages import translate
    user = User(phone_number='+249912345678', is_verified=True, is_active=True)
    db.session.add(user)
    db.session.commit()
    with client.session_transaction() as auth_session:
        auth_session['user_id'] = user.id
    page = client.get('/?lang=' + language).get_data(as_text=True)
    assert f'<html lang="{language}" dir="{direction}">' in page
    navigation = re.search(r'<nav .*?</nav>', page, re.S).group(0)
    suffix = '?lang=en' if language == 'en' else ''
    assert f'href="/account{suffix}">{translate("My Account", language)}</a>' in navigation
    assert f'href="/my-properties{suffix}"' in navigation
    assert translate('My Properties', language) in navigation
    assert f'href="/saved-properties{suffix}"' in navigation
    assert translate('Saved Properties', language) in navigation
    assert 'method="post" action="/logout"' in navigation
    assert translate('Logout', language) in navigation
    assert 'name="csrf_token"' in navigation
    assert translate('Login / Sign Up', language) not in navigation
    assert 'href="/auth' not in navigation


@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
def test_compact_auth_ui_and_actions(client, language, direction):
    from app.languages import translate
    for route in ('/auth', '/login', '/signup'):
        page = client.get(route + '?next=/properties/new&lang=' + language).get_data(as_text=True)
        assert f'<html lang="{language}" dir="{direction}">' in page
        content = page.split('<main', 1)[1].split('</main>', 1)[0]
        assert 'auth-page' in content
        assert translate('Create Account', language) in content
        assert 'next=/properties/new' in content
    entry = client.get('/auth?lang=' + language).get_data(as_text=True)
    assert 'button-secondary' in entry
    signup_page = client.get('/signup?lang=' + language).get_data(as_text=True)
    assert f'<button type="submit">{translate("Create Account", language)}</button>' in signup_page
    assert translate('Account Type', language) in signup_page
    assert f'<button type="submit">{translate("Continue", language)}</button>' in client.get('/login?lang=' + language).get_data(as_text=True)
    with client.session_transaction() as auth_session:
        auth_session['pending_phone'] = '+249912345678'
        auth_session['auth_next'] = '/properties/new'
    otp_page = client.get('/auth/verify?lang=' + language).get_data(as_text=True)
    assert 'auth-page' in otp_page and 'auth-resend' in otp_page
    assert 'auth-change-phone' in otp_page
    assert '/login?next=/properties/new' in otp_page


@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
def test_post_property_homepage_cta(client, language, direction):
    from app.languages import translate
    page = client.get('/?lang=' + language).get_data(as_text=True)
    assert f'<html lang="{language}" dir="{direction}">' in page
    suffix = '?lang=en' if language == 'en' else ''
    assert f'<a class="primary-link" href="/properties/new{suffix}">{translate("Post Property", language)}</a>' in page
    assert 'List Your Property' not in page


@pytest.mark.parametrize('language', ['ar', 'en'])
def test_mobile_menu_trigger_and_navigation_relationship(client, language):
    from app.languages import translate
    page = client.get('/?lang=' + language).get_data(as_text=True)
    assert 'id="site-navigation"' in page
    button = re.search(r'<button class="mobile-menu-toggle".*?</button>', page, re.S).group(0)
    assert 'type="button"' in button
    assert 'aria-expanded="false"' in button
    assert 'aria-controls="site-navigation"' in button
    assert 'aria-hidden="true"' in button
    assert translate('Menu', language) in button
    assert '/static/js/navigation.js' in page
    assert '/static/js/navigation.js' in client.get('/login?lang=' + language).get_data(as_text=True)
