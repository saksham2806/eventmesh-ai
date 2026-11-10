
import os
import hmac
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Header, HTTPException

# Load local environment variables
load_dotenv(Path(__file__).parent / ".env")

router = APIRouter(tags=["PayPal Sandbox"])

# Sandbox only — never live transactions
PAYPAL_BASE_URL = "https://api-m.sandbox.paypal.com"


@router.post("/paypal/sandbox/check")
async def check_paypal_connection(
    x_organizer_key: str | None = Header(default=None)
):
    # Temporary development authorization
    expected_key = os.getenv("EVENTMESH_ORGANIZER_KEY")

    if not expected_key:
        raise HTTPException(
            status_code=503,
            detail="Organizer key not configured"
        )

    if not x_organizer_key or not hmac.compare_digest(
        x_organizer_key, expected_key
    ):
        raise HTTPException(
            status_code=403,
            detail="Unauthorized"
        )

    client_id = os.getenv("PAYPAL_CLIENT_ID")
    client_secret = os.getenv("PAYPAL_CLIENT_SECRET")

    # Allow development without PayPal credentials
    if not client_id or not client_secret:
        return {
            "status": "NOT_CONFIGURED",
            "environment": "SANDBOX",
            "message": "PayPal credentials are not configured"
        }

    # Request a temporary OAuth access token
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{PAYPAL_BASE_URL}/v1/oauth2/token",
                auth=(client_id, client_secret),
                data={
                    "grant_type": "client_credentials"
                },
                headers={
                    "Accept": "application/json"
                }
            )

    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Unable to contact PayPal Sandbox"
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="PayPal sandbox authentication failed"
        )

    result = response.json()

    if not result.get("access_token"):
        raise HTTPException(
            status_code=502,
            detail="No access token returned"
        )

    # Never expose the token to the frontend
    return {
        "status": "CONNECTED",
        "environment": "SANDBOX",
        "authenticated": True,
        "expires_in_seconds": result.get("expires_in")
    }
