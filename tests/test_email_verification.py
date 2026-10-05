"""Email verification never shares phone OTP state and never sends real mail."""
import re
from datetime import timedelta
from unittest.mock import Mock

import pytest
import requests
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text

from app import db
from app.email_verification import issue_code
from app.google_provider import GoogleAuthProvider, GoogleIdentity
from app.languages import translate
from app.models import EmailVerificationChallenge, User, UserIdentity, utc_now
from test_auth import client, csrf
from test_manual_signup import register
from test_properties import migrated_connection
from test_google_auth import google_client, begin, isolated_google_environment


def current_challenge():
    return db.session.scalar(select(EmailVerificationChallenge).order_by(EmailVerificationChallenge.id.desc()))


def delivered_code(post):
    return re.search(r'\b[0-9]{6}\b', post.call_args.kwargs['json']['text']).group()


def verify(client, code, language='en'):
    return client.post('/auth/verify-email', data={
        'csrf_token': csrf(client.get('/auth/verify-email?lang=' + language)),
        'code': code, '_language': language,
    })


def resend(client, language='en'):
    return client.post('/auth/verify-email/resend', data={
        'csrf_token': csrf(client.get('/auth/verify-email?lang=' + language)),
        '_language': language,
    })


def age_challenge():
    current_challenge().created_at = utc_now() - timedelta(seconds=61)
    db.session.commit()


@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
def test_signup_challenge_and_bilingual_email(client, isolated_email_delivery, language, direction, caplog):
    response = register(client, language=language)
    assert response.location == '/auth/verify-email' + ('?lang=en' if language == 'en' else '')
    challenge = current_challenge()
    user = db.session.get(User, challenge.user_id)
    code = delivered_code(isolated_email_delivery)
    assert re.fullmatch(r'[0-9]{6}', code)
    assert challenge.email == user.email == 'member@example.test'
    assert len(challenge.code_hash) == 64 and challenge.code_hash != code
    assert challenge.expires_at - challenge.created_at == timedelta(minutes=10)
    assert challenge.attempts == 0 and challenge.consumed_at is None
    assert not user.email_verified and not user.is_verified
    assert code not in caplog.text
    payload = isolated_email_delivery.call_args.kwargs['json']
    assert payload['subject'] == translate('Verify your Manazil email', language)
    assert translate('This code expires in 10 minutes. If you did not request this, ignore this message.', language) in payload['text']
    page = client.get(response.location)
    assert f'<html lang="{language}" dir="{direction}">' in page.text
    assert translate('Verify your email', language) in page.text
    assert 'member@example.test' not in page.text and code not in page.text
    assert page.headers['Cache-Control'] == 'no-store'
    assert 'inputmode="numeric"' in page.text and 'autocomplete="one-time-code"' in page.text
    assert client.get('/account?lang=' + language).status_code == 200


def test_correct_code_single_use_and_success_notice(client, isolated_email_delivery):
    register(client)
    code = delivered_code(isolated_email_delivery)
    response = verify(client, code)
    assert response.status_code == 303 and response.location == '/?lang=en'
    user = db.session.get(User, current_challenge().user_id)
    assert user.email_verified and not user.is_verified
    assert current_challenge().consumed_at is not None
    assert 'Your email has been verified successfully.' in client.get(response.location).text
    assert client.get('/auth/verify-email').location == '/'
    count = isolated_email_delivery.call_count
    assert client.post('/auth/verify-email/resend', data={'csrf_token': csrf(client.get('/account'))}).status_code == 303
    assert isolated_email_delivery.call_count == count
    # Even if verification is cleared later, a consumed challenge is unusable.
    user.email_verified = False
    db.session.commit()
    assert verify(client, code).status_code == 422
    assert not user.email_verified


@pytest.mark.parametrize('code', ['0000000', 'bad', '', '<script>', '１２３４５６'])
def test_malformed_codes_fail_and_count_attempt(client, code):
    register(client)
    assert verify(client, code).status_code == 422
    assert current_challenge().attempts == 1


def test_wrong_code_and_five_attempt_limit(client, isolated_email_delivery):
    register(client)
    code = delivered_code(isolated_email_delivery)
    wrong = '000000' if code != '000000' else '111111'
    for attempt in range(5):
        response = verify(client, wrong)
        assert response.status_code == 422
        assert 'Invalid or expired verification code.' in response.text
        assert current_challenge().attempts == attempt + 1
    assert current_challenge().consumed_at is not None
    assert verify(client, code).status_code == 422
    assert not db.session.get(User, current_challenge().user_id).email_verified


def test_expired_code_fails(client, isolated_email_delivery):
    register(client)
    current_challenge().expires_at = utc_now() - timedelta(seconds=1)
    db.session.commit()
    assert verify(client, delivered_code(isolated_email_delivery)).status_code == 422


def test_resend_cooldown_new_code_invalidates_old(client, isolated_email_delivery, monkeypatch):
    codes = iter([123456, 123456, 654321])
    monkeypatch.setattr('app.email_verification.secrets.randbelow', lambda limit: next(codes))
    register(client)
    previous = current_challenge()
    assert resend(client).status_code == 303
    assert isolated_email_delivery.call_count == 1
    assert 'Please wait before requesting another code.' in client.get('/auth/verify-email?lang=en').text
    assert db.session.query(EmailVerificationChallenge).count() == 1
    age_challenge()
    assert resend(client).status_code == 303
    assert delivered_code(isolated_email_delivery) == '654321'
    assert previous.consumed_at is not None
    assert current_challenge().expires_at - current_challenge().created_at == timedelta(minutes=10)
    assert verify(client, '123456').status_code == 422
    assert verify(client, '654321').status_code == 303


def test_hourly_send_limit(client, isolated_email_delivery):
    register(client)
    for _ in range(4):
        age_challenge()
        resend(client)
    age_challenge()
    resend(client)
    assert isolated_email_delivery.call_count == 5
    assert db.session.query(EmailVerificationChallenge).count() == 5


@pytest.mark.parametrize('failure', ['network', 'http', 'configuration'])
def test_delivery_failure_keeps_account_and_allows_retry(client, isolated_email_delivery, failure, caplog):
    from flask import current_app
    if failure == 'network':
        isolated_email_delivery.side_effect = requests.Timeout('secret-provider-body')
    elif failure == 'http':
        isolated_email_delivery.return_value.status_code = 500
    else:
        current_app.config['RESEND_API_KEY'] = None
    response = register(client)
    assert response.status_code == 303
    page = client.get(response.location)
    assert 'Unable to send the email.' in page.text
    assert db.session.query(User).count() == 1
    assert current_challenge().consumed_at is None
    assert 'secret-provider-body' not in page.text + caplog.text
    age_challenge()
    isolated_email_delivery.side_effect = None
    isolated_email_delivery.return_value.status_code = 200
    current_app.config['RESEND_API_KEY'] = 'fake-test-key'
    assert resend(client).status_code == 303
    assert verify(client, delivered_code(isolated_email_delivery)).status_code == 303


def test_authenticated_existing_user_can_request_code_no_get_send(client, isolated_email_delivery):
    user = User(email='existing@example.test', phone_number='+249912345678')
    user.set_password('test-password')
    db.session.add(user)
    db.session.commit()
    with client.session_transaction() as session:
        session['user_id'] = user.id
    assert '/auth/verify-email' in client.get('/account').text
    assert client.get('/auth/verify-email').status_code == 200
    isolated_email_delivery.assert_not_called()
    assert resend(client).status_code == 303
    assert verify(client, delivered_code(isolated_email_delivery)).status_code == 303


def test_email_change_clears_verification_and_old_code_cannot_verify_new_email(client, isolated_email_delivery):
    register(client)
    old = delivered_code(isolated_email_delivery)
    user = db.session.get(User, current_challenge().user_id)
    user.email_verified = True
    db.session.commit()
    user.email = 'changed@example.test'
    db.session.commit()
    assert not user.email_verified
    assert verify(client, old).status_code == 422
    age_challenge()
    resend(client)
    assert current_challenge().email == 'changed@example.test'
    assert verify(client, delivered_code(isolated_email_delivery)).status_code == 303


def test_code_is_bound_to_user(client, isolated_email_delivery):
    register(client)
    old = delivered_code(isolated_email_delivery)
    second = User(email='second@example.test')
    second.set_password('test-password')
    db.session.add(second)
    db.session.commit()
    with client.session_transaction() as session:
        session['user_id'] = second.id
    assert verify(client, old).status_code == 422
    assert not second.email_verified


def test_csrf_and_authentication_required(client, isolated_email_delivery):
    for path in ('/auth/verify-email', '/auth/verify-email/resend'):
        assert client.post(path).status_code == 400
        token = csrf(client.get('/login'))
        assert client.post(path, data={'csrf_token': token}).status_code == 302
    assert client.get('/auth/verify-email').status_code == 302
    isolated_email_delivery.assert_not_called()
    register(client)
    count = isolated_email_delivery.call_count
    assert client.post('/auth/verify-email', data={'code': '123456'}).status_code == 400
    assert client.post('/auth/verify-email/resend').status_code == 400
    assert isolated_email_delivery.call_count == count


@pytest.mark.parametrize('email,verified', [('google@example.test', True), ('google@example.test', False), (None, False)])
def test_google_callback_unchanged_no_automatic_email_challenge(google_client, monkeypatch, isolated_email_delivery, email, verified):
    identity = GoogleIdentity('verified-sub', 'Google User', None, 'Google', 'User', email, verified)
    monkeypatch.setattr(GoogleAuthProvider, 'authenticate', lambda *a: identity)
    _, state = begin(google_client)
    response = google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'fake-code'})
    assert response.location == '/?lang=en'
    user = db.session.get(UserIdentity, ('google', 'verified-sub')).user
    assert user.email_verified is verified
    assert db.session.query(EmailVerificationChallenge).count() == 0
    isolated_email_delivery.assert_not_called()
    page = google_client.get('/auth/verify-email?lang=en')
    assert page.status_code == (200 if email and not verified else 303)
    if email and not verified:
        assert resend(google_client).status_code == 303
        assert verify(google_client, delivered_code(isolated_email_delivery)).status_code == 303


def test_migration_roundtrip_preserves_users(migrated_connection):
    config = Config('migrations/alembic.ini')
    config.set_main_option('script_location', 'migrations')
    config.attributes['connection'] = migrated_connection
    command.downgrade(config, '0019_user_email_profile')
    migrated_connection.execute(text("INSERT INTO users (email, email_verified, is_verified, is_active, role, created_at, updated_at) VALUES ('existing@example.test', false, false, true, 'user', now(), now())"))
    command.upgrade(config, 'head')
    assert 'email_verification_challenges' in inspect(migrated_connection).get_table_names()
    assert migrated_connection.scalar(text('SELECT count(*) FROM email_verification_challenges')) == 0
    assert migrated_connection.scalar(text('SELECT email_verified FROM users')) is False
    command.downgrade(config, '0019_user_email_profile')
    assert 'email_verification_challenges' not in inspect(migrated_connection).get_table_names()
    assert migrated_connection.scalar(text('SELECT email FROM users')) == 'existing@example.test'
    command.upgrade(config, 'head')
