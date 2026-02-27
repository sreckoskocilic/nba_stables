FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install -U pip
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 8000

CMD ["python", "api/api.py"]