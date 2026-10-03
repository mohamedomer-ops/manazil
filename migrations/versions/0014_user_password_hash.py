"""Add optional password credentials for manual accounts."""
from alembic import op
import sqlalchemy as sa

revision = '0014_user_password_hash'
down_revision = '0013_user_avatar'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('password_hash', sa.String(255), nullable=True))


def downgrade():
    op.drop_column('users', 'password_hash')
