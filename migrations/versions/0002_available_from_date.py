"""Add an optional property availability date.

Revision ID: 0002_available_from_date
Revises: 0001_properties
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_available_from_date"
down_revision = "0001_properties"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("properties", sa.Column("available_from_date", sa.Date(), nullable=True))


def downgrade():
    op.drop_column("properties", "available_from_date")
