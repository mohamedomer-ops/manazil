from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import Property, PropertyPhoto, MAX_COMMENT_LENGTH
from app.property_forms import FORM_DEFAULTS, FORM_FIELDS, validate_posting
from app.languages import current_language, translate
from app.states import STATE_BY_NAME, state_options
from app.photo_storage import MAX_PHOTOS_PER_PROPERTY, photo_storage, PhotoError
from app.auth import login_required
from app.property_rules import PROPERTY_RULES, LAND_USES, public_rules
from flask import g


admin = Blueprint("admin", __name__, url_prefix="/admin")


def render_form(values, errors, language, **kwargs):
    values = dict(values)
    for state_language in ("ar", "en"):
        selected = STATE_BY_NAME[state_language].get(values.get(f"state_{state_language}", "").strip())
        if selected:
            values["state_en"], values["state_ar"] = selected
            break
    storage = photo_storage()
    token = kwargs.pop("photo_token", None) or request.form.get("_photo_token") or storage.new_token()
    try:
        photos = sorted(storage.read(token)["photos"], key=lambda photo: photo["display_order"])
    except PhotoError:
        token, photos = storage.new_token(), []
    edit = kwargs.get('edit_property')
    rules = public_rules()
    rules['original'] = {'property_type': edit.property_type, 'transaction_type': edit.transaction_type} if edit else None
    rules['legacy_missing'] = [key for key in rules['labels'] if edit and getattr(edit, key, None) is None]
    rules['errors'] = list(errors)
    sections = {'transaction_type': 'purpose', 'property_type': 'property', 'property_occupancy': 'occupancy',
                'state_ar': 'location', 'state_en': 'location', 'neighborhood_ar': 'location',
                'coordinates': 'location', 'latitude': 'location', 'longitude': 'location',
                'price': 'transaction', 'currency': 'transaction', 'rent_period': 'transaction',
                'available_from_date': 'transaction', 'title_ar': 'description', 'description_ar': 'description', 'comment': 'description',
                'contact_name': 'contact', 'whatsapp': 'contact', 'agent': 'contact'}
    requested = request.form.get('_wizard_section', 'purpose')
    allowed_sections = {'purpose', 'property', 'occupancy', 'location', 'details', 'transaction', 'description', 'photos', 'contact', 'review'}
    initial = sections.get(next(iter(errors), ''), 'details') if errors else requested
    if kwargs.get('photo_error'):
        initial = 'photos'
    elif request.form.get('_action', '').startswith(('upload', 'delete_', 'primary_', 'up_', 'down_')):
        initial = requested if requested in ('contact', 'review') else 'photos'
    if initial not in allowed_sections:
        initial = 'purpose'
    return render_template(
        "admin/property_form.html", values=values, errors=errors,
        state_options=state_options(language), language=language,
        photo_token=token, photos=photos, max_photos=MAX_PHOTOS_PER_PROPERTY,
        property_types={key: rule["label"] for key, rule in PROPERTY_RULES.items()}, land_uses=LAND_USES,
        wizard_rules=rules, wizard_initial=initial, max_comment_length=MAX_COMMENT_LENGTH,
        t=lambda message: translate(message, language), **kwargs,
    )


@admin.errorhandler(CSRFError)
def handle_csrf_error(error):
    return render_form(request.form, {}, current_language(),
                       save_error="The form could not be submitted. Refresh the page and try again."), 400


@admin.get("/properties/new")
@login_required
def new_property():
    if not g.user.contact_complete:
        from flask import session
        session['contact_next'] = request.full_path if request.query_string else request.path
        return redirect(url_for('auth.account', **({'lang': 'en'} if current_language() == 'en' else {})))
    defaults = FORM_DEFAULTS | {'contact_name': g.user.contact_name,
                                'whatsapp': g.user.whatsapp,
                                'agent': 'yes' if g.user.contact_role == 'broker' else 'no'}
    return render_form(defaults, {}, current_language(), photo_token=photo_storage().new_token())


@admin.post("/properties")
@login_required
def create_property():
    if not g.user.contact_complete:
        from flask import session
        session['contact_next'] = url_for('admin.new_property')
        return redirect(url_for('auth.account'), code=303)
    language = current_language()
    action = request.form.get("_action", "submit")
    storage = photo_storage()
    token = request.form.get("_photo_token") or storage.new_token()
    try:
        staged = storage.read(token)
    except PhotoError as error:
        return render_form(request.form, {}, language, photo_error=str(error)), 400
    if staged.get("submitted_property_id"):
        return render_form(request.form, {}, language, photo_token=token,
                           photo_error="This property has already been submitted."), 409
    values = {key: request.form.get(key, "") for key in FORM_FIELDS}
    if action == "upload":
        try:
            storage.add(token, "other", [file for file in request.files.getlist("photos") if file.filename])
        except PhotoError as error:
            return render_form(values, {}, language, photo_token=token, photo_error=str(error)), 422
        return render_form(values, {}, language, photo_token=token)
    if action.startswith(("delete_", "primary_", "up_", "down_")):
        operation, _, photo_id = action.partition("_")
        try:
            storage.change(token, photo_id, operation)
        except PhotoError as error:
            return render_form(values, {}, language, photo_token=token, photo_error=str(error)), 422
        return render_form(values, {}, language, photo_token=token)
    if action in ("switch_ar", "switch_en"):
        selected = [file for file in request.files.getlist('photos') if file.filename]
        if selected:
            try:
                storage.add(token, 'other', selected)
            except PhotoError as error:
                return render_form(values, {}, action[-2:], photo_token=token, photo_error=str(error)), 422
        return render_form(values, {}, action[-2:], photo_token=token)
    if action != "submit":
        return render_form(values, {}, language, photo_token=token), 400
    selected = [file for file in request.files.getlist('photos') if file.filename]
    if selected:
        try:
            storage.add(token, 'other', selected)
        except PhotoError as error:
            return render_form(values, {}, language, photo_token=token, photo_error=str(error)), 422
    values, data, errors = validate_posting(values, language)
    if errors:
        return render_form(values, errors, language, photo_token=token), 422
    copied = []
    try:
        property = Property(**data, owner_id=g.user.id, publication_status="published")
        db.session.add(property)
        db.session.flush()
        prepared, copied = storage.prepare_property_photos(token, property.id)
        for photo in prepared:
            db.session.add(PropertyPhoto(
                property_id=property.id, category=photo["category"], storage_key=photo["storage_key"],
                original_filename=photo["original_filename"], content_type=photo["content_type"],
                file_size=photo["file_size"], display_order=photo["display_order"],
                is_primary=photo["is_primary"],
            ))
        db.session.commit()
    except (PhotoError, SQLAlchemyError, ValueError, OSError) as error:
        db.session.rollback()
        storage.remove_keys(copied)
        current_app.logger.warning("Property creation failed: %s", error)
        return render_form(values, {}, language, photo_token=token,
                           save_error="The property could not be saved. Your entries are still here. Please try again."), 503
    try:
        storage.mark_submitted(token, property.id)
    except (PhotoError, OSError):
        current_app.logger.warning("Property submitted, but staged-photo cleanup failed.")
    return redirect(url_for("main.property_detail", property_id=property.id,
                            **({"lang": "en"} if language == "en" else {})), code=303)


@admin.get("/properties/staged-photos/<token>/<photo_id>")
def staged_photo(token, photo_id):
    storage = photo_storage()
    try:
        photo = next((item for item in storage.read(token)["photos"] if item["id"] == photo_id), None)
        if photo is None:
            abort(404)
        return storage.send(photo["storage_key"], photo["content_type"], max_age=0)
    except (PhotoError, OSError):
        abort(404)


@admin.get("/property-photos/<int:photo_id>")
@login_required
def review_photo(photo_id):
    photo = db.session.scalar(select(PropertyPhoto).join(Property).where(
        PropertyPhoto.id == photo_id, Property.owner_id == g.user.id))
    if photo is None:
        abort(404)
    try:
        response = photo_storage().send(photo.storage_key, photo.content_type, max_age=0)
        response.headers['Cache-Control'] = 'private, no-store'
        return response
    except (PhotoError, OSError):
        abort(404)


