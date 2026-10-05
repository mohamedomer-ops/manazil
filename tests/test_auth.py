import re
from datetime import timedelta
from pathlib import Path

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
        'contact_name': 'Mohamed Ahmed', 'password': 'password-for-tests',
        'confirm_password': 'password-for-tests',
        'next': destination, '_language': 'en'})
    assert response.status_code == 303
    return response


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
    assert not user.is_verified and user.is_active and user.last_login_at
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
    assert signup(client, destination='/admin/properties/new').location == '/?lang=en'
    assert client.get('/admin/properties/new').location == '/account'
    complete_account(client)
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
    assert saved.status_code == 303 and saved.location == '/?lang=en'
    with client.session_transaction() as auth_session:
        assert 'user_id' in auth_session and 'pending_setup_user_id' not in auth_session
    user = db.session.scalar(select(User).where(User.phone_number == '+249912345678'))
    assert (user.contact_name, user.whatsapp, user.contact_role) == ('Mohamed Ahmed', '+249912345678', None)
    assert client.get('/properties/new?lang=en').location.startswith('/account')
    page = client.get('/account?lang=en')
    client.post('/account', data={'csrf_token': csrf(page), '_language': 'en',
        'contact_name': 'Mohamed Ahmed', 'whatsapp': '0912345678', 'contact_role': role})
    listing = client.get('/properties/new?lang=en').get_data(as_text=True)
    assert 'name="contact_name" type="text" value="Mohamed Ahmed"' in listing
    assert 'name="phone"' not in listing
    assert 'name="whatsapp" type="tel" value="+249912345678"' in listing
    assert f'name="agent" value="{"yes" if role == "broker" else "no"}" checked' in listing
    assert '<html lang="ar" dir="rtl">' in client.get('/account').get_data(as_text=True)


def test_signup_asks_for_auth_phone_once_and_prefills_contact(client):
    form = client.get('/signup?lang=en').text
    assert form.count('name="phone_number"') == 1
    assert 'name="whatsapp"' not in form
    signup(client)
    user = db.session.scalar(select(User))
    assert user.phone_number == user.whatsapp == '+249912345678'


def test_existing_account_edit_and_verified_phone(client):
    signup(client)
    user = db.session.scalar(select(User).where(User.phone_number == '+249912345678'))
    client.post('/logout', data={'csrf_token': csrf(client.get('/account'))})
    for challenge in db.session.scalars(select(OTPChallenge)).all():
        challenge.created_at = utc_now() - timedelta(seconds=31)
    db.session.commit()
    assert login(client, destination='/admin/properties/new').location == '/?lang=en'
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
    assert login(client, destination='/admin/properties/new').location == '/?lang=en'
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
    entry_response = client.get(response.location, follow_redirects=False)
    assert urlsplit(entry_response.location).path == '/login'
    assert parse_qs(urlsplit(entry_response.location).query)['next'] == ['/properties/new']
    page = client.get(entry_response.location).get_data(as_text=True)
    assert 'class="signin-main"' in page
    assert '/signup?next=/properties/new' in page
    for route in ('/login', '/signup'):
        page = client.get(route + '?next=/properties/new&lang=en').get_data(as_text=True)
        assert 'name="next" value="/properties/new"' in page
        assert 'next=/properties/new' in page and 'lang=ar' in page and 'lang=en' in page


@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
def test_auth_entry_redirects_into_signin_and_preserves_language_and_safe_next(client, language, direction):
    from urllib.parse import parse_qs, urlsplit

    response = client.get('/auth?next=/properties/new&lang=' + language, follow_redirects=False)
    target = urlsplit(response.location)
    query = parse_qs(target.query)
    assert response.status_code == 302
    assert target.path == '/login'
    assert query['next'] == ['/properties/new']
    assert query['lang'] == [language]
    signin = client.get(response.location).get_data(as_text=True)
    assert f'<html lang="{language}" dir="{direction}">' in signin
    assert 'class="signin-main"' in signin
    assert 'href="/signup?next=/properties/new' in signin

    unsafe = client.get('/auth?next=https://evil.example&lang=' + language, follow_redirects=False)
    safe_query = parse_qs(urlsplit(unsafe.location).query)
    assert safe_query['next'] == ['/account']


def test_duplicate_and_returning_profile(client):
    signup(client, destination='/properties/new')
    user = db.session.scalar(select(User))
    identity = user.id
    profile = (user.contact_name, user.whatsapp, user.contact_role)
    client.post('/logout', data={'csrf_token': csrf(client.get('/account'))})
    page = client.get('/signup?next=/properties/new')
    response = client.post('/signup', data={'csrf_token': csrf(page), 'next': '/properties/new',
        'phone_number': '00249912345678', 'contact_name': 'Overwrite',
        'password': 'another-password', 'confirm_password': 'another-password', '_language': 'en'})
    assert response.status_code == 409
    assert 'already associated' in response.get_data(as_text=True)
    assert 'name="next" value="/properties/new"' in response.get_data(as_text=True)
    for challenge in db.session.scalars(select(OTPChallenge)):
        challenge.created_at = utc_now() - timedelta(seconds=31)
    db.session.commit()
    assert login(client, '+249912345678', '/properties/new').location == '/?lang=en'
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


@pytest.mark.parametrize('field,value', [('contact_name', ''), ('phone_number', 'bad'),
                                         ('password', ''), ('confirm_password', 'wrong')])
def test_signup_validation_before_account_creation(client, field, value):
    data = {'csrf_token': csrf(client.get('/signup')), 'phone_number': '0912345678',
            'contact_name': 'Name', 'password': 'password-for-tests',
            'confirm_password': 'password-for-tests', 'next': '/properties/new'}
    data[field] = value
    assert client.post('/signup', data=data).status_code == 422
    assert db.session.query(User).count() == db.session.query(OTPChallenge).count() == 0


def test_manual_signup_creates_no_otp_challenge(client):
    page = client.get('/signup?next=/properties/new&lang=en')
    response = client.post('/signup', data={'csrf_token': csrf(page), 'next': '/properties/new',
        'phone_number': '0912345678', 'contact_name': 'Name', 'password': 'password-for-tests',
        'confirm_password': 'password-for-tests', '_language': 'en'})
    assert response.status_code == 303 and response.location == '/?lang=en'
    user = db.session.scalar(select(User))
    assert user.phone_number == user.whatsapp == '+249912345678' and not user.is_verified
    assert user.check_password('password-for-tests')
    assert db.session.query(OTPChallenge).count() == 0
    with client.session_transaction() as auth_session:
        assert auth_session['user_id'] == user.id


def test_signup_existing_phone_does_not_overwrite(client):
    existing = User(phone_number='+249912345678', contact_name='Original',
                    whatsapp='+249912222222', contact_role='owner', is_verified=True)
    db.session.add(existing)
    db.session.commit()
    page = client.get('/signup')
    response = client.post('/signup', data={'csrf_token': csrf(page), 'next': '/properties/new',
        'phone_number': '00249912345678', 'contact_name': 'Overwrite',
        'password': 'password-for-tests', 'confirm_password': 'password-for-tests'})
    assert response.status_code == 409
    assert db.session.query(User).count() == 1
    db.session.refresh(existing)
    assert existing.contact_name == 'Original' and existing.contact_role == 'owner'
    with client.session_transaction() as auth_session:
        assert 'user_id' not in auth_session


def test_signup_csrf_and_safe_destination(client):
    assert client.post('/signup', data={'phone_number': '0912345678'}).status_code == 400
    page = client.get('/signup?next=https://example.com').get_data(as_text=True)
    assert 'name="next" value="/"' in page


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
    entry_response = client.get(links[-1][0], follow_redirects=False)
    assert entry_response.status_code == 302
    signin = unescape(client.get(entry_response.location).get_data(as_text=True))
    assert 'class="signin-main"' in signin
    assert translate("Don't have an account?", language) in signin
    assert 'href="/signup' in signin
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
    assert f'href="/account{suffix}" class="desktop-auth-link">{translate("My Account", language)}</a>' in navigation
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
    entry = client.get('/auth?next=/properties/new&lang=' + language, follow_redirects=False)
    assert entry.status_code == 302 and entry.location.startswith('/login?')
    assert 'next=/properties/new' in entry.location
    for route in ('/login', '/signup'):
        page = client.get(route + '?next=/properties/new&lang=' + language).get_data(as_text=True)
        assert f'<html lang="{language}" dir="{direction}">' in page
        content = page.split('<main', 1)[1].split('</main>', 1)[0]
        assert 'auth-page' in content
        assert translate('Create Account' if route != '/login' else 'Sign Up', language) in content
        assert 'next=/properties/new' in content
    signup_page = client.get('/signup?lang=' + language).get_data(as_text=True)
    assert f'<button type="submit">{translate("Create Account", language)}</button>' in signup_page
    assert translate('Full name', language) in signup_page
    assert translate('Password', language) in signup_page
    assert translate('Confirm password', language) in signup_page
    login_page = client.get('/login?lang=' + language).get_data(as_text=True)
    assert f'<button class="signin-submit" type="submit">{translate("Sign In", language)}</button>' in login_page
    assert '/auth/request-otp' not in login_page
    with client.session_transaction() as auth_session:
        auth_session['pending_phone'] = '+249912345678'
        auth_session['auth_next'] = '/properties/new'
    otp_page = client.get('/auth/verify?lang=' + language).get_data(as_text=True)
    assert 'auth-page' in otp_page and 'auth-resend' in otp_page
    assert 'auth-change-phone' in otp_page
    assert '/login?next=/properties/new' in otp_page


@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
def test_redesigned_signin_preserves_auth_forms_and_localized_layout(client, language, direction):
    from app.languages import translate

    response = client.get('/login?next=/properties/new&lang=' + language)
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert f'<html lang="{language}" dir="{direction}">' in page
    assert 'class="signin-main"' in page
    assert 'class="signin-promo"' in page
    assert 'class="auth-page signin-card"' in page
    for phrase in (
        'Homes closer to your life',
        'Find a suitable home in Sudan easily and safely.',
        'Trusted properties',
        'A secure experience',
        'Coverage across Sudan',
        'Welcome back',
        'Sign in to continue to Manazil',
    ):
        assert translate(phrase, language) in page
    assert 'manazil-logo.png' in page
    assert 'auth-password-toggle' in page
    assert 'data-password-toggle' in page
    assert 'data-show-label="' + translate('Show password', language) + '"' in page
    assert 'action="/auth/password-login"' in page
    assert 'name="csrf_token"' in page
    assert 'name="next" value="/properties/new"' in page
    assert 'name="country_code"' in page and 'name="phone_number"' in page
    assert '/static/js/auth-password-toggle.js' in page


def test_signin_background_asset_is_served_from_static_images(client):
    response = client.get('/static/images/manazil-login-background.png')
    assert response.status_code == 200
    assert response.mimetype == 'image/png'
    assert len(response.data) > 100_000

    css = Path('app/static/css/style.css').read_text(encoding='utf-8')
    assert "url('../images/manazil-login-background.png')" in css
    assert 'background-size: cover' in css
    assert '@media (max-width: 767px)' in css
    assert '.signin-promo { display: none; }' in css
    assert 'width: min(calc(100% - 24px), 480px)' in css


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


@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
def test_mobile_header_keeps_account_outside_menu_and_language_inside(client, language, direction):
    from app.languages import translate
    suffix = '?lang=en' if language == 'en' else ''
    page = client.get('/' + suffix).get_data(as_text=True)
    assert f'<html lang="{language}" dir="{direction}">' in page
    header = re.search(r'<header class="site-header">.*?</header>', page, re.S).group(0)
    panel = re.search(r'<div class="site-navigation-panel" id="site-navigation">.*?</nav>.*?</div>\s*</div>', header, re.S).group(0)
    assert header.count('class="language-switcher"') == 1
    assert 'class="language-switcher"' in panel
    assert 'lang="ar"' in panel and 'lang="en"' in panel
    assert all(f'href="{path}{suffix}"' in panel for path in ('/', '/properties', '/properties/new'))
    assert f'href="/auth{suffix}" class="desktop-auth-link"' in panel
    account = re.search(r'<a class="mobile-account-link".*?</a>', header, re.S).group(0)
    assert header.index(account) >= header.index(panel) + len(panel)
    assert f'href="/auth{suffix}"' in account
    assert translate('Sign in', language) in account
    assert 'class="mobile-account-icon"' in account and 'aria-hidden="true"' in account
    assert header.count('class="mobile-account-link"') == 1
    assert 'class="mobile-menu-toggle"' in header
    assert 'aria-controls="site-navigation"' in header


@pytest.mark.parametrize('language', ['ar', 'en'])
def test_authenticated_mobile_header_links_account_without_changing_menu(client, language):
    from app.languages import translate
    user = User(phone_number='+249912345678', is_verified=True, is_active=True)
    db.session.add(user)
    db.session.commit()
    with client.session_transaction() as auth_session:
        auth_session['user_id'] = user.id
    suffix = '?lang=en' if language == 'en' else ''
    header = re.search(r'<header class="site-header">.*?</header>', client.get('/' + suffix).text, re.S).group(0)
    account = re.search(r'<a class="mobile-account-link".*?</a>', header, re.S).group(0)
    assert f'href="/account{suffix}"' in account
    assert translate('My Account', language) in account
    assert 'href="/auth' not in header
    for path in ('/my-properties', '/saved-properties'):
        assert f'href="{path}{suffix}"' in header
    assert 'method="post" action="/logout"' in header


def test_mobile_menu_css_and_keyboard_behavior_remain_scoped():
    styles = Path('app/static/css/style.css').read_text(encoding='utf-8')
    script = Path('app/static/js/navigation.js').read_text(encoding='utf-8')
    mobile = styles.split('@media (max-width: 959px) {', 1)[1].split('\n}', 1)[0]
    assert '.site-header { position: relative; display: grid; grid-template-columns: max-content minmax(0, 1fr) 44px;' in mobile
    assert '.site-header .site-navigation-panel.is-open { display: flex; }' in mobile
    assert '.site-header nav .desktop-auth-link { display: none; }' in mobile
    assert '.site-header .language-switcher {' in mobile
    assert '.mobile-menu-label { position: absolute;' in mobile
    assert '.site-navigation-panel { display: contents; }' in styles
    assert 'navigation.addEventListener("click"' in script
    assert 'event.target.closest("a, button")' in script
    assert 'event.key === "Escape"' in script
    assert 'mobile.addEventListener("change"' in script
