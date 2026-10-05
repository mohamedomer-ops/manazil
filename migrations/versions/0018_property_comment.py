"""Optional manually written poster comment, independent of description."""
from alembic import op
import sqlalchemy as sa

revision = '0018_property_comment'
down_revision = '0017_property_rules'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('properties', sa.Column('comment', sa.Text(), nullable=True))
    op.create_check_constraint('ck_properties_comment_length', 'properties', 'char_length(comment) <= 2000')


def downgrade():
    # Only comments are discarded; all existing property fields/records remain.
    op.drop_constraint('ck_properties_comment_length', 'properties', type_='check')
    op.drop_column('properties', 'comment')
