"""Listing age and compact facts remain informational, localized, and shared."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from flask import current_app, render_template_string

from app import db
from app.languages import relative_posting_age, translate, format_rent
from app.models import SavedProperty
from test_auth import client
from test_properties import migrated_connection, values
from test_public_properties import add_property
from test_saved_properties import sign_in

NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize('seconds,en,ar', [
    (0, 'Just now', 'الآن'), (59, 'Just now', 'الآن'),
    (60, '1 minute ago', 'منذ دقيقة'), (120, '2 minutes ago', 'منذ دقيقتين'),
    (300, '5 minutes ago', 'منذ 5 دقائق'), (3540, '59 minutes ago', 'منذ 59 دقيقة'),
    (3600, '1 hour ago', 'منذ ساعة'), (7200, '2 hours ago', 'منذ ساعتين'),
    (10800, '3 hours ago', 'منذ 3 ساعات'), (82800, '23 hours ago', 'منذ 23 ساعة'),
    (86400, '1 day ago', 'منذ يوم'), (172800, '2 days ago', 'منذ يومين'),
    (432000, '5 days ago', 'منذ 5 أيام'), (518400, '6 days ago', 'منذ 6 أيام'),
    (604800, '1 week ago', 'منذ أسبوع'), (1209600, '2 weeks ago', 'منذ أسبوعين'),
    (1814400, '3 weeks ago', 'منذ 3 أسابيع'), (2505600, '4 weeks ago', 'منذ 4 أسابيع'),
    (2592000, '1 month ago', 'منذ شهر'), (5184000, '2 months ago', 'منذ شهرين'),
    (7776000, '3 months ago', 'منذ 3 أشهر'), (15552000, '6 months ago', 'منذ 6 أشهر'),
    (31536000, '12 months ago', 'منذ 12 شهر'), (38880000, '15 months ago', 'منذ 15 شهر'),
    (63072000, '24 months ago', 'منذ 24 شهر'),
])
def test_relative_age_ranges_and_arabic_forms(seconds, en, ar):
    created = NOW - timedelta(seconds=seconds)
    assert relative_posting_age(created, 'en', NOW) == en
    assert relative_posting_age(created, 'ar', NOW) == ar
    assert 'year' not in en and 'سنة' not in ar


@pytest.mark.parametrize('timestamp', [None, '', 'not-a-date'])
def test_missing_age_is_omitted(timestamp):
    assert relative_posting_age(timestamp, 'en', NOW) is None


def test_relative_age_handles_naive_utc_offsets_and_future():
    assert relative_posting_age((NOW - timedelta(hours=2)).replace(tzinfo=None), 'en', NOW) == '2 hours ago'
    assert relative_posting_age((NOW - timedelta(hours=2)).astimezone(timezone(timedelta(hours=3))), 'en', NOW) == '2 hours ago'
    assert relative_posting_age(NOW + timedelta(hours=1), 'en', NOW) == 'Just now'


@pytest.mark.parametrize('language', ['ar', 'en'])
def test_created_at_age_and_shared_card_surfaces(client, values, monkeypatch, language):
    user = sign_in(client)
    property = add_property(values, publication_status='published', owner_id=user.id,
                            created_at=NOW - timedelta(days=450), updated_at=NOW,
                            neighborhood_ar='العمارات', size=230, bedrooms=8, bathrooms=6)
    db.session.add(SavedProperty(user_id=user.id, property_id=property.id))
    db.session.commit()
    monkeypatch.setitem(current_app.jinja_env.globals, 'posting_age',
                        lambda timestamp: relative_posting_age(timestamp, language, NOW))
    suffix = '?lang=en' if language == 'en' else ''
    for route in ('/', '/properties', '/saved-properties', f'/properties/{property.id}'):
        html = client.get(route + suffix).text
        assert ('15 months ago' if language == 'en' else 'منذ 15 شهر') in html
        assert 'class="poster-age"' in html and 'class="poster-verified"' in html
        if route != f'/properties/{property.id}':
            assert 'class="market-result-meta"' not in html
            assert 'class="market-result-facts"' in html
            assert 'class="home-card-transaction is-rent"' in html
            assert '230 m²' in html and 'العمارات' in html
            assert f'href="/properties/{property.id}{suffix}"' in html


@pytest.mark.parametrize('missing', ['bedrooms', 'bathrooms', 'size', 'location', 'all'])
def test_missing_facts_are_omitted_without_turning_zero_into_null(client, missing):
    values = dict(bedrooms=0, bathrooms=0, size=230, neighborhood_ar='Al Riyadh')
    state = 'Khartoum'
    if missing == 'all':
        values = dict(bedrooms=None, bathrooms=None, size=None, neighborhood_ar='')
        state = ''
    elif missing == 'location':
        values['neighborhood_ar'] = ''
        state = ''
    else:
        values[missing] = None
    with current_app.test_request_context('/?lang=en'):
        html = render_template_string(
            "{% from 'components/property_facts.html' import property_facts %}{{ property_facts(property, state, t, format_rent) }}",
            property=SimpleNamespace(**values), state=state,
            t=lambda key: translate(key, 'en'), format_rent=format_rent)
    assert 'None' not in html and 'N/A' not in html and 'null' not in html
    assert ('0 bedrooms' in html) == (missing not in ('bedrooms', 'all'))
    assert ('0 bathrooms' in html) == (missing not in ('bathrooms', 'all'))
    assert ('230 m²' in html) == (missing not in ('size', 'all'))
    assert ('market-result-fact-location' in html) == (missing not in ('location', 'all'))


def test_poster_age_omitted_when_timestamp_unavailable(client):
    property = SimpleNamespace(owner=None, created_at=None, contact_role='owner')
    with current_app.test_request_context('/?lang=en'):
        html = render_template_string(
            "{% from 'components/poster_identity.html' import poster_identity %}{{ poster_identity(property, t) }}",
            property=property, t=lambda key: translate(key, 'en'))
    assert 'poster-age' not in html and 'Property poster' in html
