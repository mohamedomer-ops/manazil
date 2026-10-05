import json
import re
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Property
from app.property_forms import validate_posting
from app.property_rules import PROPERTY_RULES, field_rules, public_rules
from test_property_creation import client, form_data
from test_properties import migrated_connection, values


@pytest.mark.parametrize('kind', PROPERTY_RULES)
@pytest.mark.parametrize('transaction', ['rent', 'sale'])
def test_type_transaction_matrix(form_data, kind, transaction):
    form = form_data | {'property_type': kind, 'transaction_type': transaction,
                        'rent_period': 'monthly' if transaction == 'rent' else '',
                        'floor': '4', 'land_use': 'residential', 'property_occupancy': 'room'}
    _, data, errors = validate_posting(form, 'en')
    assert not errors
    rules = field_rules(kind, transaction)
    for field in ('bedrooms', 'bathrooms', 'floor', 'land_use'):
        if rules[field] == 'inapplicable':
            assert data[field] is None
    assert data['property_occupancy'] == ('room' if rules['property_occupancy'] == 'required' else 'entire_property')
    if rules['furnished'] == 'inapplicable':
        assert data['furnished'] is False


@pytest.mark.parametrize('kind', PROPERTY_RULES)
def test_required_and_optional_fields(form_data, kind):
    form = form_data | {'property_type': kind, 'floor': '1', 'land_use': 'mixed'}
    for field, requirement in field_rules(kind, 'rent').items():
        if field in ('furnished', 'rent_period', 'property_occupancy'):
            continue
        _, _, errors = validate_posting(form | {field: ''}, 'en')
        assert (field in errors) == (requirement == 'required')


@pytest.mark.parametrize('field,value', [('property_type', 'castle'), ('floor', '-1'),
    ('floor', '1.2'), ('floor', 'NaN'), ('floor', '2147483648'), ('floor', 'abc'),
    ('size', ''), ('bedrooms', ''), ('bathrooms', ''), ('transaction_type', 'lease'),
    ('property_occupancy', 'invalid'), ('rent_period', '')])
def test_invalid_fields(form_data, field, value):
    assert field in validate_posting(form_data | {field: value}, 'en')[2]


def test_sale_rejects_period_and_ignores_stale_occupancy(form_data):
    _, data, errors = validate_posting(form_data | {'transaction_type': 'sale', 'property_occupancy': 'bad'}, 'en')
    assert 'rent_period' in errors
    assert 'property_occupancy' not in errors
    assert data['rent_period'] is None


@pytest.mark.parametrize('land_use', ['residential', 'commercial', 'agricultural', 'industrial', 'mixed'])
def test_land_use_values(form_data, land_use):
    _, data, errors = validate_posting(form_data | {'property_type': 'land', 'land_use': land_use,
        'bedrooms': 'malicious', 'bathrooms': '-1', 'floor': 'invalid', 'furnished': 'bad'}, 'en')
    assert not errors
    assert data['land_use'] == land_use
    assert (data['bedrooms'], data['bathrooms'], data['floor'], data['furnished']) == (None, None, None, False)


def test_invalid_land_use(form_data):
    assert 'land_use' in validate_posting(form_data | {'property_type': 'land', 'land_use': 'unknown'}, 'en')[2]


def test_legacy_missing_facts_and_preserved_historical_values(form_data, values):
    old = Property(**values, size=None)
    _, data, errors = validate_posting(form_data | {'size': '', 'floor': ''}, 'en', existing=old)
    assert not errors
    assert data['size'] is None and data['floor'] is None
    old.property_type = 'land'
    old.property_occupancy = 'room'
    _, data, errors = validate_posting(form_data | {'property_type': 'land', 'land_use': ''}, 'en', existing=old)
    assert not errors
    assert data['bedrooms'] == old.bedrooms and data['property_occupancy'] == 'room'


def test_type_changes_persist_and_require_new_facts(client, form_data):
    assert client.post('/admin/properties', data=form_data).status_code == 303
    listing = db.session.scalar(select(Property).order_by(Property.id.desc()))
    url = f'/properties/{listing.id}/edit'
    page = client.get(url).text
    form_data = form_data | {'_photo_token': re.search(r'name="_photo_token" value="([^"]+)"', page).group(1)}
    assert client.post(url, data=form_data | {'property_type': 'land', 'land_use': 'commercial'}).status_code == 303
    db.session.refresh(listing)
    assert (listing.bedrooms, listing.bathrooms, listing.floor, listing.furnished) == (None, None, None, False)
    assert listing.land_use == 'commercial'
    assert client.get(f'/properties/{listing.id}?lang=en').status_code == 200
    assert client.post(url, data=form_data | {'floor': '', 'bedrooms': ''}).status_code == 422
    assert client.post(url, data=form_data).status_code == 303
    db.session.refresh(listing)
    assert listing.land_use is None and listing.bedrooms == 2 and listing.floor == 2


def test_metadata_is_safe_and_complete():
    metadata = json.loads(json.dumps(public_rules()))
    assert set(metadata['types']) == {'apartment', 'house', 'villa', 'land', 'office', 'shop', 'warehouse'}
    assert metadata['types']['land']['transactions']['sale']['bedrooms'] == 'inapplicable'


def test_model_nullable_facts(values):
    listing = Property(**(values | {'bedrooms': None, 'bathrooms': None, 'floor': None}))
    assert listing.bedrooms is None and listing.bathrooms is None
    for value in (-1, 1.5, '1'):
        with pytest.raises(ValueError):
            listing.floor = value


def test_migration_upgrade_and_safe_downgrade(migrated_connection, values):
    connection = migrated_connection
    config = Config(str(Path('migrations/alembic.ini')))
    config.set_main_option('script_location', 'migrations')
    config.attributes['connection'] = connection
    columns = {column['name']: column for column in inspect(connection).get_columns('properties')}
    assert columns['bedrooms']['nullable'] and columns['bathrooms']['nullable']
    assert 'floor' in columns and 'land_use' in columns
    connection.execute(Property.__table__.insert().values(**(values | {'bedrooms': None, 'price': 1, 'rent_period': 'monthly'})))
    with pytest.raises(RuntimeError, match='Cannot downgrade'):
        command.downgrade(config, '0016_property_coordinates')
    connection.execute(text('DELETE FROM properties'))
    command.downgrade(config, '0016_property_coordinates')
    assert not next(column for column in inspect(connection).get_columns('properties') if column['name'] == 'bedrooms')['nullable']
    # An old row is upgraded in place: zero facts remain zero; new fields are NULL.
    old_data = values | {'bedrooms': 0, 'bathrooms': 0, 'price': 1, 'rent_period': 'monthly'}
    connection.execute(text('INSERT INTO properties (' + ', '.join(old_data) + ') VALUES (' +
                            ', '.join(':' + key for key in old_data) + ')'), old_data)
    command.upgrade(config, 'head')
    row = connection.execute(text('SELECT bedrooms, bathrooms, floor, land_use FROM properties')).one()
    assert tuple(row) == (0, 0, None, None)


@pytest.mark.parametrize('field,value', [('floor', -1), ('land_use', 'unknown')])
def test_new_database_constraints(migrated_connection, values, field, value):
    with pytest.raises(IntegrityError), migrated_connection.begin_nested():
        migrated_connection.execute(Property.__table__.insert().values(
            **(values | {'price': 1, 'rent_period': 'monthly', field: value})))


@pytest.mark.parametrize('language', ['ar', 'en'])
def test_new_fields_and_warehouse_are_localized(client, language):
    from app.languages import translate
    page = client.get('/properties/new?lang=' + language).text
    assert 'value="warehouse"' in page and 'name="floor"' in page and 'name="land_use"' in page
    for label in ('Warehouse', 'Floor', 'Land use', 'Residential', 'Commercial',
                  'Agricultural', 'Industrial', 'Mixed use'):
        assert translate(label, language) in page
