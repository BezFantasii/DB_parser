FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends chromium chromium-driver xvfb xauth fonts-liberation ca-certificates curl tini \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt /app/requirements.txt
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY contracts.py features.py /app/
COPY parsers /app/parsers
COPY backend /app/backend
COPY tests/fixtures /app/tests/fixtures
RUN useradd -m -u 10001 parser && mkdir -p /data/profiles /data/logs && chown -R parser:parser /data /app
ENV CHROME_BINARY=/usr/bin/chromium CHROMEDRIVER_PATH=/usr/bin/chromedriver CHROME_NO_SANDBOX=1 PROFILE_ROOT=/data/profiles LOG_ROOT=/data/logs API_HOST=0.0.0.0
USER parser
EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--", "sh", "/app/backend/entrypoint.sh"]
CMD ["python", "-m", "backend.api"]
