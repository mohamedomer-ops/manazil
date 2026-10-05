"""Normalization shared by manual signup and validated provider profile claims."""
import re


def normalize_email(value):
    if not isinstance(value, str):
        raise ValueError('Invalid email')
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r'[^\s@\x00-\x1f\x7f]+@[^\s@\x00-\x1f\x7f]+\.[^\s@\x00-\x1f\x7f]+', value):
        raise ValueError('Invalid email')
    return value


def normalize_name(value):
    if not isinstance(value, str):
        raise ValueError('Invalid name')
    value = value.strip()
    if not value or len(value) > 100 or any(ord(char) < 32 for char in value):
        raise ValueError('Invalid name')
    return value
