"""Allow Google-sourced account avatars alongside Facebook and manual avatars."""
from alembic import op

revision = '0015_google_avatar_source'
down_revision = '0014_user_password_hash'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('ck_users_avatar_source', 'users', type_='check')
    op.create_check_constraint('ck_users_avatar_source', 'users',
                               "avatar_source IN ('facebook', 'google', 'manual')")


def downgrade():
    # A downgrade must not silently discard managed Google avatar references.
    connection = op.get_bind()
    if connection.exec_driver_sql("SELECT 1 FROM users WHERE avatar_source = 'google' LIMIT 1").first():
        raise RuntimeError('Remove Google avatars explicitly before downgrading this constraint.')
    op.drop_constraint('ck_users_avatar_source', 'users', type_='check')
    op.create_check_constraint('ck_users_avatar_source', 'users',
                               "avatar_source IN ('facebook', 'manual')")
