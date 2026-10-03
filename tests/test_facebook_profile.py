"""Facebook contact onboarding does not send an OTP; phone login still does."""
from sqlalchemy import select

from app import db
from app.languages import translate
from app.models import OTPChallenge, User, UserIdentity
from test_auth import client, csrf, login
from test_facebook_auth import complete_facebook_profile, facebook_login
from test_properties import migrated_connection


def test_new_facebook_user_can_complete_profile_without_otp(client):
    response = facebook_login(client, '/properties/new', language='en')
    assert response.location == '/auth/complete-profile?lang=en'
    user = db.session.scalar(select(User))
    assert user.phone_number is None and user.whatsapp is None and not user.is_verified
    assert client.get('/properties/new').location == '/auth/complete-profile'
    page = client.get(response.location)
    assert page.status_code == 200
    assert 'name="whatsapp"' in page.text and 'name="phone_number"' not in page.text
    assert 'verification code' not in page.text.lower()
    completed = complete_facebook_profile(client)
    assert completed.status_code == 303 and completed.location == '/properties/new'
    assert user.phone_number == user.whatsapp == '+249912222222'
    assert not user.is_verified  # Entered contact information is not OTP-verified.
    assert user.facebook_contact_complete
    assert db.session.query(OTPChallenge).count() == 0
    assert client.get('/account?lang=en').status_code == 200
    with client.session_transaction() as stored:
        assert 'profile_next' not in stored


def test_incomplete_user_returns_to_onboarding_but_completed_user_goes_home(client):
    assert facebook_login(client, '/', language='en').location == '/auth/complete-profile?lang=en'
    user = db.session.scalar(select(User))
    page = client.get('/auth/complete-profile?lang=en')
    assert client.post('/logout', data={'csrf_token': csrf(page)}).status_code == 303
    assert facebook_login(client, '/', language='en').location == '/auth/complete-profile?lang=en'
    assert db.session.query(User).count() == db.session.query(UserIdentity).count() == 1
    assert complete_facebook_profile(client).location == '/?lang=en'
    page = client.get('/account')
    client.post('/logout', data={'csrf_token': csrf(page)})
    assert facebook_login(client, '/', language='en').location == '/?lang=en'
    assert db.session.scalar(select(User)).id == user.id
    assert db.session.query(OTPChallenge).count() == 0


def test_existing_facebook_user_with_phone_bypasses_onboarding(client):
    facebook_login(client)
    user = db.session.scalar(select(User))
    user.phone_number = '+249912222222'
    user.is_verified = False
    db.session.commit()
    page = client.get('/auth/complete-profile')
    client.post('/logout', data={'csrf_token': csrf(page)})
    assert facebook_login(client, '/properties/new').location == '/properties/new'
    assert db.session.query(OTPChallenge).count() == 0


def test_existing_phone_number_is_not_linked_or_duplicated(client):
    phone_user = User(phone_number='+249912345678', is_verified=True, whatsapp='+249912345678')
    db.session.add(phone_user)
    db.session.commit()
    facebook_login(client, '/properties/new')
    facebook_user = db.session.scalar(select(UserIdentity)).user
    page = client.get('/auth/complete-profile')
    conflict = client.post('/auth/complete-profile', data={
        'csrf_token': csrf(page), 'whatsapp': '0912345678'})
    assert conflict.status_code == 422
    assert translate('This number cannot be used for this account.', 'ar') in conflict.text
    assert db.session.query(OTPChallenge).count() == 0
    assert facebook_user.id != phone_user.id and facebook_user.phone_number is None
    assert not facebook_user.is_verified
    assert complete_facebook_profile(client).location == '/properties/new'
    assert db.session.query(User).count() == 2
    assert phone_user.phone_number == '+249912345678'


def test_invalid_phone_and_csrf_rejected_without_otp(client):
    facebook_login(client)
    page = client.get('/auth/complete-profile')
    assert client.post('/auth/complete-profile', data={'whatsapp': '0912222222'}).status_code == 400
    invalid = client.post('/auth/complete-profile', data={
        'csrf_token': csrf(page), 'whatsapp': 'not-a-number'})
    assert invalid.status_code == 422
    assert translate('Enter a valid phone number.', 'ar') in invalid.text
    assert db.session.scalar(select(User)).phone_number is None
    assert db.session.query(OTPChallenge).count() == 0
    assert client.get('/auth/complete-profile/verify').status_code == 404


def test_facebook_number_change_uses_same_form_without_marking_verified(client):
    facebook_login(client)
    complete_facebook_profile(client)
    user = db.session.scalar(select(User))
    account = client.get('/account?lang=en')
    assert 'readonly' in account.text and '/auth/complete-profile?lang=en' in account.text
    tampered = client.post('/account', data={'csrf_token': csrf(account), '_language': 'en',
        'contact_name': 'Changed', 'whatsapp': '0913333333', 'contact_role': 'broker'})
    assert tampered.status_code == 422
    assert user.phone_number == user.whatsapp == '+249912222222'
    assert complete_facebook_profile(client, '0913333333').location == '/account'
    assert user.phone_number == user.whatsapp == '+249913333333' and not user.is_verified


def test_profile_completion_is_bilingual_and_phone_login_still_works(client):
    for language in ('ar', 'en'):
        assert client.get('/auth/complete-profile?lang=' + language).status_code == 302
    phone_user = User(phone_number='+249912345678', is_verified=True)
    db.session.add(phone_user)
    db.session.commit()
    facebook_login(client, language='ar')
    for language, direction in (('ar', 'rtl'), ('en', 'ltr')):
        page = client.get('/auth/complete-profile?lang=' + language)
        assert page.status_code == 200
        assert f'<html lang="{language}" dir="{direction}">' in page.text
        assert translate('Complete your profile', language) in page.text
        assert translate('WhatsApp/mobile number', language) in page.text
        assert translate('Add your WhatsApp/mobile number for Manazil contact and property listings.', language) in page.text
    complete_facebook_profile(client, language='ar')
    page = client.get('/account')
    client.post('/logout', data={'csrf_token': csrf(page)})
    assert login(client, phone='0912345678').status_code == 303
    assert db.session.scalar(select(User).where(User.id == phone_user.id)).is_verified
