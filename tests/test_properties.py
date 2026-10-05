from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import inspect, insert, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema

from app import create_app, db
from app.models import Property, REQUIRED_TEXT_FIELDS


@pytest.fixture
def values():
    return {
        "title_en": "Apartment in Khartoum", "title_ar": "شقة في الخرطوم",
        "description_en": "A spacious apartment", "description_ar": "شقة واسعة",
        "state_en": "Khartoum", "state_ar": "الخرطوم",
        "city_en": "Khartoum", "city_ar": "الخرطوم",
        "area_en": "Al Riyadh", "area_ar": "الرياض",
        "property_type": "apartment", "monthly_rent": Decimal("125000.50"),
        "bedrooms": 2, "bathrooms": 1,
        "contact_name": "Ahmed Mohamed", "phone": "+249123456789",
    }


@pytest.fixture
def migrated_connection():
    app = create_app({"TESTING": True})
    with app.app_context(), db.engine.connect() as connection:
        transaction = connection.begin()
        try:
            schema = f"test_properties_{uuid4().hex}"
            connection.execute(CreateSchema(schema))
            # Only the generated test schema is visible; never touch public data.
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            config = Config(str(Path("migrations/alembic.ini")))
            config.set_main_option("script_location", "migrations")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            yield connection
        finally:
            transaction.rollback()


@pytest.fixture
def session(migrated_connection):
    with Session(bind=migrated_connection, join_transaction_mode="create_savepoint") as session:
        yield session


def test_model_and_defaults(values):
    property = Property(**values)
    assert Property.__tablename__ == "properties"
    assert property.publication_status == "draft"
    assert property.availability_status == "available"
    assert property.currency == "SDG"
    assert property.furnished is False
    assert property.contact_role == "owner"
    assert property.amenities == []
    assert property.size is None
    assert property.whatsapp is None
    other = Property(**values)
    property.amenities.append("Water")
    assert other.amenities == []


def test_english_text_can_be_empty_through_publication(session, values):
    english_fields = ("title_en", "description_en", "city_en", "area_en")
    property = Property(**(values | {field: "" for field in english_fields}))
    session.add(property)
    session.commit()
    assert all(getattr(property, field) == "" for field in english_fields)
    property.publication_status = "published"
    session.flush()
    assert property.publication_status == "published"


@pytest.mark.parametrize("role", ["owner", "broker"])
def test_save_and_retrieve_property(session, values, role):
    property = Property(**values, contact_role=role)
    session.add(property)
    session.commit()
    property_id = property.id
    assert isinstance(property_id, int)
    session.expunge_all()
    saved = session.get(Property, property_id)
    assert saved.title_ar == values["title_ar"]
    assert saved.monthly_rent == Decimal("125000.50")
    assert saved.contact_role == role
    assert saved.publication_status == "draft"
    assert saved.availability_status == "available"
    assert saved.currency == "SDG"
    assert saved.furnished is False
    assert saved.amenities == []
    assert saved.created_at.tzinfo is not None
    assert saved.updated_at.tzinfo is not None
    created_at, updated_at = saved.created_at, saved.updated_at
    saved.title_en = "Updated apartment"
    saved.amenities.append("Water")
    session.commit()
    session.refresh(saved)
    assert saved.updated_at > updated_at
    assert saved.created_at == created_at
    assert saved.amenities == ["Water"]


@pytest.mark.parametrize("field", ["monthly_rent", "bedrooms", "bathrooms", "size"])
def test_negative_numbers_rejected(values, field):
    with pytest.raises(ValueError, match=field):
        Property(**(values | {field: -1}))


@pytest.mark.parametrize("field,value", [
    ("contact_role", "admin"), ("publication_status", "visible"), ("publication_status", "pending"), ("publication_status", "archived"),
    ("availability_status", "unavailable"),
    ("monthly_rent", "NaN"), ("size", "Infinity"),
    ("bedrooms", 1.5), ("bathrooms", True), ("furnished", "false"),
    ("amenities", ["Water", 1]), ("amenities", "Water"),
])
def test_invalid_values_rejected(values, field, value):
    with pytest.raises(ValueError):
        Property(**(values | {field: value}))


@pytest.mark.parametrize("field", REQUIRED_TEXT_FIELDS)
@pytest.mark.parametrize("value", [None, "", " \t\n"])
def test_required_text_rejected(values, field, value):
    with pytest.raises(ValueError, match=field):
        Property(**(values | {field: value}))


@pytest.mark.parametrize("field", ["monthly_rent", "furnished"])
def test_required_numbers_and_boolean_reject_none(values, field):
    with pytest.raises(ValueError):
        Property(**(values | {field: None}))


def test_missing_required_field_rejected_on_save(session, values):
    del values["title_ar"]
    session.add(Property(**values))
    with pytest.raises(ValueError, match="title_ar"):
        session.flush()


def test_invalid_amenity_mutation_rejected(session, values):
    property = Property(**values)
    session.add(property)
    session.commit()
    property.amenities.append(123)
    with pytest.raises(ValueError, match="amenities"):
        session.flush()


def test_zero_values_and_optional_fields(session, values):
    property = Property(**(values | {
        "monthly_rent": 0, "bedrooms": 0, "bathrooms": 0, "size": 0,
        "whatsapp": "+249123456789", "furnished": True,
        "publication_status": "published", "availability_status": "rented",
    }))
    session.add(property)
    session.commit()
    assert property.size == Decimal(0)
    assert property.monthly_rent == Decimal(0)
    assert property.publication_status == "published"
    assert property.availability_status == "rented"


def test_migration_creates_table_and_version(migrated_connection):
    assert set(inspect(migrated_connection).get_table_names()) == {"properties", "property_photos", "users", "otp_challenges", "saved_properties", "user_identities", "alembic_version"}
    assert migrated_connection.scalar(text("SELECT version_num FROM alembic_version")) == "0018_property_comment"
    columns = inspect(migrated_connection).get_columns("properties")
    assert {column["name"] for column in columns} == set(Property.__table__.columns.keys())
    assert all(column['nullable'] for column in columns if column['name'] in ('latitude', 'longitude'))
    user_columns = {column['name']: column for column in inspect(migrated_connection).get_columns('users')}
    assert user_columns['avatar_storage_key']['nullable']
    assert user_columns['avatar_source']['nullable']
    assert user_columns['password_hash']['nullable']


def test_direct_publication_migration_preserves_unpublished_records(values):
    app = create_app({"TESTING": True})
    with app.app_context(), db.engine.connect() as connection:
        transaction = connection.begin()
        try:
            schema = f"test_lifecycle_{uuid4().hex}"
            connection.execute(CreateSchema(schema))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            config = Config(str(Path("migrations/alembic.ini")))
            config.set_main_option("script_location", "migrations")
            config.attributes["connection"] = connection
            command.upgrade(config, "0006_single_page_posting")
            from sqlalchemy import MetaData, Table
            table = Table("properties", MetaData(), autoload_with=connection)
            for status in ("pending", "archived", "published", "draft"):
                connection.execute(insert(table).values(**(values | {
                    "price": values["monthly_rent"], "rent_period": "monthly",
                    "publication_status": status,
                })))
            command.upgrade(config, "head")
            statuses = connection.execute(text("SELECT publication_status FROM properties ORDER BY id")).scalars().all()
            assert statuses == ["draft", "draft", "published", "draft"]
        finally:
            transaction.rollback()


@pytest.mark.parametrize("field,value", [
    ("monthly_rent", -1), ("bedrooms", -1), ("bathrooms", -1), ("size", -1),
    ("contact_role", "admin"), ("publication_status", "invalid"), ("publication_status", "pending"), ("publication_status", "archived"),
    ("availability_status", "invalid"), ("property_type", " \t"),
    ("title_ar", ""), ("title_ar", None),
])
def test_database_constraints_reject_bypassed_validation(migrated_connection, values, field, value):
    with pytest.raises(IntegrityError):
        with migrated_connection.begin_nested():
            migrated_connection.execute(insert(Property.__table__).values(**(values | {field: value})))


def test_database_server_defaults(migrated_connection, values):
    # Reflection excludes Python defaults, so this tests the migrated server defaults.
    from sqlalchemy import MetaData, Table

    table = Table("properties", MetaData(), autoload_with=migrated_connection)
    saved = migrated_connection.execute(insert(table).values(**(values | {"price": values["monthly_rent"], "rent_period": "monthly"})).returning(table)).mappings().one()
    assert saved["currency"] == "SDG"
    assert saved["furnished"] is False
    assert saved["contact_role"] == "owner"
    assert saved["publication_status"] == "draft"
    assert saved["availability_status"] == "available"
    assert saved["amenities"] == []
    assert saved["created_at"] is not None
    assert saved["updated_at"] is not None
