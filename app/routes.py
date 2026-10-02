from flask import Blueprint, abort, current_app, g, jsonify, render_template, request, send_file
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app import db
from app.languages import PROPERTY_TYPE_NAMES, availability_label, format_rent, property_type_label
from app.models import Property, PropertyPhoto, SavedProperty
from app.property_filters import STATE_OPTIONS, apply_filters, validated_filters
from app.photo_storage import LocalPhotoStorage, PhotoError, category_label
from app.property_forms import sudan_today
from app.phone import property_contact_number


main = Blueprint("main", __name__)


@main.get("/")
def index():
    latest = db.session.scalars(
        public_properties().order_by(Property.created_at.desc(), Property.id.desc()).limit(4)
    ).all()
    saved_ids = saved_property_ids(latest)
    return render_template(
        "index.html", latest_properties=latest, saved_ids=saved_ids,
        state_options=STATE_OPTIONS, property_types=PROPERTY_TYPE_NAMES, today=sudan_today(),
        availability_label=availability_label, format_rent=format_rent,
    )


def public_properties():
    return select(Property).options(selectinload(Property.photos)).where(
        Property.publication_status == "published", Property.availability_status == "available",
        Property.moderation_status == "clear"
    )


def saved_property_ids(listings):
    if not g.get('user') or not listings:
        return set()
    return set(db.session.scalars(select(SavedProperty.property_id).where(
        SavedProperty.user_id == g.user.id,
        SavedProperty.property_id.in_([listing.id for listing in listings]),
    )).all())


@main.get("/properties")
def properties():
    filters = validated_filters(request.args)
    listings = db.session.scalars(
        apply_filters(public_properties(), filters)
        .order_by(Property.created_at.desc(), Property.id.desc())
    ).all()
    saved_ids = saved_property_ids(listings)
    return render_template(
        "properties.html", properties=listings, filters=filters, saved_ids=saved_ids,
        state_options=STATE_OPTIONS, property_types=PROPERTY_TYPE_NAMES, today=sudan_today(),
        availability_label=availability_label, format_rent=format_rent,
    )


@main.get("/properties/<int:property_id>")
def property_detail(property_id):
    property = db.session.scalar(
        select(Property).options(selectinload(Property.photos)).where(
            Property.id == property_id,
            Property.publication_status == "published",
            Property.availability_status == "available",
            Property.moderation_status == "clear",
        )
    )
    if property is None:
        abort(404)
    contact_number = property_contact_number(property)
    is_saved = bool(g.get('user') and db.session.get(SavedProperty, (g.user.id, property.id)))
    response = current_app.make_response(render_template(
        "property_detail.html", property=property, today=sudan_today(),
        availability_label=availability_label, format_rent=format_rent,
        property_type_label=property_type_label,
        contact_number=contact_number,
        phone_url=f"tel:{contact_number}" if contact_number else None,
        whatsapp_url=f"https://wa.me/{contact_number.lstrip('+')}" if contact_number else None,
        category_label=category_label, is_saved=is_saved,
    ))
    response.headers['Cache-Control'] = 'private, no-store'
    return response


@main.get("/properties/photos/<int:photo_id>")
def public_photo(photo_id):
    photo = db.session.scalar(
        select(PropertyPhoto).join(Property).where(
            PropertyPhoto.id == photo_id,
            Property.publication_status == "published",
            Property.availability_status == "available",
            Property.moderation_status == "clear",
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
