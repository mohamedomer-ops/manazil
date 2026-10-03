"""Add optional Manazil-managed avatar key and source to users."""
from alembic import op
import sqlalchemy as sa

revision = '0013_user_avatar'
down_revision = '0012_admin_authorization'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('avatar_storage_key', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('avatar_source', sa.String(16), nullable=True))
    op.create_check_constraint('ck_users_avatar_source', 'users',
                               "avatar_source IN ('facebook', 'manual')")


def downgrade():
    op.drop_constraint('ck_users_avatar_source', 'users', type_='check')
    op.drop_column('users', 'avatar_source')
    op.drop_column('users', 'avatar_storage_key')
