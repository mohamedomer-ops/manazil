"""Add users, OTP challenges, and optional property ownership."""
from alembic import op
import sqlalchemy as sa

revision = '0008_user_phone_otp'
down_revision = '0007_direct_publication'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('phone_number', sa.String(16), nullable=False, unique=True),
        sa.Column('is_verified', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True)))
    op.create_table('otp_challenges',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('phone_number', sa.String(16), nullable=False),
        sa.Column('otp_hash', sa.String(255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_otp_challenges_phone_number', 'otp_challenges', ['phone_number'])
    op.add_column('properties', sa.Column('owner_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_properties_owner_id_users', 'properties', 'users', ['owner_id'], ['id'])
    op.create_index('ix_properties_owner_id', 'properties', ['owner_id'])


def downgrade():
    op.drop_index('ix_properties_owner_id', 'properties')
    op.drop_constraint('fk_properties_owner_id_users', 'properties', type_='foreignkey')
    op.drop_column('properties', 'owner_id')
    op.drop_index('ix_otp_challenges_phone_number', 'otp_challenges')
    op.drop_table('otp_challenges')
    op.drop_table('users')
