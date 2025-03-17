"""
Routes for the billing blueprint.
"""
import stripe
from flask import (
    render_template, redirect, url_for, flash, request, 
    jsonify, current_app, session, abort
)
from flask_login import login_required, current_user

from app import db
from app.billing import billing_bp
from app.models import User, Subscription
from app.stripe_config import (
    SUBSCRIPTION_PLANS, create_checkout_session, create_customer_portal_session,
    handle_webhook_event, get_subscription_details, cancel_subscription,
    reactivate_subscription, get_invoice_history
)


@billing_bp.route('/')
@login_required
def index():
    """
    Display the billing page with subscription plans.
    """
    # Check if user already has an active subscription
    has_subscription = current_user.subscription and current_user.subscription.is_active()
    
    return render_template(
        'billing/index.html',
        plans=SUBSCRIPTION_PLANS,
        has_subscription=has_subscription,
        subscription=current_user.subscription
    )


@billing_bp.route('/checkout/<plan_id>')
@login_required
def checkout(plan_id):
    """
    Redirect to Stripe Checkout for the selected plan.
    """
    if plan_id not in SUBSCRIPTION_PLANS:
        flash('Invalid subscription plan.', 'error')
        return redirect(url_for('billing.index'))
    
    try:
        # Create a checkout session
        checkout_session_id = create_checkout_session(current_user, plan_id)
        
        # Store the checkout session ID in the user's session
        session['checkout_session_id'] = checkout_session_id
        
        # Redirect to Stripe Checkout
        return redirect(f"https://checkout.stripe.com/c/pay/{checkout_session_id}")
    except Exception as e:
        current_app.logger.error(f"Error creating checkout session: {str(e)}", extra={
            'user_id': current_user.id,
            'plan_id': plan_id,
        })
        flash('An error occurred while processing your request. Please try again.', 'error')
        return redirect(url_for('billing.index'))


@billing_bp.route('/checkout/success')
@login_required
def checkout_success():
    """
    Handle successful checkout.
    """
    session_id = request.args.get('session_id')
    plan = request.args.get('plan')
    
    if not session_id or not plan:
        flash('Invalid checkout session.', 'error')
        return redirect(url_for('billing.index'))
    
    try:
        # Retrieve the checkout session
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        
        # Verify that the session belongs to the current user
        if str(current_user.id) != checkout_session.client_reference_id:
            flash('Invalid checkout session.', 'error')
            return redirect(url_for('billing.index'))
        
        # Get the subscription ID from the session
        subscription_id = checkout_session.subscription
        
        # Update the user's subscription
        if current_user.subscription:
            # Update existing subscription
            subscription = current_user.subscription
            subscription.stripe_subscription_id = subscription_id
            subscription.plan = plan
            subscription.status = 'active'
        else:
            # Create new subscription
            subscription = Subscription(
                user_id=current_user.id,
                stripe_subscription_id=subscription_id,
                plan=plan,
                status='active'
            )
            db.session.add(subscription)
        
        # Update the user's Stripe customer ID if not already set
        if not current_user.stripe_customer_id:
            # Retrieve the subscription to get the customer ID
            stripe_subscription = stripe.Subscription.retrieve(subscription_id)
            current_user.stripe_customer_id = stripe_subscription.customer
        
        db.session.commit()
        
        flash('Your subscription has been activated successfully!', 'success')
        return redirect(url_for('main.dashboard'))
    except Exception as e:
        current_app.logger.error(f"Error processing checkout success: {str(e)}", extra={
            'user_id': current_user.id,
            'session_id': session_id,
            'plan': plan,
        })
        flash('An error occurred while processing your subscription. Please contact support.', 'error')
        return redirect(url_for('billing.index'))


@billing_bp.route('/checkout/cancel')
@login_required
def checkout_cancel():
    """
    Handle canceled checkout.
    """
    flash('Your subscription checkout was canceled.', 'info')
    return redirect(url_for('billing.index'))


@billing_bp.route('/portal')
@login_required
def customer_portal():
    """
    Redirect to Stripe Customer Portal for subscription management.
    """
    if not current_user.stripe_customer_id:
        flash('You do not have an active subscription.', 'error')
        return redirect(url_for('billing.index'))
    
    try:
        # Create a customer portal session
        portal_url = create_customer_portal_session(current_user)
        
        # Redirect to the customer portal
        return redirect(portal_url)
    except Exception as e:
        current_app.logger.error(f"Error creating customer portal session: {str(e)}", extra={
            'user_id': current_user.id,
        })
        flash('An error occurred while processing your request. Please try again.', 'error')
        return redirect(url_for('billing.index'))


@billing_bp.route('/subscription')
@login_required
def subscription_details():
    """
    Display subscription details.
    """
    if not current_user.subscription or not current_user.subscription.stripe_subscription_id:
        flash('You do not have an active subscription.', 'error')
        return redirect(url_for('billing.index'))
    
    try:
        # Get subscription details from Stripe
        subscription_details = get_subscription_details(
            current_user.subscription.stripe_subscription_id
        )
        
        # Get invoice history
        invoices = get_invoice_history(current_user.stripe_customer_id)
        
        return render_template(
            'billing/subscription.html',
            subscription=current_user.subscription,
            details=subscription_details,
            invoices=invoices,
            plans=SUBSCRIPTION_PLANS
        )
    except Exception as e:
        current_app.logger.error(f"Error retrieving subscription details: {str(e)}", extra={
            'user_id': current_user.id,
            'subscription_id': current_user.subscription.stripe_subscription_id,
        })
        flash('An error occurred while retrieving your subscription details. Please try again.', 'error')
        return redirect(url_for('billing.index'))


@billing_bp.route('/subscription/cancel', methods=['POST'])
@login_required
def cancel_subscription_route():
    """
    Cancel the user's subscription.
    """
    if not current_user.subscription or not current_user.subscription.stripe_subscription_id:
        flash('You do not have an active subscription.', 'error')
        return redirect(url_for('billing.index'))
    
    try:
        # Cancel the subscription at the end of the billing period
        cancel_subscription(current_user.subscription.stripe_subscription_id)
        
        # Update the subscription status
        current_user.subscription.status = 'canceled'
        db.session.commit()
        
        flash('Your subscription has been canceled and will end at the end of the current billing period.', 'success')
        return redirect(url_for('billing.subscription_details'))
    except Exception as e:
        current_app.logger.error(f"Error canceling subscription: {str(e)}", extra={
            'user_id': current_user.id,
            'subscription_id': current_user.subscription.stripe_subscription_id,
        })
        flash('An error occurred while canceling your subscription. Please try again.', 'error')
        return redirect(url_for('billing.subscription_details'))


@billing_bp.route('/subscription/reactivate', methods=['POST'])
@login_required
def reactivate_subscription_route():
    """
    Reactivate a canceled subscription.
    """
    if not current_user.subscription or not current_user.subscription.stripe_subscription_id:
        flash('You do not have an active subscription.', 'error')
        return redirect(url_for('billing.index'))
    
    try:
        # Get subscription details from Stripe
        subscription_details = get_subscription_details(
            current_user.subscription.stripe_subscription_id
        )
        
        # Check if the subscription is canceled but not yet expired
        if not subscription_details['cancel_at_period_end']:
            flash('Your subscription is not canceled.', 'error')
            return redirect(url_for('billing.subscription_details'))
        
        # Reactivate the subscription
        reactivate_subscription(current_user.subscription.stripe_subscription_id)
        
        # Update the subscription status
        current_user.subscription.status = 'active'
        db.session.commit()
        
        flash('Your subscription has been reactivated successfully!', 'success')
        return redirect(url_for('billing.subscription_details'))
    except Exception as e:
        current_app.logger.error(f"Error reactivating subscription: {str(e)}", extra={
            'user_id': current_user.id,
            'subscription_id': current_user.subscription.stripe_subscription_id,
        })
        flash('An error occurred while reactivating your subscription. Please try again.', 'error')
        return redirect(url_for('billing.subscription_details'))


@billing_bp.route('/webhook', methods=['POST'])
def webhook():
    """
    Handle Stripe webhook events.
    """
    payload = request.data
    signature = request.headers.get('Stripe-Signature')
    
    if not payload or not signature:
        return jsonify({'error': 'Missing payload or signature'}), 400
    
    try:
        event_type, event_data = handle_webhook_event(payload, signature)
        
        # Handle specific event types
        if event_type == 'customer.subscription.updated':
            # Update subscription status
            subscription_id = event_data['id']
            subscription = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
            
            if subscription:
                # Update subscription status based on Stripe status
                if event_data['status'] == 'active':
                    subscription.status = 'active'
                elif event_data['status'] == 'canceled':
                    subscription.status = 'canceled'
                elif event_data['status'] == 'past_due':
                    subscription.status = 'past_due'
                elif event_data['status'] == 'unpaid':
                    subscription.status = 'unpaid'
                
                db.session.commit()
        
        elif event_type == 'customer.subscription.deleted':
            # Mark subscription as expired
            subscription_id = event_data['id']
            subscription = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
            
            if subscription:
                subscription.status = 'expired'
                db.session.commit()
        
        elif event_type == 'invoice.payment_succeeded':
            # Update subscription status to active if payment succeeds
            subscription_id = event_data.get('subscription')
            if subscription_id:
                subscription = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
                
                if subscription:
                    subscription.status = 'active'
                    db.session.commit()
        
        elif event_type == 'invoice.payment_failed':
            # Update subscription status to past_due if payment fails
            subscription_id = event_data.get('subscription')
            if subscription_id:
                subscription = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
                
                if subscription:
                    subscription.status = 'past_due'
                    db.session.commit()
        
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        current_app.logger.error(f"Error handling webhook: {str(e)}")
        return jsonify({'error': str(e)}), 400
