FROM python:3.12-slim

# Install system dependencies + tectonic
RUN apt-get update && apt-get install -y curl wget && \
    wget -qO /tmp/tectonic.tar.gz \
      https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-x86_64-unknown-linux-musl.tar.gz && \
    tar -xzf /tmp/tectonic.tar.gz -C /usr/local/bin && \
    chmod +x /usr/local/bin/tectonic && \
    rm /tmp/tectonic.tar.gz && \
    apt-get clean

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . pipeline/

# Tectonic caches TeX packages here on first run
ENV TECTONIC_CACHE_DIR=/tmp/tectonic-cache
ENV COMPILE_WORKER_ENABLED=true

CMD ["uvicorn", "pipeline.main:app", "--host", "0.0.0.0", "--port", "8000"]
