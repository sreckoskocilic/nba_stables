FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install -U pip --no-cache-dir && \
    pip install --no-cache-dir -r requirements.txt

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

EXPOSE 8000

CMD ["python", "api/main.py"]