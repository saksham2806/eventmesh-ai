
from fastapi import FastAPI
from paypal_webhooks import receive_paypal_webhook

# Only expose the webhook endpoint.
# No Swagger, database administration, or organizer APIs.
app = FastAPI(
    title="EventMesh PayPal Webhook Receiver",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_api_route(
    "/webhooks/paypal",
    receive_paypal_webhook,
    methods=["POST"],
    include_in_schema=False,
)
