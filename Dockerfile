FROM python:3.10-slim

WORKDIR /app

# System packages:
#   libmagic1 — required by python-magic for content-based MIME
#               sniffing in utils.file_validation. Without it the
#               upload validator falls back to extension-only checks,
#               which an attacker can spoof by renaming a payload.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libmagic1 \
 && rm -rf /var/lib/apt/lists/*

COPY . .

RUN pip install --upgrade pip \
 && pip install -r requirements.txt \
 && pip install gunicorn

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "version2.wsgi:application"]
