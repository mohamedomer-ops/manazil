"""Canonical state names used by the property creation form."""

SUDAN_STATES = (
    ("Khartoum", "الخرطوم"),
    ("Al Jazirah", "الجزيرة"),
    ("Red Sea", "البحر الأحمر"),
    ("Kassala", "كسلا"),
    ("Gedaref", "القضارف"),
    ("Sennar", "سنار"),
    ("Blue Nile", "النيل الأزرق"),
    ("White Nile", "النيل الأبيض"),
    ("Northern", "الشمالية"),
    ("River Nile", "نهر النيل"),
)

STATE_BY_NAME = {
    "en": {state[0]: state for state in SUDAN_STATES},
    "ar": {state[1]: state for state in SUDAN_STATES},
}


def state_options(language):
    index = 1 if language == "ar" else 0
    return [(state[index], state[index]) for state in SUDAN_STATES]
