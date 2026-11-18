FROM python:3.12.11-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 120 --retries 8 -r requirements.txt
COPY requirements-auth.txt .
RUN pip install --no-cache-dir --timeout 120 --retries 8 -r requirements-auth.txt
COPY . .
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/srv
RUN useradd --uid 10001 --create-home callguard && mkdir -p /srv/storage && chown -R callguard:callguard /srv/storage
USER callguard
