from unittest.mock import Mock

import pytest
import requests

from app import create_app


@pytest.fixture
def email_app(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('An unmocked email request was attempted.')
    monkeypatch.setattr('app.mail.requests.post', forbidden)
    return create_app({
        'TESTING': True, 'ENVIRONMENT': 'development',
        'SQLALCHEMY_DATABASE_URI': 'postgresql+psycopg://test@localhost/test',
        'PHOTO_STORAGE_BACKEND': 'local', 'PUBLIC_GOOGLE_LOGIN_ENABLED': False,
        'RESEND_API_KEY': 'fake-test-key', 'MAIL_FROM': 'Manazil <sender@example.test>',
    })


def invoke(app):
    return app.test_cli_runner().invoke(args=['test-email', 'recipient@example.test'])


def test_email_success(email_app, monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {'id': 'fake-id'}
    post = Mock(return_value=response)
    monkeypatch.setattr('app.mail.requests.post', post)
    result = invoke(email_app)
    assert result.exit_code == 0
    assert 'accepted by Resend' in result.output
    args, kwargs = post.call_args
    assert args == ('https://api.resend.com/emails',)
    assert kwargs['json'] == {
        'from': 'Manazil <sender@example.test>', 'to': ['recipient@example.test'],
        'subject': 'Manazil Email Test', 'text': 'Your Manazil email service is working correctly.',
    }
    assert kwargs['headers']['Authorization'] == 'Bearer fake-test-key'
    assert kwargs['headers']['Content-Type'] == 'application/json'
    assert kwargs['verify'] is True
    assert kwargs['allow_redirects'] is False
    assert kwargs['timeout'] == (3, 10)
    assert 'fake-test-key' not in result.output
    response.close.assert_called_once()


@pytest.mark.parametrize('status', [302, 400, 401, 429, 500])
def test_http_errors_are_sanitized(email_app, monkeypatch, status):
    response = Mock(status_code=status)
    monkeypatch.setattr('app.mail.requests.post', Mock(return_value=response))
    result = invoke(email_app)
    assert result.exit_code != 0
    assert f'HTTP {status}' in result.output
    response.json.assert_not_called()
    assert 'fake-test-key' not in result.output


@pytest.mark.parametrize('error', [requests.Timeout, requests.ConnectionError])
def test_network_errors_are_sanitized(email_app, monkeypatch, error):
    monkeypatch.setattr('app.mail.requests.post', Mock(side_effect=error('secret-provider-body')))
    result = invoke(email_app)
    assert result.exit_code != 0
    assert 'Delivery status is unknown' in result.output
    assert 'secret-provider-body' not in result.output


@pytest.mark.parametrize('value', [None, {}, {'id': ''}, {'id': 42}])
def test_invalid_response(email_app, monkeypatch, value):
    response = Mock(status_code=200)
    response.json.return_value = value
    monkeypatch.setattr('app.mail.requests.post', Mock(return_value=response))
    assert 'invalid response' in invoke(email_app).output


def test_invalid_json(email_app, monkeypatch):
    response = Mock(status_code=200)
    response.json.side_effect = ValueError('secret-body')
    monkeypatch.setattr('app.mail.requests.post', Mock(return_value=response))
    result = invoke(email_app)
    assert 'invalid response' in result.output
    assert 'secret-body' not in result.output


@pytest.mark.parametrize('setting,value', [
    ('RESEND_API_KEY', None), ('MAIL_FROM', None), ('RESEND_API_KEY', 'key\n'),
    ('MAIL_FROM', 'invalid'), ('MAIL_FROM', 'sender@example.test\nBcc:other@example.test'),
])
def test_invalid_configuration_never_sends(email_app, setting, value):
    email_app.config[setting] = value
    assert invoke(email_app).exit_code != 0


def test_invalid_recipient_never_sends(email_app):
    result = email_app.test_cli_runner().invoke(args=['test-email', 'invalid'])
    assert result.exit_code != 0


def test_development_guard(email_app):
    email_app.config['ENVIRONMENT'] = 'production'
    assert 'restricted to development' in invoke(email_app).output


def test_not_registered_outside_development(email_app):
    from app.dev_email import register_email_cli
    from flask import Flask
    for environment in ('testing', 'production'):
        app = Flask(__name__)
        app.config['ENVIRONMENT'] = environment
        register_email_cli(app)
        assert 'test-email' not in app.cli.commands
    assert not any('test-email' in rule.rule for rule in email_app.url_map.iter_rules())
