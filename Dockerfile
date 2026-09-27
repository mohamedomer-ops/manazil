FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home manazil && mkdir -p /app/instance/property_photos && chown -R manazil:manazil /app/instance /app
COPY --chown=manazil:manazil . .
USER manazil

EXPOSE 5000
CMD ["python", "run.py"]
