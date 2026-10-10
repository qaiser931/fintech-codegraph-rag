FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY docker-constraints.txt requirements.txt ./

RUN python -m pip install --no-cache-dir --upgrade pip --timeout 120 --retries 10

RUN python -m pip install --no-cache-dir --timeout 120 --retries 10 --resume-retries 10 \
    --index-url https://download.pytorch.org/whl/cpu torch==2.14.0+cpu

RUN python -m pip install --no-cache-dir --timeout 120 --retries 10 --resume-retries 10 \
    -c docker-constraints.txt -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
