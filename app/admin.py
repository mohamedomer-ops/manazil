from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import Property
from app.property_forms import FORM_DEFAULTS, sudan_today, validate_property_form
from app.languages import current_language, translate
from app.states import state_options


admin = Blueprint("admin", __name__, url_prefix="/admin")


def render_form(values, errors, language, **kwargs):
    return render_template(
        "admin/property_form.html", values=values, errors=errors,
        state_options=state_options(language), today=sudan_today().isoformat(),
        language=language, t=lambda message: translate(message, language), **kwargs,
    )


@admin.errorhandler(CSRFError)
def handle_csrf_error(error):
    return render_form(
        request.form, {}, current_language(),
        save_error="The form could not be submitted. Refresh the page and try again.",
    ), 400


@admin.get("/properties/new")
def new_property():
    return render_form(FORM_DEFAULTS, {}, current_language())


@admin.post("/properties")
def create_property():
    language = current_language()
    values, data, errors = validate_property_form(request.form, language)
    action = request.form.get("_action", "save")
    if action in ("switch_ar", "switch_en"):
        return render_form(values, {}, action[-2:])
    if action == "next":
        errors = {key: message for key, message in errors.items() if not key.endswith("_en")}
        if errors:
            return render_form(values, errors, "ar"), 422
        return render_form(values, {}, "en")
    if errors:
        if any(key.endswith("_ar") for key in errors):
            language = "ar"
        elif any(key.endswith("_en") for key in errors):
            language = "en"
        return render_form(values, errors, language), 422

    try:
        property = Property(**data, publication_status="draft")
        db.session.add(property)
        db.session.flush()
        property_id = property.id
        db.session.commit()
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        current_app.logger.warning("Property creation failed; transaction rolled back.")
        return render_form(
            values, {}, language,
            save_error="The property could not be saved. Your entries are still here. Please try again.",
        ), 503

    flash({"message": "Property #{id} was saved as Draft. It is not publicly visible.", "id": property_id}, "success")
    return redirect(url_for("admin.new_property", **({"lang": "en"} if language == "en" else {})), code=303)
