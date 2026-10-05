from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import validates

from app import db
from app.property_rules import LAND_USES, TRANSACTION_RULES, OCCUPANCIES, field_rules


REQUIRED_TEXT_FIELDS = (
    "title_ar", "description_ar", "state_en", "state_ar", "property_type",
    "currency", "contact_name", "phone", "contact_role",
    "publication_status", "availability_status",
)
DRAFT_OPTIONAL_TEXT_FIELDS = ("title_en", "description_en", "city_en", "area_en")
PHOTO_CATEGORIES = ("exterior", "entrance", "living_room", "bedroom", "kitchen", "bathroom", "other")
CURRENCIES = ("SDG", "USD")
MAX_COMMENT_LENGTH = 2000
CHOICES = {
    "currency": CURRENCIES,
    "contact_role": ("owner", "broker"),
    "transaction_type": tuple(TRANSACTION_RULES),
    "property_occupancy": OCCUPANCIES,
    "publication_status": ("draft", "published"),
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
        db.CheckConstraint("price >= 0 AND price < 'Infinity'::numeric", name="ck_properties_price_nonnegative"),
        db.CheckConstraint("transaction_type IN ('rent', 'sale')", name="ck_properties_transaction_type"),
        db.CheckConstraint("property_occupancy IN ('room', 'entire_property')", name="ck_properties_property_occupancy"),
        db.CheckConstraint("(transaction_type = 'rent' AND rent_period IN ('monthly', 'weekly')) OR (transaction_type = 'sale' AND rent_period IS NULL)", name="ck_properties_rent_period"),
        db.CheckConstraint("floor >= 0", name="ck_properties_floor_nonnegative"),
        db.CheckConstraint("land_use IN ('residential', 'commercial', 'agricultural', 'industrial', 'mixed')", name="ck_properties_land_use"),
        db.CheckConstraint("bedrooms >= 0", name="ck_properties_bedrooms_nonnegative"),
        db.CheckConstraint("bathrooms >= 0", name="ck_properties_bathrooms_nonnegative"),
        db.CheckConstraint("size >= 0 AND size < 'Infinity'::numeric", name="ck_properties_size_nonnegative"),
        db.CheckConstraint("contact_role IN ('owner', 'broker')", name="ck_properties_contact_role"),
        db.CheckConstraint("publication_status IN ('draft', 'published')", name="ck_properties_publication_status"),
        db.CheckConstraint("moderation_status IN ('clear', 'disabled')", name="ck_properties_moderation_status"),
        db.CheckConstraint("availability_status IN ('available', 'rented')", name="ck_properties_availability_status"),
        db.CheckConstraint("jsonb_typeof(amenities) = 'array'", name="ck_properties_amenities_array"),
        db.CheckConstraint("char_length(comment) <= 2000", name="ck_properties_comment_length"),
        db.CheckConstraint("(latitude IS NULL AND longitude IS NULL) OR (latitude IS NOT NULL AND longitude IS NOT NULL)", name="ck_properties_coordinate_pair"),
        db.CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="ck_properties_latitude_range"),
        db.CheckConstraint("longitude IS NULL OR longitude BETWEEN -180 AND 180", name="ck_properties_longitude_range"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    owner = db.relationship('User', back_populates='properties')
    saved_by = db.relationship('User', secondary='saved_properties', back_populates='saved_properties', passive_deletes=True)
    title_en = db.Column(db.String, nullable=False)
    title_ar = db.Column(db.String, nullable=False)
    description_en = db.Column(db.Text, nullable=False)
    description_ar = db.Column(db.Text, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    state_en = db.Column(db.String, nullable=False)
    state_ar = db.Column(db.String, nullable=False)
    city_en = db.Column(db.String, nullable=False)
    city_ar = db.Column(db.String, nullable=True)
    area_en = db.Column(db.String, nullable=False)
    area_ar = db.Column(db.String, nullable=True)
    neighborhood_ar = db.Column(db.String, nullable=True)
    latitude = db.Column(db.Numeric(9, 6), nullable=True)
    longitude = db.Column(db.Numeric(9, 6), nullable=True)
    property_type = db.Column(db.String, nullable=False)
    transaction_type = db.Column(db.String, nullable=False, default="rent", server_default="rent")
    property_occupancy = db.Column(db.String, nullable=False, default="entire_property", server_default="entire_property")
    rent_period = db.Column(db.String, nullable=True)
    price = db.Column(db.Numeric, nullable=False)
    monthly_rent = db.Column(db.Numeric, nullable=True)
    currency = db.Column(db.String, nullable=False, default="SDG", server_default="SDG")
    bedrooms = db.Column(db.Integer, nullable=True)
    bathrooms = db.Column(db.Integer, nullable=True)
    floor = db.Column(db.Integer, nullable=True)
    land_use = db.Column(db.String(32), nullable=True)
    size = db.Column(db.Numeric, nullable=True)
    furnished = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    amenities = db.Column(MutableList.as_mutable(JSONB), nullable=False, default=list, server_default=db.text("'[]'::jsonb"))
    contact_name = db.Column(db.String, nullable=False)
    phone = db.Column(db.String, nullable=False)
    whatsapp = db.Column(db.String, nullable=True)
    # The property's contact role is independent of any future staff/user roles.
    contact_role = db.Column(db.String, nullable=False, default="owner", server_default="owner")
    publication_status = db.Column(db.String, nullable=False, default="draft", server_default="draft")
    moderation_status = db.Column(db.String(16), nullable=False, default="clear", server_default="clear")
    availability_status = db.Column(db.String, nullable=False, default="available", server_default="available")
    available_from_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=db.func.now())
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=db.func.now(), onupdate=utc_now)
    photos = db.relationship("PropertyPhoto", back_populates="property", cascade="all, delete-orphan", order_by="PropertyPhoto.display_order")

    @property
    def furnishing_applicable(self):
        return field_rules(self.property_type, self.transaction_type)["furnished"] != "inapplicable"

    def __init__(self, **kwargs):
        defaults = {
            "currency": "SDG", "furnished": False, "amenities": [],
            "contact_role": "owner", "publication_status": "draft", "moderation_status": "clear",
            "availability_status": "available",
            "transaction_type": "rent", "property_occupancy": "entire_property",
        }
        if "price" not in kwargs and "monthly_rent" in kwargs:
            kwargs["price"] = kwargs["monthly_rent"]
        if "rent_period" not in kwargs:
            kwargs["rent_period"] = "monthly" if kwargs.get("transaction_type", "rent") == "rent" else None
        super().__init__(**(defaults | kwargs))

    @validates(*REQUIRED_TEXT_FIELDS, *DRAFT_OPTIONAL_TEXT_FIELDS)
    def validate_text(self, key, value):
        if not isinstance(value, str) or (key in REQUIRED_TEXT_FIELDS and not value.strip()):
            raise ValueError(f"{key} must be a nonempty string")
        if key in CHOICES and value not in CHOICES[key]:
            raise ValueError(f"{key} must be one of {', '.join(CHOICES[key])}")
        return value

    @validates("monthly_rent", "price", "size")
    def validate_decimal(self, key, value):
        if key in ("size", "monthly_rent") and value is None:
            return None
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError(f"{key} must be a nonnegative decimal") from None
        if not number.is_finite() or number < 0:
            raise ValueError(f"{key} must be a finite nonnegative decimal")
        return number

    @validates("bedrooms", "bathrooms", "floor")
    def validate_integer(self, key, value):
        if value is None:
            return None
        if type(value) is not int or value < 0:
            raise ValueError(f"{key} must be a nonnegative integer")
        return value

    @validates("land_use")
    def validate_land_use(self, key, value):
        if value is not None and value not in LAND_USES:
            raise ValueError("invalid land use")
        return value

    @validates("comment")
    def validate_comment(self, key, value):
        if value is None:
            return None
        if not isinstance(value, str) or '\x00' in value or len(value.strip()) > MAX_COMMENT_LENGTH:
            raise ValueError('invalid comment')
        return value.strip() or None

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

    @validates("latitude", "longitude")
    def validate_coordinate(self, key, value):
        if value is None:
            return None
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError(f"{key} must be a valid coordinate") from None
        limit = 90 if key == "latitude" else 180
        if not number.is_finite() or abs(number) > limit or number.as_tuple().exponent < -6:
            raise ValueError(f"{key} must be a valid coordinate")
        return number


@event.listens_for(Property, "before_insert")
@event.listens_for(Property, "before_update")
def validate_property(mapper, connection, target):
    target.comment = target.validate_comment('comment', target.comment)
    # Also catch omitted required fields and in-place changes to the JSON list.
    for key in REQUIRED_TEXT_FIELDS:
        target.validate_text(key, getattr(target, key))
    for key in DRAFT_OPTIONAL_TEXT_FIELDS:
        target.validate_text(key, getattr(target, key))
    for key in ("price", "monthly_rent", "size"):
        target.validate_decimal(key, getattr(target, key))
    for key in ("transaction_type", "property_occupancy"):
        target.validate_text(key, getattr(target, key))
    if (target.transaction_type == "rent" and target.rent_period not in TRANSACTION_RULES["rent"]["allowed_values"]["rent_period"]) or (target.transaction_type == "sale" and target.rent_period is not None):
        raise ValueError("invalid rent period")
    if target.neighborhood_ar is not None and not target.neighborhood_ar.strip():
        raise ValueError("neighborhood must not be blank")
    for key in ("bedrooms", "bathrooms", "floor"):
        target.validate_integer(key, getattr(target, key))
    target.validate_land_use("land_use", target.land_use)
    target.validate_boolean("furnished", target.furnished)
    target.validate_amenities("amenities", target.amenities)
    if (target.latitude is None) != (target.longitude is None):
        raise ValueError("latitude and longitude must be supplied together")
    for key in ("latitude", "longitude"):
        target.validate_coordinate(key, getattr(target, key))


class PropertyPhoto(db.Model):
    __tablename__ = "property_photos"
    __table_args__ = (
        db.CheckConstraint(f"category IN ({', '.join(repr(category) for category in PHOTO_CATEGORIES)})", name="ck_property_photos_category"),
        db.CheckConstraint("file_size > 0 AND file_size <= 5242880", name="ck_property_photos_file_size"),
        db.CheckConstraint("display_order >= 0", name="ck_property_photos_display_order"),
        db.CheckConstraint("content_type IN ('image/jpeg', 'image/png', 'image/webp')", name="ck_property_photos_content_type"),
        db.Index("uq_property_photos_one_primary", "property_id", unique=True, postgresql_where=db.text("is_primary")),
    )

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    category = db.Column(db.String(32), nullable=False)
    storage_key = db.Column(db.String(255), nullable=False, unique=True)
    original_filename = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(32), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    display_order = db.Column(db.Integer, nullable=False)
    is_primary = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=db.func.now())
    property = db.relationship("Property", back_populates="photos")


class User(db.Model):
    __tablename__ = 'users'
    __table_args__ = (
        db.CheckConstraint("role IN ('user', 'admin')", name='ck_users_role'),
        db.CheckConstraint("avatar_source IN ('facebook', 'google', 'manual')", name='ck_users_avatar_source'),
    )
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(16), nullable=True, unique=True)
    password_hash = db.Column(db.String(255), nullable=True)
    whatsapp = db.Column(db.String(16), nullable=True)
    contact_name = db.Column(db.String, nullable=True)
    contact_role = db.Column(db.String, nullable=True)
    avatar_storage_key = db.Column(db.String(255), nullable=True)
    avatar_source = db.Column(db.String(16), nullable=True)
    is_verified = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    role = db.Column(db.String(16), nullable=False, default='user', server_default='user')
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    last_login_at = db.Column(db.DateTime(timezone=True))
    properties = db.relationship('Property', back_populates='owner')
    saved_properties = db.relationship('Property', secondary='saved_properties', back_populates='saved_by', passive_deletes=True)
    identities = db.relationship('UserIdentity', back_populates='user', cascade='all, delete-orphan')

    @property
    def has_authenticated_identity(self):
        return self.is_verified or bool(self.identities) or bool(self.password_hash)

    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return bool(self.password_hash) and check_password_hash(self.password_hash, password)

    @property
    def contact_complete(self):
        return bool(self.contact_name and self.contact_name.strip() and self.whatsapp and self.contact_role in CHOICES['contact_role'])

    @property
    def social_contact_complete(self):
        return bool(self.whatsapp or self.phone_number)


class UserIdentity(db.Model):
    __tablename__ = 'user_identities'
    provider = db.Column(db.String(32), primary_key=True)
    provider_user_id = db.Column(db.String(255), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    display_name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=db.func.now())
    user = db.relationship('User', back_populates='identities')


class OTPChallenge(db.Model):
    __tablename__ = 'otp_challenges'
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(16), nullable=False, index=True)
    otp_hash = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    consumed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class SavedProperty(db.Model):
    __tablename__ = 'saved_properties'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id', ondelete='CASCADE'), primary_key=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, server_default=db.func.now())
