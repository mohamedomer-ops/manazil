"""Purpose-separated reset codes and DB-backed, single-use reset authorization."""
import hashlib
import hmac
import re
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import BoundedSemaphore, Lock

from flask import current_app, session
from sqlalchemy import select

from app import db
from app.account_profile import normalize_email
from app.email_verification import locked_user
from app.languages import translate
from app.mail import send_email
from app.models import PasswordResetChallenge, User, utc_now

CODE_TTL = timedelta(minutes=10)
AUTHORIZATION_TTL = timedelta(minutes=5)
PENDING_TTL = timedelta(minutes=15)
COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5
MAX_SENDS_PER_HOUR = 5
GENERIC_NOTICE = 'If an eligible account exists for this email, we have sent a password reset code.'
_mail_pool = None
_mail_lock = Lock()
_mail_slots = BoundedSemaphore(10)


def digest(purpose, value):
    key = current_app.config['SECRET_KEY']
    key = key.encode() if isinstance(key, str) else key
    return hmac.new(key, f'{purpose}:{value}'.encode(), hashlib.sha256).hexdigest()


def credential_digest(user):
    return digest('password-reset-credential', f'{user.id}:{user.password_hash}')


def code_digest(challenge, code):
    return digest('password-reset-code',
                  f'{challenge.id}:{challenge.user_id}:{challenge.email}:{challenge.credential_hash}:{code}')


def eligible(user):
    return bool(user and user.is_active and user.email and user.email_verified and user.password_hash)


def _send(recipient, subject, body):
    try:
        send_email(recipient, subject, body)
    except Exception:
        # Never include exceptions, response bodies, addresses, or codes.
        current_app.logger.warning('PASSWORD_RESET_MAIL_DELIVERY_FAILED')


def _process_request(app, email, language):
    with app.app_context():
        try:
            _issue_code(email, language)
        except Exception:
            db.session.rollback()
            app.logger.warning('PASSWORD_RESET_REQUEST_FAILED')


def request_code(email, language):
    """Queue every address alike, keeping DB/provider timing out of the response."""
    app = current_app._get_current_object()
    if app.testing:
        # Deterministic isolated DB and mocked delivery in automated tests.
        _issue_code(email, language)
        return
    if not _mail_slots.acquire(blocking=False):
        return
    global _mail_pool
    try:
        with _mail_lock:
            if _mail_pool is None:
                _mail_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='reset-mail')
        future = _mail_pool.submit(_process_request, app, email, language)
        future.add_done_callback(lambda result: _mail_slots.release())
    except Exception:
        _mail_slots.release()


def _issue_code(email, language):
    """Return no eligibility/delivery result to the public request handler."""
    user_id = db.session.scalar(select(User.id).where(User.email == email)) if email else None
    user = locked_user(user_id) if user_id else None
    if not eligible(user) or user.email != email:
        db.session.commit()
        return
    now = utc_now()
    recent = db.session.scalars(select(PasswordResetChallenge).where(
        PasswordResetChallenge.user_id == user.id,
        PasswordResetChallenge.created_at > now - timedelta(hours=1),
    ).order_by(PasswordResetChallenge.id.desc())).all()
    if len(recent) >= MAX_SENDS_PER_HOUR or (recent and now - recent[0].created_at < COOLDOWN):
        db.session.commit()
        return
    previous = db.session.scalar(select(PasswordResetChallenge).where(
        PasswordResetChallenge.user_id == user.id).order_by(PasswordResetChallenge.id.desc()))
    code = f'{secrets.randbelow(1_000_000):06d}'
    while previous and hmac.compare_digest(previous.code_hash, code_digest(previous, code)):
        code = f'{secrets.randbelow(1_000_000):06d}'
    for old in db.session.scalars(select(PasswordResetChallenge).where(
            PasswordResetChallenge.user_id == user.id, PasswordResetChallenge.consumed_at.is_(None))):
        old.consumed_at = now
        old.authorization_hash = old.authorization_expires_at = None
    db.session.flush()
    challenge = PasswordResetChallenge(user_id=user.id, email=user.email,
        credential_hash=credential_digest(user), code_hash='', created_at=now, expires_at=now + CODE_TTL)
    db.session.add(challenge)
    db.session.flush()
    challenge.code_hash = code_digest(challenge, code)
    recipient = user.email
    db.session.commit()
    body = translate('Your Manazil password reset code is:', language) + '\n\n' + code + '\n\n' + translate(
        'This code expires in 10 minutes. If you did not request a password reset, ignore this message.', language)
    body += '\n\n' + translate('Check Spam or Junk if the email is not in your Inbox.', language)
    _send(recipient, translate('Reset your Manazil password', language), body)


def begin_request(email, language):
    try:
        email = normalize_email(email)
    except ValueError:
        email = None
    # Identical cookie state for known, unknown and ineligible addresses.
    session.pop('password_reset_authorization', None)
    session['password_reset_pending'] = {
        'email': email, 'expires': (utc_now() + PENDING_TTL).timestamp(),
    }
    now = utc_now().timestamp()
    requests = [stamp for stamp in session.get('password_reset_requests', [])
                if isinstance(stamp, (int, float)) and now - 3600 < stamp <= now]
    allowed = len(requests) < MAX_SENDS_PER_HOUR and (not requests or now - requests[-1] >= 60)
    if allowed:
        requests.append(now)
    session['password_reset_requests'] = requests
    if allowed:
        request_code(email, language)


def pending_request():
    pending = session.get('password_reset_pending')
    if not isinstance(pending, dict) or not isinstance(pending.get('expires'), (float, int)) or pending['expires'] <= utc_now().timestamp():
        session.pop('password_reset_pending', None)
        return None
    return pending


def verify_code(email, code):
    user_id = db.session.scalar(select(User.id).where(User.email == email)) if email else None
    user = locked_user(user_id) if user_id else None
    challenge = db.session.scalar(select(PasswordResetChallenge).where(
        PasswordResetChallenge.user_id == user_id, PasswordResetChallenge.consumed_at.is_(None),
    ).order_by(PasswordResetChallenge.id.desc())) if eligible(user) and user.email == email else None
    now = utc_now()
    if (not challenge or challenge.email != user.email or challenge.code_verified_at is not None or
            challenge.expires_at <= now or challenge.attempts >= MAX_ATTEMPTS or
            not hmac.compare_digest(challenge.credential_hash, credential_digest(user))):
        db.session.commit()
        return None
    valid = bool(isinstance(code, str) and re.fullmatch(r'[0-9]{6}', code) and
                 hmac.compare_digest(challenge.code_hash, code_digest(challenge, code)))
    if not valid:
        challenge.attempts += 1
        if challenge.attempts >= MAX_ATTEMPTS:
            challenge.consumed_at = now
        db.session.commit()
        return None
    token = secrets.token_urlsafe(32)
    challenge.code_verified_at = now
    challenge.authorization_hash = digest('password-reset-authorization', f'{challenge.id}:{token}')
    challenge.authorization_expires_at = now + AUTHORIZATION_TTL
    challenge_id = challenge.id
    db.session.commit()
    return {'challenge_id': challenge_id, 'token': token}


def authorized_challenge(grant):
    if (not isinstance(grant, dict) or type(grant.get('challenge_id')) is not int or
            not isinstance(grant.get('token'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', grant['token'])):
        return None
    challenge = db.session.get(PasswordResetChallenge, grant['challenge_id'])
    if not challenge:
        return None
    user = locked_user(challenge.user_id)
    db.session.refresh(challenge)
    if (not eligible(user) or challenge.consumed_at is not None or challenge.code_verified_at is None or
            challenge.email != user.email or not challenge.authorization_hash or
            not challenge.authorization_expires_at or challenge.authorization_expires_at <= utc_now() or
            not hmac.compare_digest(challenge.credential_hash, credential_digest(user)) or
            not hmac.compare_digest(challenge.authorization_hash,
                digest('password-reset-authorization', f"{challenge.id}:{grant['token']}"))):
        return None
    return challenge, user


def set_new_password(grant, password):
    from app.password_policy import password_errors
    if password_errors(password, password):
        return False
    authorized = authorized_challenge(grant)
    if not authorized:
        db.session.commit()
        return False
    challenge, user = authorized
    user.set_password(password)
    now = utc_now()
    for old in db.session.scalars(select(PasswordResetChallenge).where(
            PasswordResetChallenge.user_id == user.id, PasswordResetChallenge.consumed_at.is_(None))):
        old.consumed_at = now
        old.authorization_hash = old.authorization_expires_at = None
    db.session.commit()
    return True
