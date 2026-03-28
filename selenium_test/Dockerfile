FROM python:alpine

ENV CHROME_BIN=/usr/bin/chromium-browser \
    CHROME_PATH=/usr/lib/chromium/

RUN apk update && \
    apk add --no-cache chromium chromium-chromedriver

WORKDIR /app
COPY app/ .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python3", "main.py"]
