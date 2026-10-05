"""Optional type-specific property facts without rewriting historical data."""
from alembic import op
import sqlalchemy as sa

revision = '0017_property_rules'
down_revision = '0016_property_coordinates'
branch_labels = None
depends_on = None


def upgrade():
    for field in ('bedrooms', 'bathrooms'):
        op.alter_column('properties', field, existing_type=sa.Integer(), nullable=True)
    op.add_column('properties', sa.Column('floor', sa.Integer(), nullable=True))
    op.add_column('properties', sa.Column('land_use', sa.String(32), nullable=True))
    op.create_check_constraint('ck_properties_floor_nonnegative', 'properties', 'floor >= 0')
    op.create_check_constraint('ck_properties_land_use', 'properties',
                               "land_use IN ('residential', 'commercial', 'agricultural', 'industrial', 'mixed')")


def downgrade():
    incompatible = op.get_bind().scalar(sa.text(
        'SELECT count(*) FROM properties WHERE bedrooms IS NULL OR bathrooms IS NULL '
        'OR floor IS NOT NULL OR land_use IS NOT NULL'))
    if incompatible:
        raise RuntimeError('Cannot downgrade while properties use nullable facts, floor or land use.')
    op.drop_constraint('ck_properties_land_use', 'properties', type_='check')
    op.drop_constraint('ck_properties_floor_nonnegative', 'properties', type_='check')
    op.drop_column('properties', 'land_use')
    op.drop_column('properties', 'floor')
    for field in ('bedrooms', 'bathrooms'):
        op.alter_column('properties', field, existing_type=sa.Integer(), nullable=False)
