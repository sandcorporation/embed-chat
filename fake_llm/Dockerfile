FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PORT=8090

COPY app.py .

EXPOSE 8090

CMD ["python", "app.py"]
