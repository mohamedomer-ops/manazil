"""Owner-only property management using the existing posting form."""
import re

from flask import Blueprint, abort, current_app, g, redirect, render_template, request, send_file, url_for
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app import db
from app.admin import render_form
from app.auth import login_required
from app.languages import current_language, format_rent, property_type_label
from app.models import Property, PropertyPhoto
from app.photo_storage import MAX_PHOTOS_PER_PROPERTY, LocalPhotoStorage, PhotoError
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


def change_existing_photo(property, action, photo_id, storage, token):
    photo = next((item for item in property.photos if item.id == photo_id), None)
    if photo is None:
        abort(404)
    ordered = sorted(property.photos, key=lambda item: (item.display_order, item.id))
    removed_key = None
    if action == 'delete':
        removed_key = photo.storage_key
        if photo.is_primary:
            photo.is_primary = False
            db.session.flush()  # Release the unique primary slot before choosing its replacement.
        remaining = [item for item in ordered if item.id != photo_id]
        db.session.delete(photo)
        for position, item in enumerate(remaining):
            item.display_order = position
        if remaining and not any(item.is_primary for item in remaining):
            remaining[0].is_primary = True
    elif action == 'primary':
        for item in ordered:
            item.is_primary = False
        db.session.flush()
        photo.is_primary = True
        storage.clear_primary(token)
    elif action in ('up', 'down'):
        position = ordered.index(photo)
        destination = position + (-1 if action == 'up' else 1)
        if 0 <= destination < len(ordered):
            ordered[position], ordered[destination] = ordered[destination], ordered[position]
            for index, item in enumerate(ordered):
                item.display_order = index
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.warning('Photo update failed for property %s.', property.id)
        abort(503)
    if removed_key:
        try:
            storage.remove_keys([removed_key])
        except (PhotoError, OSError):
            current_app.logger.warning('Deleted photo file cleanup failed for property %s.', property.id)


@ownership.route('/properties/<int:property_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_property(property_id):
    property = owned_property(property_id)
    language = current_language()
    if request.method == 'GET':
        return render_form(editing_values(property), {}, language, edit_property=property)
    action = request.form.get('_action', 'submit')
    values = {key: request.form.get(key, '') for key in FORM_FIELDS}
    storage = LocalPhotoStorage()
    token = request.form.get('_photo_token') or storage.new_token()
    try:
        staged = storage.read(token)
    except PhotoError as error:
        return render_form(values, {}, language, edit_property=property, photo_error=str(error)), 400
    if staged.get('submitted_property_id'):
        return render_form(values, {}, language, edit_property=property, photo_token=token,
                           photo_error='This property has already been submitted.'), 409
    if action in ('switch_ar', 'switch_en'):
        return render_form(values, {}, action[-2:], edit_property=property, photo_token=token)
    if action == 'upload':
        try:
            storage.add(token, 'other', [file for file in request.files.getlist('photos') if file.filename],
                        max_photos=MAX_PHOTOS_PER_PROPERTY - len(property.photos),
                        auto_primary=not any(photo.is_primary for photo in property.photos))
        except PhotoError as error:
            return render_form(values, {}, language, edit_property=property, photo_token=token,
                               photo_error=str(error)), 422
        return render_form(values, {}, language, edit_property=property, photo_token=token)
    existing_action = re.fullmatch(r'(delete|primary|up|down)_existing_(\d+)', action)
    if existing_action:
        change_existing_photo(property, existing_action.group(1), int(existing_action.group(2)), storage, token)
        return render_form(values, {}, language, edit_property=property, photo_token=token)
    staged_action = re.fullmatch(r'(delete|primary|up|down)_([0-9a-f]{32})', action)
    if staged_action:
        try:
            storage.change(token, staged_action.group(2), staged_action.group(1))
        except PhotoError as error:
            return render_form(values, {}, language, edit_property=property, photo_token=token,
                               photo_error=str(error)), 422
        return render_form(values, {}, language, edit_property=property, photo_token=token)
    if action != 'submit':
        abort(400)
    selected_uploads = [file for file in request.files.getlist('photos') if file.filename]
    if selected_uploads:
        try:
            storage.add(token, 'other', selected_uploads,
                        max_photos=MAX_PHOTOS_PER_PROPERTY - len(property.photos),
                        auto_primary=not any(photo.is_primary for photo in property.photos))
            staged = storage.read(token)
        except PhotoError as error:
            return render_form(values, {}, language, edit_property=property, photo_token=token,
                               photo_error=str(error)), 422
    values, data, errors = validate_posting(values, language)
    if errors:
        return render_form(values, errors, language, edit_property=property, photo_token=token), 422
    # Posting-only defaults must never reset fields absent from the edit form.
    for key in ('title_en', 'description_en', 'city_en', 'area_en', 'city_ar', 'area_ar',
                'availability_status', 'available_from_date'):
        data.pop(key, None)
    copied = []
    try:
        # Lock the parent before counting so concurrent edits cannot exceed the total limit.
        db.session.execute(select(Property.id).where(Property.id == property.id).with_for_update()).scalar_one()
        existing_count = db.session.scalar(select(func.count(PropertyPhoto.id)).where(PropertyPhoto.property_id == property.id))
        if existing_count + len(staged['photos']) > MAX_PHOTOS_PER_PROPERTY:
            return render_form(values, {}, language, edit_property=property, photo_token=token,
                               photo_error='A property can contain at most 20 photos.'), 422
        prepared, copied = storage.prepare_property_photos(token, property.id)
        if any(photo['is_primary'] for photo in prepared):
            for photo in property.photos:
                photo.is_primary = False
            db.session.flush()
        for key, value in data.items():
            setattr(property, key, value)
        for index, photo in enumerate(sorted(prepared, key=lambda item: item['display_order'])):
            db.session.add(PropertyPhoto(
                property_id=property.id, category=photo['category'], storage_key=photo['storage_key'],
                original_filename=photo['original_filename'], content_type=photo['content_type'],
                file_size=photo['file_size'], display_order=existing_count + index,
                is_primary=photo['is_primary'],
            ))
        db.session.commit()
    except (PhotoError, SQLAlchemyError, ValueError, OSError):
        db.session.rollback()
        storage.remove_keys(copied)
        current_app.logger.warning('Property update failed for property %s.', property_id)
        return render_form(values, {}, language, edit_property=property, photo_token=token,
                           save_error='The property could not be saved. Your entries are still here. Please try again.'), 503
    if staged['photos']:
        try:
            storage.mark_submitted(token, property.id)
        except (PhotoError, OSError):
            current_app.logger.warning('Property updated, but staged-photo cleanup failed.')
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
