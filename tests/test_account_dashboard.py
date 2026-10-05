import re
from html import unescape
from urllib.parse import parse_qs, urlsplit

import pytest

from app import db
from app.languages import translate
from app.models import User, UserIdentity
from test_auth import client, csrf
from test_properties import migrated_connection, values
from test_public_properties import add_property


def account_user(client, method='phone'):
    user = User(id=777777, contact_name='Marketplace Member',
                phone_number='+249912345678' if method == 'phone' else '+249911111111',
                is_verified=True, whatsapp='+249911111111', contact_role='owner')
    db.session.add(user)
    db.session.flush()
    if method == 'google':
        db.session.add(UserIdentity(provider='google', provider_user_id='private-provider-identifier',
                                    user_id=user.id, display_name='Provider Display Name'))
    db.session.commit()
    with client.session_transaction() as auth_session:
        auth_session['user_id'] = user.id
        auth_session['pending_phone'] = 'private-pending-auth-value'
    return user


def test_account_dashboard_requires_authentication(client):
    response = client.get('/account?lang=en')
    assert response.status_code == 302
    assert urlsplit(response.location).path == '/auth'
    assert parse_qs(urlsplit(response.location).query)['next'] == ['/account?lang=en']
    assert client.post('/account', data={'csrf_token': csrf(client.get('/login'))}).status_code == 302


@pytest.mark.parametrize('method', ['phone', 'google'])
@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
def test_dashboard_profile_actions_identity_and_languages(client, method, language, direction):
    user = account_user(client, method)
    response = client.get('/account?lang=' + language)
    assert response.status_code == 200
    page = unescape(response.text)
    content = page.split('<main', 1)[1].split('</main>', 1)[0]
    assert f'<html lang="{language}" dir="{direction}">' in page
    assert 'class="account-page"' in page
    assert '<h1>' + translate('My Account', language) + '</h1>' in content
    assert '<bdi>Marketplace Member</bdi>' in content
    for label in ('Profile Information', 'Account & Security', 'Save Changes'):
        assert translate(label, language) in content
    if method == 'phone':
        assert translate('Read-only', language) in content
    suffix = '?lang=en' if language == 'en' else ''
    assert translate('Your Properties', language) not in content
    assert translate('My Properties', language) not in content
    assert 'account-actions' not in content
    for path, label in (
        ('/saved-properties', 'Saved Properties'),
        ('/properties/new', 'Post Property'),
    ):
        assert f'href="{path}{suffix}"' in content
        assert translate(label, language) in content
    navigation = page.split('<nav', 1)[1].split('</nav>', 1)[0]
    assert f'href="/my-properties{suffix}"' in navigation
    assert 'name="contact_name"' in content and 'value="Marketplace Member"' in content
    assert 'name="whatsapp"' in content and 'value="+249911111111"' in content
    assert 'value="owner" selected' in content
    assert re.search(r'id="phone_number"[^>]+readonly', content) is not None
    assert 'class="account-logout-form"' in content and 'action="/logout"' in content
    assert translate('Logout', language) in content
    if method == 'phone':
        assert translate('Phone login', language) in content
        assert translate('Google account', language) not in content
        assert 'value="+249912345678"' in content
    else:
        assert translate('Google account', language) in content
        assert translate('Google login', language) in content
        assert translate('Phone login', language) in content
        assert 'id="phone_number"' in content
        assert translate('Change WhatsApp/mobile number', language) in content
    for secret in ('private-provider-identifier', 'private-pending-auth-value', '777777', 'provider_user_id', 'otp_hash'):
        assert secret not in page


def test_removed_account_section_does_not_affect_my_properties(client, values):
    user = account_user(client)
    other = User(phone_number='+249911111111', is_verified=True)
    db.session.add(other)
    db.session.flush()
    add_property(values, owner_id=user.id, publication_status='published',
                 title_en='Owned Home', title_ar='Owned Home')
    add_property(values, owner_id=other.id, publication_status='published',
                 title_en='Other Home', title_ar='Other Home')
    db.session.commit()
    content = client.get('/account?lang=en&user_id=' + str(other.id)).text.split('<main', 1)[1]
    assert 'Your Properties' not in content and 'My Properties' not in content
    assert 'Owned Home' not in content and 'Other Home' not in content
    management = client.get('/my-properties?lang=en').text
    assert 'Owned Home' in management and 'Other Home' not in management


@pytest.mark.parametrize('method', ['phone', 'google'])
def test_profile_edit_keeps_identity_and_existing_validation(client, method):
    user = account_user(client, method)
    page = client.get('/account?lang=en')
    response = client.post('/account', data={'csrf_token': csrf(page), '_language': 'en',
        'contact_name': 'Edited Member', 'whatsapp': '0912222222' if method == 'phone' else '0911111111', 'contact_role': 'broker',
        'phone_number': '+249999999999', 'provider_user_id': 'forged-provider'})
    assert response.status_code == 200
    assert 'Account information updated successfully' in response.text
    assert '<bdi>Edited Member</bdi>' in response.text
    assert user.contact_name == 'Edited Member' and user.whatsapp == ('+249912222222' if method == 'phone' else '+249911111111') and user.contact_role == 'broker'
    assert user.phone_number == ('+249912345678' if method == 'phone' else '+249911111111')
    assert user.is_verified
    if method == 'google':
        assert db.session.query(UserIdentity).one().provider_user_id == 'private-provider-identifier'
    response = client.post('/account', data={'csrf_token': csrf(response), '_language': 'en',
        'contact_name': '', 'whatsapp': 'bad', 'contact_role': 'invalid'})
    assert response.status_code == 422
    assert 'aria-invalid="true" aria-describedby="contact-name-error"' in response.text
    assert 'aria-describedby="whatsapp-help whatsapp-error" aria-invalid="true"' in response.text
    assert 'aria-invalid="true" aria-describedby="contact-role-error"' in response.text
    assert user.contact_name == 'Edited Member' and user.whatsapp == ('+249912222222' if method == 'phone' else '+249911111111')
    assert client.post('/account').status_code == 400
    response = client.post('/logout', data={'csrf_token': csrf(response)})
    assert response.status_code == 303
    assert client.get('/account').status_code == 302


def test_google_display_name_fallback_without_contact_name_or_role(client):
    user = account_user(client, 'google')
    user.contact_name = user.contact_role = None
    db.session.commit()
    page = client.get('/account?lang=en').text
    assert '<bdi>Provider Display Name</bdi>' in page
    assert 'value="None"' not in page and 'private-provider-identifier' not in page
