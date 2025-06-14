FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY config.yaml .
COPY app.py .
CMD ["python", "app.py"]
