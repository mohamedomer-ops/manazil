"""Short-lived, hashed email verification challenges; existing users unchanged."""
from alembic import op
import sqlalchemy as sa

revision = '0020_email_verification'
down_revision = '0019_user_email_profile'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'email_verification_challenges',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.String(254), nullable=False),
        sa.Column('code_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('consumed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('attempts BETWEEN 0 AND 5', name='ck_email_verification_attempts'),
    )
    op.create_index('ix_email_verification_challenges_user_id', 'email_verification_challenges', ['user_id'])
    op.create_index('uq_email_verification_active_user', 'email_verification_challenges', ['user_id'],
                    unique=True, postgresql_where=sa.text('consumed_at IS NULL'),
                    sqlite_where=sa.text('consumed_at IS NULL'))


def downgrade():
    # Discard temporary challenges only; accounts and verification flags remain.
    op.drop_table('email_verification_challenges')
