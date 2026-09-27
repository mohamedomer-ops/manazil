"""Allow Arabic-only draft properties while preserving bilingual publication.

Revision ID: 0004_optional_english_drafts
Revises: 0003_property_states
"""
from alembic import op


revision = "0004_optional_english_drafts"
down_revision = "0003_property_states"
branch_labels = None
depends_on = None


ENGLISH_FIELDS = ("title_en", "description_en", "city_en", "area_en")


def upgrade():
    for field in ENGLISH_FIELDS:
        name = f"ck_properties_{field}_not_blank"
        op.drop_constraint(name, "properties", type_="check")
        op.create_check_constraint(
            name, "properties", f"publication_status = 'draft' OR {field} ~ '[^[:space:]]'"
        )


def downgrade():
    for field in ENGLISH_FIELDS:
        name = f"ck_properties_{field}_not_blank"
        op.drop_constraint(name, "properties", type_="check")
        op.create_check_constraint(name, "properties", f"{field} ~ '[^[:space:]]'")
