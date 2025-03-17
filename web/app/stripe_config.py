"""
Stripe configuration and utility functions for the AIHawk application.
"""
import os
import stripe
from flask import current_app, url_for
from datetime import datetime, timedelta

# Initialize Stripe with the API key
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
stripe.api_version = '2023-10-16'  # Use a specific API version for stability

# Subscription plan IDs
SUBSCRIPTION_PLANS = {
    'basic': {
        'name': 'Basic',
        'description': 'Up to 50 job applications per month',
        'price_id': os.environ.get('STRIPE_BASIC_PRICE_ID'),
        'features': [
            'Up to 50 job applications per month',
            'Basic resume management',
            'Standard support',
        ],
        'monthly_applications': 50,
        'resume_limit': 3,
    },
    'professional': {
        'name': 'Professional',
        'description': 'Up to 200 job applications per month',
        'price_id': os.environ.get('STRIPE_PROFESSIONAL_PRICE_ID'),
        'features': [
            'Up to 200 job applications per month',
            'Advanced resume management',
            'Priority support',
            'Custom cover letter generation',
        ],
        'monthly_applications': 200,
        'resume_limit': 10,
    },
    'enterprise': {
        'name': 'Enterprise',
        'description': 'Unlimited job applications',
        'price_id': os.environ.get('STRIPE_ENTERPRISE_PRICE_ID'),
        'features': [
            'Unlimited job applications',
            'Unlimited resume management',
            'Premium support',
            'Custom cover letter generation',
            'Advanced analytics',
            'API access',
        ],
        'monthly_applications': float('inf'),
        'resume_limit': float('inf'),
    }
}


def create_checkout_session(user, plan_id):
    """
    Create a Stripe Checkout Session for subscription purchase.
    
    Args:
        user: User object
        plan_id: Subscription plan ID ('basic', 'professional', 'enterprise')
        
    Returns:
        Stripe Checkout Session ID
    """
    if plan_id not in SUBSCRIPTION_PLANS:
        raise ValueError(f"Invalid plan ID: {plan_id}")
    
    # Get the price ID for the selected plan
    price_id = SUBSCRIPTION_PLANS[plan_id]['price_id']
    if not price_id:
        raise ValueError(f"Price ID not configured for plan: {plan_id}")
    
    # Create the checkout session
    try:
        checkout_session = stripe.checkout.Session.create(
            customer_email=user.email,
            client_reference_id=str(user.id),
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=url_for('billing.checkout_success', _external=True) + 
                        f'?session_id={{CHECKOUT_SESSION_ID}}&plan={plan_id}',
            cancel_url=url_for('billing.checkout_cancel', _external=True),
            metadata={
                'user_id': str(user.id),
                'plan': plan_id,
            },
        )
        return checkout_session.id
    except stripe.error.StripeError as e:
        current_app.logger.error(f"Stripe error: {str(e)}", extra={
            'user_id': user.id,
            'plan': plan_id,
            'error': str(e),
        })
        raise


def create_customer_portal_session(user):
    """
    Create a Stripe Customer Portal Session for subscription management.
    
    Args:
        user: User object
        
    Returns:
        Stripe Customer Portal Session URL
    """
    if not user.stripe_customer_id:
        raise ValueError("User does not have a Stripe customer ID")
    
    try:
        session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=url_for('account.billing', _external=True),
        )
        return session.url
    except stripe.error.StripeError as e:
        current_app.logger.error(f"Stripe error: {str(e)}", extra={
            'user_id': user.id,
            'error': str(e),
        })
        raise


def handle_webhook_event(payload, signature):
    """
    Handle Stripe webhook events.
    
    Args:
        payload: Webhook request body
        signature: Stripe signature header
        
    Returns:
        Tuple of (event_type, event_data)
    """
    webhook_secret = current_app.config['STRIPE_WEBHOOK_SECRET']
    
    try:
        event = stripe.Webhook.construct_event(
            payload, signature, webhook_secret
        )
    except ValueError as e:
        # Invalid payload
        current_app.logger.error(f"Invalid Stripe webhook payload: {str(e)}")
        raise
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        current_app.logger.error(f"Invalid Stripe webhook signature: {str(e)}")
        raise
    
    # Handle the event
    event_type = event['type']
    event_data = event['data']['object']
    
    current_app.logger.info(f"Received Stripe webhook: {event_type}", extra={
        'event_type': event_type,
        'event_id': event['id'],
    })
    
    return event_type, event_data


def get_subscription_details(stripe_subscription_id):
    """
    Get details about a Stripe subscription.
    
    Args:
        stripe_subscription_id: Stripe subscription ID
        
    Returns:
        Dictionary with subscription details
    """
    try:
        subscription = stripe.Subscription.retrieve(stripe_subscription_id)
        
        # Get the plan information
        plan = None
        for plan_id, plan_info in SUBSCRIPTION_PLANS.items():
            if subscription.items.data[0].price.id == plan_info['price_id']:
                plan = plan_id
                break
        
        # Calculate next billing date
        current_period_end = datetime.fromtimestamp(subscription.current_period_end)
        
        return {
            'id': subscription.id,
            'status': subscription.status,
            'plan': plan,
            'current_period_start': datetime.fromtimestamp(subscription.current_period_start),
            'current_period_end': current_period_end,
            'days_until_renewal': (current_period_end - datetime.now()).days,
            'cancel_at_period_end': subscription.cancel_at_period_end,
        }
    except stripe.error.StripeError as e:
        current_app.logger.error(f"Stripe error: {str(e)}", extra={
            'subscription_id': stripe_subscription_id,
            'error': str(e),
        })
        raise


def cancel_subscription(stripe_subscription_id, at_period_end=True):
    """
    Cancel a Stripe subscription.
    
    Args:
        stripe_subscription_id: Stripe subscription ID
        at_period_end: Whether to cancel at the end of the billing period
        
    Returns:
        Updated subscription object
    """
    try:
        if at_period_end:
            subscription = stripe.Subscription.modify(
                stripe_subscription_id,
                cancel_at_period_end=True,
            )
        else:
            subscription = stripe.Subscription.delete(stripe_subscription_id)
        
        return subscription
    except stripe.error.StripeError as e:
        current_app.logger.error(f"Stripe error: {str(e)}", extra={
            'subscription_id': stripe_subscription_id,
            'error': str(e),
        })
        raise


def reactivate_subscription(stripe_subscription_id):
    """
    Reactivate a canceled subscription that hasn't expired yet.
    
    Args:
        stripe_subscription_id: Stripe subscription ID
        
    Returns:
        Updated subscription object
    """
    try:
        subscription = stripe.Subscription.modify(
            stripe_subscription_id,
            cancel_at_period_end=False,
        )
        return subscription
    except stripe.error.StripeError as e:
        current_app.logger.error(f"Stripe error: {str(e)}", extra={
            'subscription_id': stripe_subscription_id,
            'error': str(e),
        })
        raise


def create_usage_record(subscription_item_id, quantity):
    """
    Create a usage record for metered billing.
    
    Args:
        subscription_item_id: Stripe subscription item ID
        quantity: Usage quantity to report
        
    Returns:
        Created usage record
    """
    try:
        usage_record = stripe.SubscriptionItem.create_usage_record(
            subscription_item_id,
            quantity=quantity,
            timestamp=int(datetime.now().timestamp()),
        )
        return usage_record
    except stripe.error.StripeError as e:
        current_app.logger.error(f"Stripe error: {str(e)}", extra={
            'subscription_item_id': subscription_item_id,
            'quantity': quantity,
            'error': str(e),
        })
        raise


def get_invoice_history(stripe_customer_id, limit=10):
    """
    Get invoice history for a customer.
    
    Args:
        stripe_customer_id: Stripe customer ID
        limit: Maximum number of invoices to retrieve
        
    Returns:
        List of invoice objects
    """
    try:
        invoices = stripe.Invoice.list(
            customer=stripe_customer_id,
            limit=limit,
        )
        
        # Format invoice data
        formatted_invoices = []
        for invoice in invoices.data:
            formatted_invoices.append({
                'id': invoice.id,
                'number': invoice.number,
                'amount_due': invoice.amount_due / 100,  # Convert from cents
                'amount_paid': invoice.amount_paid / 100,
                'currency': invoice.currency.upper(),
                'status': invoice.status,
                'created': datetime.fromtimestamp(invoice.created),
                'hosted_invoice_url': invoice.hosted_invoice_url,
                'pdf_url': invoice.invoice_pdf,
            })
        
        return formatted_invoices
    except stripe.error.StripeError as e:
        current_app.logger.error(f"Stripe error: {str(e)}", extra={
            'customer_id': stripe_customer_id,
            'error': str(e),
        })
        raise
