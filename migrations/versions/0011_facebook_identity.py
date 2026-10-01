"""Separate provider identities from optional verified contact phones."""
from alembic import op
import sqlalchemy as sa

revision = '0011_facebook_identity'
down_revision = '0010_saved_properties'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('users', 'phone_number', existing_type=sa.String(16), nullable=True)
    op.create_table('user_identities',
        sa.Column('provider', sa.String(32), primary_key=True),
        sa.Column('provider_user_id', sa.String(255), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index('ix_user_identities_user_id', 'user_identities', ['user_id'])


def downgrade():
    # Refuse to discard Facebook-only accounts or invent phone numbers.
    connection = op.get_bind()
    if connection.scalar(sa.text('SELECT count(*) FROM users WHERE phone_number IS NULL')):
        raise RuntimeError('Cannot downgrade while accounts without phone numbers exist.')
    op.drop_table('user_identities')
    op.alter_column('users', 'phone_number', existing_type=sa.String(16), nullable=False)
