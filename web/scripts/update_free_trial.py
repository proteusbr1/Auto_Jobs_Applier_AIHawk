#!/usr/bin/env python3
"""
Script to update the free trial plan to have only 1 resume and 1 job configuration.
"""
import sys
import os
import json

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web.app import create_app, db
from web.app.models.subscription import SubscriptionPlan

app = create_app()

def update_free_trial_plan():
    """
    Update the free trial plan to have only 1 resume and 1 job configuration.
    """
    with app.app_context():
        # Find the Starter (free trial) plan
        starter_plan = SubscriptionPlan.query.filter_by(name="Starter").first()
        
        if not starter_plan:
            print("Error: Starter plan not found in the database.")
            return
        
        try:
            # Parse the current features
            if starter_plan.features:
                features = json.loads(starter_plan.features)
            else:
                features = {}
            
            # Update the features
            features['max_resumes'] = 1
            features['max_job_configs'] = 1
            features['max_applications_per_day'] = 5
            
            # Save the updated features
            starter_plan.features = json.dumps(features)
            db.session.commit()
            
            print("Successfully updated the Starter (free trial) plan:")
            print(f"- Name: {starter_plan.name}")
            print(f"- Price: ${starter_plan.price}/{starter_plan.interval}")
            print(f"- Features: {starter_plan.features}")
        except Exception as e:
            db.session.rollback()
            print(f"Error updating the Starter plan: {str(e)}")

if __name__ == "__main__":
    update_free_trial_plan()
