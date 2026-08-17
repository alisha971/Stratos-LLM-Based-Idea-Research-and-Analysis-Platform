FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg2 + lxml/bs4 builds.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Exports live here; mount a Railway volume at /app/exports so PDFs survive restarts.
RUN mkdir -p /app/exports
EXPOSE 8000

RUN chmod +x start.sh
CMD ["./start.sh"]
