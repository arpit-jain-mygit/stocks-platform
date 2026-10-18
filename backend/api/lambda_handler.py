"""
lambda_handler.py - AWS Lambda entry point for the API.

Lambda calls handler(event, context) for each request from API Gateway. Mangum turns that
event into a request for the FastAPI app (api/main.py), and turns the app's reply back into
an API Gateway response. The same app runs locally with: uvicorn api.main:app
"""

# --- Imports -----------------------------------------------------------------
# Mangum: the adapter between API Gateway events and ASGI apps (FastAPI).
# app: the FastAPI application.
from mangum import Mangum

from api.main import app

# lifespan="off": the app has no startup or shutdown work to run per request.
handler = Mangum(app, lifespan="off")
