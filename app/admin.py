from flask import Blueprint, abort, current_app, redirect, render_template, request, send_file, url_for
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import Property, PropertyPhoto
from app.property_forms import FORM_DEFAULTS, FORM_FIELDS, validate_posting
from app.languages import current_language, translate
from app.states import STATE_BY_NAME, state_options
from app.photo_storage import LocalPhotoStorage, PhotoError


admin = Blueprint("admin", __name__, url_prefix="/admin")


def render_form(values, errors, language, **kwargs):
    values = dict(values)
    for state_language in ("ar", "en"):
        selected = STATE_BY_NAME[state_language].get(values.get(f"state_{state_language}", "").strip())
        if selected:
            values["state_en"], values["state_ar"] = selected
            break
    storage = LocalPhotoStorage()
    token = kwargs.pop("photo_token", None) or request.form.get("_photo_token") or storage.new_token()
    try:
        photos = sorted(storage.read(token)["photos"], key=lambda photo: photo["display_order"])
    except PhotoError:
        token, photos = storage.new_token(), []
    return render_template(
        "admin/property_form.html", values=values, errors=errors,
        state_options=state_options(language), language=language,
        photo_token=token, photos=photos,
        t=lambda message: translate(message, language), **kwargs,
    )


@admin.errorhandler(CSRFError)
def handle_csrf_error(error):
    return render_form(request.form, {}, current_language(),
                       save_error="The form could not be submitted. Refresh the page and try again."), 400


@admin.get("/properties/new")
def new_property():
    return render_form(FORM_DEFAULTS, {}, current_language(), photo_token=LocalPhotoStorage().new_token())


@admin.post("/properties")
def create_property():
    language = current_language()
    action = request.form.get("_action", "submit")
    storage = LocalPhotoStorage()
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
        return render_form(values, {}, action[-2:], photo_token=token)
    if action != "submit":
        return render_form(values, {}, language, photo_token=token), 400
    values, data, errors = validate_posting(values, language)
    if errors:
        return render_form(values, errors, language, photo_token=token), 422
    copied = []
    try:
        property = Property(**data, publication_status="published")
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
    storage = LocalPhotoStorage()
    try:
        photo = next((item for item in storage.read(token)["photos"] if item["id"] == photo_id), None)
        if photo is None:
            abort(404)
        return send_file(storage.path(photo["storage_key"]), mimetype=photo["content_type"], max_age=0)
    except (PhotoError, OSError):
        abort(404)


@admin.get("/property-photos/<int:photo_id>")
def review_photo(photo_id):
    photo = db.session.get(PropertyPhoto, photo_id)
    if photo is None:
        abort(404)
    try:
        return send_file(LocalPhotoStorage().path(photo.storage_key), mimetype=photo.content_type)
    except (PhotoError, OSError):
        abort(404)


