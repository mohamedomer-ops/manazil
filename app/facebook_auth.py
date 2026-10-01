"""State validation, identity persistence and sessions shared by Facebook providers."""
import secrets
import time

from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import db
from app.auth import auth_destination, establish_session
from app.facebook_provider import DevelopmentFacebookAuthProvider, development_enabled
from app.languages import current_language
from app.models import User, UserIdentity, utc_now

facebook = Blueprint('facebook', __name__)
STATE_TTL = 300


@facebook.before_request
def guard_development_routes():
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
    return bool(pending and supplied and isinstance(supplied, str) and
                secrets.compare_digest(pending['state'].encode(), supplied.encode()) and
                0 <= time.time() - pending['issued_at'] <= STATE_TTL)


@facebook.post('/auth/facebook')
def start():
    pending = {'state': secrets.token_urlsafe(32), 'issued_at': time.time(),
               'next': auth_destination(), 'language': current_language()}
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


@facebook.post('/auth/facebook/callback')
def callback():
    pending = session.pop('facebook_auth', None)  # Single use, including failed attempts.
    if not valid_state(pending, request.form.get('state')):
        abort(400)
    identity = current_app.extensions['facebook_auth_provider'].authenticate(request.form)
    user = find_or_create_user(identity)
    if not user.is_active:
        abort(403)
    user.last_login_at = utc_now()
    db.session.commit()
    return establish_session(user, pending['next'])
