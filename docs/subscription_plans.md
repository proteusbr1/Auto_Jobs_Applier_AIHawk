# AIHawk Subscription Plans

This document outlines the subscription plans available in the AIHawk application, including their features and limitations.

## Available Plans

| ID | Name | Price | Interval | Features |
|----|------|-------|----------|----------|
| 3 | Free Trial | $0.00 | month | <ul><li>max_applications_per_day: 5</li><li>max_resumes: 1</li><li>max_job_configs: 1</li></ul> |
| 4 | Job Seeker | $14.99 | month | <ul><li>max_applications_per_day: 25</li><li>max_resumes: 3</li><li>max_job_configs: 3</li><li>has_custom_resume_generation: true</li></ul> |
| 5 | Career Pro | $29.99 | month | <ul><li>max_applications_per_day: 50</li><li>max_resumes: 10</li><li>max_job_configs: 10</li><li>has_custom_resume_generation: true</li></ul> |

## Feature Descriptions

- **max_applications_per_day**: Maximum number of job applications that can be submitted per day
- **max_resumes**: Maximum number of resumes that can be stored in the system
- **max_job_configs**: Maximum number of job search configurations that can be created
- **has_custom_resume_generation**: Whether the plan includes the ability to generate custom resumes for specific job applications

## Implementation Details

The subscription plan features are stored as a JSON string in the `features` column of the `subscription_plans` table. When checking if a user has reached their limit, the system:

1. Gets the user's active subscription
2. Retrieves the subscription plan by name
3. Parses the features JSON string
4. Checks if the user has reached the limit for the specific feature

### Example JSON for Free Trial Plan

```json
{
  "max_applications_per_day": 5,
  "max_resumes": 1,
  "max_job_configs": 1
}
```

### Example JSON for Job Seeker Plan

```json
{
  "max_applications_per_day": 25,
  "max_resumes": 3,
  "max_job_configs": 3,
  "has_custom_resume_generation": true
}
```

### Example JSON for Career Pro Plan

```json
{
  "max_applications_per_day": 50,
  "max_resumes": 10,
  "max_job_configs": 10,
  "has_custom_resume_generation": true
}
```

## Code Implementation

The subscription plan limits are enforced in the following files:

- `web/app/api/job_configs.py`: Enforces the `max_job_configs` limit when creating a new job configuration
- `web/app/api/resumes.py`: Enforces the `max_resumes` limit when uploading a new resume

The code checks if the user has reached their limit by:

```python
# Check if user has reached the maximum number of job configs/resumes
subscription = user.subscription
if subscription and subscription.is_active():
    # Get the subscription plan
    plan = SubscriptionPlan.query.filter_by(name=subscription.plan).first()
    if plan and plan.features:
        import json
        try:
            features = json.loads(plan.features)
            max_items = features.get('max_job_configs')  # or 'max_resumes'
            if max_items and user.job_configs.count() >= int(max_items):  # or user.resumes.count()
                return jsonify({
                    'error': f'You have reached the maximum number of job configurations ({max_items}) allowed by your subscription plan.'
                }), 403
        except (json.JSONDecodeError, ValueError) as e:
            current_app.logger.error(f"Error parsing subscription plan features: {e}")
