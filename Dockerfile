FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CLIPHUB_DATA_DIR=/data

WORKDIR /app
COPY app ./app

RUN useradd --create-home --uid 10001 cliphub && mkdir -p /data && chown cliphub:cliphub /data
USER cliphub

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=2)"

CMD ["python", "-m", "app.server"]

