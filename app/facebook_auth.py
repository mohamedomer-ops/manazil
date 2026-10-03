"""State validation, identity persistence and sessions shared by Facebook providers."""
import secrets
import time

from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError

from app import db
from app.auth import auth_destination, establish_session, safe_next
from app.facebook_provider import DevelopmentFacebookAuthProvider, development_enabled
from app.languages import current_language, translate
from app.meta_facebook_provider import MetaFacebookAuthProvider, MetaProviderError
from app.models import User, UserIdentity, utc_now

facebook = Blueprint('facebook', __name__)
STATE_TTL = 300


@facebook.before_request
def guard_facebook_routes():
    # Also fail closed if configuration changes after registration.
    provider = current_app.extensions.get('facebook_auth_provider')
    if not provider or (isinstance(provider, DevelopmentFacebookAuthProvider) and not development_enabled(current_app.config)):
        abort(404)


@facebook.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


def valid_state(pending, supplied):
    return bool(isinstance(pending, dict) and isinstance(pending.get('state'), str) and
                isinstance(pending.get('issued_at'), (int, float)) and supplied and isinstance(supplied, str) and
                secrets.compare_digest(pending['state'].encode(), supplied.encode()) and
                0 <= time.time() - pending['issued_at'] <= STATE_TTL)


@facebook.post('/auth/facebook')
def start():
    pending = {'state': secrets.token_urlsafe(32), 'issued_at': time.time(),
               'next': auth_destination(url_for('main.index')), 'language': current_language()}
    session['facebook_auth'] = pending
    provider = current_app.extensions['facebook_auth_provider']
    return redirect(provider.authorization_url(pending['state'], url_for('facebook.callback', _external=True)), code=303)


@facebook.get('/auth/facebook/development')
def development():
    if not isinstance(current_app.extensions['facebook_auth_provider'], DevelopmentFacebookAuthProvider):
        abort(404)
    pending = session.get('facebook_auth')
    if not valid_state(pending, request.args.get('state')):
        abort(400)
    from app.languages import translate
    language = pending['language']
    return render_template('auth/facebook_development.html', state=pending['state'], next=pending['next'],
                           display_name=current_app.config['FACEBOOK_DEVELOPMENT_DISPLAY_NAME'],
                           language=language, t=lambda text: translate(text, language))


def find_or_create_user(identity):
    existing = db.session.get(UserIdentity, ('facebook', identity.provider_user_id))
    if existing:
        return existing.user
    try:
        # The unique provider identity wins even if two callbacks race.
        with db.session.begin_nested():
            user = User(contact_name=identity.display_name, is_verified=False)
            db.session.add(user)
            db.session.flush()
            db.session.add(UserIdentity(provider='facebook', provider_user_id=identity.provider_user_id,
                                        display_name=identity.display_name, user_id=user.id))
            db.session.flush()
        return user
    except IntegrityError:
        existing = db.session.get(UserIdentity, ('facebook', identity.provider_user_id))
        if existing:
            return existing.user
        raise


def failure(pending, message, status):
    language = pending.get('language') if pending.get('language') in ('ar', 'en') else current_language()
    return render_template('auth/entry.html', next=pending.get('next', '/account'),
                           error=message, language=language,
                           t=lambda phrase: translate(phrase, language)), status


@facebook.route('/auth/facebook/callback', methods=['GET', 'POST'])
def callback():
    provider = current_app.extensions['facebook_auth_provider']
    if isinstance(provider, DevelopmentFacebookAuthProvider) and request.method != 'POST':
        abort(405)
    if isinstance(provider, MetaFacebookAuthProvider) and request.method != 'GET':
        abort(405)
    pending = session.pop('facebook_auth', None)  # Single use, including failed attempts.
    callback_data = request.args if request.method == 'GET' else request.form
    if not valid_state(pending, callback_data.get('state')):
        abort(400)
    if isinstance(provider, MetaFacebookAuthProvider):
        if callback_data.get('error'):
            return failure(pending, 'Facebook sign-in was cancelled.', 400)
        if not callback_data.get('code'):
            return failure(pending, 'Facebook sign-in could not be completed. Please try again.', 400)
    try:
        identity = provider.authenticate(callback_data)
    except MetaProviderError:
        return failure(pending, 'Facebook sign-in could not be completed. Please try again.', 502)
    user = find_or_create_user(identity)
    if not user.is_active:
        abort(403)
    user.last_login_at = utc_now()
    db.session.commit()
    if isinstance(provider, MetaFacebookAuthProvider):
        from app.avatar_storage import sync_facebook_avatar
        sync_facebook_avatar(user, identity.picture_url)
    if not user.facebook_contact_complete:
        language = pending['language'] if pending['language'] in ('ar', 'en') else 'ar'
        response = establish_session(user, url_for('auth.facebook_profile', **({'lang': 'en'} if language == 'en' else {})))
        session['profile_next'] = safe_next(pending['next'], url_for('main.index'))
        session['profile_language'] = language
        return response
    destination = pending['next']
    if destination == url_for('main.index') and pending['language'] == 'en':
        destination = url_for('main.index', lang='en')
    return establish_session(user, destination)
