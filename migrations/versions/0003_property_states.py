"""Store state separately from city for the property wizard.

Revision ID: 0003_property_states
Revises: 0002_available_from_date
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_property_states"
down_revision = "0002_available_from_date"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("properties", sa.Column("state_en", sa.String(), nullable=True))
    op.add_column("properties", sa.Column("state_ar", sa.String(), nullable=True))
    properties = sa.table(
        "properties", sa.column("city_en"), sa.column("city_ar"),
        sa.column("state_en"), sa.column("state_ar"),
    )
    op.execute(properties.update().values(state_en=properties.c.city_en, state_ar=properties.c.city_ar))
    op.alter_column("properties", "state_en", nullable=False)
    op.alter_column("properties", "state_ar", nullable=False)
    for language in ("en", "ar"):
        op.create_check_constraint(
            f"ck_properties_state_{language}_not_blank", "properties",
            f"state_{language} ~ '[^[:space:]]'",
        )


def downgrade():
    for language in ("ar", "en"):
        op.drop_constraint(f"ck_properties_state_{language}_not_blank", "properties", type_="check")
    op.drop_column("properties", "state_ar")
    op.drop_column("properties", "state_en")
