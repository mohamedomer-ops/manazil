"""The shared manual-account password policy; passwords are never normalized."""


def password_errors(password, confirmation):
    errors = {}
    if not password:
        errors['password'] = 'This field is required.'
    elif len(password) < 8 or len(password) > 128:
        errors['password'] = 'Use a password between 8 and 128 characters.'
    if not confirmation:
        errors['confirm_password'] = 'This field is required.'
    elif password != confirmation:
        errors['confirm_password'] = 'Passwords do not match.'
    return errors
