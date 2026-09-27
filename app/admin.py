from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_wtf.csrf import CSRFError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app import db
from app.models import DRAFT_OPTIONAL_TEXT_FIELDS, PHOTO_CATEGORIES, Property, PropertyPhoto
from app.property_forms import FORM_DEFAULTS, FORM_FIELDS, sudan_today, validate_property_form
from app.languages import availability_label, current_language, format_rent, property_type_label, translate
from app.states import STATE_BY_NAME, state_options
from app.photo_storage import LocalPhotoStorage, PhotoError, category_label


admin = Blueprint("admin", __name__, url_prefix="/admin")
STEPS = ("Basic Information", "Location", "Property Details", "Price & Availability",
         "Photos", "Contact Information", "Review")


def step_fields(step, language):
    if step == 1:
        return {"title_ar", "description_ar", "property_type"}
    if step == 2:
        return {f"state_{language}", "city_ar", "area_ar"}
    if step == 3:
        return {"bedrooms", "bathrooms", "size", "furnished", "amenities"}
    if step == 4:
        return {"monthly_rent", "currency", "availability_status", "availability_mode", "available_from_date"}
    if step == 6:
        return {"contact_name", "phone", "whatsapp", "contact_role"}
    return set()


def error_step(key):
    for step in (1, 2, 3, 4, 6):
        if key in step_fields(step, "ar") | step_fields(step, "en"):
            return step
    return 1


def render_form(values, errors, language, step=1, **kwargs):
    token = kwargs.pop("photo_token", None) or request.form.get("_photo_token") or LocalPhotoStorage().new_token()
    storage = LocalPhotoStorage()
    try:
        photos = storage.read(token)["photos"]
    except PhotoError:
        token, photos = storage.new_token(), []
    photos = sorted(photos, key=lambda photo: (PHOTO_CATEGORIES.index(photo["category"]), photo["display_order"]))
    return render_template(
        "admin/property_form.html", values=values, errors=errors,
        state_options=state_options(language), today=sudan_today().isoformat(),
        language=language, step=step, steps=STEPS,
        form_fields=tuple(field for field in FORM_FIELDS if field not in DRAFT_OPTIONAL_TEXT_FIELDS),
        visible_fields=step_fields(step, language),
        photo_token=token, photos=photos, photo_categories=PHOTO_CATEGORIES,
        category_label=category_label,
        t=lambda message: translate(message, language), **kwargs,
    )


@admin.errorhandler(CSRFError)
def handle_csrf_error(error):
    return render_form(
        request.form, {}, current_language(),
        step=max(1, min(7, int(request.form.get("_step", "1")) if request.form.get("_step", "1").isdigit() else 1)),
        save_error="The form could not be submitted. Refresh the page and try again.",
    ), 400


@admin.get("/properties/new")
def new_property():
    return render_form(FORM_DEFAULTS, {}, current_language(), photo_token=LocalPhotoStorage().new_token())


@admin.post("/properties")
def create_property():
    language = current_language()
    action = request.form.get("_action", "save")
    raw_step = request.form.get("_step", "1")
    step = max(1, min(7, int(raw_step))) if raw_step.isdigit() else 1
    if request.form.get("_wizard") == "1":
        storage = LocalPhotoStorage()
        token = request.form.get("_photo_token") or storage.new_token()
        try:
            staged = storage.read(token)
        except PhotoError as error:
            return render_form(request.form, {}, language, step=step, photo_error=str(error)), 400
        if staged.get("submitted_property_id"):
            return render_form(request.form, {}, language, step=step,
                               photo_error="This property has already been submitted."), 409
        values = {key: request.form.get(key, "") for key in FORM_FIELDS}
        values["availability_mode"] = request.form.get("availability_mode", "now")
        selected = STATE_BY_NAME[language].get(values[f"state_{language}"].strip())
        if selected:
            values["state_en"], values["state_ar"] = selected
        if step == 5 and action.startswith("upload_"):
            category = action[7:]
            try:
                storage.add(token, category, [file for file in request.files.getlist(f"photos_{category}") if file.filename])
            except PhotoError as error:
                return render_form(values, {}, language, step=5, photo_token=token, photo_error=str(error)), 422
            return render_form(values, {}, language, step=5, photo_token=token)
        if step == 5 and action.startswith(("delete_", "primary_", "up_", "down_")):
            operation, _, photo_id = action.partition("_")
            try:
                storage.change(token, photo_id, operation)
            except PhotoError as error:
                return render_form(values, {}, language, step=5, photo_token=token, photo_error=str(error)), 422
            return render_form(values, {}, language, step=5, photo_token=token)
        if action in ("switch_ar", "switch_en"):
            return render_form(values, {}, action[-2:], step=step, photo_token=token)
        if action == "back":
            return render_form(values, {}, language, step=max(1, step - 1), photo_token=token)
        if action.startswith("go_") and action[3:].isdigit():
            destination = int(action[3:])
            if 1 <= destination <= step:
                return render_form(values, {}, language, step=destination, photo_token=token)
            return render_form(values, {}, language, step=step), 400
        if action == "next" and step < 7:
            values, _, errors = validate_property_form(values, language, step_fields(step, language))
            if errors:
                return render_form(values, errors, language, step=step, photo_token=token), 422
            return render_form(values, {}, language, step=step + 1, photo_token=token)
        if action != "submit" or step != 7:
            return render_form(values, {}, language, step=step), 400
        values, data, errors = validate_property_form(values, language)
        if errors:
            first = next(iter(errors))
            if first.endswith(("_ar", "_en")):
                language = first[-2:]
            return render_form(values, errors, language, step=error_step(first), photo_token=token), 422
    else:
        # Preserve existing direct POST behavior for integrations and old clients.
        values, data, errors = validate_property_form(request.form, language)
    if action in ("switch_ar", "switch_en"):
        return render_form(values, {}, action[-2:])
    if action == "next":
        return render_form(values, {}, language), 400
    if errors:
        first = next(iter(errors))
        if any(key.endswith("_ar") for key in errors):
            language = "ar"
        elif any(key.endswith("_en") for key in errors):
            language = "en"
        return render_form(values, errors, language, step=error_step(first)), 422

    copied = []
    try:
        property = Property(**data, publication_status="pending" if request.form.get("_wizard") == "1" else "draft")
        db.session.add(property)
        db.session.flush()
        property_id = property.id
        if request.form.get("_wizard") == "1":
            prepared, copied = storage.prepare_property_photos(token, property_id)
            for photo in prepared:
                db.session.add(PropertyPhoto(
                    property_id=property_id, category=photo["category"], storage_key=photo["storage_key"],
                    original_filename=photo["original_filename"], content_type=photo["content_type"],
                    file_size=photo["file_size"], display_order=photo["display_order"],
                    is_primary=photo["is_primary"],
                ))
        db.session.commit()
    except PhotoError as error:
        db.session.rollback()
        storage.remove_keys(copied)
        return render_form(values, {}, language, step=5, photo_token=token, photo_error=str(error)), 422
    except (SQLAlchemyError, ValueError, OSError):
        db.session.rollback()
        if request.form.get("_wizard") == "1":
            storage.remove_keys(copied)
        current_app.logger.warning("Property creation failed; transaction rolled back.")
        return render_form(
            values, {}, language, step=step if request.form.get("_wizard") == "1" else 1,
            photo_token=token if request.form.get("_wizard") == "1" else None,
            save_error="The property could not be saved. Your entries are still here. Please try again.",
        ), 503

    if request.form.get("_wizard") == "1":
        try:
            storage.mark_submitted(token, property_id)
        except (PhotoError, OSError):
            current_app.logger.warning("Property submitted, but staged-photo cleanup failed.")
        flash({"message": "Your property has been submitted for review successfully.", "id": property_id}, "success")
    else:
        flash({"message": "Property #{id} was saved as Draft. It is not publicly visible.", "id": property_id}, "success")
    return redirect(url_for("admin.new_property", **({"lang": "en"} if language == "en" else {})), code=303)


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


@admin.get("/properties/pending")
def pending_properties():
    properties = db.session.scalars(
        select(Property).where(Property.publication_status == "pending")
        .options(selectinload(Property.photos)).order_by(Property.created_at.desc(), Property.id.desc())
    ).all()
    return render_template("admin/pending_properties.html", properties=properties,
                           category_label=category_label, format_rent=format_rent,
                           property_type_label=property_type_label)


@admin.get("/properties/<int:property_id>/review")
def review_property(property_id):
    property = db.session.scalar(
        select(Property).where(Property.id == property_id).options(selectinload(Property.photos))
    )
    if property is None:
        abort(404)
    return render_template("admin/property_review.html", property=property,
                           category_label=category_label, photo_categories=PHOTO_CATEGORIES,
                           today=sudan_today(), availability_label=availability_label,
                           format_rent=format_rent, property_type_label=property_type_label)


@admin.post("/properties/<int:property_id>/approve")
def approve_property(property_id):
    property = db.session.get(Property, property_id)
    if property is None or property.publication_status != "pending":
        abort(404)
    property.publication_status = "published"
    db.session.commit()
    flash("Property published successfully.", "success")
    return redirect(url_for("admin.pending_properties", **({"lang": "en"} if current_language() == "en" else {})), code=303)


@admin.post("/properties/<int:property_id>/reject")
def reject_property(property_id):
    property = db.session.get(Property, property_id)
    if property is None or property.publication_status != "pending":
        abort(404)
    property.publication_status = "draft"
    db.session.commit()
    flash("Property returned to Draft for changes.", "success")
    return redirect(url_for("admin.pending_properties", **({"lang": "en"} if current_language() == "en" else {})), code=303)
