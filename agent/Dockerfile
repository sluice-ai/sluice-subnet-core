FROM python:3.12-slim

WORKDIR /app

COPY runner.py /app/runner.py
COPY entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
