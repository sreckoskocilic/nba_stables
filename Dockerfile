FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install -U pip
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 8000

# Run the application
# CMD ["uvicorn", "--app-dir", "api", "api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--log-config", "log_config.yml"]
CMD ["python", "api/api.py"]