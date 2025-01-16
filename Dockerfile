FROM python:3.8

COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt

ENTRYPOINT ["gunicorn", "-b", "0.0.0.0:5000", "application:app"]
