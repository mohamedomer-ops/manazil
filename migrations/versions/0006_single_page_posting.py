"""Represent rent, sale, occupancy, price and neighborhood without losing legacy data."""
from alembic import op
import sqlalchemy as sa

revision = "0006_single_page_posting"
down_revision = "0005_property_photos"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("properties", sa.Column("transaction_type", sa.String(), nullable=False, server_default="rent"))
    op.add_column("properties", sa.Column("property_occupancy", sa.String(), nullable=False, server_default="entire_property"))
    op.add_column("properties", sa.Column("rent_period", sa.String(), nullable=True))
    op.add_column("properties", sa.Column("price", sa.Numeric(), nullable=True))
    op.add_column("properties", sa.Column("neighborhood_ar", sa.String(), nullable=True))
    op.execute("UPDATE properties SET price = monthly_rent, rent_period = 'monthly'")
    op.alter_column("properties", "price", nullable=False)
    op.alter_column("properties", "monthly_rent", nullable=True)
    for field in ("city_ar", "area_ar"):
        op.drop_constraint(f"ck_properties_{field}_not_blank", "properties", type_="check")
        op.alter_column("properties", field, nullable=True)
    op.create_check_constraint("ck_properties_price_nonnegative", "properties", "price >= 0 AND price < 'Infinity'::numeric")
    op.create_check_constraint("ck_properties_transaction_type", "properties", "transaction_type IN ('rent', 'sale')")
    op.create_check_constraint("ck_properties_property_occupancy", "properties", "property_occupancy IN ('room', 'entire_property')")
    op.create_check_constraint("ck_properties_rent_period", "properties", "(transaction_type = 'rent' AND rent_period IN ('monthly', 'weekly')) OR (transaction_type = 'sale' AND rent_period IS NULL)")


def downgrade():
    incompatible = op.get_bind().scalar(sa.text(
        "SELECT count(*) FROM properties WHERE monthly_rent IS NULL OR city_ar IS NULL "
        "OR area_ar IS NULL OR transaction_type <> 'rent' OR rent_period <> 'monthly'"
    ))
    if incompatible:
        raise RuntimeError("Cannot downgrade while properties use the new posting fields.")
    op.drop_constraint("ck_properties_rent_period", "properties", type_="check")
    op.drop_constraint("ck_properties_property_occupancy", "properties", type_="check")
    op.drop_constraint("ck_properties_transaction_type", "properties", type_="check")
    op.drop_constraint("ck_properties_price_nonnegative", "properties", type_="check")
    op.alter_column("properties", "monthly_rent", nullable=False)
    for field in ("city_ar", "area_ar"):
        op.alter_column("properties", field, nullable=False)
        op.create_check_constraint(f"ck_properties_{field}_not_blank", "properties", f"{field} ~ '[^[:space:]]'")
    for field in ("neighborhood_ar", "price", "rent_period", "property_occupancy", "transaction_type"):
        op.drop_column("properties", field)
