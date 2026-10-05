import json
import re
from pathlib import Path

import pytest
from sqlalchemy import select

from app import db
from app.models import Property
from app.property_rules import PROPERTY_RULES, field_rules
from test_photo_review import image_file, photo_client
from test_properties import migrated_connection
from test_property_creation import client, form_data

def test_wizard_navigation(client):
    page = client.get('/admin/properties/new?lang=en').text
    assert 'id="wizard-progress"' not in page
    assert 'id="wizard-next"' not in page and 'id="wizard-back"' not in page
    assert 'id="wizard-navigation"' not in page
    assert page.count('class="wizard-continue"') == 6
    assert 'id="property-leave"' in page
    assert 'data-initial-section="purpose"' in page
    assert 'data-wizard-step="review"' in page
    assert page.count('id="property-form"') == 1

def test_language_switch_preserves_entries(client, form_data):
    response = client.post('/admin/properties', data=form_data | {'_action':'switch_ar'})
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'شقة' in page and 'الخرطوم' in page


def metadata(page):
    return json.loads(re.search(r'<script type="application/json" id="property-wizard-rules">(.*?)</script>', page, re.S).group(1))


@pytest.mark.parametrize('kind', PROPERTY_RULES)
@pytest.mark.parametrize('transaction', ['rent', 'sale'])
def test_central_branch_metadata(client, kind, transaction):
    rules = metadata(client.get('/properties/new').text)
    assert rules['types'][kind]['transactions'][transaction] == field_rules(kind, transaction)
    assert rules['types'][kind]['label'] == PROPERTY_RULES[kind]['label']


@pytest.mark.parametrize('language,direction', [('ar', 'rtl'), ('en', 'ltr')])
def test_wizard_localization_and_fallback(client, language, direction):
    page = client.get('/properties/new?lang=' + language).text
    assert f'dir="{direction}"' in page
    assert '<noscript>' in page
    assert 'type="button" class="wizard-continue" hidden' in page
    for kind in PROPERTY_RULES:
        assert f'value="{kind}"' in page
    assert 'name="csrf_token"' in page and 'name="latitude"' in page and 'name="longitude"' in page


@pytest.mark.parametrize('field,section', [('floor', 'details'), ('title_ar', 'description'),
                                         ('whatsapp', 'contact'), ('price', 'transaction'), ('state_en', 'location')])
def test_server_errors_restore_section(client, form_data, field, section):
    response = client.post('/admin/properties', data=form_data | {field: '', '_wizard_section': 'review'})
    assert response.status_code == 422
    assert f'data-initial-section="{section}"' in response.text
    assert 'value="100"' in response.text


def test_language_switch_retains_section_and_date(client, form_data):
    response = client.post('/admin/properties', data=form_data | {'_action': 'switch_ar',
                           '_wizard_section': 'transaction', 'available_from_date': '2030-01-02'})
    assert response.status_code == 200
    assert 'data-initial-section="transaction"' in response.text
    assert 'value="2030-01-02"' in response.text
    assert client.post('/admin/properties', data=form_data | {'_action': 'switch_en', '_wizard_section': 'evil'}).status_code == 200


def test_edit_metadata_and_legacy_missing_fields(client, form_data):
    assert client.post('/admin/properties', data=form_data).status_code == 303
    listing = db.session.scalar(select(Property).order_by(Property.id.desc()))
    listing.floor = listing.size = None
    db.session.commit()
    rules = metadata(client.get(f'/properties/{listing.id}/edit').text)
    assert rules['original'] == {'property_type': 'apartment', 'transaction_type': 'rent'}
    assert {'floor', 'size'}.issubset(rules['legacy_missing'])


def test_final_publish_ingests_selected_photo(photo_client, form_data):
    response = photo_client.post('/admin/properties', data=form_data | {'photos': image_file(), '_wizard_section': 'review'})
    assert response.status_code == 303
    listing = db.session.scalar(select(Property).order_by(Property.id.desc()))
    assert len(listing.photos) == 1 and listing.photos[0].is_primary


def test_selected_photo_survives_language_switch(photo_client, form_data):
    response = photo_client.post('/admin/properties', data=form_data | {'photos': image_file(), '_action': 'switch_ar', '_wizard_section': 'photos'})
    assert response.status_code == 200
    assert 'data-current-count="1"' in response.text
    assert 'data-initial-section="photos"' in response.text


@pytest.mark.parametrize('transaction,date,expected_status', [('rent', '2030-02-03', 303),
                                                         ('rent', 'invalid', 422), ('sale', 'invalid', 303)])
def test_rental_date_server_rules(client, form_data, transaction, date, expected_status):
    response = client.post('/admin/properties', data=form_data | {'transaction_type': transaction,
                           'rent_period': 'monthly' if transaction == 'rent' else '', 'available_from_date': date})
    assert response.status_code == expected_status
    if expected_status == 303:
        listing = db.session.scalar(select(Property).order_by(Property.id.desc()))
        assert str(listing.available_from_date) == (date if transaction == 'rent' else 'None')


def test_client_code_has_no_property_matrix_and_uses_safe_review_text():
    script = Path('app/static/js/property-form.js').read_text()
    assert 'metadata.types[type]?.transactions[transaction]' in script
    assert 'control.disabled = !applicable' in script
    assert 'text.textContent = entry.value' in script
    assert 'innerHTML' not in script
    assert 'control.checkValidity()' in script
    assert 'section.hidden = !revealed.includes(key)' in script
    assert 'section.hidden = section.dataset.wizardStep !== current' not in script
    assert 'wizard-progress' not in script
    assert 'ManazilPropertyWizard.showContinue(key, current)' in script
    assert 'invalidateChangedSection(section)' in script
    assert 'control.checked = false' in script and 'control.value = ""' in script
    assert 'prefers-reduced-motion: reduce' in script
    assert 'reveal(initial)' in script and 'if (metadata.original' in script


def test_local_continue_only_in_data_sections(client):
    page = client.get('/properties/new?lang=en').text
    for section, body in re.findall(r'<section[^>]*data-wizard-step="([^"]+)"[^>]*>(.*?)</section>', page, re.S):
        assert ('class="wizard-continue"' in body) == (section in {
            'location', 'details', 'transaction', 'description', 'photos', 'contact'})
    assert 'value="submit">Publish Property</button>' in page
    assert 'Scroll up to edit your answers.' in page


@pytest.mark.parametrize('lang', ['ar', 'en'])
def test_language_switch_preserves_revealed_prefix_and_comment(client, form_data, lang):
    response = client.post('/admin/properties', data=form_data | {
        '_action': 'switch_' + lang, '_wizard_section': 'review', 'comment': 'Manual note'})
    assert response.status_code == 200
    assert 'data-initial-section="review"' in response.text
    assert 'Manual note</textarea>' in response.text
    assert 'data-rerendered="true"' in response.text


def test_photo_action_preserves_later_revealed_sections(photo_client, form_data):
    response = photo_client.post('/admin/properties', data=form_data | {
        '_action': 'upload', '_wizard_section': 'review', 'photos': image_file()})
    assert response.status_code == 200
    assert 'data-initial-section="review"' in response.text


@pytest.mark.parametrize('lang', ['ar', 'en'])
def test_new_purpose_has_no_default(client, lang):
    from app.property_forms import FORM_DEFAULTS
    assert FORM_DEFAULTS['transaction_type'] == ''
    page = client.get('/properties/new?lang=' + lang).text
    radios = re.findall(r'<input[^>]*name="transaction_type"[^>]*>', page)
    assert len(radios) == 2
    assert all('checked' not in radio for radio in radios)
    assert 'data-initial-section="purpose"' in page


def test_missing_purpose_rejected_server_side(client, form_data):
    response = client.post('/admin/properties', data=form_data | {'transaction_type': ''})
    assert response.status_code == 422
    assert 'data-initial-section="purpose"' in response.text
    assert db.session.scalar(select(Property)) is None


@pytest.mark.parametrize('purpose', ['rent', 'sale'])
def test_edit_keeps_saved_purpose(client, form_data, purpose):
    response = client.post('/admin/properties', data=form_data | {
        'transaction_type': purpose, 'rent_period': 'monthly' if purpose == 'rent' else ''})
    assert response.status_code == 303
    listing = db.session.scalar(select(Property))
    page = client.get(f'/properties/{listing.id}/edit').text
    radio = re.search(r'<input[^>]*name="transaction_type"[^>]*value="' + purpose + r'"[^>]*>', page).group()
    assert 'checked' in radio
    assert metadata(page)['original']['transaction_type'] == purpose
