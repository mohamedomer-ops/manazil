"""Public poster identity uses the posting account, not listing contact snapshots."""
import io
import re

import pytest
from flask import current_app
from PIL import Image

from app import db
from app.models import User, UserIdentity
from app.photo_storage import photo_storage
from test_auth import client
from test_properties import migrated_connection, values
from test_public_properties import add_property


def poster_property(values, **changes):
    user = User(contact_name='Posting Account', is_verified=changes.pop('verified', False))
    db.session.add(user)
    db.session.flush()
    property = add_property(values, owner_id=user.id, publication_status='published',
                            contact_name='Separate Listing Contact', **changes)
    return user, property


@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
@pytest.mark.parametrize('role', ['owner', 'broker'])
def test_poster_identity_on_all_public_surfaces(client, values, language, direction, role):
    from app.languages import translate
    user, property = poster_property(values, contact_role=role, verified=True)
    suffix = '?lang=en' if language == 'en' else ''
    for route in ('/', '/properties', f'/properties/{property.id}'):
        html = client.get(route + suffix).text
        assert f'<html lang="{language}" dir="{direction}">' in html
        strip = re.search(r'<div class="poster-identity.*?</div>\s*</div>', html, re.S).group()
        assert 'Posting Account' in strip and 'Separate Listing Contact' not in strip
        assert translate('Owner' if role == 'owner' else 'Broker', language) in strip
        assert f'aria-label="{translate("Verified account", language)}"' in strip
        assert 'poster-avatar-fallback' in strip
        assert 'password' not in strip and 'phone_number' not in strip
        if route != f'/properties/{property.id}':
            assert f'href="/properties/{property.id}{suffix}"' in html
            assert html.index('class="poster-identity') < html.index('class="property-card-media"')
            assert 'market-result-save' in html
        else:
            assert 'Separate Listing Contact' in html and 'tel:+249123456789' in html
            assert 'https://wa.me/249123456789' in html


def test_unverified_poster_has_no_badge(client, values):
    user, property = poster_property(values)
    for route in ('/', '/properties', f'/properties/{property.id}'):
        html = client.get(route + '?lang=en').text
        assert 'poster-verified' not in html


def test_identity_name_fallback_is_escaped_and_does_not_expose_provider_id(client, values):
    user, property = poster_property(values)
    user.contact_name = None
    db.session.add(UserIdentity(provider='google', provider_user_id='private-provider-id',
                               display_name='<b>Social Name</b>', user=user))
    db.session.commit()
    html = client.get('/?lang=en').text
    assert '&lt;b&gt;Social Name&lt;/b&gt;' in html
    assert 'private-provider-id' not in html


def test_legacy_property_without_owner_has_safe_fallback(client, values):
    property = add_property(values, publication_status='published')
    html = client.get(f'/properties/{property.id}?lang=en').text
    assert 'Property poster' in html and 'poster-avatar-fallback' in html
    assert 'poster-verified' not in html


def test_public_avatar_uses_existing_storage_and_visibility(client, values, monkeypatch, tmp_path):
    monkeypatch.setitem(current_app.config, 'PHOTO_STORAGE_ROOT', str(tmp_path))
    user, property = poster_property(values)
    output = io.BytesIO()
    Image.new('RGB', (40, 40), 'green').save(output, 'WEBP')
    user.avatar_storage_key = photo_storage().save_avatar(user.id, output.getvalue())
    user.avatar_source = 'manual'
    db.session.commit()
    path = f'/properties/{property.id}/poster-avatar'
    html = client.get('/?lang=en').text
    assert f'src="{path}"' in html and user.avatar_storage_key not in html
    response = client.get(path)
    assert response.status_code == 200 and response.mimetype == 'image/webp'
    assert response.data == output.getvalue()
    assert response.headers['Cache-Control'] == 'private, no-store'
    property.moderation_status = 'disabled'
    db.session.commit()
    assert client.get(path).status_code == 404


@pytest.mark.parametrize('key', ['../secret.webp', 'avatars/999/00000000000000000000000000000000.webp'])
def test_public_avatar_rejects_unsafe_or_other_account_keys(client, values, key):
    user, property = poster_property(values)
    user.avatar_storage_key = key
    db.session.commit()
    assert client.get(f'/properties/{property.id}/poster-avatar').status_code == 404


def test_missing_avatar_returns_404_with_rendered_fallback(client, values):
    user, property = poster_property(values)
    html = client.get('/?lang=en').text
    assert 'poster-avatar-fallback' in html and '/poster-avatar' not in html
    assert client.get(f'/properties/{property.id}/poster-avatar').status_code == 404
