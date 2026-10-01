"""Validated, URL-friendly filters for publicly visible property listings."""
import re

from app.languages import PROPERTY_TYPE_NAMES
from app.models import Property
from app.states import SUDAN_STATES


STATE_OPTIONS = tuple((re.sub(r'[^a-z0-9]+', '-', english.lower()).strip('-'), english, arabic)
                      for english, arabic in SUDAN_STATES)
STATE_BY_SLUG = {slug: english for slug, english, _ in STATE_OPTIONS}
FILTER_FIELDS = ('transaction', 'state', 'bedrooms', 'seller', 'property_type')


def validated_filters(params):
    """Ignore unknown/invalid values; never pass raw input into query structure."""
    allowed = {
        'transaction': ('rent', 'sale'),
        'state': STATE_BY_SLUG,
        'bedrooms': ('1', '2', '3', '4', '5'),
        'seller': ('owner', 'broker'),
        'property_type': PROPERTY_TYPE_NAMES,
    }
    return {key: value for key in FILTER_FIELDS
            if (value := params.get(key, '')) in allowed[key]}


def apply_filters(statement, filters):
    if transaction := filters.get('transaction'):
        statement = statement.where(Property.transaction_type == transaction)
    if state := filters.get('state'):
        statement = statement.where(Property.state_en == STATE_BY_SLUG[state])
    if bedrooms := filters.get('bedrooms'):
        statement = statement.where(Property.bedrooms >= int(bedrooms))
    if seller := filters.get('seller'):
        statement = statement.where(Property.contact_role == seller)
    if property_type := filters.get('property_type'):
        statement = statement.where(Property.property_type == property_type)
    return statement
