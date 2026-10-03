"""Public bilingual policy and deletion instructions."""

import pytest
from flask import current_app

from app.languages import translate
from test_auth import client
from test_properties import migrated_connection


@pytest.mark.parametrize('language,direction,suffix', [
    ('ar', 'rtl', ''), ('en', 'ltr', '?lang=en'),
])
def test_public_legal_pages_and_footer_links(client, language, direction, suffix):
    current_app.config['DATA_DELETION_CONTACT_EMAIL'] = 'privacy@example.test'
    for path, title in (('/privacy-policy', 'Privacy Policy'), ('/data-deletion', 'Data Deletion')):
        response = client.get(path + suffix)
        assert response.status_code == 200
        html = response.text
        assert f'<html lang="{language}" dir="{direction}">' in html
        assert f'<h1>{translate(title, language)}</h1>' in html
        assert f'href="/privacy-policy{suffix}"' in html
        assert f'href="/data-deletion{suffix}"' in html
        assert 'facebook_auth' not in html

    deletion = client.get('/data-deletion' + suffix).text
    assert 'mailto:privacy@example.test?subject=Manazil%20data%20deletion' in deletion
    assert translate('How to request deletion', language) in deletion
    assert translate('What happens next', language) in deletion
    homepage = client.get('/' + suffix).text
    assert f'href="/privacy-policy{suffix}"' in homepage
    assert f'href="/data-deletion{suffix}"' in homepage


def test_deletion_page_uses_confirmed_public_support_mailbox(client):
    current_app.config['DATA_DELETION_CONTACT_EMAIL'] = 'support@manazilelsaudan.com'
    response = client.get('/data-deletion?lang=en')
    assert response.status_code == 200
    assert 'mailto:support@manazilelsaudan.com?subject=Manazil%20data%20deletion' in response.text
