FROM python:3.11-slim

RUN apt-get update && apt-get install -y build-essential libpq-dev curl

WORKDIR /code


COPY requirements.txt .

RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
