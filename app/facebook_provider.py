"""Facebook identity boundary. No Meta API integration is implemented here."""
from dataclasses import dataclass
from typing import Mapping, Protocol

from flask import current_app, url_for


@dataclass(frozen=True)
class FacebookIdentity:
    provider_user_id: str
    display_name: str


class FacebookAuthProvider(Protocol):
    def authorization_url(self, state: str, callback_url: str) -> str: ...
    def authenticate(self, callback_data: Mapping[str, str]) -> FacebookIdentity: ...


def development_enabled(config):
    return bool(config.get('TESTING') or (
        config.get('ENVIRONMENT') == 'development' and config.get('FACEBOOK_DEVELOPMENT_MODE') is True))


class DevelopmentFacebookAuthProvider:
    """A server-configured fake identity, never a real Facebook response."""

    def _guard(self):
        if not development_enabled(current_app.config):
            raise RuntimeError('Development Facebook authentication is disabled.')

    def authorization_url(self, state, callback_url):
        self._guard()
        return url_for('facebook.development', state=state)

    def authenticate(self, callback_data):
        self._guard()
        # Never accept an identity supplied by the browser.
        return FacebookIdentity(
            current_app.config['FACEBOOK_DEVELOPMENT_USER_ID'],
            current_app.config['FACEBOOK_DEVELOPMENT_DISPLAY_NAME'])


def configure_facebook(app):
    if not development_enabled(app.config):
        return
    for key in ('FACEBOOK_DEVELOPMENT_USER_ID', 'FACEBOOK_DEVELOPMENT_DISPLAY_NAME'):
        value = app.config[key]
        if not isinstance(value, str) or not value.strip() or len(value) > 255:
            raise ValueError(f'{key} must be a nonempty string of at most 255 characters.')
    app.extensions['facebook_auth_provider'] = DevelopmentFacebookAuthProvider()
    from app.facebook_auth import facebook
    app.register_blueprint(facebook)
