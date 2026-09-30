"""Use draft and published as the only property publication states."""
from alembic import op
import sqlalchemy as sa

revision = "0007_direct_publication"
down_revision = "0006_single_page_posting"
branch_labels = None
depends_on = None


def upgrade():
    # Unreviewed and archived records remain private; preserve their contents.
    op.execute("UPDATE properties SET publication_status = 'draft' WHERE publication_status IN ('pending', 'archived')")
    op.drop_constraint("ck_properties_publication_status", "properties", type_="check")
    op.create_check_constraint("ck_properties_publication_status", "properties", "publication_status IN ('draft', 'published')")


def downgrade():
    op.drop_constraint("ck_properties_publication_status", "properties", type_="check")
    op.create_check_constraint("ck_properties_publication_status", "properties", "publication_status IN ('draft', 'pending', 'published', 'archived')")
