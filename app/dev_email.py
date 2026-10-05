"""Explicit, development-only email delivery smoke test; no HTTP endpoint."""

import click
from flask import current_app


def register_email_cli(app):
    if app.config['ENVIRONMENT'] != 'development':
        return

    @app.cli.command('test-email')
    @click.argument('recipient')
    def test_email(recipient):
        """Send one development test email to RECIPIENT through Resend."""
        if current_app.config['ENVIRONMENT'] != 'development':
            raise click.ClickException('Email testing is restricted to development.')
        from app.mail import MailDeliveryError, send_email
        try:
            send_email(recipient, 'Manazil Email Test',
                       'Your Manazil email service is working correctly.')
        except MailDeliveryError as error:
            raise click.ClickException(str(error)) from None
        click.echo('Test email accepted by Resend.')
