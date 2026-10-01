"""Add account-owned saved-property relationships."""
from alembic import op
import sqlalchemy as sa

revision = '0010_saved_properties'
down_revision = '0009_user_contact_profile'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('saved_properties',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('property_id', sa.Integer(), sa.ForeignKey('properties.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index('ix_saved_properties_property_id', 'saved_properties', ['property_id'])


def downgrade():
    op.drop_index('ix_saved_properties_property_id', 'saved_properties')
    op.drop_table('saved_properties')
