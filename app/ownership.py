"""Owner-only property management using the existing posting form."""
from flask import Blueprint, abort, current_app, g, redirect, render_template, request, send_file, url_for
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app import db
from app.admin import render_form
from app.auth import login_required
from app.languages import current_language, format_rent, property_type_label
from app.models import Property, PropertyPhoto
from app.photo_storage import LocalPhotoStorage, PhotoError
from app.property_forms import FORM_FIELDS, validate_posting

ownership = Blueprint('ownership', __name__)


@ownership.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'private, no-store'
    return response


def owned_property(property_id):
    property = db.session.scalar(select(Property).options(selectinload(Property.photos)).where(
        Property.id == property_id, Property.owner_id == g.user.id))
    if property is None:
        abort(404)
    return property


@ownership.get('/my-properties')
@login_required
def my_properties():
    properties = db.session.scalars(select(Property).options(selectinload(Property.photos)).where(
        Property.owner_id == g.user.id).order_by(Property.created_at.desc(), Property.id.desc())).all()
    return render_template('my_properties.html', properties=properties,
                           format_rent=format_rent, property_type_label=property_type_label)


def editing_values(property):
    values = {key: '' if getattr(property, key, None) is None else str(getattr(property, key))
              for key in FORM_FIELDS if key not in ('agent', 'amenities', 'furnished')}
    values.update(agent='yes' if property.contact_role == 'broker' else 'no',
                  amenities='\n'.join(property.amenities), furnished='on' if property.furnished else '')
    return values


@ownership.route('/properties/<int:property_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_property(property_id):
    property = owned_property(property_id)
    language = current_language()
    if request.method == 'GET':
        return render_form(editing_values(property), {}, language, edit_property=property)
    action = request.form.get('_action', 'submit')
    values = {key: request.form.get(key, '') for key in FORM_FIELDS}
    if action in ('switch_ar', 'switch_en'):
        return render_form(values, {}, action[-2:], edit_property=property)
    if action != 'submit':
        abort(400)
    values, data, errors = validate_posting(values, language)
    if errors:
        return render_form(values, errors, language, edit_property=property), 422
    # Posting-only defaults must never reset fields absent from the edit form.
    for key in ('title_en', 'description_en', 'city_en', 'area_en', 'city_ar', 'area_ar',
                'availability_status', 'available_from_date'):
        data.pop(key, None)
    try:
        for key, value in data.items():
            setattr(property, key, value)
        db.session.commit()
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        current_app.logger.warning('Property update failed for property %s.', property_id)
        return render_form(values, {}, language, edit_property=property,
                           save_error='The property could not be saved. Your entries are still here. Please try again.'), 503
    return redirect(url_for('ownership.my_properties', saved=property.id,
                            **({'lang': 'en'} if language == 'en' else {})), code=303)


@ownership.get('/my-properties/photos/<int:photo_id>')
@login_required
def owner_photo(photo_id):
    photo = db.session.scalar(select(PropertyPhoto).join(Property).where(
        PropertyPhoto.id == photo_id, Property.owner_id == g.user.id))
    if photo is None:
        abort(404)
    try:
        return send_file(LocalPhotoStorage().path(photo.storage_key), mimetype=photo.content_type, max_age=0)
    except (PhotoError, OSError):
        abort(404)


def change_availability(property_id, status):
    property = owned_property(property_id)
    property.availability_status = status
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.warning('Availability update failed for property %s.', property_id)
        abort(503)
    return redirect(url_for('ownership.my_properties',
                            **({'lang': 'en'} if current_language() == 'en' else {})), code=303)


@ownership.post('/properties/<int:property_id>/mark-rented')
@login_required
def mark_rented(property_id):
    return change_availability(property_id, 'rented')


@ownership.post('/properties/<int:property_id>/make-available')
@login_required
def make_available(property_id):
    return change_availability(property_id, 'available')
