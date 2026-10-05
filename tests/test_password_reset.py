"""Recovery is purpose-separated, non-enumerating, and never sends real email."""
import re
from datetime import timedelta
from unittest.mock import Mock

import pytest
import requests
from alembic import command
from alembic.config import Config
from flask import current_app, g
from sqlalchemy import inspect, select, text

from app import db
from app.models import EmailVerificationChallenge, PasswordResetChallenge, User, UserIdentity, utc_now
from app.password_reset import GENERIC_NOTICE, verify_code
from app.languages import translate
from test_auth import client, csrf
from test_properties import migrated_connection


def account(email='member@example.test', verified=True, active=True, password=True):
    user = User(email=email, email_verified=verified, is_active=active, phone_number='+249912345678')
    if password:
        user.set_password('old-test-password')
    db.session.add(user)
    db.session.commit()
    return user


def form_token(client, path):
    # The DB fixture retains an app context across requests. Real HTTP requests
    # have fresh g; clear only its cached signed CSRF rendering when switching browsers.
    g.pop('csrf_token', None)
    return csrf(client.get(path))


def request_reset(client, email='member@example.test', language='en'):
    token = form_token(client, '/auth/forgot-password?lang=' + language)
    return client.post('/auth/forgot-password', data={'csrf_token': token, 'email': email, '_language': language})


def challenge():
    return db.session.scalar(select(PasswordResetChallenge).order_by(PasswordResetChallenge.id.desc()))


def code(post):
    return re.search(r'\b[0-9]{6}\b', post.call_args.kwargs['json']['text']).group()


def verify(client, value, language='en'):
    return client.post('/auth/password-reset/code', data={
        'csrf_token': form_token(client, '/auth/password-reset/code?lang=' + language),
        'code': value, '_language': language})


def resend(client, language='en'):
    return client.post('/auth/password-reset/resend', data={
        'csrf_token': form_token(client, '/auth/password-reset/code?lang=' + language), '_language': language})


def advance_cooldown(client):
    challenge().created_at = utc_now() - timedelta(seconds=61)
    db.session.commit()
    with client.session_transaction() as session:
        session['password_reset_requests'] = [stamp - 61 for stamp in session.get('password_reset_requests', [])]


def authorize(client, post):
    assert request_reset(client).status_code == 303
    assert verify(client, code(post)).location == '/auth/reset-password?lang=en'


def replace_password(client, password='new-secure-password', confirmation=None, language='en', **extra):
    return client.post('/auth/reset-password', data={
        'csrf_token': form_token(client, '/auth/reset-password?lang=' + language),
        'password': password, 'confirm_password': password if confirmation is None else confirmation,
        '_language': language, **extra})


@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
def test_pages_link_background_and_localization(client, isolated_email_delivery, language, direction):
    page = client.get('/login?lang=' + language)
    assert translate('Forgot password?', language) in page.text
    assert '/auth/forgot-password' in page.text
    user = account()
    forgot = client.get('/auth/forgot-password?lang=' + language)
    assert f'<html lang="{language}" dir="{direction}">' in forgot.text
    assert 'class="signin-main"' in forgot.text and 'class="auth-page signin-card"' in forgot.text
    assert 'name="email"' in forgot.text
    assert translate('If you normally use Google, continue with Google.', language) in forgot.text
    response = request_reset(client, language=language)
    page = client.get(response.location)
    assert f'<html lang="{language}" dir="{direction}">' in page.text
    assert translate(GENERIC_NOTICE, language) in page.text
    assert translate('Check Spam or Junk if the email is not in your Inbox.', language) in page.text
    assert 'member@example.test' not in page.text
    payload = isolated_email_delivery.call_args.kwargs['json']
    assert payload['subject'] == translate('Reset your Manazil password', language)
    assert translate('Check Spam or Junk if the email is not in your Inbox.', language) in payload['text']
    assert page.headers['Cache-Control'] == 'no-store' and page.headers['Referrer-Policy'] == 'no-referrer'
    verified = verify(client, code(isolated_email_delivery), language)
    password_page = client.get(verified.location)
    assert f'<html lang="{language}" dir="{direction}">' in password_page.text
    assert translate('Use a password between 8 and 128 characters.', language) in password_page.text
    assert 'autocomplete="new-password"' in password_page.text
    assert '/static/js/auth-password-toggle.js' in password_page.text
    changed = replace_password(client, language=language)
    assert changed.location == '/login' + ('?lang=en' if language == 'en' else '')
    assert translate('Your password has been updated. Please sign in.', language) in client.get(changed.location).text
    assert user.check_password('new-secure-password')


@pytest.mark.parametrize('kind', ['eligible', 'unknown', 'unverified', 'inactive', 'google', 'malformed'])
def test_eligibility_and_generic_response(client, isolated_email_delivery, kind):
    email = 'member@example.test'
    if kind not in ('unknown', 'malformed'):
        user = account(verified=kind != 'unverified', active=kind != 'inactive', password=kind != 'google')
        if kind == 'google':
            db.session.add(UserIdentity(provider='google', provider_user_id='only-google', user_id=user.id, display_name='Name'))
            db.session.commit()
    if kind == 'malformed':
        email = 'not-email'
    response = request_reset(client, email)
    assert response.status_code == 303 and response.location == '/auth/password-reset/code?lang=en'
    page = client.get(response.location)
    assert GENERIC_NOTICE in page.text
    assert 'member@example.test' not in page.text and 'not-email' not in page.text
    assert db.session.query(PasswordResetChallenge).count() == (1 if kind == 'eligible' else 0)
    assert isolated_email_delivery.call_count == (1 if kind == 'eligible' else 0)
    with client.session_transaction() as session:
        assert set(session['password_reset_pending']) == {'email', 'expires'}
        assert 'password_reset_authorization' not in session
    if kind != 'eligible':
        assert verify(client, '123456').status_code == 422
        assert client.get('/auth/reset-password').location == '/auth/forgot-password'
        if kind == 'google':
            assert user.password_hash is None


def test_same_public_markup_for_known_and_unknown(client, isolated_email_delivery):
    account()
    known = request_reset(client)
    known_html = client.get(known.location).text
    unknown = request_reset(client, 'unknown@example.test')
    # CSRF signatures legitimately include a render timestamp; compare all other
    # markup, including notices, fields, actions and account-independent content.
    token = r'(name="csrf_token" value=")[^"]+(" )?'
    normalize = lambda html: re.sub(token, r'\1CSRF', html)
    assert normalize(client.get(unknown.location).text) == normalize(known_html)


def test_normalized_email_hashes_and_no_logging(client, isolated_email_delivery, caplog):
    user = account()
    request_reset(client, '  MEMBER@Example.TEST  ')
    row = challenge()
    actual = code(isolated_email_delivery)
    assert row.email == user.email == 'member@example.test'
    assert row.user_id == user.id and row.code_hash != actual and len(row.code_hash) == 64
    assert row.credential_hash != user.password_hash
    assert row.expires_at - row.created_at == timedelta(minutes=10)
    assert row.attempts == 0 and row.consumed_at is None and row.code_verified_at is None
    assert actual not in caplog.text
    assert db.session.query(EmailVerificationChallenge).count() == 0
    assert isolated_email_delivery.call_args.kwargs['json']['to'] == ['member@example.test']


@pytest.mark.parametrize('failure', ['network', 'http', 'configuration'])
def test_delivery_failure_is_generic_and_password_unchanged(client, isolated_email_delivery, failure, caplog, monkeypatch):
    user = account()
    warning = Mock()
    monkeypatch.setattr(current_app.logger, 'warning', warning)
    if failure == 'network':
        isolated_email_delivery.side_effect = requests.Timeout('sensitive-provider-body')
    elif failure == 'http':
        isolated_email_delivery.return_value.status_code = 401
    else:
        current_app.config['RESEND_API_KEY'] = None
    response = request_reset(client)
    page = client.get(response.location)
    assert response.status_code == 303 and GENERIC_NOTICE in page.text
    assert 'sensitive-provider-body' not in page.text + caplog.text
    warning.assert_called_once_with('PASSWORD_RESET_MAIL_DELIVERY_FAILED')
    assert user.check_password('old-test-password') and not user.check_password('new-secure-password')
    assert challenge().consumed_at is None


def test_wrong_code_limit_and_no_password_change(client, isolated_email_delivery):
    user = account()
    request_reset(client)
    actual = code(isolated_email_delivery)
    wrong = '000000' if actual != '000000' else '111111'
    for index in range(5):
        response = verify(client, wrong)
        assert response.status_code == 422 and 'Invalid or expired verification code.' in response.text
        assert challenge().attempts == index + 1
    assert challenge().consumed_at is not None
    assert verify(client, actual).status_code == 422
    assert user.check_password('old-test-password')
    with client.session_transaction() as session:
        assert 'password_reset_authorization' not in session


@pytest.mark.parametrize('invalid', ['expired', 'consumed', 'changed-email', 'unverified', 'inactive', 'changed-password'])
def test_code_rechecks_eligibility_and_snapshot(client, isolated_email_delivery, invalid):
    user = account()
    request_reset(client)
    actual = code(isolated_email_delivery)
    if invalid == 'expired':
        challenge().expires_at = utc_now() - timedelta(seconds=1)
    elif invalid == 'consumed':
        challenge().consumed_at = utc_now()
    elif invalid == 'changed-email':
        user.email = 'changed@example.test'
    elif invalid == 'unverified':
        user.email_verified = False
    elif invalid == 'inactive':
        user.is_active = False
    else:
        user.set_password('different-current-password')
    db.session.commit()
    assert verify(client, actual).status_code == 422


def test_resend_new_code_and_old_code_invalidation(client, isolated_email_delivery, monkeypatch):
    account()
    values = iter([123456, 123456, 654321])
    monkeypatch.setattr('app.password_reset.secrets.randbelow', lambda limit: next(values))
    request_reset(client)
    old = challenge()
    assert resend(client).status_code == 303
    assert isolated_email_delivery.call_count == 1
    advance_cooldown(client)
    resend(client)
    assert isolated_email_delivery.call_count == 2 and code(isolated_email_delivery) == '654321'
    assert old.consumed_at is not None
    assert challenge().expires_at - challenge().created_at == timedelta(minutes=10)
    assert verify(client, '123456').status_code == 422
    assert verify(client, '654321').status_code == 303


def test_hourly_send_limit_applies_across_browsers(client, isolated_email_delivery):
    account()
    request_reset(client)
    for _ in range(4):
        advance_cooldown(client)
        resend(client)
    advance_cooldown(client)
    # A fresh browser cannot evade the database account rate limit.
    assert request_reset(current_app.test_client()).status_code == 303
    assert isolated_email_delivery.call_count == 5
    assert db.session.query(PasswordResetChallenge).count() == 5


def test_session_throttle_applies_to_unknown_requests_too(client, isolated_email_delivery):
    account()
    request_reset(client, 'unknown@example.test')
    request_reset(client)
    assert isolated_email_delivery.call_count == 0
    assert db.session.query(PasswordResetChallenge).count() == 0
    assert GENERIC_NOTICE in client.get('/auth/password-reset/code?lang=en').text


def test_correct_code_creates_expiring_authorization_not_password_change(client, isolated_email_delivery):
    user = account()
    authorize(client, isolated_email_delivery)
    row = challenge()
    assert user.check_password('old-test-password')
    assert row.code_verified_at is not None and row.consumed_at is None
    assert row.authorization_expires_at - row.code_verified_at == timedelta(minutes=5)
    with client.session_transaction() as session:
        grant = dict(session['password_reset_authorization'])
        assert row.authorization_hash != grant['token']
        assert 'user_id' not in session and 'password_reset_pending' not in session
    assert verify_code(user.email, code(isolated_email_delivery)) is None
    assert client.get('/auth/reset-password?lang=en').status_code == 200
    other = current_app.test_client()
    with other.session_transaction() as session:
        session['password_reset_authorization'] = {'challenge_id': row.id, 'token': 'a' * 43}
    assert other.get('/auth/reset-password').location == '/auth/forgot-password'


def test_new_request_invalidates_verified_authorization(client, isolated_email_delivery):
    account()
    authorize(client, isolated_email_delivery)
    old = challenge()
    old_id = old.id
    advance_cooldown(client)
    fresh_client = current_app.test_client()
    response = request_reset(fresh_client)
    assert response.status_code == 303
    assert isolated_email_delivery.call_count == 2, (
        db.session.query(PasswordResetChallenge).count(),
        (utc_now() - challenge().created_at).total_seconds())
    old = db.session.get(PasswordResetChallenge, old_id)
    assert old.consumed_at is not None and old.authorization_hash is None
    assert client.get('/auth/reset-password').location == '/auth/forgot-password'


@pytest.mark.parametrize('invalid', ['expired', 'changed-email', 'changed-password', 'inactive'])
def test_reset_authorization_rechecks_user_and_expiry(client, isolated_email_delivery, invalid):
    user = account()
    authorize(client, isolated_email_delivery)
    if invalid == 'expired':
        challenge().authorization_expires_at = utc_now() - timedelta(seconds=1)
    elif invalid == 'changed-email':
        user.email = 'changed@example.test'
    elif invalid == 'changed-password':
        user.set_password('changed-elsewhere-password')
    else:
        user.is_active = False
    db.session.commit()
    assert client.get('/auth/reset-password').location == '/auth/forgot-password'
    with client.session_transaction() as session:
        assert 'password_reset_authorization' not in session


@pytest.mark.parametrize('password,confirmation,error', [
    ('', '', 'This field is required.'), ('short', 'short', 'Use a password between 8 and 128 characters.'),
    ('x' * 129, 'x' * 129, 'Use a password between 8 and 128 characters.'),
    ('new-secure-password', '', 'This field is required.'),
    ('new-secure-password', 'mismatch', 'Passwords do not match.'),
])
def test_password_policy_server_side(client, isolated_email_delivery, password, confirmation, error):
    user = account()
    authorize(client, isolated_email_delivery)
    response = replace_password(client, password, confirmation)
    assert response.status_code == 422 and error in response.text
    assert user.check_password('old-test-password')
    assert challenge().consumed_at is None
    assert client.get('/auth/reset-password').status_code == 200


def test_success_replaces_password_clears_session_and_prevents_replay(client, isolated_email_delivery):
    user = account()
    with client.session_transaction() as session:
        session['user_id'] = user.id
    authorize(client, isolated_email_delivery)
    with client.session_transaction() as session:
        old_grant = dict(session['password_reset_authorization'])
    response = replace_password(client, user_id='999999', email='attacker@example.test')
    assert response.status_code == 303 and response.location == '/login?lang=en'
    assert user.check_password('new-secure-password') and not user.check_password('old-test-password')
    assert 'new-secure-password' not in user.password_hash
    assert challenge().consumed_at is not None and challenge().authorization_hash is None
    assert user.email_verified and not user.is_verified
    with client.session_transaction() as session:
        assert 'user_id' not in session and 'password_reset_authorization' not in session
        assert 'password_reset_pending' not in session
        session['password_reset_authorization'] = old_grant
    assert client.get('/auth/reset-password').location == '/auth/forgot-password'
    assert verify_code(user.email, code(isolated_email_delivery)) is None
    page = client.get('/login?lang=en')
    assert client.post('/auth/password-login', data={'csrf_token': csrf(page),
        'phone_number': user.phone_number, 'password': 'old-test-password'}).status_code == 422
    assert client.post('/auth/password-login', data={'csrf_token': csrf(page), '_language': 'en',
        'phone_number': user.phone_number, 'password': 'new-secure-password'}).location == '/?lang=en'


def test_reset_page_no_authorization_and_csrf_on_all_posts(client, isolated_email_delivery):
    user = account()
    assert client.get('/auth/reset-password?user_id=' + str(user.id)).location == '/auth/forgot-password'
    token = csrf(client.get('/auth/forgot-password'))
    assert client.post('/auth/reset-password', data={'csrf_token': token,
        'user_id': user.id, 'email': user.email, 'password': 'new-secure-password',
        'confirm_password': 'new-secure-password'}).location == '/auth/forgot-password'
    for path in ('/auth/forgot-password', '/auth/password-reset/code', '/auth/password-reset/resend', '/auth/reset-password'):
        assert client.post(path).status_code == 400
    assert user.check_password('old-test-password')
    isolated_email_delivery.assert_not_called()


def test_pending_flow_expires(client):
    request_reset(client, 'unknown@example.test')
    with client.session_transaction() as session:
        session['password_reset_pending']['expires'] = (utc_now() - timedelta(seconds=1)).timestamp()
        session.modified = True
    assert client.get('/auth/password-reset/code').location == '/auth/forgot-password'


def test_non_test_delivery_is_bounded_background_work(client, monkeypatch):
    from app import password_reset
    pool = Mock()
    future = Mock()
    pool.submit.return_value = future
    monkeypatch.setattr(password_reset, '_mail_pool', pool)
    slots = Mock()
    slots.acquire.return_value = True
    monkeypatch.setattr(password_reset, '_mail_slots', slots)
    lookup = Mock(side_effect=AssertionError('Eligibility must not be queried in the public request.'))
    monkeypatch.setattr(db.session, 'scalar', lookup)
    current_app.config['TESTING'] = False
    password_reset.request_code('member@example.test', 'en')
    pool.submit.assert_called_once()
    assert pool.submit.call_args.args[0] is password_reset._process_request
    future.add_done_callback.call_args.args[0](future)
    slots.release.assert_called_once()
    password_reset.request_code('unknown@example.test', 'en')
    assert pool.submit.call_count == 2
    lookup.assert_not_called()
    pool.reset_mock()
    slots.acquire.return_value = False
    password_reset.request_code('unknown@example.test', 'en')
    pool.submit.assert_not_called()


def test_reset_migration_roundtrip_preserves_users_and_verification(migrated_connection):
    config = Config('migrations/alembic.ini')
    config.set_main_option('script_location', 'migrations')
    config.attributes['connection'] = migrated_connection
    command.downgrade(config, '0020_email_verification')
    migrated_connection.execute(text("INSERT INTO users (email, email_verified, password_hash, is_verified, is_active, role, created_at, updated_at) VALUES ('existing@example.test', true, 'existing-hash', false, true, 'user', now(), now())"))
    command.upgrade(config, 'head')
    assert 'password_reset_challenges' in inspect(migrated_connection).get_table_names()
    assert migrated_connection.scalar(text('SELECT count(*) FROM password_reset_challenges')) == 0
    assert migrated_connection.execute(text('SELECT password_hash, email_verified FROM users')).one() == ('existing-hash', True)
    command.downgrade(config, '0020_email_verification')
    assert 'password_reset_challenges' not in inspect(migrated_connection).get_table_names()
    assert 'email_verification_challenges' in inspect(migrated_connection).get_table_names()
    assert migrated_connection.execute(text('SELECT password_hash, email_verified FROM users')).one() == ('existing-hash', True)
    command.upgrade(config, 'head')
