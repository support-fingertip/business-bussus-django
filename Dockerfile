FROM python:3.10-slim

WORKDIR /app

COPY . .

RUN pip install --upgrade pip \
 && pip install -r requirements.txt \
 && pip install gunicorn

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "version2.wsgi:application"]
