import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from app.models import CHOICES, DRAFT_OPTIONAL_TEXT_FIELDS
from app.states import STATE_BY_NAME


TEXT_FIELDS = (
    "title_en", "title_ar", "description_en", "description_ar",
    "state_en", "state_ar", "city_en", "city_ar", "area_en", "area_ar", "property_type",
    "currency", "contact_name", "phone", "contact_role", "availability_status",
)
FORM_FIELDS = (*TEXT_FIELDS, "monthly_rent", "bedrooms", "bathrooms", "size",
               "furnished", "amenities", "whatsapp", "availability_mode", "available_from_date")
FORM_DEFAULTS = {"currency": "SDG", "contact_role": "owner", "availability_status": "available", "availability_mode": "now"}


def sudan_today():
    return datetime.now(ZoneInfo("Africa/Khartoum")).date()


def validate_property_form(form, language="ar", fields=None):
    """Return display values, typed model values, and field-specific errors."""
    values = {key: form.get(key, "") for key in FORM_FIELDS}
    if "availability_mode" not in form:
        values["availability_mode"] = "now"
    data, errors = {}, {}

    for state_language in ("ar", "en"):
        key = f"state_{state_language}"
        if values[key].strip() and values[key].strip() not in STATE_BY_NAME[state_language]:
            errors[key] = "Choose a Sudanese state from the list."
    selected_state = STATE_BY_NAME[language].get(values[f"state_{language}"].strip())
    if selected_state and not any(key in errors for key in ("state_ar", "state_en")):
        # The visible selection is authoritative; never store mismatched translations.
        values["state_en"], values["state_ar"] = selected_state

    for key in TEXT_FIELDS:
        value = values[key].strip()
        if not value and key in DRAFT_OPTIONAL_TEXT_FIELDS:
            data[key] = ""
        elif not value:
            errors[key] = "This field is required."
        elif key in CHOICES and value not in CHOICES[key]:
            errors[key] = "Choose one of the available options."
        elif "\x00" in value:
            errors[key] = "Remove the invalid character from this field."
        else:
            data[key] = value

    for key in ("monthly_rent", "bedrooms", "bathrooms", "size"):
        value = values[key].strip()
        if not value:
            if key == "size":
                data[key] = None
            else:
                errors[key] = "This field is required."
            continue
        try:
            if key in ("bedrooms", "bathrooms"):
                if not re.fullmatch(r"[0-9]+", value):
                    raise ValueError
                number = int(value)
                if number > 2147483647:
                    raise ValueError
            else:
                number = Decimal(value)
                if not number.is_finite() or number < 0:
                    raise ValueError
                # PostgreSQL NUMERIC has finite storage limits even without precision.
                if number.adjusted() >= 131072 or number.as_tuple().exponent < -16383:
                    raise ValueError
            data[key] = number
        except (ValueError, InvalidOperation):
            errors[key] = (
                "Enter a whole number from 0 to 2147483647."
                if key in ("bedrooms", "bathrooms")
                else "Enter a valid, finite number of 0 or greater."
            )

    data["furnished"] = values["furnished"] == "on"
    if values["furnished"] not in ("", "on"):
        errors["furnished"] = "Choose checked or unchecked."
    data["amenities"] = [line.strip() for line in values["amenities"].splitlines() if line.strip()]
    data["whatsapp"] = values["whatsapp"].strip() or None
    for key in ("amenities", "whatsapp"):
        if "\x00" in values[key]:
            errors[key] = "Remove the invalid character from this field."

    data["available_from_date"] = None
    if values["availability_mode"] not in ("now", "date"):
        errors["availability_mode"] = "Choose one of the available options."
    elif values["availability_mode"] == "date":
        date_value = values["available_from_date"].strip()
        if not date_value:
            errors["available_from_date"] = "Choose an availability date."
        else:
            try:
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", date_value):
                    raise ValueError
                available_from = date.fromisoformat(date_value)
                if available_from < sudan_today():
                    errors["available_from_date"] = "Choose today or a future date."
                else:
                    data["available_from_date"] = available_from
            except ValueError:
                errors["available_from_date"] = "Enter a valid date."
    if fields is not None:
        errors = {key: message for key, message in errors.items() if key in fields}
    return values, data, errors
