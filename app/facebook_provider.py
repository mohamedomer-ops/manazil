"""Facebook identity boundary shared by development and real Meta providers."""
import re
from dataclasses import dataclass
from typing import Mapping, Protocol
from urllib.parse import urlsplit

from flask import current_app, url_for


PRODUCTION_CALLBACK = 'https://manazilelsaudan.com/auth/facebook/callback'
LEGACY_PRODUCTION_CALLBACK = 'https://manazil-prod.azurewebsites.net/auth/facebook/callback'


@dataclass(frozen=True)
class FacebookIdentity:
    provider_user_id: str
    display_name: str
    picture_url: str | None = None


class FacebookAuthProvider(Protocol):
    def authorization_url(self, state: str, callback_url: str) -> str: ...
    def authenticate(self, callback_data: Mapping[str, str]) -> FacebookIdentity: ...


def development_enabled(config):
    return config.get('ENVIRONMENT') != 'production' and bool(config.get('TESTING') or (
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
    selected = app.config.get('FACEBOOK_AUTH_PROVIDER') or (
        'development' if development_enabled(app.config) else 'disabled')
    if selected not in ('disabled', 'development', 'meta'):
        raise ValueError('FACEBOOK_AUTH_PROVIDER must be disabled, development, or meta.')
    if selected == 'disabled':
        return
    if selected == 'development':
        if not development_enabled(app.config):
            raise ValueError('Development Facebook authentication is disabled.')
        for key in ('FACEBOOK_DEVELOPMENT_USER_ID', 'FACEBOOK_DEVELOPMENT_DISPLAY_NAME'):
            value = app.config[key]
            if not isinstance(value, str) or not value.strip() or len(value) > 255:
                raise ValueError(f'{key} must be a nonempty string of at most 255 characters.')
        provider = DevelopmentFacebookAuthProvider()
    else:
        if app.config.get('FACEBOOK_DEVELOPMENT_MODE'):
            raise ValueError('Meta authentication cannot use development Facebook mode.')
        app_id = app.config.get('FACEBOOK_APP_ID')
        secret = app.config.get('FACEBOOK_APP_SECRET')
        redirect_uri = app.config.get('FACEBOOK_REDIRECT_URI')
        if not isinstance(app_id, str) or not re.fullmatch(r'[0-9]{1,64}', app_id):
            raise ValueError('FACEBOOK_APP_ID must be a numeric Meta app ID.')
        if (not isinstance(secret, str) or not 16 <= len(secret) <= 255 or
                any(char.isspace() or ord(char) < 33 for char in secret)):
            raise ValueError('FACEBOOK_APP_SECRET is missing or invalid.')
        if not isinstance(redirect_uri, str):
            raise ValueError('FACEBOOK_REDIRECT_URI must be an HTTPS callback URI.')
        parsed = urlsplit(redirect_uri)
        if (parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password or
                parsed.query or parsed.fragment or parsed.path != '/auth/facebook/callback'):
            raise ValueError('FACEBOOK_REDIRECT_URI must be an HTTPS callback URI.')
        if app.config['ENVIRONMENT'] == 'production':
            if redirect_uri == LEGACY_PRODUCTION_CALLBACK:
                # Allow a code-first deployment while Azure still has the old setting.
                # A cross-host callback cannot recover the apex domain's OAuth state cookie.
                app.logger.warning('Facebook Login is disabled until the canonical callback is configured.')
                return
            if redirect_uri != PRODUCTION_CALLBACK:
                raise ValueError('Production Facebook redirect URI does not match the canonical callback.')
        from app.meta_facebook_provider import MetaFacebookAuthProvider
        provider = MetaFacebookAuthProvider(app_id, secret, redirect_uri)
    app.extensions['facebook_auth_provider'] = provider
    from app.facebook_auth import facebook
    app.register_blueprint(facebook)
