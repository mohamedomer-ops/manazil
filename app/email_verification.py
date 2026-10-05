"""Session-owned verification, serialized per user to enforce send/attempt limits."""
import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from flask import current_app
from sqlalchemy import select

from app import db
from app.languages import translate
from app.mail import MailDeliveryError, send_email
from app.models import EmailVerificationChallenge, User, utc_now

EXPIRY = timedelta(minutes=10)
COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5
MAX_SENDS_PER_HOUR = 5


def code_digest(challenge, code):
    # A server-secret keyed hash protects low-entropy codes against a DB-only leak.
    key = current_app.config['SECRET_KEY']
    key = key.encode() if isinstance(key, str) else key
    value = f'{challenge.id}:{challenge.user_id}:{challenge.email}:{code}'.encode()
    return hmac.new(key, value, hashlib.sha256).hexdigest()


def locked_user(user_id):
    return db.session.scalar(select(User).where(User.id == user_id).with_for_update()
                             .execution_options(populate_existing=True))


def issue_code(user_id, language):
    user = locked_user(user_id)
    if not user or not user.is_active or not user.email or user.email_verified:
        db.session.commit()
        return 'unavailable'
    now = utc_now()
    recent = db.session.scalars(select(EmailVerificationChallenge).where(
        EmailVerificationChallenge.user_id == user.id,
        EmailVerificationChallenge.created_at > now - timedelta(hours=1),
    ).order_by(EmailVerificationChallenge.created_at.desc(), EmailVerificationChallenge.id.desc())).all()
    if len(recent) >= MAX_SENDS_PER_HOUR or (recent and now - recent[0].created_at < COOLDOWN):
        db.session.commit()
        return 'limited'
    # Ensure even the previous code value is not accidentally reused.
    previous = db.session.scalar(select(EmailVerificationChallenge).where(
        EmailVerificationChallenge.user_id == user.id).order_by(EmailVerificationChallenge.id.desc()))
    code = f'{secrets.randbelow(1_000_000):06d}'
    while previous and hmac.compare_digest(previous.code_hash, code_digest(previous, code)):
        code = f'{secrets.randbelow(1_000_000):06d}'
    for challenge in db.session.scalars(select(EmailVerificationChallenge).where(
            EmailVerificationChallenge.user_id == user.id,
            EmailVerificationChallenge.consumed_at.is_(None))):
        challenge.consumed_at = now
    db.session.flush()
    challenge = EmailVerificationChallenge(user_id=user.id, email=user.email,
        code_hash='', created_at=now, expires_at=now + EXPIRY)
    db.session.add(challenge)
    db.session.flush()
    challenge.code_hash = code_digest(challenge, code)
    recipient = user.email
    db.session.commit()
    # Delivery is outside the transaction: failures never delete the account.
    body = translate('Your Manazil email verification code is:', language) + '\n\n' + code + '\n\n' + translate(
        'This code expires in 10 minutes. If you did not request this, ignore this message.', language)
    try:
        send_email(recipient, translate('Verify your Manazil email', language), body)
    except MailDeliveryError:
        return 'delivery_failed'
    return 'sent'


def verify_email_code(user_id, code):
    user = locked_user(user_id)
    if not user or not user.is_active or not user.email or user.email_verified:
        db.session.commit()
        return False
    challenge = db.session.scalar(select(EmailVerificationChallenge).where(
        EmailVerificationChallenge.user_id == user.id,
        EmailVerificationChallenge.email == user.email,
        EmailVerificationChallenge.consumed_at.is_(None),
    ).order_by(EmailVerificationChallenge.id.desc()))
    now = utc_now()
    if not challenge or challenge.expires_at <= now or challenge.attempts >= MAX_ATTEMPTS:
        db.session.commit()
        return False
    challenge.attempts += 1
    valid = bool(isinstance(code, str) and re.fullmatch(r'[0-9]{6}', code) and
                 hmac.compare_digest(challenge.code_hash, code_digest(challenge, code)))
    if valid or challenge.attempts >= MAX_ATTEMPTS:
        challenge.consumed_at = now
    if valid:
        user.email_verified = True
    db.session.commit()
    return valid
