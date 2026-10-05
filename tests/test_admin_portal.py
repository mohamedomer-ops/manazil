"""Administrator access and marketplace-management regression coverage."""
from flask import current_app
from sqlalchemy import select

from app import db
from app.models import Property, User
from app.phone import normalize_phone
from test_auth import client, csrf
from test_properties import migrated_connection, values


def account(phone, role='user'):
    user = User(phone_number=normalize_phone(phone), is_verified=True, is_active=True,
                role=role, contact_name='Test account', whatsapp=normalize_phone(phone), contact_role='owner')
    db.session.add(user)
    db.session.commit()
    return user


def admin_login(client, phone='0912345678', next='/admin'):
    page = client.get('/admin/login?lang=en&next=' + next)
    result = client.post('/admin/login', data={'csrf_token': csrf(page), 'phone_number': phone,
                                               'next': next, '_language': 'en'})
    assert result.status_code == 303, result.get_data(as_text=True)
    code = current_app.extensions['development_otps'][normalize_phone(phone)]
    page = client.get('/admin/verify?lang=en')
    return client.post('/admin/verify', data={'csrf_token': csrf(page), 'code': code, '_language': 'en'})


def property_record(values, owner_id=None, **changes):
    item = Property(**(values | {'owner_id': owner_id, 'publication_status': 'published',
                                 'neighborhood_ar': 'الرياض'} | changes))
    db.session.add(item)
    db.session.commit()
    return item


def test_admin_login_separate_and_authorization(client):
    admin = account('0912345678', role='admin')
    normal = account('0912345679')
    assert client.get('/admin/login').status_code == 200
    for path in ('/admin', '/admin/properties', '/admin/users', '/admin/reports', '/admin/admins'):
        response = client.get(path)
        assert response.status_code == 302 and '/admin/login' in response.location
    assert admin_login(client, phone='0912345679').status_code == 403
    with client.session_transaction() as state:
        state['user_id'] = normal.id
        state['admin_authenticated'] = True
    assert client.get('/admin').status_code == 403
    with client.session_transaction() as state:
        state['user_id'] = admin.id
        state['admin_authenticated'] = False
    admin_result = admin_login(client)
    assert admin_result.location == '/?lang=en', (admin_result.status_code, admin_result.get_data(as_text=True))
    for path in ('/admin', '/admin/properties', '/admin/users', '/admin/reports', '/admin/admins'):
        assert client.get(path).status_code == 200
    assert client.post('/admin/logout', data={'csrf_token': csrf(client.get('/admin'))}).status_code == 303
    assert client.get('/admin').status_code == 302


def test_admin_login_otp_and_safe_destination(client):
    account('0912345678', role='admin')
    page = client.get('/admin/login?lang=en')
    assert client.post('/admin/login', data={'csrf_token': csrf(page), 'phone_number': 'bad'}).status_code == 422
    response = client.post('/admin/login', data={'csrf_token': csrf(page), 'phone_number': '0912345678',
                                                  'next': '//example.com'})
    assert response.status_code == 303
    verify_page = client.get('/admin/verify')
    assert client.post('/admin/verify', data={'csrf_token': csrf(verify_page), 'code': '000000'}).status_code == 422
    code = current_app.extensions['development_otps']['+249912345678']
    assert client.post('/admin/verify', data={'csrf_token': csrf(verify_page), 'code': code}).location == '/'
    assert client.post('/admin/properties/1/moderate', data={'action': 'disable'}).status_code == 400


def test_property_moderation_is_reversible_and_private(client, values):
    admin = account('0912345678', role='admin')
    owner = account('0912345679')
    item = property_record(values, owner_id=owner.id)
    assert client.get(f'/properties/{item.id}').status_code == 200
    admin_login(client)
    page = client.get(f'/admin/properties/{item.id}?lang=en')
    assert page.status_code == 200 and b'Disable Property' in page.data
    route = f'/admin/properties/{item.id}/moderate'
    assert client.get(route).status_code == 405
    assert client.post(route, data={'action': 'disable'}).status_code == 400
    assert client.post(route, data={'csrf_token': csrf(page), 'action': 'disable'}).status_code == 303
    db.session.refresh(item)
    assert item.moderation_status == 'disabled' and item.publication_status == 'published'
    assert client.get(f'/properties/{item.id}').status_code == 404
    assert f'href="/properties/{item.id}"' not in client.get('/properties?lang=en').get_data(as_text=True)
    assert client.get(f'/admin/properties/{item.id}').status_code == 200
    page = client.get(f'/admin/properties/{item.id}')
    assert client.post(route, data={'csrf_token': csrf(page), 'action': 'restore'}).status_code == 303
    assert client.get(f'/properties/{item.id}').status_code == 200


def test_user_suspension_and_admin_role_safety(client):
    admin = account('0912345678', role='admin')
    user = account('0912345679')
    admin_login(client)
    page = client.get(f'/admin/users/{user.id}?lang=en')
    assert page.status_code == 200
    status_route = f'/admin/users/{user.id}/status'
    assert client.post(status_route, data={'csrf_token': csrf(page), 'action': 'suspend'}).status_code == 303
    assert not user.is_active
    assert client.post(f'/admin/users/{admin.id}/status', data={'csrf_token': csrf(page), 'action': 'suspend'}).status_code == 409
    assert client.post('/admin/admins/promote', data={'csrf_token': csrf(page), 'user_id': user.id}).status_code == 409
    assert client.post(status_route, data={'csrf_token': csrf(page), 'action': 'reactivate'}).status_code == 303
    assert client.post('/admin/admins/promote', data={'csrf_token': csrf(page), 'user_id': user.id}).status_code == 303
    assert user.role == 'admin'
    assert client.post(f'/admin/admins/{admin.id}/role', data={'csrf_token': csrf(page), 'action': 'revoke'}).status_code == 409
    assert client.post(f'/admin/admins/{user.id}/role', data={'csrf_token': csrf(page), 'action': 'revoke'}).status_code == 303
    assert user.role == 'user'
    user.is_active = False
    db.session.commit()
    with client.session_transaction() as state:
        state['user_id'] = user.id
        state.pop('admin_authenticated', None)
    assert client.get('/account').status_code == 302


def test_admin_reports_filters_and_languages(client, values):
    admin = account('0912345678', role='admin')
    property_record(values, owner_id=admin.id, transaction_type='sale', rent_period=None, availability_status='rented')
    admin_login(client)
    english = client.get('/admin?lang=en')
    arabic = client.get('/admin')
    assert b'Dashboard' in english.data and 'لوحة التحكم'.encode() in arabic.data
    assert b'dir="ltr"' in english.data and b'dir="rtl"' in arabic.data
    assert client.get('/admin/properties?transaction_type=sale&availability_status=rented').status_code == 200
    assert client.get('/admin/properties?transaction_type=invalid').status_code == 200
    reports = client.get('/admin/reports?lang=en')
    assert b'Properties by State' in reports.data and b'Rent vs Sale' in reports.data
    assert b'New Users Over Time' in reports.data
    assert 'التقارير'.encode() in client.get('/admin/reports').data
    assert b'/admin/login' not in client.get('/?lang=en').data


def test_admin_defaults_and_post_only_guards(client, values):
    admin = account('0912345678', role='admin')
    user = account('0912345679')
    item = property_record(values, owner_id=user.id)
    assert item.moderation_status == 'clear' and user.role == 'user'
    ordinary = User(phone_number='+249911111111', is_verified=True)
    db.session.add(ordinary)
    db.session.commit()
    assert ordinary.role == 'user'
    admin_login(client)
    routes = (f'/admin/properties/{item.id}/moderate', f'/admin/users/{user.id}/status',
              f'/admin/admins/{user.id}/role', '/admin/admins/promote')
    for route in routes:
        assert client.get(route).status_code == 405
        assert client.post(route, data={'action': 'disable'}).status_code == 400
    token = csrf(client.get('/admin/admins'))
    assert client.post('/admin/admins/promote', data={'csrf_token': token, 'user_id': '999999'}).status_code == 404
    assert client.post(f'/admin/users/{user.id}/status', data={'csrf_token': token,
                                                               'action': 'nonsense'}).status_code == 400
    assert client.post(f'/admin/properties/{item.id}/moderate', data={'csrf_token': token,
                                                                      'action': 'nonsense'}).status_code == 400


def test_cli_requires_existing_user_and_retains_one_admin(client):
    admin = account('0912345678', role='admin')
    other = account('0912345679')
    runner = current_app.test_cli_runner()
    assert runner.invoke(args=['grant-admin', '0912345679']).exit_code == 0
    assert other.role == 'admin'
    assert runner.invoke(args=['revoke-admin', '0912345679']).exit_code == 0
    assert other.role == 'user'
    assert runner.invoke(args=['revoke-admin', '0912345678']).exit_code != 0
    assert runner.invoke(args=['grant-admin', '0911111111']).exit_code != 0
    assert db.session.get(User, admin.id).role == 'admin'
