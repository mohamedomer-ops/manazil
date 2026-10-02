"""Add explicit administrator rights and reversible listing moderation."""
from alembic import op
import sqlalchemy as sa

revision = '0012_admin_authorization'
down_revision = '0011_facebook_identity'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('role', sa.String(16), nullable=False, server_default='user'))
    op.create_check_constraint('ck_users_role', 'users', "role IN ('user', 'admin')")
    op.add_column('properties', sa.Column('moderation_status', sa.String(16), nullable=False, server_default='clear'))
    op.create_check_constraint('ck_properties_moderation_status', 'properties', "moderation_status IN ('clear', 'disabled')")


def downgrade():
    op.drop_constraint('ck_properties_moderation_status', 'properties', type_='check')
    op.drop_column('properties', 'moderation_status')
    op.drop_constraint('ck_users_role', 'users', type_='check')
    op.drop_column('users', 'role')
