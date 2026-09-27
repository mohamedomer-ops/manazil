import re

from flask import Blueprint, abort, current_app, jsonify, render_template, send_file
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app import db
from app.languages import availability_label, format_rent, property_type_label
from app.models import PHOTO_CATEGORIES, Property, PropertyPhoto
from app.photo_storage import LocalPhotoStorage, PhotoError, category_label
from app.property_forms import sudan_today


main = Blueprint("main", __name__)


@main.get("/")
def index():
    return render_template("index.html")


@main.get("/properties")
def properties():
    listings = db.session.scalars(
        select(Property).options(selectinload(Property.photos))
        .where(Property.publication_status == "published", Property.availability_status == "available")
        .order_by(Property.created_at.desc(), Property.id.desc())
    ).all()
    return render_template(
        "properties.html", properties=listings, today=sudan_today(),
        availability_label=availability_label, format_rent=format_rent,
        property_type_label=property_type_label,
    )


def safe_phone_number(value):
    if not value or not re.fullmatch(r"\+?[0-9][0-9\s().-]*", value.strip()):
        return None
    digits = re.sub(r"\D", "", value)
    if not 7 <= len(digits) <= 15:
        return None
    return ("+" if value.strip().startswith("+") else "") + digits


@main.get("/properties/<int:property_id>")
def property_detail(property_id):
    property = db.session.scalar(
        select(Property).options(selectinload(Property.photos)).where(
            Property.id == property_id,
            Property.publication_status == "published",
            Property.availability_status == "available",
        )
    )
    if property is None:
        abort(404)
    phone = safe_phone_number(property.phone)
    whatsapp = safe_phone_number(property.whatsapp)
    return render_template(
        "property_detail.html", property=property, today=sudan_today(),
        availability_label=availability_label, format_rent=format_rent,
        property_type_label=property_type_label,
        phone_url=f"tel:{phone}" if phone else None,
        whatsapp_url=f"https://wa.me/{whatsapp.lstrip('+')}" if whatsapp else None,
        category_label=category_label,
        photo_categories=PHOTO_CATEGORIES,
    )


@main.get("/properties/photos/<int:photo_id>")
def public_photo(photo_id):
    photo = db.session.scalar(
        select(PropertyPhoto).join(Property).where(
            PropertyPhoto.id == photo_id,
            Property.publication_status == "published",
            Property.availability_status == "available",
        )
    )
    if photo is None:
        abort(404)
    try:
        return send_file(LocalPhotoStorage().path(photo.storage_key), mimetype=photo.content_type)
    except (PhotoError, OSError):
        abort(404)


@main.get("/api/health")
def health():
    try:
        with db.engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
    except SQLAlchemyError:
        current_app.logger.warning("Database health check failed.")
        return jsonify(status="error", service="Manazil", database="unavailable"), 503
    return jsonify(status="ok", service="Manazil", database="connected")
