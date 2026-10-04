"""Keep developer OAuth settings out of the automated test environment."""

import pytest


@pytest.fixture(autouse=True)
def isolated_google_environment(monkeypatch):
    monkeypatch.setenv('PUBLIC_GOOGLE_LOGIN_ENABLED', '0')
    for name in ('GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REDIRECT_URI'):
        monkeypatch.delenv(name, raising=False)
