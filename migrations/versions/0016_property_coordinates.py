"""Optional precise location for owner property forms."""
from alembic import op
import sqlalchemy as sa


revision = '0016_property_coordinates'
down_revision = '0015_google_avatar_source'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('properties', sa.Column('latitude', sa.Numeric(9, 6), nullable=True))
    op.add_column('properties', sa.Column('longitude', sa.Numeric(9, 6), nullable=True))
    op.create_check_constraint('ck_properties_coordinate_pair', 'properties',
                               '(latitude IS NULL AND longitude IS NULL) OR (latitude IS NOT NULL AND longitude IS NOT NULL)')
    op.create_check_constraint('ck_properties_latitude_range', 'properties',
                               'latitude IS NULL OR latitude BETWEEN -90 AND 90')
    op.create_check_constraint('ck_properties_longitude_range', 'properties',
                               'longitude IS NULL OR longitude BETWEEN -180 AND 180')


def downgrade():
    op.drop_constraint('ck_properties_longitude_range', 'properties', type_='check')
    op.drop_constraint('ck_properties_latitude_range', 'properties', type_='check')
    op.drop_constraint('ck_properties_coordinate_pair', 'properties', type_='check')
    op.drop_column('properties', 'longitude')
    op.drop_column('properties', 'latitude')
