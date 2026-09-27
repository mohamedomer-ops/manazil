"""Add property photos and allow untranslated property text through review.

Revision ID: 0005_property_photos
Revises: 0004_optional_english_drafts
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_property_photos"
down_revision = "0004_optional_english_drafts"
branch_labels = None
depends_on = None

ENGLISH_FIELDS = ("title_en", "description_en", "city_en", "area_en")
CATEGORIES = ("exterior", "entrance", "living_room", "bedroom", "kitchen", "bathroom", "other")


def upgrade():
    for field in ENGLISH_FIELDS:
        op.drop_constraint(f"ck_properties_{field}_not_blank", "properties", type_="check")
    op.create_table(
        "property_photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("property_id", sa.Integer(), sa.ForeignKey("properties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False, unique=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(32), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(f"category IN ({', '.join(repr(category) for category in CATEGORIES)})", name="ck_property_photos_category"),
        sa.CheckConstraint("file_size > 0 AND file_size <= 5242880", name="ck_property_photos_file_size"),
        sa.CheckConstraint("display_order >= 0", name="ck_property_photos_display_order"),
        sa.CheckConstraint("content_type IN ('image/jpeg', 'image/png', 'image/webp')", name="ck_property_photos_content_type"),
    )
    op.create_index("ix_property_photos_property_id", "property_photos", ["property_id"])
    op.create_index("uq_property_photos_one_primary", "property_photos", ["property_id"], unique=True, postgresql_where=sa.text("is_primary"))


def downgrade():
    op.drop_index("uq_property_photos_one_primary", table_name="property_photos")
    op.drop_index("ix_property_photos_property_id", table_name="property_photos")
    op.drop_table("property_photos")
    for field in ENGLISH_FIELDS:
        op.create_check_constraint(
            f"ck_properties_{field}_not_blank", "properties",
            f"publication_status = 'draft' OR {field} ~ '[^[:space:]]'",
        )
