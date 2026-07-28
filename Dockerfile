FROM python:3.12-slim

ARG LABPULSE_VERSION

LABEL org.opencontainers.image.source="https://github.com/Tommystorm-cpu/LabPulse"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.version="${LABPULSE_VERSION}"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gpiod \
        modemmanager \
    && rm -rf /var/lib/apt/lists/*

COPY dist/labpulse-${LABPULSE_VERSION}-py3-none-any.whl /tmp/

RUN python -m pip install --no-cache-dir \
      "labpulse[serial,x1200,dht11] @ file:///tmp/labpulse-${LABPULSE_VERSION}-py3-none-any.whl" \
    && rm "/tmp/labpulse-${LABPULSE_VERSION}-py3-none-any.whl"

CMD ["python", "-m", "labpulse.hardware", "--help"]
