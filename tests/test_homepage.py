"""Homepage discovery uses public marketplace data and routes."""
import re
from datetime import timedelta
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import event, select

from app import db
from app.languages import PROPERTY_TYPE_NAMES
from app.models import PropertyPhoto, SavedProperty, utc_now
from app.property_filters import STATE_OPTIONS
from test_auth import client, csrf
from test_properties import migrated_connection, values
from test_public_properties import add_property
from test_saved_properties import sign_in


def public_property(values, title, **changes):
    return add_property(values, title_en=title, title_ar=title,
                        publication_status='published', **changes)


def homepage_titles(html):
    section = html.split('class="home-latest-grid"', 1)[1].split('</section>', 1)[0]
    return re.findall(r'<div class="market-result-info">\s*<h2>(.*?)</h2>', section)


def test_homepage_languages_search_discovery_and_footer(client):
    for suffix, direction, heading, rent, sale in (
        ('', 'rtl', 'ابحث عن بيتك القادم', 'عقارات للإيجار', 'عقارات للبيع'),
        ('?lang=en', 'ltr', 'Find your next home', 'Properties for Rent', 'Properties for Sale'),
    ):
        page = client.get('/' + suffix)
        assert page.status_code == 200
        html = page.text
        assert f'dir="{direction}"' in html and heading in html
        assert '<form class="home-search" method="get" action="/properties"' in html
        assert 'name="transaction"' in html and 'name="state"' in html
        assert 'name="property_type"' in html and 'name="bedrooms"' not in html
        for value in ('rent', 'sale'):
            assert f'<option value="{value}">' in html
            assert f'href="/properties?transaction={value}' in html
        for slug, english, arabic in STATE_OPTIONS:
            assert f'<option value="{slug}">' in html
            assert (arabic if direction == 'rtl' else english) in html
        for property_type in PROPERTY_TYPE_NAMES:
            assert f'<option value="{property_type}">' in html
        assert rent in html and sale in html
        assert 'Latest Properties' in html if direction == 'ltr' else 'أحدث العقارات' in html
        assert 'href="/properties' in html
        assert '<footer class="site-footer home-footer">' in html
        assert 'href="#"' not in html
        if suffix:
            assert '<input type="hidden" name="lang" value="en">' in html


def test_hero_search_uses_marketplace_filters(client, values):
    public_property(values, 'Matching', transaction_type='sale', rent_period=None,
                    state_en='Khartoum', property_type='villa')
    public_property(values, 'Wrong type', transaction_type='sale', rent_period=None,
                    state_en='Khartoum', property_type='house')
    page = client.get('/properties', query_string={
        'transaction': 'sale', 'state': 'khartoum', 'property_type': 'villa', 'lang': 'en',
    })
    assert page.status_code == 200
    assert 'Matching' in page.text and 'Wrong type' not in page.text


def test_homepage_removes_state_discovery_and_keeps_search_and_images(client):
    for suffix in ('', '?lang=en'):
        html = client.get('/' + suffix).text
        assert 'home-states-title' not in html
        assert 'home-state-grid' not in html and 'home-state-card' not in html
        assert 'images/states/' not in html
        assert 'Browse by State' not in html and 'تصفح حسب الولاية' not in html
        assert html.index('home-latest-title') < html.index('home-post-title')
        for slug, _, _ in STATE_OPTIONS:
            assert f'<option value="{slug}">' in html
    for slug, _, _ in STATE_OPTIONS:
        asset = Path('app/static/images/states') / f'{slug}.webp'
        assert asset.is_file() and asset.stat().st_size < 100_000
        assert asset.read_bytes()[:4] == b'RIFF' and asset.read_bytes()[8:12] == b'WEBP'


def test_homepage_discovery_icons_and_no_decorative_arrows(client, values):
    public_property(values, 'A listing')
    for suffix in ('', '?lang=en'):
        html = client.get('/' + suffix).text
        rent = re.search(r'<a class="home-discovery-card home-discovery-rent".*?</a>', html).group()
        sale = re.search(r'<a class="home-discovery-card home-discovery-sale".*?</a>', html).group()
        assert 'href="/properties?transaction=rent' in rent
        assert 'href="/properties?transaction=sale' in sale
        for card in (rent, sale):
            assert '<svg class="home-discovery-svg"' in card
            assert 'stroke="currentColor" stroke-width="2"' in card
            assert '<span class="home-discovery-icon" aria-hidden="true">' in card
            assert '⌂' not in card
        assert '<circle cx="19" cy="29" r="3"/>' in rent
        assert '<path d="M22 29h10m-5 0v4m5-4v4"/>' in rent
        assert '<path d="M16 25h12l6 5-6 5H16z"/>' in sale
        assert '<circle cx="20" cy="30" r="1"/>' in sale
        assert 'home-link-arrow' not in html and '↗' not in html
        assert 'class="market-result-open"' not in html
        assert 'class="market-carousel-previous"' not in html


def test_latest_properties_visibility_order_limit_and_links(client, values):
    now = utc_now()
    for index in range(6):
        public_property(values, f'Public {index}', created_at=now + timedelta(minutes=index))
    add_property(values, title_en='Private draft', title_ar='Private draft', publication_status='draft')
    public_property(values, 'Rented secret', availability_status='rented')
    page = client.get('/?lang=en')
    assert homepage_titles(page.text) == ['Public 5', 'Public 4', 'Public 3', 'Public 2']
    assert page.text.count('class="market-result"') == 4
    assert 'Private draft' not in page.text and 'Rented secret' not in page.text
    assert 'Public 1' not in page.text and 'Public 0' not in page.text
    assert page.text.count('class="market-result-link" href="/properties/') == 4
    assert 'class="property-card-image-placeholder"' in page.text
    assert 'View all properties' in page.text


def test_latest_cards_share_listing_facts_with_homepage_order(client, values):
    public_property(values, 'With neighborhood', bedrooms=3, bathrooms=2,
                    neighborhood_ar='الرياض', property_type='villa')
    public_property(values, 'State only', bedrooms=1, bathrooms=0,
                    property_type='house')
    for suffix, state, bed_label, bath_label, rent, owner in (
        ('', 'الخرطوم', '3 غرف نوم', '2 حمام', 'للإيجار', 'مالك'),
        ('?lang=en', 'Khartoum', '3 bedrooms', '2 bathrooms', 'For Rent', 'Owner'),
    ):
        html = client.get('/' + suffix).text
        cards = re.findall(r'<article class="market-result">(.*?)</article>', html, re.S)
        assert len(cards) == 2
        with_neighborhood = next(card for card in cards if 'With neighborhood' in card)
        state_only = next(card for card in cards if 'State only' in card)
        assert with_neighborhood.index('<h2>') < with_neighborhood.index('class="market-result-bottom"')
        assert with_neighborhood.index('class="market-result-bottom"') < with_neighborhood.index('class="market-result-facts"')
        assert with_neighborhood.index('class="market-result-facts"') < with_neighborhood.index('class="market-result-meta"')
        assert f'role="img" aria-label="{bed_label}"' in with_neighborhood
        assert f'role="img" aria-label="{bath_label}"' in with_neighborhood
        assert f'; {bed_label}; {bath_label}; {state} · الرياض"' in with_neighborhood
        assert with_neighborhood.count('stroke="currentColor"') >= 3
        assert f'<bdi>{state} · الرياض</bdi>' in with_neighborhood
        assert f'<bdi>{state}</bdi>' in state_only
        assert rent in with_neighborhood and owner in with_neighborhood
        assert 'class="property-card-type"' not in with_neighborhood
        assert 'Al Riyadh' not in with_neighborhood

    listing_card = re.search(r'<article class="market-result">(.*?)</article>', client.get('/properties?lang=en').text, re.S).group(1)
    assert listing_card.index('class="market-result-meta"') < listing_card.index('class="market-result-facts"')
    assert listing_card.index('class="market-result-facts"') < listing_card.index('class="market-result-bottom"')


def test_homepage_photo_carousel_reuses_marketplace_markup(client, values):
    no_photo = public_property(values, 'No photo')
    one_photo = public_property(values, 'One photo')
    multiple = public_property(values, 'Multiple photos')
    for property, count in ((one_photo, 1), (multiple, 3)):
        for index in range(count):
            db.session.add(PropertyPhoto(property_id=property.id, category='exterior',
                storage_key=f'properties/{property.id}/{index:032x}.jpg',
                original_filename=f'{index}.jpg', content_type='image/jpeg',
                file_size=1, display_order=index, is_primary=index == count - 1))
    db.session.commit()
    for suffix, previous, next_label in (('', 'الصورة السابقة', 'الصورة التالية'),
                                          ('?lang=en', 'Previous photo', 'Next photo')):
        html = client.get('/' + suffix).text
        assert f'href="/properties/{no_photo.id}' in html
        assert f'<span class="market-photo-current">1</span> / <span>1</span>' in html
        assert f'<span class="market-photo-current">1</span> / <span>3</span>' in html
        assert html.count('data-market-carousel') == 1
        assert f'aria-label="{previous}"' in html
        assert f'aria-label="{next_label}"' in html
        assert html.count('data-photo-src="/properties/photos/') == 3
        assert f'src="/properties/photos/{multiple.photos[-1].id}"' in html
        assert 'js/properties.js' in html


def test_homepage_limits_property_query_and_eager_loads_photos(client, values):
    for index in range(6):
        property = public_property(values, f'Home {index}')
        db.session.add(PropertyPhoto(property_id=property.id, category='exterior',
            storage_key=f'properties/{property.id}/{index:032x}.jpg',
            original_filename='photo.jpg', content_type='image/jpeg',
            file_size=1, display_order=0, is_primary=True))
    db.session.commit()
    statements = []
    def record(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith('select'):
            statements.append(statement.lower())
    event.listen(db.engine, 'before_cursor_execute', record)
    try:
        page = client.get('/?lang=en')
    finally:
        event.remove(db.engine, 'before_cursor_execute', record)
    assert page.status_code == 200
    property_queries = [statement for statement in statements if 'from properties' in statement]
    photo_queries = [statement for statement in statements if 'from property_photos' in statement]
    assert len(property_queries) == 1 and 'limit' in property_queries[0]
    assert len(photo_queries) == 1
    assert page.text.count('class="property-card-image"') == 4


def test_homepage_save_and_unsave_return_home_and_require_csrf(client, values):
    property = public_property(values, 'Save me')
    anonymous = client.get('/?lang=en')
    auth_url = unescape(re.search(r'<a href="([^"]+)"><span aria-hidden="true">♡</span> Save Property', anonymous.text).group(1))
    assert urlsplit(auth_url).path == '/auth'
    assert parse_qs(urlsplit(auth_url).query)['next'] == [f'/properties/{property.id}?lang=en']
    user = sign_in(client)
    homepage = client.get('/?lang=en')
    assert 'name="return_to" value="home"' in homepage.text
    assert client.post(f'/properties/{property.id}/save', data={'return_to': 'home'}).status_code == 400
    response = client.post(f'/properties/{property.id}/save', data={
        'csrf_token': csrf(homepage), '_language': 'en', 'return_to': 'home'})
    assert response.status_code == 303 and response.location == '/?lang=en'
    assert db.session.scalar(select(SavedProperty).where(SavedProperty.user_id == user.id))
    saved_page = client.get('/?lang=en')
    assert 'Saved</button>' in saved_page.text
    response = client.post(f'/properties/{property.id}/unsave', data={
        'csrf_token': csrf(saved_page), '_language': 'en', 'return_to': 'home'})
    assert response.status_code == 303 and response.location == '/?lang=en'
    assert db.session.query(SavedProperty).count() == 0


def test_empty_homepage_cta_auth_and_navigation(client):
    arabic = client.get('/')
    assert arabic.status_code == 200 and 'لا توجد عقارات متاحة حالياً.' in arabic.text
    assert 'class="home-latest-grid"' not in arabic.text
    english = client.get('/?lang=en')
    assert 'No properties are currently available.' in english.text
    assert '<a class="primary-link" href="/properties/new?lang=en">Post Property</a>' in english.text
    assert 'href="/auth?lang=en"' in english.text
    assert '/my-properties' not in english.text and '/saved-properties' not in english.text
    response = client.get('/properties/new?lang=en')
    assert response.status_code == 302
    assert parse_qs(urlsplit(response.location).query)['next'] == ['/properties/new?lang=en']
    sign_in(client)
    authenticated = client.get('/?lang=en').text
    assert '/my-properties?lang=en' in authenticated
    assert '/saved-properties?lang=en' in authenticated
    assert '/account?lang=en' in authenticated
    assert 'href="/auth?lang=en"' not in authenticated
