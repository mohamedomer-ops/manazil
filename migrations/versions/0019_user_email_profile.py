"""Optional account names and unique normalized email for future recovery."""
from alembic import op
import sqlalchemy as sa

revision = '0019_user_email_profile'
down_revision = '0018_property_comment'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('first_name', sa.String(100), nullable=True))
    op.add_column('users', sa.Column('last_name', sa.String(100), nullable=True))
    op.add_column('users', sa.Column('email', sa.String(254), nullable=True))
    op.add_column('users', sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index('uq_users_email_lower', 'users', [sa.text('lower(email)')], unique=True)
    op.create_check_constraint('ck_users_email_normalized', 'users', 'email IS NULL OR email = lower(trim(email))')
    op.create_check_constraint('ck_users_email_verification', 'users', 'NOT email_verified OR email IS NOT NULL')


def downgrade():
    # Only new profile fields are discarded; users, credentials and identities remain.
    op.drop_constraint('ck_users_email_verification', 'users', type_='check')
    op.drop_constraint('ck_users_email_normalized', 'users', type_='check')
    op.drop_index('uq_users_email_lower', table_name='users')
    for column in ('email_verified', 'email', 'last_name', 'first_name'):
        op.drop_column('users', column)
