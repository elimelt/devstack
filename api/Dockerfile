FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y wget docker.io && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN wget -O GeoLite2-City.mmdb "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-City.mmdb" || \
    echo "GeoIP database not available, will use fallback"

COPY main.py .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]

