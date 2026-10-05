from pathlib import Path
import re

import pytest
from sqlalchemy import select
from app import db
from app.models import Property
from test_properties import migrated_connection
from test_property_creation import client, form_data


@pytest.mark.parametrize('lang,cancel,continue_label', [('en', 'Cancel', 'Continue Editing'), ('ar', 'إلغاء', 'متابعة التعديل')])
def test_cancel_outside_every_wizard_section(client, lang, cancel, continue_label):
    page = client.get('/properties/new?lang=' + lang).text
    assert f'>{cancel}</a>' in page
    assert continue_label in page
    assert page.count('id="wizard-cancel"') == 1
    # The action bar sits after all stage sections, including Review.
    assert page.index('id="wizard-cancel"') > page.index('data-wizard-step="review"')
    bar = re.search(r'<div class="wizard-action-bar">(.*?)<dialog', page, re.S).group(1)
    assert '<a id="wizard-cancel" class="wizard-cancel"' in bar
    assert 'data-staged-count="0"' in bar
    assert 'id="wizard-cancel-dialog"' in page
    assert 'type="button" id="wizard-confirm-cancel"' in page
    assert 'type="button" id="wizard-continue-editing"' in page


def test_cancel_styles_and_non_submission():
    css = Path('app/static/css/style.css').read_text(encoding='utf-8')
    assert '.wizard-action-bar' in css and 'position: sticky' in css
    assert 'background: #fff2f2' in css and 'color: #9b3333' in css
    assert '.wizard-cancel:hover' in css and '.wizard-cancel:focus-visible' in css
    js = Path('app/static/js/property-form.js').read_text(encoding='utf-8')
    cancel = js[js.index('const cancel ='):js.index('const completed =')]
    assert 'cancelDialog.close()' in cancel
    assert 'window.location.assign(cancel.href)' in cancel
    assert '.submit(' not in cancel and '.reset(' not in cancel
    assert 'show(' not in cancel  # Continue Editing does not navigate stages.


def test_exit_links_do_not_create_or_delete_property(client, form_data):
    assert client.get('/').status_code == 200
    assert db.session.scalar(select(Property)) is None
    assert client.post('/admin/properties', data=form_data).status_code == 303
    listing = db.session.scalar(select(Property))
    page = client.get(f'/properties/{listing.id}/edit').text
    assert 'href="/my-properties"' in page
    assert client.get('/my-properties').status_code == 200
    assert db.session.get(Property, listing.id) is not None


@pytest.mark.parametrize('action,status', [('switch_en', 200), ('submit', 422)])
def test_cancel_preserves_rerendered_data(client, form_data, action, status):
    response = client.post('/admin/properties', data=form_data | {'_action': action,
                           'comment': 'Keep my note', 'price': '', '_wizard_section': 'description'})
    assert response.status_code == status
    assert 'data-rerendered="true"' in response.text
    assert 'Keep my note</textarea>' in response.text
    assert 'id="wizard-cancel"' in response.text
    assert db.session.scalar(select(Property)) is None
