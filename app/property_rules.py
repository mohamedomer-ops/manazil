"""Server-owned field applicability; JSON-safe metadata for a future wizard."""
PROPERTY_RULES = {
    'apartment': {'label': 'Apartment', 'required': ('size', 'bedrooms', 'bathrooms', 'floor'), 'optional': ('furnished',)},
    'house': {'label': 'House', 'required': ('size', 'bedrooms', 'bathrooms'), 'optional': ('floor', 'furnished')},
    'villa': {'label': 'Villa', 'required': ('size', 'bedrooms', 'bathrooms'), 'optional': ('floor', 'furnished')},
    'land': {'label': 'Land', 'required': ('size', 'land_use'), 'optional': ()},
    'office': {'label': 'Office', 'required': ('size', 'floor'), 'optional': ('bathrooms', 'furnished')},
    'shop': {'label': 'Shop', 'required': ('size', 'floor'), 'optional': ('bathrooms',)},
    'warehouse': {'label': 'Warehouse', 'required': ('size',), 'optional': ('bathrooms', 'floor')},
}
TRANSACTION_RULES = {
    'rent': {'label': 'For Rent', 'required': ('rent_period',), 'optional': ('available_from_date',), 'allowed_values': {'rent_period': ('monthly', 'weekly')}},
    'sale': {'label': 'For Sale', 'required': (), 'allowed_values': {}},
}
LAND_USES = {'residential': 'Residential', 'commercial': 'Commercial', 'agricultural': 'Agricultural',
             'industrial': 'Industrial', 'mixed': 'Mixed use'}
FIELD_LABELS = {'size': 'Size in square meters', 'bedrooms': 'Bedrooms', 'bathrooms': 'Bathrooms',
                'floor': 'Floor', 'land_use': 'Land use', 'furnished': 'Furnished',
                'property_occupancy': 'What are you renting?', 'rent_period': 'Rent period',
                'available_from_date': 'Available from'}
OCCUPANCIES = ('room', 'entire_property')
RESIDENTIAL_TYPES = ('apartment', 'house', 'villa')


def field_rules(property_type, transaction_type):
    rule = PROPERTY_RULES.get(property_type, {'required': (), 'optional': ()})
    required, optional = set(rule['required']), set(rule['optional'])
    required.update(TRANSACTION_RULES.get(transaction_type, {}).get('required', ()))
    optional.update(TRANSACTION_RULES.get(transaction_type, {}).get('optional', ()))
    if transaction_type == 'rent' and property_type in RESIDENTIAL_TYPES:
        required.add('property_occupancy')
    return {field: 'required' if field in required else 'optional' if field in optional else 'inapplicable'
            for field in FIELD_LABELS}


def public_rules():
    """Fresh plain metadata only: no application state or executable validators."""
    return {'types': {key: {'label': rule['label'], 'transactions': {
                transaction: field_rules(key, transaction) for transaction in TRANSACTION_RULES}}
            for key, rule in PROPERTY_RULES.items()}, 'transactions': list(TRANSACTION_RULES),
            'labels': dict(FIELD_LABELS), 'land_uses': dict(LAND_USES),
            'rent_periods': list(TRANSACTION_RULES['rent']['allowed_values']['rent_period']),
            'occupancies': list(OCCUPANCIES)}
