from functools import wraps
from urllib.parse import urlsplit

from flask import Blueprint, g, redirect, render_template, request, session, url_for
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
    return {'current_user': g.get('user'), 'facebook_auth_enabled': enabled}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get('user') is None:
            destination = request.full_path if request.query_string else request.path
            return redirect(url_for('auth.entry', next=destination, **({'lang': 'en'} if request.args.get('lang') == 'en' else {})))
        if session.get('pending_setup_user_id') and request.endpoint not in ('auth.account', 'auth.account_post'):
            return redirect(url_for('auth.account', **({'lang': 'en'} if request.args.get('lang') == 'en' else {})))
        return view(*args, **kwargs)
    return wrapped


def safe_next(value):
    parsed = urlsplit(value or '')
    return value if value and value.startswith('/') and not value.startswith('//') and '\\' not in value and not any(ord(char) < 32 for char in value) and not parsed.scheme and not parsed.netloc else url_for('auth.account')


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
    if not errors:
        for key, value in values.items():
            setattr(user, key, value)
        db.session.commit()
    values['phone_number'] = user.phone_number
    return values, errors


def auth_destination():
    return safe_next(request.values.get('next') or session.get('auth_next'))


@auth.get('/auth')
def entry():
    return render_template('auth/entry.html', next=auth_destination())


@auth.get('/signup')
def signup():
    return render_template('auth/signup.html', next=auth_destination(), values={}, errors={})


@auth.post('/signup')
def signup_post():
    values, errors = validate_contact(request.form)
    try:
        phone = normalize_phone(request.form.get('phone_number'))
        values['phone_number'] = phone
    except ValueError:
        values['phone_number'] = request.form.get('phone_number', '')
        errors['phone_number'] = 'Enter a valid phone number.'
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
