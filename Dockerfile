FROM python:3.10.13-alpine
EXPOSE 5000

WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY ./ .
ENV PYTHONUNBUFFERED 1
CMD ["gunicorn","dispatcher:app","--threads","60","--worker-class","gunicorn.workers.ggevent.GeventWorker","--bind","0.0.0.0:5000","--log-level","info", "--limit-request-line","0"]
