import logging
import hashlib
import os
import secrets
from datetime import timedelta
from typing import Protocol

from flask import current_app
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.models import OTPChallenge, utc_now

MAX_ATTEMPTS = 5
MAX_REQUESTS_PER_HOUR = 5
MIN_REQUEST_INTERVAL = timedelta(seconds=30)


class OTPDeliveryProvider(Protocol):
    def send(self, phone_number: str, code: str) -> None: ...


class DevelopmentOTPProvider:
    def send(self, phone_number: str, code: str) -> None:
        if not (current_app.debug or current_app.testing or current_app.config.get('OTP_DEVELOPMENT_MODE')):
            raise RuntimeError('Development OTP provider is disabled')
        current_app.extensions.setdefault('development_otps', {})[phone_number] = code
        if current_app.config.get('OTP_DEVELOPMENT_MODE') and not current_app.testing:
            directory = os.path.join(current_app.instance_path, 'dev_otps')
            os.makedirs(directory, mode=0o700, exist_ok=True)
            path = os.path.join(directory, hashlib.sha256(phone_number.encode()).hexdigest())
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, 'w') as output:
                output.write(code)
        if current_app.debug and not current_app.testing:
            logging.getLogger(__name__).info('Development OTP for %s: %s', phone_number, code)


def provider() -> OTPDeliveryProvider:
    return current_app.config.get('OTP_DELIVERY_PROVIDER') or DevelopmentOTPProvider()


def request_code(phone_number):
    now = utc_now()
    recent = db.session.scalars(select(OTPChallenge).where(
        OTPChallenge.phone_number == phone_number,
        OTPChallenge.created_at > now - timedelta(hours=1),
    ).order_by(OTPChallenge.created_at.desc())).all()
    if len(recent) >= MAX_REQUESTS_PER_HOUR or (recent and now - recent[0].created_at < MIN_REQUEST_INTERVAL):
        return False
    code = f'{secrets.randbelow(1_000_000):06d}'
    for challenge in recent:
        if challenge.consumed_at is None:
            challenge.consumed_at = now
    db.session.add(OTPChallenge(phone_number=phone_number,
                                otp_hash=generate_password_hash(code),
                                expires_at=now + timedelta(minutes=5)))
    db.session.commit()
    provider().send(phone_number, code)
    return True


def verify_code(phone_number, code):
    challenge = db.session.scalar(select(OTPChallenge).where(
        OTPChallenge.phone_number == phone_number, OTPChallenge.consumed_at.is_(None)
    ).order_by(OTPChallenge.created_at.desc(), OTPChallenge.id.desc()))
    if challenge is None:
        return False
    now = utc_now()
    if challenge.expires_at <= now or challenge.attempts >= MAX_ATTEMPTS:
        return False
    challenge.attempts += 1
    valid = isinstance(code, str) and bool(__import__('re').fullmatch(r'\d{6}', code)) and check_password_hash(challenge.otp_hash, code)
    if valid or challenge.attempts >= MAX_ATTEMPTS:
        challenge.consumed_at = now
    db.session.commit()
    return valid
