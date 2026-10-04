"""Homepage discovery uses public marketplace data and routes."""
import re
from datetime import timedelta
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import event, select

from app import db
from app.languages import PROPERTY_TYPE_NAMES, translate
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


def test_official_logo_replaces_public_header_and_homepage_footer_brand(client):
    logo = Path('app/static/images/manazil-logo.png')
    assert logo.is_file() and logo.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    assert logo.read_bytes()[16:24] == bytes.fromhex('000004e6000004e6')
    for suffix, alt in (('', 'منازل السودان'), ('?lang=en', 'Manazil Sudan')):
        for route in ('/', '/properties'):
            page = client.get(route + suffix).text
            header = re.search(r'<header class="site-header">.*?</header>', page, re.S).group()
            brand = re.search(r'<a class="site-brand".*?</a>', header, re.S).group()
            assert f'<img class="brand-logo" src="/static/images/manazil-logo.png" alt="{alt}" width="1254" height="1254">' in brand
            assert re.search(r'href="/(?:\?lang=en)?"', brand)
            assert 'Manazil</a>' not in brand and 'منازل</a>' not in brand
            assert '/static/images/manazil-logo-light-v2.png' not in page
        homepage = client.get('/' + suffix).text
        footer = re.search(r'<a class="home-footer-brand".*?</a>', homepage, re.S).group()
        assert f'<img class="brand-logo" src="/static/images/manazil-logo.png" alt="{alt}" width="1254" height="1254" loading="lazy">' in footer
        assert re.search(r'href="/(?:\?lang=en)?"', footer)

    styles = Path('app/static/css/style.css').read_text(encoding='utf-8')
    assert '.brand-logo { display: block; max-width: 100%; height: auto; object-fit: contain; }' in styles
    assert '.site-brand .brand-logo { width: 68px; }' in styles
    mobile = styles.split('@media (max-width: 959px) {', 1)[1].split('\n}', 1)[0]
    assert '.site-header .site-brand .brand-logo { width: 56px; }' in mobile
    assert '.home-footer-brand .brand-logo { width: 72px; }' in styles


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
        for slug, english, arabic in STATE_OPTIONS:
            assert f'<option value="{slug}">' in html
            assert (arabic if direction == 'rtl' else english) in html
        for property_type in PROPERTY_TYPE_NAMES:
            assert f'<option value="{property_type}">' in html
        assert f'<strong>{rent}</strong>' not in html and f'<strong>{sale}</strong>' not in html
        assert 'Latest Properties' in html if direction == 'ltr' else 'أحدث العقارات' in html
        assert 'href="/properties' in html
        assert '<footer class="site-footer home-footer">' in html
        assert 'href="#"' not in html
        if suffix:
            assert '<input type="hidden" name="lang" value="en">' in html


def test_homepage_hero_slideshow_uses_four_local_images(client):
    for suffix in ('', '?lang=en'):
        html = client.get('/' + suffix).text
        hero = re.search(r'<section class="home-hero".*?</section>', html, re.S).group()
        assert 'data-home-hero' in html and 'js/home-hero.js' in html
        assert 'data-mobile-initial' in hero
        assert hero.count('<img class="home-hero-slide') == 4
        assert hero.count('<img class="home-hero-slide is-active"') == 1
        assert 'fetchpriority="high" loading="eager"' in hero
        assert hero.count('loading="lazy" decoding="async"') == 3
        assert 'home-hero-toggle' not in hero
        assert 'Pause slideshow' not in hero and 'Play slideshow' not in hero
        assert 'إيقاف عرض الصور' not in hero and 'تشغيل عرض الصور' not in hero
        for number in range(1, 5):
            assert f'src="/static/images/sudan-hero-{number}.webp"' in hero
    for number in range(1, 5):
        asset = Path(f'app/static/images/sudan-hero-{number}.webp')
        assert asset.is_file() and asset.stat().st_size < 100_000
        assert asset.read_bytes()[:4] == b'RIFF' and asset.read_bytes()[8:12] == b'WEBP'


def test_hero_slideshow_keeps_automatic_timing_and_reduced_motion():
    script = Path('app/static/js/home-hero.js').read_text(encoding='utf-8')
    styles = Path('app/static/css/style.css').read_text(encoding='utf-8')
    assert 'window.setInterval' in script and '6500' in script
    assert "window.matchMedia('(prefers-reduced-motion: reduce)').matches" in script
    assert 'document.hidden' in script
    assert '.home-hero-slide { transition: none; }' in styles
    assert 'home-hero-toggle' not in script and 'home-hero-toggle' not in styles
    assert "window.matchMedia('(max-width: 767px)').matches" in script
    assert "hero.removeAttribute('data-mobile-initial')" in script
    assert '.home-hero[data-mobile-initial] .home-hero-slide:last-child { opacity: 1; }' in styles


def test_hero_is_outside_constrained_home_content(client):
    for suffix in ('', '?lang=en'):
        html = client.get('/' + suffix).text
        main = html.split('<main id="main-content" class="home-page">', 1)[1].split('</main>', 1)[0]
        hero = main.split('<section class="home-hero"', 1)[1].split('</section>', 1)[0]
        constrained = main.split('<div class="home-content">', 1)[1]
        assert 'class="home-hero-content"' in hero
        assert 'class="home-hero-copy"' in hero and 'class="home-hero-actions"' in hero
        assert main.index('</section>') < main.index('<div class="home-content">')
        assert 'id="property-search"' in constrained
        assert 'id="home-latest-title"' in constrained
        assert 'id="home-post-title"' in constrained
        assert 'class="home-hero-slides"' not in constrained


def test_hero_has_no_search_control_and_single_search_form_below_discovery_heading(client):
    for suffix, language, direction in (('', 'ar', 'rtl'), ('?lang=en', 'en', 'ltr')):
        html = client.get('/' + suffix).text
        hero = re.search(r'<section class="home-hero".*?</section>', html, re.S).group()
        search_section = re.search(r'<section class="home-section" id="property-search".*?</section>', html, re.S).group()
        assert f'<html lang="{language}" dir="{direction}">' in html
        assert 'class="home-search"' not in hero and '<form' not in hero
        assert translate('Search for Property', language) not in hero
        assert 'href="#property-search"' not in hero
        assert f'href="/properties/new{suffix}"><span class="home-hero-action-plus" aria-hidden="true">+</span><span class="home-hero-label-desktop">{translate("Post Property", language)}</span><span class="home-hero-label-mobile">{translate("Post a Property", language)}</span></a>' in hero
        assert html.count('class="home-search"') == 1
        assert search_section.index('id="home-discover-title"') < search_section.index('class="home-search"')
        assert 'home-discovery-grid' not in search_section
        assert f'<h2 id="home-discover-title">{translate("Find what fits you", language)}</h2>' in search_section
        assert '<form class="home-search" method="get" action="/properties"' in search_section
        assert all(f'name="{name}"' in search_section for name in ('transaction', 'state', 'property_type'))
        assert all(translate(label, language) in search_section for label in ('Transaction', 'State', 'Property type', 'For Rent', 'For Sale', 'Rent', 'Buy', 'Find a property'))
        assert f'{translate("Search", language)}</button>' in search_section
        assert html.index('id="property-search"') < html.index('id="home-latest-title"')


def test_mobile_hero_actions_keep_shared_content_start_and_desktop_layout():
    styles = Path('app/static/css/style.css').read_text(encoding='utf-8')
    mobile = styles.split('@media (max-width: 959px) {\n  .home-hero-actions', 1)[1].split('\n}', 1)[0]
    assert 'flex-direction: column' in mobile
    assert 'align-items: flex-start' in mobile
    assert '.home-hero-actions .home-hero-action { width: 66.6667%' in mobile
    assert '.home-hero-actions { flex-direction: column; align-items: stretch; }' not in styles
    assert '.home-hero-content { display: flex; flex-direction: column;' in styles


def test_mobile_homepage_search_and_bottom_navigation_keep_existing_routes(client):
    for suffix, language, direction in (('', 'ar', 'rtl'), ('?lang=en', 'en', 'ltr')):
        html = client.get('/' + suffix).text
        assert f'<html lang="{language}" dir="{direction}">' in html
        assert html.count('class="home-search"') == 1
        assert '<form class="home-search" method="get" action="/properties"' in html
        assert '<select id="home-transaction" name="transaction"><option value="rent">' in html
        assert '<option value="sale">' in html
        assert '<button type="button" data-transaction="rent" aria-pressed="true">' in html
        assert '<button type="button" data-transaction="sale" aria-pressed="false">' in html
        assert 'js/home-search.js' in html
        assert '<select id="home-state" name="state">' in html
        assert '<select id="home-property-type" name="property_type">' in html
        assert f'<h2 class="home-search-mobile-title">{translate("Find a property", language)}</h2>' in html
        navigation = re.search(r'<nav class="home-mobile-bottom-nav".*?</nav>', html, re.S).group()
        assert f'aria-label="{translate("Mobile navigation", language)}"' in navigation
        assert navigation.count('<a href=') == 4
        for route in ('/', '/properties', '/properties/new', '/auth'):
            assert f'href="{route}{suffix}"' in navigation
        assert 'aria-current="page"' in navigation


def test_mobile_latest_cards_use_real_price_period_size_and_existing_save(client, values):
    property = public_property(values, 'Measured rental', size=120, price=500000,
                               rent_period='monthly')
    html = client.get('/?lang=en').text
    card = re.search(r'<article class="market-result">(.*?)</article>', html, re.S).group(1)
    assert f'href="/properties/{property.id}?lang=en"' in card
    assert 'class="home-card-transaction is-rent">For Rent' in card
    assert '500,000 SDG' in card and 'class="home-card-period">/ Monthly' in card
    assert 'class="market-result-fact home-card-size"' in card and '120 m²' in card
    assert 'class="market-result-facts"' in card
    assert 'Save Property' in card


def test_mobile_homepage_css_is_scoped_and_scrolls_cards_without_page_overflow():
    styles = Path('app/static/css/style.css').read_text(encoding='utf-8')
    mobile = styles.split('@media (max-width: 767px) {\n  .home-page', 1)[1].split('\n}', 1)[0]
    assert '.home-latest-grid { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 87%);' in mobile
    assert 'overflow-x: auto' in mobile and 'scroll-snap-type: x proximity' in mobile
    assert '.home-mobile-bottom-nav { position: fixed;' in mobile
    assert 'env(safe-area-inset-bottom)' in mobile
    assert '.home-search { grid-template-columns: minmax(0, 1fr);' in mobile
    assert '.home-page .home-hero { min-height: 225px;' in mobile
    assert '.home-footer' in mobile
    assert '.home-mobile-bottom-nav { display: none; }' in styles
    assert '.home-search-segments { display: none; }' in styles
    assert '.home-search-transaction.home-search-enhanced .home-search-segments { display: grid;' in mobile
    script = Path('app/static/js/home-search.js').read_text(encoding='utf-8')
    assert 'select.value = value' in script
    assert "field.classList.add('home-search-enhanced')" in script


def test_homepage_search_uses_marketplace_filters(client, values):
    public_property(values, 'Matching', transaction_type='sale', rent_period=None,
                    state_en='Khartoum', property_type='villa')
    public_property(values, 'Wrong type', transaction_type='sale', rent_period=None,
                    state_en='Khartoum', property_type='house')
    public_property(values, 'Rental', transaction_type='rent', state_en='Khartoum', property_type='villa')
    page = client.get('/properties', query_string={
        'transaction': 'sale', 'state': 'khartoum', 'property_type': 'villa', 'lang': 'en',
    })
    assert page.status_code == 200
    assert 'Matching' in page.text and 'Wrong type' not in page.text
    rental_page = client.get('/properties', query_string={
        'transaction': 'rent', 'state': 'khartoum', 'property_type': 'villa', 'lang': 'en',
    })
    assert rental_page.status_code == 200
    assert 'Rental' in rental_page.text and 'Matching' not in rental_page.text


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


def test_homepage_has_no_rent_sale_discovery_cards(client):
    for suffix in ('', '?lang=en'):
        html = client.get('/' + suffix).text
        assert 'home-discovery-' not in html
        assert 'Properties for Rent' not in html and 'Properties for Sale' not in html
        assert 'class="home-search"' in html


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
    assert '<a class="home-hero-action home-hero-action-secondary" href="/properties/new?lang=en"><span class="home-hero-action-plus" aria-hidden="true">+</span><span class="home-hero-label-desktop">Post Property</span><span class="home-hero-label-mobile">Post a Property</span></a>' in english.text
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
