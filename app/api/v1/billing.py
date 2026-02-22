"""Stripe webhooks and billing."""

import stripe
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Request, status
from stripe import Webhook

from app.config import get_settings

router = APIRouter(prefix="/webhooks", tags=["billing"])


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
):
    """Handle Stripe webhooks: checkout.session.completed, invoice.paid, customer.subscription.updated."""
    settings = get_settings()
    if not settings.stripe_webhook_secret or not settings.stripe_secret_key:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Stripe not configured")
    payload = await request.body()
    try:
        event = Webhook.construct_event(
            payload, stripe_signature or "", settings.stripe_webhook_secret
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")
    except stripe.SignatureVerificationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")
    # Dispatch by event type
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        # TODO: create or update Subscription, set workspace.plan, grant credits
        pass
    elif event["type"] == "invoice.paid":
        invoice = event["data"]["object"]
        # TODO: add credits if one-time purchase; extend period
        pass
    elif event["type"] == "customer.subscription.updated":
        sub = event["data"]["object"]
        # TODO: update Subscription and Plan, adjust workspace.credits_balance
        pass
    return {"received": True}
