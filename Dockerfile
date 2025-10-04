FROM python:3.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PATH="/root/.local/bin:$PATH"

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gdal-bin \
        libgdal-dev \
        curl \
        build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN CPLUS_INCLUDE_PATH=/usr/include/gdal \
    pip install --no-cache-dir --user -r requirements.txt

COPY . .

EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "600", "--log-level", "info", "app.main:app"]
