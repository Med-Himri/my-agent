# Chromium + Node + Playwright 1.63.0 come with the base image
FROM mcr.microsoft.com/playwright:v1.63.0-noble

RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip ffmpeg tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY renderer/package.json renderer/
RUN cd renderer && npm install --omit=dev --no-audit --no-fund

COPY . .
ENV PYTHONUNBUFFERED=1 DATA_DIR=/app/data
VOLUME /app/data
CMD ["python3", "bot.py"]
