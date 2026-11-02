import os

USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://localhost:8000")
ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://localhost:8001")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "dev-webhook-secret")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "dev-internal-key")