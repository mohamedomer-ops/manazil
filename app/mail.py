"""Shared Resend transport. Never log credentials, messages, or provider bodies."""
from email.utils import parseaddr

import requests
from flask import current_app

from app.account_profile import normalize_email


class MailDeliveryError(RuntimeError):
    pass


def send_email(recipient, subject, body):
    key = current_app.config.get('RESEND_API_KEY')
    sender = current_app.config.get('MAIL_FROM')
    if not key or not sender:
        raise MailDeliveryError('Set RESEND_API_KEY and MAIL_FROM before sending email.')
    if not isinstance(key, str) or any(char.isspace() for char in key):
        raise MailDeliveryError('RESEND_API_KEY configuration is invalid.')
    try:
        recipient = normalize_email(recipient)
    except ValueError:
        raise MailDeliveryError('Enter a valid recipient email address.') from None
    try:
        if not isinstance(sender, str) or any(ord(char) < 32 for char in sender):
            raise ValueError
        _, address = parseaddr(sender)
        normalize_email(address)
    except ValueError:
        raise MailDeliveryError('MAIL_FROM must contain a valid sender email address.') from None
    try:
        response = requests.post(
            'https://api.resend.com/emails',
            headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
            json={
                'from': sender,
                'to': [recipient],
                'subject': subject,
                'text': body,
            },
            timeout=(3, 10),
            allow_redirects=False,
            verify=True,
        )
    except requests.RequestException:
        # Exception strings may contain credentials or provider response data.
        raise MailDeliveryError(
            'Email request failed. Delivery status is unknown; check Resend before retrying.'
        ) from None
    try:
        if not 200 <= response.status_code < 300:
            raise MailDeliveryError(f'Email test failed (HTTP {response.status_code}).')
        try:
            result = response.json()
        except ValueError:
            raise MailDeliveryError('Resend returned an invalid response.') from None
        if not isinstance(result, dict) or not isinstance(result.get('id'), str) or not result['id']:
            raise MailDeliveryError('Resend returned an invalid response.')
    finally:
        response.close()
