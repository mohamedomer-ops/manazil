"""Create properties table

Revision ID: 0001_properties
Revises:
Create Date: 2026-09-27 08:14:48.882228

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0001_properties'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('properties',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('title_en', sa.String(), nullable=False),
    sa.Column('title_ar', sa.String(), nullable=False),
    sa.Column('description_en', sa.Text(), nullable=False),
    sa.Column('description_ar', sa.Text(), nullable=False),
    sa.Column('city_en', sa.String(), nullable=False),
    sa.Column('city_ar', sa.String(), nullable=False),
    sa.Column('area_en', sa.String(), nullable=False),
    sa.Column('area_ar', sa.String(), nullable=False),
    sa.Column('property_type', sa.String(), nullable=False),
    sa.Column('monthly_rent', sa.Numeric(), nullable=False),
    sa.Column('currency', sa.String(), server_default='SDG', nullable=False),
    sa.Column('bedrooms', sa.Integer(), nullable=False),
    sa.Column('bathrooms', sa.Integer(), nullable=False),
    sa.Column('size', sa.Numeric(), nullable=True),
    sa.Column('furnished', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('amenities', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('contact_name', sa.String(), nullable=False),
    sa.Column('phone', sa.String(), nullable=False),
    sa.Column('whatsapp', sa.String(), nullable=True),
    sa.Column('contact_role', sa.String(), server_default='owner', nullable=False),
    sa.Column('publication_status', sa.String(), server_default='draft', nullable=False),
    sa.Column('availability_status', sa.String(), server_default='available', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("area_ar ~ '[^[:space:]]'", name='ck_properties_area_ar_not_blank'),
    sa.CheckConstraint("area_en ~ '[^[:space:]]'", name='ck_properties_area_en_not_blank'),
    sa.CheckConstraint("availability_status IN ('available', 'rented')", name='ck_properties_availability_status'),
    sa.CheckConstraint("availability_status ~ '[^[:space:]]'", name='ck_properties_availability_status_not_blank'),
    sa.CheckConstraint("city_ar ~ '[^[:space:]]'", name='ck_properties_city_ar_not_blank'),
    sa.CheckConstraint("city_en ~ '[^[:space:]]'", name='ck_properties_city_en_not_blank'),
    sa.CheckConstraint("contact_name ~ '[^[:space:]]'", name='ck_properties_contact_name_not_blank'),
    sa.CheckConstraint("contact_role IN ('owner', 'broker')", name='ck_properties_contact_role'),
    sa.CheckConstraint("contact_role ~ '[^[:space:]]'", name='ck_properties_contact_role_not_blank'),
    sa.CheckConstraint("currency ~ '[^[:space:]]'", name='ck_properties_currency_not_blank'),
    sa.CheckConstraint("description_ar ~ '[^[:space:]]'", name='ck_properties_description_ar_not_blank'),
    sa.CheckConstraint("description_en ~ '[^[:space:]]'", name='ck_properties_description_en_not_blank'),
    sa.CheckConstraint("jsonb_typeof(amenities) = 'array'", name='ck_properties_amenities_array'),
    sa.CheckConstraint("monthly_rent >= 0 AND monthly_rent < 'Infinity'::numeric", name='ck_properties_rent_nonnegative'),
    sa.CheckConstraint("phone ~ '[^[:space:]]'", name='ck_properties_phone_not_blank'),
    sa.CheckConstraint("property_type ~ '[^[:space:]]'", name='ck_properties_property_type_not_blank'),
    sa.CheckConstraint("publication_status IN ('draft', 'pending', 'published', 'archived')", name='ck_properties_publication_status'),
    sa.CheckConstraint("publication_status ~ '[^[:space:]]'", name='ck_properties_publication_status_not_blank'),
    sa.CheckConstraint("size >= 0 AND size < 'Infinity'::numeric", name='ck_properties_size_nonnegative'),
    sa.CheckConstraint("title_ar ~ '[^[:space:]]'", name='ck_properties_title_ar_not_blank'),
    sa.CheckConstraint("title_en ~ '[^[:space:]]'", name='ck_properties_title_en_not_blank'),
    sa.CheckConstraint('bathrooms >= 0', name='ck_properties_bathrooms_nonnegative'),
    sa.CheckConstraint('bedrooms >= 0', name='ck_properties_bedrooms_nonnegative'),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('properties')
