"""
lambda_handler.py - AWS Lambda entry point for the API.

Lambda calls handler(event, context) for each request from API Gateway. Mangum turns that
event into a request for the FastAPI app (api/main.py), and turns the app's reply back into
an API Gateway response. The same app runs locally with: uvicorn api.main:app

Secrets are loaded from Parameter Store BEFORE the app is imported, because some modules
read their settings when they are imported.
"""

# --- Imports -----------------------------------------------------------------
# load_secrets: copies the SSM parameters into the environment (utils/secrets.py).
# Mangum: the adapter between API Gateway events and ASGI apps (FastAPI).
from utils.secrets import load_secrets

load_secrets()

from mangum import Mangum  # noqa: E402  (must come after load_secrets)
from api.main import app  # noqa: E402

# lifespan="off": the app has no startup or shutdown work to run per request.
handler = Mangum(app, lifespan="off")
