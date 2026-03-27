# Stage 1: Build dependencies
FROM python:3.12-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Production image
FROM python:3.12-slim
RUN useradd -m -u 1000 deploy

WORKDIR /app

COPY --from=builder /install /usr/local

COPY . .

RUN chown -R deploy:deploy /app
USER deploy

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://localhost:8000/api/health', timeout=3)"]

EXPOSE 8000

CMD ["python", "api/main.py"]
