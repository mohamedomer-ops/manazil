from app import create_app
from werkzeug.serving import WSGIRequestHandler


class LocalRequestHandler(WSGIRequestHandler):
    def log_request(self, code='-', size='-'):
        # Google's callback query carries an authorization code and state.
        # Werkzeug's default access log includes the query string.
        if self.path.partition('?')[0] == '/auth/google/callback':
            original_path = self.path
            try:
                self.path = '/auth/google/callback'
                super().log_request(code, size)
            finally:
                self.path = original_path
        else:
            super().log_request(code, size)


app = create_app()


if __name__ == "__main__":
    if app.config['ENVIRONMENT'] == 'production':
        raise RuntimeError('Use Gunicorn to serve Manazil in production.')
    app.run(host="0.0.0.0", port=5000, request_handler=LocalRequestHandler)
