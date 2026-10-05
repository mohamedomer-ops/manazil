"""Keep developer OAuth settings out of the automated test environment."""

import pytest
from unittest.mock import Mock


@pytest.fixture(autouse=True)
def isolated_google_environment(monkeypatch):
    monkeypatch.setenv('PUBLIC_GOOGLE_LOGIN_ENABLED', '0')
    for name in ('GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REDIRECT_URI'):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def isolated_email_delivery(monkeypatch):
    """No test can send a real email, including existing signup regressions."""
    monkeypatch.setenv('RESEND_API_KEY', 'fake-test-resend-key')
    monkeypatch.setenv('MAIL_FROM', 'sender@example.test')
    response = Mock(status_code=200)
    response.json.return_value = {'id': 'fake-email-id'}
    post = Mock(return_value=response)
    monkeypatch.setattr('app.mail.requests.post', post)
    return post
