FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default command is overridden in docker-compose per sensor
CMD ["python", "temperature_sensor.py"]
