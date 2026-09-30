"""Add optional contact defaults to existing users."""
from alembic import op
import sqlalchemy as sa

revision = '0009_user_contact_profile'
down_revision = '0008_user_phone_otp'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('whatsapp', sa.String(16), nullable=True))
    op.add_column('users', sa.Column('contact_name', sa.String(), nullable=True))
    op.add_column('users', sa.Column('contact_role', sa.String(), nullable=True))
    op.create_check_constraint('ck_users_contact_role', 'users', "contact_role IN ('owner', 'broker')")


def downgrade():
    op.drop_constraint('ck_users_contact_role', 'users', type_='check')
    op.drop_column('users', 'contact_role')
    op.drop_column('users', 'contact_name')
    op.drop_column('users', 'whatsapp')
