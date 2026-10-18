"""
secrets.py - Loads secrets from AWS Systems Manager Parameter Store into environment variables.

On AWS the API keys are stored as SecureString parameters under /stocks-insights/
(docs/AWS.md step 2.6). At startup, when SECRETS_FROM_SSM=true, every parameter there is
copied into the environment under its name: /stocks-insights/APP_API_KEY -> APP_API_KEY.
A variable that already has a value is never overwritten, so local .env values still win.
An empty variable counts as not set.
Locally (SECRETS_FROM_SSM unset) nothing happens.
"""

# --- Imports -----------------------------------------------------------------
# os: reads the settings and sets the environment variables.
import os

PREFIX = os.getenv("SSM_PREFIX", "/stocks-insights/")


def load_secrets(client=None) -> list[str]:
    """Copies the parameters into the environment. Returns the names loaded."""
    if os.getenv("SECRETS_FROM_SSM", "false").lower() != "true":
        return []
    if client is None:
        import boto3                           # imported only on AWS
        client = boto3.client("ssm", region_name=os.getenv("AWS_REGION", "ap-south-1"))
    loaded, token = [], None
    while True:
        request = {"Path": PREFIX, "Recursive": False, "WithDecryption": True}
        if token:
            request["NextToken"] = token
        page = client.get_parameters_by_path(**request)
        for parameter in page.get("Parameters", []):
            name = parameter["Name"].rsplit("/", 1)[-1]
            if not os.environ.get(name):
                os.environ[name] = parameter["Value"]
                loaded.append(name)
        token = page.get("NextToken")
        if not token:
            return loaded
