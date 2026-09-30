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


def complete_account(client, role='owner'):
    page = client.get('/account?lang=en')
    return client.post('/account', data={'csrf_token': csrf(page), '_language': 'en',
        'contact_name': 'Mohamed Ahmed', 'whatsapp': '0911111111', 'contact_role': role})


def test_phone_normalization_and_login(client):
    assert normalize_phone('0912345678') == '+249912345678'
    assert normalize_phone('+249912345678') == '+249912345678'
    assert normalize_phone('00249912345678') == '+249912345678'
    assert login(client).status_code == 303
    assert complete_account(client).status_code == 303
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
    assert response.status_code == 302 and '/login' in response.location
    assert '/account' in login(client, destination='/admin/properties/new').location
    assert complete_account(client).location == '/admin/properties/new'
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
    response = login(client, destination='/admin/properties/new?lang=en')
    assert '/account' in response.location
    page = client.get(response.location).get_data(as_text=True)
    assert '<html lang="en" dir="ltr">' in page
    assert 'value="+249912345678" readonly' in page
    assert 'name="phone_number"' not in page
    assert 'Account Type' in page and 'WhatsApp Number' in page
    assert '/account' in client.get('/admin/properties/new').location
    with client.session_transaction() as auth_session:
        assert 'user_id' not in auth_session
    saved = complete_account(client, role)
    assert saved.status_code == 303 and saved.location == '/admin/properties/new?lang=en'
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
    login(client)
    complete_account(client)
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
