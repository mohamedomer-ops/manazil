"""Account profile claims never replace provider identities or phone credentials."""
import time

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app import db
from app.google_auth import populate_google_profile
from app.google_provider import GoogleAuthProvider, GoogleIdentity
from app.languages import translate
from app.models import User, UserIdentity
from test_auth import client, csrf
from test_manual_signup import register
from test_properties import migrated_connection
from test_google_auth import (google_client, isolated_google_environment, begin,
                              CLIENT_ID, CLIENT_SECRET, CALLBACK, FakeResponse, _with_claims)


@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
def test_manual_profile_and_localization(client, language, direction):
    page = client.get('/signup?lang=' + language)
    assert f'dir="{direction}"' in page.text
    for label in ('First name', 'Last name', 'Email address'):
        assert translate(label, language) in page.text
    response = register(client, name='Ahmed Ali', email='  AHMED@Example.Test  ', language=language)
    assert response.status_code == 303
    user = db.session.scalar(select(User))
    assert (user.first_name, user.last_name, user.contact_name) == ('Ahmed', 'Ali', 'Ahmed Ali')
    assert user.email == 'ahmed@example.test' and user.email_verified is False
    assert user.is_verified is False and user.check_password('correct-horse-password')


@pytest.mark.parametrize('field,value', [('first_name', ''), ('last_name', ''), ('email', ''),
                                        ('email', 'not-email'), ('first_name', 'x' * 101)])
def test_required_profile_validation_and_retention(client, field, value):
    data = {'first_name': 'Ahmed', 'last_name': 'Ali', 'email': 'member@example.test',
            'phone_number': '0912345678', 'password': 'test-password',
            'confirm_password': 'test-password', '_language': 'en',
            'csrf_token': csrf(client.get('/signup'))}
    data[field] = value
    response = client.post('/signup', data=data)
    assert response.status_code == 422
    assert f'id="{field}-error"' in response.text
    assert db.session.scalar(select(User)) is None
    if field != 'last_name':
        assert 'value="Ali"' in response.text


def test_duplicate_email_is_generic_and_does_not_merge(client):
    assert register(client).status_code == 303
    original = db.session.scalar(select(User))
    response = register(client, phone='0911111111', email='MEMBER@EXAMPLE.TEST')
    assert response.status_code == 409
    assert 'Unable to create an account with these details.' in response.text
    assert 'email is already' not in response.text.lower()
    assert db.session.query(User).count() == 1
    assert original.phone_number == '+249912345678' and not original.email_verified


@pytest.mark.parametrize('email,verified,expected', [
    ('MEMBER@Example.Test', True, True), ('member@example.test', False, False),
    ('member@example.test', 'true', False), (None, True, False),
])
def test_google_optional_profile_claims(monkeypatch, email, verified, expected):
    provider = GoogleAuthProvider(CLIENT_ID, CLIENT_SECRET, CALLBACK)
    monkeypatch.setattr('app.google_provider.urlopen', lambda *a, **k: FakeResponse({'id_token': 'mock-id-token'}))
    claims = {'sub': 'stable-sub', 'iss': 'https://accounts.google.com', 'aud': CLIENT_ID,
              'nonce': 'nonce', 'exp': time.time() + 3600, 'given_name': ' Ahmed ',
              'family_name': ' Ali ', 'email_verified': verified}
    if email is not None:
        claims['email'] = email
    identity = _with_claims(provider, claims)
    assert identity.provider_user_id == 'stable-sub'
    assert identity.email == ('member@example.test' if email else None)
    assert identity.email_verified is expected
    assert (identity.first_name, identity.last_name) == ('Ahmed', 'Ali')


@pytest.mark.parametrize('email,verified', [('MEMBER@example.test', True),
                                         ('member@example.test', False), (None, False)])
def test_google_callback_persists_profile(google_client, monkeypatch, email, verified):
    identity = GoogleIdentity('profile-sub', 'Ahmed Ali', None, 'Ahmed', 'Ali', email, verified)
    monkeypatch.setattr(GoogleAuthProvider, 'authenticate', lambda *a: identity)
    _, state = begin(google_client)
    response = google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'mock-code'})
    assert response.location == '/?lang=en'
    user = db.session.get(UserIdentity, ('google', 'profile-sub')).user
    assert user.email == ('member@example.test' if email else None)
    assert user.email_verified is verified
    assert (user.first_name, user.last_name) == ('Ahmed', 'Ali')
    assert not user.is_verified


def test_google_email_conflict_does_not_link_accounts(google_client, monkeypatch):
    register(google_client)
    manual = db.session.scalar(select(User))
    identity = GoogleIdentity('separate-sub', 'Mohamed Ahmed', None, 'Mohamed', 'Ahmed', 'member@example.test', True)
    monkeypatch.setattr(GoogleAuthProvider, 'authenticate', lambda *a: identity)
    _, state = begin(google_client)
    response = google_client.get('/auth/google/callback', query_string={'state': state, 'code': 'mock-code'})
    assert response.location == '/?lang=en'
    social = db.session.get(UserIdentity, ('google', 'separate-sub')).user
    assert social.id != manual.id and social.email is None and not social.email_verified
    assert manual.email == 'member@example.test' and not manual.email_verified
    assert manual.check_password('correct-horse-password')
    assert db.session.query(User).count() == 2


def test_google_preserves_user_profile_and_promotes_matching_email(client):
    user = User(first_name='Chosen', last_name='Name', contact_name='Custom display',
                email='member@example.test', email_verified=False)
    db.session.add(user)
    db.session.flush()
    populate_google_profile(user, GoogleIdentity('sub', 'Provider display', None, 'Other', 'Person',
                                                'member@example.test', True))
    assert user.email_verified and user.contact_name == 'Custom display'
    assert (user.first_name, user.last_name) == ('Chosen', 'Name')
    populate_google_profile(user, GoogleIdentity('sub', 'Other', None, None, None, 'changed@example.test', True))
    assert user.email == 'member@example.test' and user.email_verified
    populate_google_profile(user, GoogleIdentity('sub', 'Other', None, None, None, 'member@example.test', False))
    assert user.email_verified


def test_email_race_keeps_google_account_and_transaction_usable(client, monkeypatch):
    db.session.add(User(email='taken@example.test'))
    user = User()
    db.session.add(user)
    db.session.flush()
    with monkeypatch.context() as patch:
        patch.setattr(db.session, 'scalar', lambda *a, **k: None)
        populate_google_profile(user, GoogleIdentity('sub', 'Name', None, 'First', 'Last', 'taken@example.test', True))
    assert user.email is None and not user.email_verified
    assert user.first_name == 'First'
    assert db.session.query(User).count() == 2


def test_email_changes_clear_verification_and_names_fill_only_blanks(client):
    user = User(last_name='Chosen', email='MEMBER@example.test', email_verified=True)
    user.email = 'member@EXAMPLE.TEST'
    assert user.email_verified
    user.email = 'new@example.test'
    assert user.email_verified is False
    db.session.add(user)
    db.session.flush()
    populate_google_profile(user, GoogleIdentity('sub', 'Provider', None, 'First', 'Other', None, False))
    assert (user.first_name, user.last_name) == ('First', 'Chosen')
    user.email = None
    assert user.email is None and user.email_verified is False


def test_email_schema_is_sqlite_compatible():
    engine = create_engine('sqlite://')
    User.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(User.__table__.insert(), [{'email': None}, {'email': None}])
        connection.execute(User.__table__.insert().values(email='member@example.test'))
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(User.__table__.insert().values(email='member@example.test'))
    engine.dispose()


def test_profile_migration_roundtrip(migrated_connection):
    config = Config('migrations/alembic.ini')
    config.set_main_option('script_location', 'migrations')
    config.attributes['connection'] = migrated_connection
    command.downgrade(config, '0018_property_comment')
    migrated_connection.execute(text("INSERT INTO users (phone_number, password_hash, is_verified, is_active, role, created_at, updated_at) VALUES ('+249912345678', 'existing-hash', false, true, 'user', now(), now())"))
    command.upgrade(config, 'head')
    assert migrated_connection.execute(text('SELECT email, email_verified FROM users')).one() == (None, False)
    migrated_connection.execute(text("UPDATE users SET email = 'member@example.test'"))
    with pytest.raises(IntegrityError), migrated_connection.begin_nested():
        migrated_connection.execute(text("INSERT INTO users (email, is_verified, is_active, role, created_at, updated_at) VALUES ('member@example.test', false, true, 'user', now(), now())"))
    command.downgrade(config, '0018_property_comment')
    assert 'email' not in {column['name'] for column in inspect(migrated_connection).get_columns('users')}
    assert migrated_connection.scalar(text('SELECT password_hash FROM users')) == 'existing-hash'
    command.upgrade(config, 'head')
