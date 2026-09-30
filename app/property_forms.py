from decimal import Decimal, InvalidOperation
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from app.states import STATE_BY_NAME
from app.phone import normalize_phone

FORM_FIELDS = (
    "transaction_type", "property_occupancy", "agent", "property_type", "title_ar",
    "description_ar", "bedrooms", "bathrooms", "size", "furnished", "amenities",
    "rent_period", "price", "currency", "contact_name", "phone", "whatsapp",
    "state_ar", "state_en", "neighborhood_ar",
)
FORM_DEFAULTS = {"currency": "SDG", "transaction_type": "rent", "property_occupancy": "entire_property", "agent": "no", "rent_period": "monthly"}
PROPERTY_TYPES = {"apartment", "house", "villa", "office", "shop", "land"}


def sudan_today():
    return datetime.now(ZoneInfo("Africa/Khartoum")).date()


def validate_posting(form, language="ar"):
    values = {key: form.get(key, "") for key in FORM_FIELDS}
    errors, data = {}, {}
    for key, choices in (("transaction_type", {"rent", "sale"}), ("property_occupancy", {"room", "entire_property"}), ("agent", {"yes", "no"}), ("property_type", PROPERTY_TYPES)):
        if values[key] not in choices:
            errors[key] = "Choose one of the available options."
        else:
            if key != "agent":
                data[key] = values[key]
    data["contact_role"] = "broker" if values["agent"] == "yes" else "owner"
    if values["transaction_type"] == "rent":
        if values["rent_period"] not in ("monthly", "weekly"):
            errors["rent_period"] = "Choose one of the available options."
        else:
            data["rent_period"] = values["rent_period"]
    elif values["transaction_type"] == "sale":
        if values["rent_period"]:
            errors["rent_period"] = "Sale listings cannot have a rent period."
        data["rent_period"] = None
    for key in ("title_ar", "description_ar", "currency", "contact_name", "phone", "neighborhood_ar"):
        value = values[key].strip()
        if not value:
            errors[key] = "This field is required."
        elif "\x00" in value:
            errors[key] = "Remove the invalid character from this field."
        else:
            data[key] = value
    selected = STATE_BY_NAME[language].get(values[f"state_{language}"].strip())
    if selected is None:
        errors[f"state_{language}"] = "Choose a Sudanese state from the list."
    else:
        data["state_en"], data["state_ar"] = selected
    for key in ("price", "size", "bedrooms", "bathrooms"):
        value = values[key].strip()
        if not value and key == "size":
            data[key] = None
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
                if not number.is_finite() or number < 0 or number.adjusted() >= 131072 or number.as_tuple().exponent < -16383:
                    raise ValueError
            data[key] = number
        except (InvalidOperation, ValueError):
            errors[key] = "Enter a valid, finite number of 0 or greater."
    data["furnished"] = values["furnished"] == "on"
    if values["furnished"] not in ("", "on"):
        errors["furnished"] = "Choose checked or unchecked."
    data["amenities"] = [item.strip() for item in values["amenities"].splitlines() if item.strip()]
    for key in ('phone', 'whatsapp'):
        if key == 'whatsapp' and not values[key].strip():
            data[key] = None
            continue
        try:
            data[key] = normalize_phone(values[key])
        except ValueError:
            errors[key] = 'Enter a valid phone number.'
    for key in ("amenities", "whatsapp"):
        if "\x00" in values[key]:
            errors[key] = "Remove the invalid character from this field."
    data.update(title_en="", description_en="", city_en="", area_en="", city_ar=None, area_ar=None, monthly_rent=None, availability_status="available", available_from_date=None)
    return values, data, errors
