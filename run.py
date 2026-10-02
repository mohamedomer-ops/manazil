from app import create_app


app = create_app()


if __name__ == "__main__":
    if app.config['ENVIRONMENT'] == 'production':
        raise RuntimeError('Use Gunicorn to serve Manazil in production.')
    app.run(host="0.0.0.0", port=5000)
