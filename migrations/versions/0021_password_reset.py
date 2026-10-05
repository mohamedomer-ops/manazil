"""Independent, short-lived password reset challenges; no user-data changes."""
from alembic import op
import sqlalchemy as sa

revision = '0021_password_reset'
down_revision = '0020_email_verification'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'password_reset_challenges',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.String(254), nullable=False),
        sa.Column('credential_hash', sa.String(64), nullable=False),
        sa.Column('code_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('code_verified_at', sa.DateTime(timezone=True)),
        sa.Column('authorization_hash', sa.String(64)),
        sa.Column('authorization_expires_at', sa.DateTime(timezone=True)),
        sa.Column('consumed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('attempts BETWEEN 0 AND 5', name='ck_password_reset_attempts'),
        sa.CheckConstraint('(authorization_hash IS NULL) = (authorization_expires_at IS NULL)',
                           name='ck_password_reset_authorization'),
    )
    op.create_index('ix_password_reset_challenges_user_id', 'password_reset_challenges', ['user_id'])
    op.create_index('uq_password_reset_active_user', 'password_reset_challenges', ['user_id'],
                    unique=True, postgresql_where=sa.text('consumed_at IS NULL'),
                    sqlite_where=sa.text('consumed_at IS NULL'))


def downgrade():
    # Discard reset codes/grants only; users, passwords and email verification remain.
    op.drop_table('password_reset_challenges')
