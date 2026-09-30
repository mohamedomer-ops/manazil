from functools import wraps
from urllib.parse import urlsplit

from flask import Blueprint, g, redirect, render_template, request, session, url_for
from sqlalchemy import select

from app import db
from app.models import User, utc_now
from app.otp import request_code, verify_code
from app.phone import normalize_phone

auth = Blueprint('auth', __name__)


@auth.before_app_request
def load_user():
    user_id = session.get('user_id') or session.get('pending_setup_user_id')
    g.user = db.session.get(User, user_id) if user_id else None
    if g.user and (not g.user.is_active or not g.user.is_verified):
        session.clear()
        g.user = None


@auth.app_context_processor
def auth_template_context():
    return {'current_user': g.get('user')}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get('user') is None:
            destination = request.full_path if request.query_string else request.path
            return redirect(url_for('auth.login', next=destination, **({'lang': 'en'} if request.args.get('lang') == 'en' else {})))
        if session.get('pending_setup_user_id') and request.endpoint not in ('auth.account', 'auth.account_post'):
            return redirect(url_for('auth.account', **({'lang': 'en'} if request.args.get('lang') == 'en' else {})))
        return view(*args, **kwargs)
    return wrapped


def safe_next(value):
    parsed = urlsplit(value or '')
    return value if value and value.startswith('/') and not value.startswith('//') and not parsed.scheme and not parsed.netloc else url_for('auth.account')


def contact_values(user):
    return {'contact_name': user.contact_name or '', 'phone_number': user.phone_number,
            'whatsapp': user.whatsapp or '', 'contact_role': user.contact_role or ''}


def save_contact(user, form):
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
    if not errors:
        user.contact_name = values['contact_name']
        user.whatsapp = values['whatsapp']
        user.contact_role = values['contact_role']
        db.session.commit()
    values['phone_number'] = user.phone_number
    return values, errors


@auth.get('/login')
def login():
    return render_template('auth/login.html', next=safe_next(request.args.get('next')))


@auth.post('/auth/request-otp')
def request_otp():
    from app.languages import current_language
    try:
        phone = normalize_phone(request.form.get('phone_number'))
    except ValueError:
        return render_template('auth/login.html', next=safe_next(request.form.get('next')), error='Enter a valid phone number.'), 422
    session['pending_phone'] = phone
    session['auth_next'] = safe_next(request.form.get('next'))
    sent = request_code(phone)
    return redirect(url_for('auth.verify', **({'lang': 'en'} if current_language() == 'en' else {})), code=303)


@auth.get('/auth/verify')
def verify():
    if not session.get('pending_phone'):
        return redirect(url_for('auth.login'))
    return render_template('auth/verify.html')


@auth.post('/auth/verify')
def verify_post():
    phone = session.get('pending_phone')
    if not phone or not verify_code(phone, request.form.get('code')):
        return render_template('auth/verify.html', error='Invalid or expired verification code.'), 422
    user = db.session.scalar(select(User).where(User.phone_number == phone))
    if user and not user.is_active:
        return render_template('auth/verify.html', error='Unable to sign in.'), 403
    new_user = user is None
    if new_user:
        user = User(phone_number=phone)
        db.session.add(user)
    user.is_verified = True
    user.is_active = True
    user.last_login_at = utc_now()
    db.session.commit()
    destination = safe_next(session.get('auth_next'))
    csrf_value = session.get('csrf_token')
    session.clear()
    if csrf_value:
        session['csrf_token'] = csrf_value
    if new_user:
        session['pending_setup_user_id'] = user.id
        session['contact_next'] = destination
        return redirect(url_for('auth.account', **({'lang': 'en'} if request.form.get('_language') == 'en' else {})), code=303)
    session['user_id'] = user.id
    return redirect(destination, code=303)


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
    return render_template('auth/account.html', values=contact_values(g.user), errors={},
                           setup='contact_next' in session)


@auth.post('/account')
@login_required
def account_post():
    values, errors = save_contact(g.user, request.form)
    if errors:
        return render_template('auth/account.html', values=values, errors=errors,
                               setup='contact_next' in session), 422
    destination = session.pop('contact_next', None)
    if session.pop('pending_setup_user_id', None):
        session['user_id'] = g.user.id
    if destination:
        return redirect(safe_next(destination), code=303)
    return render_template('auth/account.html', values=contact_values(g.user), errors={}, saved=True)
