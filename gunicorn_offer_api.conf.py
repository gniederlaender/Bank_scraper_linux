"""Gunicorn configuration for Offer API."""

bind = "127.0.0.1:5004"
workers = 2
worker_class = "sync"
timeout = 60
keepalive = 5

# Logging
accesslog = "/var/log/offer-api/access.log"
errorlog = "/var/log/offer-api/error.log"
loglevel = "info"

# Process naming
proc_name = "offer-api"
