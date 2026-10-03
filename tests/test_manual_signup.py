"""Public password registration and login coexist with OTP and Facebook identities."""
import pytest
from flask import current_app
from sqlalchemy import select

from app import db
from app.languages import translate
from app.models import OTPChallenge, User, UserIdentity
from test_auth import client, csrf
from test_facebook_auth import facebook_login
from test_properties import migrated_connection


def register(client, *, phone='0912345678', name='Mohamed Ahmed', password='correct-horse-password',
             confirmation=None, destination=None, language='en'):
    query = '?lang=' + language + ('&next=' + destination if destination else '')
    page = client.get('/signup' + query)
    data = {'csrf_token': csrf(page), '_language': language, 'contact_name': name,
            'phone_number': phone, 'password': password,
            'confirm_password': password if confirmation is None else confirmation}
    if destination is not None:
        data['next'] = destination
    return client.post('/signup', data=data)


@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
def test_signup_form_is_bilingual_and_manual_first(client, language, direction):
    page = client.get('/signup?lang=' + language)
    assert page.status_code == 200
    assert f'<html lang="{language}" dir="{direction}">' in page.text
    for label in ('Full name', 'WhatsApp/mobile number', 'Password', 'Confirm password',
                  'Create Account', 'Already have an account?'):
        assert translate(label, language) in page.text
    for field in ('contact_name', 'phone_number', 'password', 'confirm_password'):
        assert f'name="{field}"' in page.text
    assert 'name="email"' not in page.text and 'name="contact_role"' not in page.text
    assert page.text.index('action="/signup"') < page.text.index('action="/auth/facebook"')


def test_successful_signup_normalizes_hashes_and_signs_in_without_otp(client):
    response = register(client, phone='00249912345678')
    assert response.status_code == 303 and response.location == '/?lang=en'
    user = db.session.scalar(select(User))
    assert user.contact_name == 'Mohamed Ahmed'
    assert user.phone_number == user.whatsapp == '+249912345678'
    assert user.password_hash and 'correct-horse-password' not in user.password_hash
    assert user.check_password('correct-horse-password')
    assert user.is_active and not user.is_verified and user.has_authenticated_identity
    assert db.session.query(OTPChallenge).count() == 0
    with client.session_transaction() as auth_session:
        assert auth_session['user_id'] == user.id
        assert 'pending_phone' not in auth_session and 'pending_signup' not in auth_session
    account = client.get('/account?lang=en')
    assert account.status_code == 200 and 'Password login' in account.text
    assert client.get('/saved-properties').status_code == 200


@pytest.mark.parametrize('field,value,message', [
    ('contact_name', '', 'This field is required.'),
    ('phone_number', 'bad', 'Enter a valid phone number.'),
    ('password', '', 'This field is required.'),
    ('password', 'short', 'Use a password between 8 and 128 characters.'),
    ('confirm_password', '', 'This field is required.'),
    ('confirm_password', 'different-password', 'Passwords do not match.'),
])
def test_signup_validation_is_server_side_and_localized(client, field, value, message):
    page = client.get('/signup')
    data = {'csrf_token': csrf(page), 'contact_name': 'Member', 'phone_number': '0912345678',
            'password': 'correct-horse-password', 'confirm_password': 'correct-horse-password'}
    data[field] = value
    response = client.post('/signup', data=data)
    assert response.status_code == 422
    assert translate(message, 'ar') in response.text
    assert db.session.query(User).count() == db.session.query(OTPChallenge).count() == 0


def test_duplicate_phone_rejected_for_manual_and_facebook_accounts(client):
    existing = User(phone_number='+249912345678', whatsapp='+249912345678', is_verified=False)
    existing.set_password('existing-password')
    db.session.add(existing)
    db.session.commit()
    duplicate = register(client, phone='00249912345678')
    assert duplicate.status_code == 409
    assert translate('This phone number is already associated with an account.', 'en') in duplicate.text
    assert db.session.query(User).count() == 1
    assert existing.check_password('existing-password')
    assert db.session.query(OTPChallenge).count() == 0


def test_facebook_account_is_never_linked_to_manual_registration(client):
    facebook_login(client)
    page = client.get('/auth/complete-profile')
    client.post('/auth/complete-profile', data={'csrf_token': csrf(page), 'whatsapp': '0912345678'})
    facebook_user = db.session.scalar(select(UserIdentity)).user
    client.post('/logout', data={'csrf_token': csrf(client.get('/account'))})
    response = register(client)
    assert response.status_code == 409
    assert db.session.query(User).count() == 1
    assert facebook_user.password_hash is None
    assert db.session.query(UserIdentity).count() == 1


def test_facebook_completion_cannot_claim_manual_account_phone(client):
    register(client)
    manual_user = db.session.scalar(select(User))
    client.post('/logout', data={'csrf_token': csrf(client.get('/account'))})
    assert facebook_login(client).location == '/auth/complete-profile?lang=en'
    page = client.get('/auth/complete-profile?lang=en')
    conflict = client.post('/auth/complete-profile', data={'csrf_token': csrf(page),
        '_language': 'en', 'whatsapp': '00249912345678'})
    assert conflict.status_code == 422
    assert 'This number cannot be used for this account.' in conflict.text
    assert db.session.query(User).count() == 2
    assert db.session.scalar(select(UserIdentity)).user_id != manual_user.id
    assert manual_user.check_password('correct-horse-password')


def test_password_login_normalizes_phone_and_rejects_bad_credentials(client):
    register(client)
    user = db.session.scalar(select(User))
    client.post('/logout', data={'csrf_token': csrf(client.get('/account'))})
    page = client.get('/login?lang=en&next=/saved-properties')
    bad = client.post('/auth/password-login', data={'csrf_token': csrf(page),
        'phone_number': '+249912345678', 'password': 'wrong', 'next': '/saved-properties',
        '_language': 'en'})
    assert bad.status_code == 422 and 'Invalid phone number or password.' in bad.text
    unknown = client.post('/auth/password-login', data={'csrf_token': csrf(page),
        'phone_number': '0911111111', 'password': 'correct-horse-password', '_language': 'en'})
    assert unknown.status_code == 422 and 'Invalid phone number or password.' in unknown.text
    assert client.post('/auth/password-login', data={'phone_number': '0912345678'}).status_code == 400
    signed_in = client.post('/auth/password-login', data={'csrf_token': csrf(page),
        'phone_number': '00249912345678', 'password': 'correct-horse-password',
        'next': '/saved-properties'})
    assert signed_in.status_code == 303 and signed_in.location == '/saved-properties'
    with client.session_transaction() as auth_session:
        assert auth_session['user_id'] == user.id
    assert not user.is_verified


@pytest.mark.parametrize('destination,expected', [
    ('/properties/new', '/properties/new'),
    ('https://evil.example/', '/'),
    ('//evil.example/', '/'),
])
def test_signup_next_rejects_external_destinations(client, destination, expected):
    response = register(client, destination=destination)
    assert response.status_code == 303
    assert response.location == (expected + '?lang=en' if expected == '/' else expected)


def test_signup_works_without_production_otp_provider(client):
    current_app.config['ENVIRONMENT'] = 'production'
    current_app.config['OTP_DEVELOPMENT_MODE'] = False
    assert register(client).status_code == 303
    assert db.session.query(OTPChallenge).count() == 0


def test_existing_otp_only_user_is_not_accepted_by_password_login(client):
    user = User(phone_number='+249912345678', is_verified=True)
    db.session.add(user)
    db.session.commit()
    page = client.get('/login')
    response = client.post('/auth/password-login', data={'csrf_token': csrf(page),
        'phone_number': '0912345678', 'password': 'anything'})
    assert response.status_code == 422
    assert db.session.query(User).count() == 1
