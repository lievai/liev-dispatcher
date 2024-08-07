#!/bin/bash
gunicorn dispatcher:app --threads 60 --worker-class gunicorn.workers.ggevent.GeventWorker --bind 0.0.0.0:5011 --log-level debug