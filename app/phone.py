import re


def normalize_phone(value):
    """Return an E.164-style number, with Sudan local numbers as the default."""
    if not isinstance(value, str) or not re.fullmatch(r'\+?[0-9\s().-]+', value.strip()):
        raise ValueError('Invalid phone number')
    raw = value.strip()
    digits = re.sub(r'\D', '', raw)
    if raw.startswith('+'):
        normalized = '+' + digits
    elif digits.startswith('00'):
        normalized = '+' + digits[2:]
    elif re.fullmatch(r'09\d{8}', digits):
        normalized = '+249' + digits[1:]
    elif re.fullmatch(r'2499\d{8}', digits):
        normalized = '+' + digits
    else:
        raise ValueError('Invalid phone number')
    if not re.fullmatch(r'\+[1-9]\d{7,14}', normalized):
        raise ValueError('Invalid phone number')
    return normalized


def safe_contact_number(value):
    """Validate an existing listing number without rewriting legacy data."""
    try:
        return normalize_phone(value)
    except ValueError:
        return None


def property_contact_number(property):
    """Choose one safe contact number from current or legacy listing fields."""
    return safe_contact_number(property.whatsapp) or safe_contact_number(property.phone)
