"""Configured Google OpenID Connect provider; browser claims are never trusted."""
import json
import re
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from requests.exceptions import RequestException


AUTHORIZATION_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
PRODUCTION_CALLBACK = 'https://www.manazilelsaudan.com/auth/google/callback'


class GoogleProviderError(ValueError):
    def __init__(self, category, http_status=None):
        super().__init__('Google identity could not be verified.')
        self.category = category
        self.http_status = http_status


def _verification_failure_category(error):
    # Inspect verifier diagnostics only to choose a fixed category. Never log
    # the exception text: it can contain token claims or configuration values.
    reason = str(error).lower()
    if 'audience' in reason:
        return 'audience_validation_failure'
    if 'issuer' in reason:
        return 'issuer_validation_failure'
    if 'expired' in reason or 'expiration' in reason:
        return 'expiration_validation_failure'
    return 'id_token_verification_failure'


class _TimedGoogleRequest(GoogleRequest):
    def __call__(self, url, method='GET', body=None, headers=None, timeout=None):
        return super().__call__(url=url, method=method, body=body, headers=headers, timeout=5)


@dataclass(frozen=True)
class GoogleIdentity:
    provider_user_id: str
    display_name: str
    picture_url: str | None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    email_verified: bool = False


class GoogleAuthProvider:
    def __init__(self, client_id, client_secret, redirect_uri):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def authorization_url(self, state, nonce, challenge):
        return AUTHORIZATION_URL + '?' + urlencode({
            'client_id': self.client_id, 'redirect_uri': self.redirect_uri,
            'response_type': 'code', 'scope': 'openid email profile',
            'state': state, 'nonce': nonce, 'code_challenge': challenge,
            'code_challenge_method': 'S256',
        })

    def authenticate(self, code, nonce, verifier):
        if not isinstance(code, str) or not 1 <= len(code) <= 4096:
            raise GoogleProviderError('authorization_code_exchange_failure')
        body = urlencode({
            'code': code, 'client_id': self.client_id,
            'client_secret': self.client_secret, 'redirect_uri': self.redirect_uri,
            'grant_type': 'authorization_code', 'code_verifier': verifier,
        }).encode()
        try:
            request = Request(TOKEN_URL, data=body, headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
            with urlopen(request, timeout=5) as response:
                token_bytes = response.read(16385)
        except HTTPError as error:
            raise GoogleProviderError('token_exchange_http_status', error.code) from error
        except (URLError, TimeoutError, OSError) as error:
            raise GoogleProviderError('authorization_code_exchange_failure') from error
        try:
            token = json.loads(token_bytes)
        except (ValueError, UnicodeError, TypeError) as error:
            raise GoogleProviderError('malformed_provider_response') from error
        encoded = token.get('id_token') if isinstance(token, dict) else None
        if not isinstance(encoded, str) or not 1 <= len(encoded) <= 16384:
            raise GoogleProviderError('malformed_provider_response')
        try:
            claims = id_token.verify_oauth2_token(encoded, _TimedGoogleRequest(), self.client_id)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, GoogleAuthError, RequestException,
                KeyError, TypeError) as error:
            raise GoogleProviderError(_verification_failure_category(error)) from error
        if not isinstance(claims, dict):
            raise GoogleProviderError('malformed_required_claims')
        if claims.get('nonce') != nonce:
            raise GoogleProviderError('nonce_validation_failure')
        # The verifier checks signature, audience, expiry and Google's issuer.
        if claims.get('iss') not in ('accounts.google.com', 'https://accounts.google.com'):
            raise GoogleProviderError('issuer_validation_failure')
        if claims.get('aud') != self.client_id:
            raise GoogleProviderError('audience_validation_failure')
        if not isinstance(claims.get('exp'), (int, float)) or claims['exp'] <= time.time():
            raise GoogleProviderError('expiration_validation_failure')
        subject = claims.get('sub')
        email = claims.get('email')
        if (not isinstance(subject, str) or not 1 <= len(subject) <= 255 or
                any(ord(char) < 33 for char in subject)):
            raise GoogleProviderError('malformed_required_claims')
        from app.account_profile import normalize_email, normalize_name
        if email is not None:
            try:
                email = normalize_email(email)
            except ValueError:
                raise GoogleProviderError('malformed_required_claims') from None
        def profile_name(key):
            try:
                return normalize_name(claims.get(key))
            except ValueError:
                return None
        first_name, last_name = profile_name('given_name'), profile_name('family_name')
        name = claims.get('name')
        display_name = name.strip() if isinstance(name, str) and 0 < len(name.strip()) <= 255 else ' '.join(filter(None, (first_name, last_name))) or 'Google Member'
        picture = claims.get('picture')
        return GoogleIdentity(subject, display_name, picture if isinstance(picture, str) else None,
                              first_name, last_name, email, bool(email and claims.get('email_verified') is True))



def configure_google(app):
    if not app.config.get('PUBLIC_GOOGLE_LOGIN_ENABLED'):
        return
    client_id = app.config.get('GOOGLE_CLIENT_ID')
    secret = app.config.get('GOOGLE_CLIENT_SECRET')
    redirect_uri = app.config.get('GOOGLE_REDIRECT_URI')
    if not isinstance(client_id, str) or not re.fullmatch(r'[A-Za-z0-9._-]{8,255}', client_id):
        raise ValueError('GOOGLE_CLIENT_ID is missing or invalid.')
    if not isinstance(secret, str) or not 16 <= len(secret) <= 255 or any(char.isspace() for char in secret):
        raise ValueError('GOOGLE_CLIENT_SECRET is missing or invalid.')
    parsed = urlsplit(redirect_uri) if isinstance(redirect_uri, str) else None
    if (not parsed or parsed.path != '/auth/google/callback' or parsed.query or parsed.fragment or
            parsed.username or parsed.password or not parsed.hostname or
            (parsed.scheme != 'https' and not (app.config['ENVIRONMENT'] != 'production' and
                                               parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1')))):
        raise ValueError('GOOGLE_REDIRECT_URI must be a configured HTTPS callback (localhost HTTP is allowed outside production).')
    if app.config['ENVIRONMENT'] == 'production' and redirect_uri != PRODUCTION_CALLBACK:
        raise ValueError('Production Google redirect URI must use the canonical callback.')
    app.extensions['google_auth_provider'] = GoogleAuthProvider(client_id, secret, redirect_uri)
    from app.google_auth import google
    app.register_blueprint(google)
