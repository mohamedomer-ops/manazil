from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import validates

from app import db


REQUIRED_TEXT_FIELDS = (
    "title_en", "title_ar", "description_en", "description_ar",
    "city_en", "city_ar", "area_en", "area_ar", "property_type",
    "currency", "contact_name", "phone", "contact_role",
    "publication_status", "availability_status",
)
CHOICES = {
    "contact_role": ("owner", "broker"),
    "publication_status": ("draft", "pending", "published", "archived"),
    "availability_status": ("available", "rented"),
}


def utc_now():
    return datetime.now(timezone.utc)


class Property(db.Model):
    __tablename__ = "properties"
    __table_args__ = (
        *(
            db.CheckConstraint(
                f"{field} ~ '[^[:space:]]'", name=f"ck_properties_{field}_not_blank"
            )
            for field in REQUIRED_TEXT_FIELDS
        ),
        db.CheckConstraint("monthly_rent >= 0 AND monthly_rent < 'Infinity'::numeric", name="ck_properties_rent_nonnegative"),
        db.CheckConstraint("bedrooms >= 0", name="ck_properties_bedrooms_nonnegative"),
        db.CheckConstraint("bathrooms >= 0", name="ck_properties_bathrooms_nonnegative"),
        db.CheckConstraint("size >= 0 AND size < 'Infinity'::numeric", name="ck_properties_size_nonnegative"),
        db.CheckConstraint("contact_role IN ('owner', 'broker')", name="ck_properties_contact_role"),
        db.CheckConstraint("publication_status IN ('draft', 'pending', 'published', 'archived')", name="ck_properties_publication_status"),
        db.CheckConstraint("availability_status IN ('available', 'rented')", name="ck_properties_availability_status"),
        db.CheckConstraint("jsonb_typeof(amenities) = 'array'", name="ck_properties_amenities_array"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title_en = db.Column(db.String, nullable=False)
    title_ar = db.Column(db.String, nullable=False)
    description_en = db.Column(db.Text, nullable=False)
    description_ar = db.Column(db.Text, nullable=False)
    city_en = db.Column(db.String, nullable=False)
    city_ar = db.Column(db.String, nullable=False)
    area_en = db.Column(db.String, nullable=False)
    area_ar = db.Column(db.String, nullable=False)
    property_type = db.Column(db.String, nullable=False)
    monthly_rent = db.Column(db.Numeric, nullable=False)
    currency = db.Column(db.String, nullable=False, default="SDG", server_default="SDG")
    bedrooms = db.Column(db.Integer, nullable=False)
    bathrooms = db.Column(db.Integer, nullable=False)
    size = db.Column(db.Numeric, nullable=True)
    furnished = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    amenities = db.Column(MutableList.as_mutable(JSONB), nullable=False, default=list, server_default=db.text("'[]'::jsonb"))
    contact_name = db.Column(db.String, nullable=False)
    phone = db.Column(db.String, nullable=False)
    whatsapp = db.Column(db.String, nullable=True)
    # The property's contact role is independent of any future staff/user roles.
    contact_role = db.Column(db.String, nullable=False, default="owner", server_default="owner")
    publication_status = db.Column(db.String, nullable=False, default="draft", server_default="draft")
    availability_status = db.Column(db.String, nullable=False, default="available", server_default="available")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=db.func.now())
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=db.func.now(), onupdate=utc_now)

    def __init__(self, **kwargs):
        defaults = {
            "currency": "SDG", "furnished": False, "amenities": [],
            "contact_role": "owner", "publication_status": "draft",
            "availability_status": "available",
        }
        super().__init__(**(defaults | kwargs))

    @validates(*REQUIRED_TEXT_FIELDS)
    def validate_text(self, key, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a nonempty string")
        if key in CHOICES and value not in CHOICES[key]:
            raise ValueError(f"{key} must be one of {', '.join(CHOICES[key])}")
        return value

    @validates("monthly_rent", "size")
    def validate_decimal(self, key, value):
        if key == "size" and value is None:
            return None
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError(f"{key} must be a nonnegative decimal") from None
        if not number.is_finite() or number < 0:
            raise ValueError(f"{key} must be a finite nonnegative decimal")
        return number

    @validates("bedrooms", "bathrooms")
    def validate_integer(self, key, value):
        if type(value) is not int or value < 0:
            raise ValueError(f"{key} must be a nonnegative integer")
        return value

    @validates("furnished")
    def validate_boolean(self, key, value):
        if type(value) is not bool:
            raise ValueError("furnished must be a boolean")
        return value

    @validates("amenities")
    def validate_amenities(self, key, value):
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError("amenities must be a list of strings")
        return value


@event.listens_for(Property, "before_insert")
@event.listens_for(Property, "before_update")
def validate_property(mapper, connection, target):
    # Also catch omitted required fields and in-place changes to the JSON list.
    for key in REQUIRED_TEXT_FIELDS:
        target.validate_text(key, getattr(target, key))
    for key in ("monthly_rent", "size"):
        target.validate_decimal(key, getattr(target, key))
    for key in ("bedrooms", "bathrooms"):
        target.validate_integer(key, getattr(target, key))
    target.validate_boolean("furnished", target.furnished)
    target.validate_amenities("amenities", target.amenities)
