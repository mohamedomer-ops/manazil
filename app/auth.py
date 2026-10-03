from functools import wraps
from urllib.parse import urlsplit

from flask import Blueprint, abort, g, redirect, render_template, request, session, url_for
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import User, utc_now
from app.otp import request_code, verify_code
from app.phone import normalize_phone

auth = Blueprint('auth', __name__)


@auth.before_app_request
def load_user():
    user_id = session.get('user_id') or session.get('pending_setup_user_id')
    g.user = db.session.get(User, user_id) if user_id else None
    if g.user and (not g.user.is_active or not g.user.has_authenticated_identity):
        csrf_value = session.get('csrf_token')
        session.clear()
        if csrf_value:
            session['csrf_token'] = csrf_value
        g.user = None


@auth.app_context_processor
def auth_template_context():
    from flask import current_app
    from app.facebook_provider import DevelopmentFacebookAuthProvider, development_enabled
    provider = current_app.extensions.get('facebook_auth_provider')
    enabled = bool(provider) and (not isinstance(provider, DevelopmentFacebookAuthProvider) or development_enabled(current_app.config))
    facebook_next = safe_next(request.values.get('next') or session.get('auth_next'), url_for('main.index'))
    return {'current_user': g.get('user'), 'facebook_auth_enabled': enabled, 'facebook_next': facebook_next,
            'facebook_is_development': enabled and isinstance(provider, DevelopmentFacebookAuthProvider)}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get('user') is None:
            destination = request.full_path if request.query_string else request.path
            return redirect(url_for('auth.entry', next=destination, **({'lang': 'en'} if request.args.get('lang') == 'en' else {})))
        if (any(identity.provider == 'facebook' for identity in g.user.identities) and
                not g.user.verified_whatsapp and request.endpoint not in (
                    'auth.facebook_profile', 'auth.facebook_profile_post',
                    'auth.facebook_profile_verify', 'auth.facebook_profile_verify_post',
                    'auth.facebook_profile_resend')):
            return redirect(url_for('auth.facebook_profile', **({'lang': 'en'} if request.args.get('lang') == 'en' else {})))
        if session.get('pending_setup_user_id') and request.endpoint not in ('auth.account', 'auth.account_post'):
            return redirect(url_for('auth.account', **({'lang': 'en'} if request.args.get('lang') == 'en' else {})))
        return view(*args, **kwargs)
    return wrapped


def safe_next(value, fallback=None):
    parsed = urlsplit(value or '')
    return value if value and value.startswith('/') and not value.startswith('//') and '\\' not in value and not any(ord(char) < 32 for char in value) and not parsed.scheme and not parsed.netloc else (fallback or url_for('auth.account'))


def establish_session(user, destination):
    csrf_value = session.get('csrf_token')
    session.clear()
    if csrf_value:
        session['csrf_token'] = csrf_value
    session['user_id'] = user.id
    return redirect(safe_next(destination), code=303)


def contact_values(user):
    return {'contact_name': user.contact_name or '', 'phone_number': user.phone_number,
            'whatsapp': user.whatsapp or '', 'contact_role': user.contact_role or ''}


def validate_contact(form):
    values = {key: form.get(key, '').strip() for key in ('contact_name', 'whatsapp', 'contact_role')}
    errors = {}
    if not values['contact_name'] or '\x00' in values['contact_name']:
        errors['contact_name'] = 'This field is required.'
    try:
        values['whatsapp'] = normalize_phone(values['whatsapp'])
    except ValueError:
        errors['whatsapp'] = 'Enter a valid phone number.'
    if values['contact_role'] not in ('owner', 'broker'):
        errors['contact_role'] = 'Choose one of the available options.'
    return values, errors


def save_contact(user, form):
    values, errors = validate_contact(form)
    if (not errors and user.verified_whatsapp and
            any(identity.provider == 'facebook' for identity in user.identities) and
            values['whatsapp'] != user.phone_number):
        errors['whatsapp'] = 'Verify a new number before using it as your WhatsApp contact.'
    if not errors:
        for key, value in values.items():
            setattr(user, key, value)
        db.session.commit()
    values['phone_number'] = user.phone_number
    return values, errors


def auth_destination(fallback=None):
    return safe_next(request.values.get('next') or session.get('auth_next'), fallback)


@auth.get('/auth')
def entry():
    return render_template('auth/entry.html', next=auth_destination())


@auth.get('/signup')
def signup():
    return render_template('auth/signup.html', next=auth_destination(), values={}, errors={})


@auth.post('/signup')
def signup_post():
    values = {key: request.form.get(key, '').strip() for key in ('contact_name', 'contact_role')}
    errors = {}
    try:
        phone = normalize_phone(request.form.get('phone_number'))
    except ValueError:
        errors['phone_number'] = 'Enter a valid phone number.'
        phone = None
    contact_values, contact_errors = validate_contact(values | {'whatsapp': phone or ''})
    values.update(contact_values)
    errors.update({key: value for key, value in contact_errors.items() if key != 'whatsapp'})
    values['phone_number'] = phone or request.form.get('phone_number', '')
    destination = auth_destination()
    if errors:
        return render_template('auth/signup.html', next=destination, values=values, errors=errors), 422
    if db.session.scalar(select(User).where(User.phone_number == phone)):
        return render_template('auth/login.html', next=destination,
                               error='An account with this number already exists. Please log in.'), 409
    session['pending_signup'] = values
    session['pending_phone'] = phone
    session['auth_next'] = destination
    request_code(phone)
    return redirect(url_for('auth.verify', **({'lang': 'en'} if request.form.get('_language') == 'en' else {})), code=303)


@auth.get('/login')
def login():
    return render_template('auth/login.html', next=auth_destination())


@auth.post('/auth/request-otp')
def request_otp():
    from app.languages import current_language
    try:
        phone = normalize_phone(request.form.get('phone_number'))
    except ValueError:
        return render_template('auth/login.html', next=safe_next(request.form.get('next')), error='Enter a valid phone number.'), 422
    session.pop('pending_signup', None)
    session['pending_phone'] = phone
    session['auth_next'] = auth_destination()
    request_code(phone)
    return redirect(url_for('auth.verify', **({'lang': 'en'} if current_language() == 'en' else {})), code=303)


@auth.get('/auth/verify')
def verify():
    if not session.get('pending_phone'):
        return redirect(url_for('auth.entry', next=auth_destination(), **({'lang': 'en'} if request.args.get('lang') == 'en' else {})))
    return render_template('auth/verify.html')


@auth.post('/auth/verify')
def verify_post():
    phone = session.get('pending_phone')
    if not phone or not verify_code(phone, request.form.get('code')):
        return render_template('auth/verify.html', error='Invalid or expired verification code.'), 422
    user = db.session.scalar(select(User).where(User.phone_number == phone))
    if user and not user.is_active:
        return render_template('auth/verify.html', error='Unable to sign in.'), 403
    registration = session.get('pending_signup')
    if registration and (user or registration.get('phone_number') != phone):
        session.pop('pending_signup', None)
        return render_template('auth/login.html', next=auth_destination(),
                               error='An account with this number already exists. Please log in.'), 409
    if not user:
        if not registration:
            return render_template('auth/login.html', next=auth_destination(),
                                   error='No account with this number. Please sign up.'), 422
        user = User(**registration)
        db.session.add(user)
    user.is_verified = True
    user.last_login_at = utc_now()
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        session.pop('pending_signup', None)
        return render_template('auth/login.html', next=auth_destination(),
                               error='An account with this number already exists. Please log in.'), 409
    destination = safe_next(session.get('auth_next'))
    return establish_session(user, destination)


@auth.post('/auth/resend')
def resend():
    if not session.get('pending_phone'):
        return redirect(url_for('auth.entry', next=auth_destination()), code=303)
    request_code(session['pending_phone'])
    return redirect(url_for('auth.verify', **({'lang': 'en'} if request.form.get('_language') == 'en' else {})), code=303)


def facebook_profile_destination():
    destination = session.get('profile_next') or url_for('auth.account')
    if destination == url_for('main.index') and session.get('profile_language') == 'en':
        return url_for('main.index', lang='en')
    return safe_next(destination, url_for('main.index'))


def facebook_profile_error(message, status=422, *, verifying=False):
    template = 'auth/facebook_profile_verify.html' if verifying else 'auth/facebook_profile.html'
    return render_template(template, error=message, pending_phone=session.get('profile_pending_phone'),
                           whatsapp=g.user.whatsapp or ''), status


@auth.get('/auth/complete-profile')
@login_required
def facebook_profile():
    if not any(identity.provider == 'facebook' for identity in g.user.identities):
        return redirect(url_for('auth.account'))
    return render_template('auth/facebook_profile.html', whatsapp=g.user.whatsapp or '')


@auth.post('/auth/complete-profile')
@login_required
def facebook_profile_post():
    if not any(identity.provider == 'facebook' for identity in g.user.identities):
        abort(403)
    try:
        phone = normalize_phone(request.form.get('whatsapp'))
    except ValueError:
        return facebook_profile_error('Enter a valid phone number.')
    if g.user.verified_whatsapp and phone == g.user.phone_number:
        return redirect(facebook_profile_destination(), code=303)
    if db.session.scalar(select(User.id).where(User.phone_number == phone, User.id != g.user.id)):
        return facebook_profile_error('This number cannot be used for this account.')
    if not request_code(phone):
        return facebook_profile_error('Please wait before requesting another code.', 429)
    session['profile_pending_phone'] = phone
    session['profile_pending_user_id'] = g.user.id
    session['profile_language'] = 'en' if request.form.get('_language') == 'en' else 'ar'
    return redirect(url_for('auth.facebook_profile_verify', **({'lang': 'en'} if request.form.get('_language') == 'en' else {})), code=303)


@auth.get('/auth/complete-profile/verify')
@login_required
def facebook_profile_verify():
    if not session.get('profile_pending_phone') or session.get('profile_pending_user_id') != g.user.id:
        return redirect(url_for('auth.facebook_profile'))
    return render_template('auth/facebook_profile_verify.html', pending_phone=session['profile_pending_phone'])


@auth.post('/auth/complete-profile/verify')
@login_required
def facebook_profile_verify_post():
    phone = session.get('profile_pending_phone')
    if not phone or session.get('profile_pending_user_id') != g.user.id:
        return redirect(url_for('auth.facebook_profile'), code=303)
    if not verify_code(phone, request.form.get('code')):
        return facebook_profile_error('Invalid or expired verification code.', verifying=True)
    if db.session.scalar(select(User.id).where(User.phone_number == phone, User.id != g.user.id)):
        session.pop('profile_pending_phone', None)
        session.pop('profile_pending_user_id', None)
        return facebook_profile_error('This number cannot be used for this account.', 409)
    g.user.phone_number = phone
    g.user.whatsapp = phone
    g.user.is_verified = True
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        session.pop('profile_pending_phone', None)
        session.pop('profile_pending_user_id', None)
        return facebook_profile_error('This number cannot be used for this account.', 409)
    session.pop('profile_pending_phone', None)
    session.pop('profile_pending_user_id', None)
    destination = facebook_profile_destination()
    session.pop('profile_next', None)
    session.pop('profile_language', None)
    return redirect(destination, code=303)


@auth.post('/auth/complete-profile/resend')
@login_required
def facebook_profile_resend():
    phone = session.get('profile_pending_phone')
    if not phone or session.get('profile_pending_user_id') != g.user.id:
        return redirect(url_for('auth.facebook_profile'), code=303)
    if not request_code(phone):
        return facebook_profile_error('Please wait before requesting another code.', 429, verifying=True)
    session['profile_language'] = 'en' if request.form.get('_language') == 'en' else 'ar'
    return redirect(url_for('auth.facebook_profile_verify', **({'lang': 'en'} if request.form.get('_language') == 'en' else {})), code=303)


@auth.post('/logout')
def logout():
    csrf_value = session.get('csrf_token')
    session.clear()
    if csrf_value:
        session['csrf_token'] = csrf_value
    return redirect(url_for('main.index'), code=303)


@auth.get('/account')
@login_required
def account():
    return render_account(contact_values(g.user), {}, setup='contact_next' in session)


@auth.get('/account/avatar')
@login_required
def account_avatar():
    if not g.user.avatar_storage_key:
        abort(404)
    from app.photo_storage import PhotoError, photo_storage
    try:
        response = photo_storage().send_avatar(g.user.avatar_storage_key, g.user.id)
    except (PhotoError, OSError):
        abort(404)
    response.headers['Cache-Control'] = 'private, no-store'
    return response


def render_account(values, errors, **options):
    facebook_identity = next((identity for identity in g.user.identities if identity.provider == 'facebook'), None)
    profile_name = (g.user.contact_name or '').strip() or (facebook_identity.display_name if facebook_identity else '')
    return render_template('auth/account.html', values=values, errors=errors,
                           profile_name=profile_name, facebook_connected=bool(facebook_identity), **options)


@auth.post('/account')
@login_required
def account_post():
    values, errors = save_contact(g.user, request.form)
    if errors:
        return render_account(values, errors, setup='contact_next' in session), 422
    destination = session.pop('contact_next', None)
    if session.pop('pending_setup_user_id', None):
        session['user_id'] = g.user.id
    if destination and g.user.contact_complete:
        return redirect(safe_next(destination), code=303)
    return render_account(contact_values(g.user), {}, saved=True)
