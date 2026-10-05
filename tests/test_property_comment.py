import re
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text

from app import db
from app.models import MAX_COMMENT_LENGTH, Property
from test_properties import migrated_connection, values
from test_property_creation import client, form_data


def latest():
    return db.session.scalar(select(Property).order_by(Property.id.desc()))


@pytest.mark.parametrize('agent', ['yes', 'no'])
@pytest.mark.parametrize('comment,expected', [(None, None), ('  ', None), ('  A personal note  ', 'A personal note')])
def test_create_optional_comment(client, form_data, agent, comment, expected):
    data = form_data | {'agent': agent}
    if comment is not None:
        data['comment'] = comment
    assert client.post('/admin/properties', data=data).status_code == 303
    listing = latest()
    assert listing.comment == expected
    assert listing.description_ar == form_data['description_ar']
    page = client.get(f'/properties/{listing.id}?lang=en').text
    assert ('id="comment-heading">Comment</h2>' in page) == bool(expected)
    if expected:
        assert expected in page


@pytest.mark.parametrize('comment', ['x' * (MAX_COMMENT_LENGTH + 1), 'bad\x00note'])
def test_comment_validation(client, form_data, comment):
    response = client.post('/admin/properties', data=form_data | {'comment': comment})
    assert response.status_code == 422
    assert 'data-initial-section="description"' in response.text
    assert latest() is None


@pytest.mark.parametrize('action,status', [('switch_ar', 200), ('switch_en', 200), ('submit', 422)])
def test_comment_survives_rerender(client, form_data, action, status):
    response = client.post('/admin/properties', data=form_data | {
        'comment': 'Separate personal note', '_action': action, 'price': '',
        '_wizard_section': 'description'})
    assert response.status_code == status
    assert 'Separate personal note</textarea>' in response.text


def test_edit_comment_and_escape(client, form_data):
    unsafe = '<script>alert(1)</script>'
    assert client.post('/admin/properties', data=form_data | {'comment': unsafe}).status_code == 303
    listing = latest()
    route = f'/properties/{listing.id}/edit?lang=en'
    page = client.get(route).text
    assert '&lt;script&gt;alert(1)&lt;/script&gt;</textarea>' in page
    public = client.get(f'/properties/{listing.id}?lang=en').text
    assert unsafe not in public
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in public
    for note in ['Updated note', '   ']:
        page = client.get(route).text
        token = re.search(r'name="_photo_token" value="([^"]+)"', page).group(1)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        assert client.post(route, data=form_data | {'_photo_token': token, 'csrf_token': csrf,
                           'comment': note}).status_code == 303
        assert listing.comment == (note.strip() or None)
        assert listing.publication_status == 'published'


def test_legacy_edit_preserves_comment_and_description_independence(client, form_data):
    assert client.post('/admin/properties', data=form_data | {'comment': 'Keep note'}).status_code == 303
    listing = latest()
    route = f'/properties/{listing.id}/edit'
    page = client.get(route).text
    token = re.search(r'name="_photo_token" value="([^"]+)"', page).group(1)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    assert client.post(route, data=form_data | {'_photo_token': token, 'csrf_token': csrf,
                       'description_ar': 'New description'}).status_code == 303
    assert listing.comment == 'Keep note'
    assert listing.description_ar == 'New description'


@pytest.mark.parametrize('language,heading,direction', [
    ('en', 'What do you want to do with your property?', 'ltr'),
    ('ar', 'ماذا تريد أن تفعل بعقارك؟', 'rtl')])
def test_wizard_visual_structure(client, language, heading, direction):
    page = client.get('/properties/new?lang=' + language).text
    assert heading in page and f'dir="{direction}"' in page
    assert 'choice-status-dot' in page and 'choice-check' not in page
    for value in ['rent', 'sale', 'apartment', 'house', 'villa', 'land', 'office', 'shop', 'warehouse', 'room', 'entire_property']:
        assert f'data-option-icon="{value}"' in page
    assert f'maxlength="{MAX_COMMENT_LENGTH}"' in page
    assert 'name="comment"' in page
    js = Path('app/static/js/property-form.js').read_text(encoding='utf-8')
    assert 'wizard-progress' not in js and 'wizard-progress' not in page
    assert '"? "' not in js and 'textContent' in js
    css = Path('app/static/css/style.css').read_text(encoding='utf-8')
    assert '.choice-status-dot' in css


def test_comment_model_validation(values):
    assert Property(**values, comment='  ').comment is None
    assert Property(**values, comment=' note ').comment == 'note'
    for invalid in ['x' * (MAX_COMMENT_LENGTH + 1), 'bad\x00note']:
        with pytest.raises(ValueError):
            Property(**values, comment=invalid)


def test_comment_migration_roundtrip(migrated_connection):
    config = Config('migrations/alembic.ini')
    config.set_main_option('script_location', 'migrations')
    config.attributes['connection'] = migrated_connection
    command.downgrade(config, '0017_property_rules')
    assert 'comment' not in {c['name'] for c in inspect(migrated_connection).get_columns('properties')}
    migrated_connection.execute(text("""INSERT INTO properties
        (title_en, title_ar, description_en, description_ar, state_en, state_ar,
         city_en, city_ar, area_en, area_ar, property_type, bedrooms, bathrooms,
         price, currency, rent_period, contact_name, phone)
        VALUES ('Legacy', 'Legacy', 'Description', 'Description', 'Khartoum', 'Khartoum',
                '', '', '', '', 'apartment', 2, 1, 100, 'SDG', 'monthly', 'Poster', '+249912345678')"""))
    command.upgrade(config, 'head')
    column = next(c for c in inspect(migrated_connection).get_columns('properties') if c['name'] == 'comment')
    assert column['nullable']
    assert migrated_connection.scalar(text('SELECT version_num FROM alembic_version')) == '0021_password_reset'
    assert migrated_connection.scalar(text('SELECT comment FROM properties')) is None
    migrated_connection.execute(text("UPDATE properties SET comment = 'Manual note'"))
    command.downgrade(config, '0017_property_rules')
    assert 'description_ar' in {c['name'] for c in inspect(migrated_connection).get_columns('properties')}
    assert migrated_connection.scalar(text('SELECT description_ar FROM properties')) == 'Description'
    command.upgrade(config, 'head')
