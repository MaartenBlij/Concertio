FROM python:3.12-slim

WORKDIR /app

COPY app.py ./
COPY concertio ./concertio

ENV HOST=0.0.0.0 \
    PORT=8080 \
    CONCERTIO_DATA=/app/data

EXPOSE 8080

VOLUME ["/app/data"]

CMD ["python3", "app.py"]
