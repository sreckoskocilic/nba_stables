FROM python:3.12.13-slim
RUN useradd -m -u 1000 deploy

WORKDIR /app

COPY requirements.txt .

RUN pip install -U pip --no-cache-dir && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chown -R deploy:deploy /app
USER deploy

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://localhost:8000/api/health', timeout=3)"]

EXPOSE 8000

CMD ["python", "api/main.py"]