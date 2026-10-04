import re


# Calling codes offered by the public account forms. Stored accounts keep one
# canonical international number; these selections are presentation only.
AUTH_COUNTRIES = (
    ('+249', 'Sudan', 'السودان', '912345678', '🇸🇩'),
    ('+211', 'South Sudan', 'جنوب السودان', '912345678', '🇸🇸'),
    ('+20', 'Egypt', 'مصر', '1001234567', '🇪🇬'),
    ('+251', 'Ethiopia', 'إثيوبيا', '911234567', '🇪🇹'),
    ('+235', 'Chad', 'تشاد', '66123456', '🇹🇩'),
    ('+254', 'Kenya', 'كينيا', '712345678', '🇰🇪'),
    ('+966', 'Saudi Arabia', 'السعودية', '512345678', '🇸🇦'),
    ('+971', 'United Arab Emirates', 'الإمارات', '501234567', '🇦🇪'),
    ('+974', 'Qatar', 'قطر', '55123456', '🇶🇦'),
    ('+44', 'United Kingdom', 'المملكة المتحدة', '7700900123', '🇬🇧'),
    ('+1', 'United States / Canada', 'الولايات المتحدة / كندا', '2025550123', '🇺🇸🇨🇦'),
    ('+49', 'Germany', 'ألمانيا', '15123456789', '🇩🇪'),
    ('+90', 'Turkey', 'تركيا', '5321234567', '🇹🇷'),
)
AUTH_CALLING_CODES = frozenset(country[0] for country in AUTH_COUNTRIES)


def normalize_auth_phone(country_code, local_number):
    """Combine a selected calling code and local entry before canonical validation."""
    code = country_code or '+249'  # Existing forms and saved clients default to Sudan.
    if code not in AUTH_CALLING_CODES or not isinstance(local_number, str):
        raise ValueError('Invalid phone number')
    raw = local_number.strip()
    if raw.startswith('+') or re.match(r'^00', raw):
        return normalize_phone(raw)  # Existing full-number entry remains valid.
    if not re.fullmatch(r'[0-9\s().-]+', raw):
        raise ValueError('Invalid phone number')
    digits = re.sub(r'\D', '', raw)
    if code == '+249' and re.fullmatch(r'2499\d{8}', digits):
        return normalize_phone('+' + digits)
    return normalize_phone(code + digits.lstrip('0'))


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
