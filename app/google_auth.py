"""Session-bound Google authorization-code flow and Manazil identity mapping."""
import base64
import hashlib
import secrets
import time

from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError

from app import db
from app.auth import auth_destination, establish_session, home_destination, safe_next
from app.google_provider import GoogleProviderError
from app.languages import current_language, translate
from app.models import User, UserIdentity, utc_now

google = Blueprint('google', __name__)
STATE_TTL = 300
DIAGNOSTIC_CATEGORIES = frozenset({
    'authorization_code_exchange_failure', 'token_exchange_http_status',
    'malformed_provider_response', 'id_token_verification_failure',
    'issuer_validation_failure', 'audience_validation_failure',
    'expiration_validation_failure', 'nonce_validation_failure',
    'missing_email', 'email_verified_failure', 'malformed_required_claims',
    'unexpected_provider_error',
})


def log_provider_failure(category, http_status=None):
    category = category if category in DIAGNOSTIC_CATEGORIES else 'unexpected_provider_error'
    status = http_status if isinstance(http_status, int) and 100 <= http_status <= 599 else 'none'
    current_app.logger.warning('GOOGLE_AUTH_DIAGNOSTIC category=%s http_status=%s', category, status)


@google.before_request
def guard_google_routes():
    if not current_app.config.get('PUBLIC_GOOGLE_LOGIN_ENABLED') or not current_app.extensions.get('google_auth_provider'):
        abort(404)


@google.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


@google.post('/auth/google')
def start():
    verifier = secrets.token_urlsafe(48)
    nonce = secrets.token_urlsafe(32)
    state = secrets.token_urlsafe(32)
    session['google_auth'] = {'state': state, 'nonce': nonce, 'verifier': verifier,
                              'issued_at': time.time(), 'next': auth_destination(url_for('main.index')),
                              'language': current_language()}
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    provider = current_app.extensions['google_auth_provider']
    return redirect(provider.authorization_url(state, nonce, challenge), code=303)


def valid_state(pending, supplied):
    return bool(isinstance(pending, dict) and isinstance(pending.get('state'), str) and
                isinstance(pending.get('nonce'), str) and isinstance(pending.get('verifier'), str) and
                isinstance(pending.get('issued_at'), (int, float)) and isinstance(supplied, str) and
                secrets.compare_digest(pending['state'].encode(), supplied.encode()) and
                0 <= time.time() - pending['issued_at'] <= STATE_TTL)


def find_or_create_user(identity):
    existing = db.session.get(UserIdentity, ('google', identity.provider_user_id))
    if existing:
        return existing.user
    try:
        with db.session.begin_nested():
            user = User(contact_name=identity.display_name, is_verified=False)
            db.session.add(user)
            db.session.flush()
            db.session.add(UserIdentity(provider='google', provider_user_id=identity.provider_user_id,
                                        display_name=identity.display_name, user_id=user.id))
            db.session.flush()
        return user
    except IntegrityError:
        existing = db.session.get(UserIdentity, ('google', identity.provider_user_id))
        if existing:
            return existing.user
        raise


def failure(pending, message, status):
    pending = pending if isinstance(pending, dict) else {}
    language = pending.get('language') if pending.get('language') in ('ar', 'en') else current_language()
    destination = safe_next(pending.get('next'), url_for('main.index'))
    return render_template('auth/login.html', next=destination,
                           google_next=destination, values={}, error=message,
                           language=language, t=lambda phrase: translate(phrase, language)), status


@google.get('/auth/google/callback')
def callback():
    pending = session.pop('google_auth', None)
    if not valid_state(pending, request.args.get('state')):
        return failure(pending, 'Google sign-in could not be completed. Please try again.', 400)
    if request.args.get('error'):
        return failure(pending, 'Google sign-in was cancelled.', 400)
    code = request.args.get('code')
    if not code:
        return failure(pending, 'Google sign-in could not be completed. Please try again.', 400)
    try:
        identity = current_app.extensions['google_auth_provider'].authenticate(
            code, pending['nonce'], pending['verifier'])
    except GoogleProviderError as error:
        log_provider_failure(error.category, error.http_status)
        return failure(pending, 'Google sign-in could not be completed. Please try again.', 502)
    except Exception:
        # Keep the public response generic and avoid logging exception text,
        # tracebacks or provider payloads while diagnosing local OAuth failures.
        log_provider_failure('unexpected_provider_error')
        return failure(pending, 'Google sign-in could not be completed. Please try again.', 502)
    user = find_or_create_user(identity)
    if not user.is_active:
        abort(403)
    user.last_login_at = utc_now()
    db.session.commit()
    from app.avatar_storage import sync_google_avatar
    sync_google_avatar(user, identity.picture_url)
    language = pending['language'] if pending['language'] in ('ar', 'en') else 'ar'
    if not user.social_contact_complete:
        response = establish_session(user, language=language)
        session['profile_next'] = home_destination(language)
        session['profile_language'] = language
        return response
    return establish_session(user, language=language)
