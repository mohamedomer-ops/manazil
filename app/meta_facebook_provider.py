"""Server-side Meta authorization-code exchange; access tokens are never persisted."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.facebook_provider import FacebookIdentity

GRAPH_VERSION = 'v26.0'
GRAPH_ROOT = f'https://graph.facebook.com/{GRAPH_VERSION}'
AUTHORIZATION_ROOT = f'https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth'
MAX_RESPONSE_BYTES = 16 * 1024
REQUEST_TIMEOUT = 5


class MetaProviderError(RuntimeError):
    """A safe, non-sensitive failure to authenticate with Meta."""


def _json_request(request):
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise MetaProviderError('Meta response is invalid.')
        data = json.loads(payload)
        if not isinstance(data, dict) or 'error' in data:
            raise MetaProviderError('Meta response is invalid.')
        return data
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, UnicodeError) as error:
        raise MetaProviderError('Meta authentication is unavailable.') from error


class MetaFacebookAuthProvider:
    def __init__(self, app_id, app_secret, redirect_uri):
        self.app_id = app_id
        self._app_secret = app_secret
        self.redirect_uri = redirect_uri

    def authorization_url(self, state, callback_url):
        # The configured URI is canonical; the incoming Host header cannot change it.
        return AUTHORIZATION_ROOT + '?' + urlencode({
            'client_id': self.app_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': 'public_profile',
            'state': state,
        })

    def authenticate(self, callback_data):
        code = callback_data.get('code')
        if not isinstance(code, str) or not code or len(code) > 4096 or any(ord(c) < 33 for c in code):
            raise MetaProviderError('Meta authorization code is invalid.')
        token_request = Request(
            GRAPH_ROOT + '/oauth/access_token',
            data=urlencode({
                'client_id': self.app_id,
                'client_secret': self._app_secret,
                'redirect_uri': self.redirect_uri,
                'code': code,
            }).encode('ascii'),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST',
        )
        token_data = _json_request(token_request)
        token = token_data.get('access_token')
        token_type = token_data.get('token_type', 'bearer')
        if (not isinstance(token, str) or not 1 <= len(token) <= 4096 or
                any(ord(char) < 33 or ord(char) > 126 for char in token) or
                not isinstance(token_type, str) or token_type.lower() != 'bearer'):
            raise MetaProviderError('Meta token response is invalid.')
        profile_request = Request(
            GRAPH_ROOT + '/me?fields=id%2Cname',
            headers={'Authorization': f'Bearer {token}'},
            method='GET',
        )
        profile = _json_request(profile_request)
        provider_id = profile.get('id')
        name = profile.get('name')
        if (not isinstance(provider_id, str) or not re.fullmatch(r'[1-9][0-9]{0,254}', provider_id) or
                not isinstance(name, str) or not name.strip() or len(name.strip()) > 255 or
                any(ord(char) < 32 for char in name)):
            raise MetaProviderError('Meta profile is invalid.')
        return FacebookIdentity(provider_user_id=provider_id, display_name=name.strip())
