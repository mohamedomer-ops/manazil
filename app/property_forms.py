from decimal import Decimal, InvalidOperation
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.states import STATE_BY_NAME
from app.phone import normalize_phone
from app.models import CURRENCIES, MAX_COMMENT_LENGTH
from app.property_rules import PROPERTY_RULES, TRANSACTION_RULES, LAND_USES, OCCUPANCIES, field_rules

FORM_FIELDS = (
    "transaction_type", "property_occupancy", "agent", "property_type", "title_ar",
    "description_ar", "bedrooms", "bathrooms", "size", "furnished", "amenities",
    "rent_period", "price", "currency", "contact_name", "whatsapp",
    "state_ar", "state_en", "neighborhood_ar",
    "latitude", "longitude", "floor", "land_use", "available_from_date", "comment",
)
FORM_DEFAULTS = {"currency": "SDG", "transaction_type": "rent", "property_occupancy": "entire_property", "agent": "no", "rent_period": "monthly"}
PROPERTY_TYPES = frozenset(PROPERTY_RULES)


def sudan_today():
    return datetime.now(ZoneInfo("Africa/Khartoum")).date()


def validate_posting(form, language="ar", existing=None):
    """Validate new listings strictly; grandfather missing facts on unchanged edits.

    A type/transaction change opts into all current requirements and clears
    inapplicable facts. Unchanged legacy classifications retain existing
    inapplicable values, ignoring posted replacements rather than losing history.
    """
    values = {key: form.get(key, "") for key in FORM_FIELDS}
    errors, data = {}, {}
    comment = values['comment'].strip()
    if '\x00' in comment:
        errors['comment'] = 'Remove the invalid character from this field.'
    elif len(comment) > MAX_COMMENT_LENGTH:
        errors['comment'] = 'Comment must be 2000 characters or fewer.'
    else:
        data['comment'] = comment or None
    rules = field_rules(values["property_type"], values["transaction_type"])
    same_classification = (existing is not None
                           and existing.property_type == values["property_type"]
                           and existing.transaction_type == values["transaction_type"])

    # Unchanged historical classifications may retain missing/newly inapplicable facts.
    def legacy_missing(key):
        return same_classification and getattr(existing, key, None) is None

    for key, choices in (("transaction_type", TRANSACTION_RULES), ("agent", {"yes", "no"}), ("property_type", PROPERTY_TYPES)):
        if values[key] not in choices:
            errors[key] = "Choose one of the available options."
        else:
            if key != "agent":
                data[key] = values[key]
    if rules["property_occupancy"] == "inapplicable":
        data["property_occupancy"] = existing.property_occupancy if same_classification else "entire_property"
    elif values["property_occupancy"] in OCCUPANCIES:
        data["property_occupancy"] = values["property_occupancy"]
    else:
        errors["property_occupancy"] = "Choose one of the available options."
    data["contact_role"] = "broker" if values["agent"] == "yes" else "owner"
    if values["transaction_type"] == "rent":
        if values["rent_period"] not in TRANSACTION_RULES["rent"]["allowed_values"]["rent_period"]:
            errors["rent_period"] = "Choose one of the available options."
        else:
            data["rent_period"] = values["rent_period"]
    elif values["transaction_type"] == "sale":
        if values["rent_period"]:
            errors["rent_period"] = "Sale listings cannot have a rent period."
        data["rent_period"] = None
    for key in ("title_ar", "description_ar", "contact_name", "neighborhood_ar"):
        value = values[key].strip()
        if not value:
            errors[key] = "This field is required."
        elif "\x00" in value:
            errors[key] = "Remove the invalid character from this field."
        else:
            data[key] = value
    if values["currency"] in CURRENCIES:
        data["currency"] = values["currency"]
    else:
        errors["currency"] = "Choose SDG or USD."
    selected = STATE_BY_NAME[language].get(values[f"state_{language}"].strip())
    if selected is None:
        errors[f"state_{language}"] = "Choose a Sudanese state from the list."
    else:
        data["state_en"], data["state_ar"] = selected
    for key in ("price", "size", "bedrooms", "bathrooms", "floor"):
        value = values[key].strip()
        applicability = rules.get(key, "required")
        if applicability == "inapplicable":
            data[key] = getattr(existing, key) if same_classification else None
            continue
        if not value and (applicability == "optional" or legacy_missing(key)):
            data[key] = None
            continue
        try:
            if key in ("bedrooms", "bathrooms", "floor"):
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
    coordinates = {key: values[key].strip() for key in ("latitude", "longitude")}
    if any(coordinates.values()) and not all(coordinates.values()):
        errors["coordinates"] = "Select both latitude and longitude on the map."
    elif not any(coordinates.values()):
        data.update(latitude=None, longitude=None)
    else:
        for key, limit in (("latitude", 90), ("longitude", 180)):
            try:
                number = Decimal(coordinates[key])
                if not number.is_finite() or abs(number) > limit or number.as_tuple().exponent < -6:
                    raise ValueError
                data[key] = number
            except (InvalidOperation, ValueError):
                errors[key] = "Select a valid location on the map."
    if rules["land_use"] == "inapplicable":
        data["land_use"] = existing.land_use if same_classification else None
    elif values["land_use"] in LAND_USES:
        data["land_use"] = values["land_use"]
    elif not values["land_use"] and legacy_missing("land_use"):
        data["land_use"] = None
    else:
        errors["land_use"] = "Choose one of the available options."
    data["furnished"] = (existing.furnished if same_classification else False) if rules["furnished"] == "inapplicable" else values["furnished"] == "on"
    if rules["furnished"] != "inapplicable" and values["furnished"] not in ("", "on"):
        errors["furnished"] = "Choose checked or unchecked."
    data["amenities"] = [item.strip() for item in values["amenities"].splitlines() if item.strip()]
    try:
        data['whatsapp'] = data['phone'] = normalize_phone(values['whatsapp'])
    except ValueError:
        errors['whatsapp'] = 'Enter a valid phone number.'
    for key in ("amenities", "whatsapp"):
        if "\x00" in values[key]:
            errors[key] = "Remove the invalid character from this field."
    if rules['available_from_date'] != 'inapplicable':
        try:
            data['available_from_date'] = date.fromisoformat(values['available_from_date']) if values['available_from_date'] else None
        except ValueError:
            errors['available_from_date'] = 'Enter a valid date.'
    else:
        data['available_from_date'] = None
    data.update(title_en="", description_en="", city_en="", area_en="", city_ar=None, area_ar=None, monthly_rent=None, availability_status="available")
    return values, data, errors
