"""Best-effort Facebook avatar import into private Manazil photo storage."""
import io
import warnings
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.photo_storage import PhotoError, photo_storage

MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024
MAX_IMAGE_PIXELS = 4_000_000
DOWNLOAD_TIMEOUT = 5


class AvatarError(ValueError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise AvatarError('Avatar redirects are not allowed.')


def _open_picture(request):
    return build_opener(_NoRedirect).open(request, timeout=DOWNLOAD_TIMEOUT)


def _allowed_picture_url(url, provider='facebook'):
    if not isinstance(url, str) or len(url) > 4096:
        return False
    try:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or '').lower()
        return (parsed.scheme == 'https' and parsed.port in (None, 443) and
                not parsed.username and not parsed.password and not parsed.fragment and
                ((provider == 'facebook' and (hostname.endswith('.fbcdn.net') or hostname == 'platform-lookaside.fbsbx.com')) or
                 (provider == 'google' and (hostname == 'googleusercontent.com' or hostname.endswith('.googleusercontent.com')))) and
                not {'access_token', 'appsecret_proof'} & set(parse_qs(parsed.query)))
    except ValueError:
        return False


def fetch_avatar(url, provider):
    if not _allowed_picture_url(url, provider):
        raise AvatarError('Avatar URL is invalid.')
    try:
        with _open_picture(Request(url, headers={'Accept': 'image/webp,image/jpeg,image/png'})) as response:
            content_type = response.headers.get('Content-Type', '').split(';', 1)[0].lower()
            content_length = response.headers.get('Content-Length')
            if content_type not in ('image/jpeg', 'image/png', 'image/webp'):
                raise AvatarError('Avatar type is invalid.')
            if content_length and int(content_length) > MAX_DOWNLOAD_BYTES:
                raise AvatarError('Avatar is too large.')
            payload = response.read(MAX_DOWNLOAD_BYTES + 1)
        if not payload or len(payload) > MAX_DOWNLOAD_BYTES:
            raise AvatarError('Avatar is too large or empty.')
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(payload)) as image:
                if image.format not in ('JPEG', 'PNG', 'WEBP') or image.width * image.height > MAX_IMAGE_PIXELS:
                    raise AvatarError('Avatar image is invalid.')
                image.verify()
            with Image.open(io.BytesIO(payload)) as image:
                image.load()
                clean = ImageOps.exif_transpose(image).convert('RGB')
                clean.thumbnail((256, 256))
                output = io.BytesIO()
                clean.save(output, format='WEBP', quality=85)
                if len(output.getvalue()) > MAX_DOWNLOAD_BYTES:
                    raise AvatarError('Avatar is too large.')
                return output.getvalue()
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, UnidentifiedImageError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise AvatarError('Avatar could not be imported.') from error


def fetch_facebook_avatar(url):
    return fetch_avatar(url, 'facebook')


def fetch_google_avatar(url):
    return fetch_avatar(url, 'google')


def sync_avatar(user, picture_url, provider):
    """Only refresh an avatar owned by this provider; login never depends on it."""
    if not picture_url or user.avatar_source not in (None, provider):
        return
    try:
        payload = fetch_facebook_avatar(picture_url) if provider == 'facebook' else fetch_google_avatar(picture_url)
        storage = photo_storage()
        new_key = storage.save_avatar(user.id, payload)
    except (AvatarError, PhotoError, OSError):
        current_app.logger.warning('Social avatar import was skipped.')
        return
    old_key = user.avatar_storage_key if user.avatar_source == provider else None
    user.avatar_storage_key = new_key
    user.avatar_source = provider
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        try:
            storage.delete_avatar(new_key, user.id)
        except (PhotoError, OSError):
            current_app.logger.warning('An unused avatar could not be removed.')
        current_app.logger.warning('Social avatar import was skipped.')
        return
    if old_key and old_key != new_key:
        try:
            storage.delete_avatar(old_key, user.id)
        except (PhotoError, OSError):
            current_app.logger.warning('A replaced avatar could not be removed.')


def sync_facebook_avatar(user, picture_url):
    sync_avatar(user, picture_url, 'facebook')


def sync_google_avatar(user, picture_url):
    sync_avatar(user, picture_url, 'google')
