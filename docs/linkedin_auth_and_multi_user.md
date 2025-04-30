# LinkedIn Authentication and Multi-User Architecture

This document provides a comprehensive overview of how LinkedIn authentication and multi-user support are implemented in the AIHawk application.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [LinkedIn Authentication Flow](#linkedin-authentication-flow)
3. [Multi-User Support](#multi-user-support)
4. [Session Management](#session-management)
5. [Browser Automation with Selenium Grid](#browser-automation-with-selenium-grid)
6. [Security Considerations](#security-considerations)
7. [Subscription Plan Limitations](#subscription-plan-limitations)
8. [Troubleshooting](#troubleshooting)

## Architecture Overview

The AIHawk application uses a multi-layered architecture for LinkedIn authentication and multi-user support:

1. **User Interface Layer**: Provides the LinkedIn authentication page and job configuration interface.
2. **API Layer**: Handles authentication requests, job configuration creation, and resume management.
3. **Authentication Layer**: Manages LinkedIn authentication and session persistence.
4. **Session Management Layer**: Handles browser sessions for multiple users.
5. **Browser Automation Layer**: Uses Selenium Grid for browser automation.

Key components:

- `LinkedInAuth`: Handles the initial authentication process in the web UI.
- `LinkedInAuthenticator`: Manages LinkedIn authentication for automated job applications.
- `SessionManager`: Manages browser sessions for multiple users.
- `JobManager`: Coordinates job search and application for a specific user.

## LinkedIn Authentication Flow

### Initial Authentication

1. User navigates to the LinkedIn authentication page (`/linkedin-auth`).
2. User clicks the "Connect LinkedIn" button, which triggers the `/linkedin/auth/start` endpoint.
3. The system creates a new authentication session and redirects to `/linkedin/auth/process`.
4. A browser window opens using Selenium (either via Selenium Grid or local WebDriver).
5. User logs in to LinkedIn manually in the browser window.
6. The system detects successful login and saves the LinkedIn session cookies.
7. The user is redirected to the dashboard with LinkedIn authentication status set to `true`.

### Session Persistence

LinkedIn session cookies are stored in the user's database record in the `linkedin_session` field. This allows the system to restore the session later without requiring the user to log in again.

### Authentication Verification

When a user attempts to create a job configuration or start a job search:

1. The system checks if the user is authenticated with LinkedIn.
2. If not authenticated, the user is redirected to the LinkedIn authentication page.
3. If authenticated, the operation proceeds.

### Session Restoration

When a user starts a job search or application process:

1. The system retrieves the user's LinkedIn session cookies from the database.
2. It attempts to restore the session by adding the cookies to the browser.
3. If successful, the user doesn't need to log in again.
4. If unsuccessful (e.g., cookies expired), the user is prompted to log in manually.

## Multi-User Support

The application supports multiple users with isolated LinkedIn sessions:

### User Isolation

Each user has:
- Their own database record with LinkedIn session cookies
- A separate browser session for LinkedIn automation
- Isolated job configurations and resumes
- Independent job application history

### Resource Allocation

Resources are allocated based on subscription plans:

- **Free Trial**: Limited to 1 resume, 1 job configuration, and 1 concurrent session
- **Basic**: More resumes, job configurations, and concurrent sessions
- **Premium**: Maximum resources and concurrent sessions

## Session Management

The `SessionManager` class handles browser sessions for multiple users:

### Session Creation

```python
def get_session(self, user_id: int) -> Optional[webdriver.Remote]:
    """
    Get a browser session for a user.
    
    Args:
        user_id (int): The ID of the user.
        
    Returns:
        Optional[webdriver.Remote]: The WebDriver instance, or None if no session could be created.
    """
    # Check if user has an existing session
    # If not, create a new session
    # Return the WebDriver instance
```

### Session Limits

Sessions are limited based on:
1. System-wide maximum concurrent sessions
2. User's subscription plan limits
3. Session timeout (inactive sessions are closed)

### Session Cleanup

Inactive sessions are automatically cleaned up by a background thread:

```python
def _cleanup_sessions(self):
    """
    Periodically clean up inactive sessions.
    """
    # Run in a loop
    # Check for inactive sessions
    # Close inactive sessions
```

## Browser Automation with Selenium Grid

The application uses Selenium Grid for browser automation:

### Selenium Grid Architecture

```
+----------------+      +------------------+
| AIHawk Web App |----->| Selenium Hub     |
+----------------+      +------------------+
                               |
                               v
                        +------------------+
                        | Firefox Node     |
                        +------------------+
```

### Docker Compose Configuration

```yaml
selenium-hub:
  image: selenium/hub:4.10.0
  container_name: AIHawk-Selenium_Hub
  restart: unless-stopped
  networks:
    - default
  environment:
    - TZ=America/New_York

selenium-firefox:
  container_name: AIHawk-Selenium
  restart: unless-stopped
  image: selenium/node-firefox:4.10.0
  ports:
    - "127.0.0.1:7900:7900"
  volumes:
    - ./downloads:/downloads
  networks:
    - default
  shm_size: 2g
  environment:
    - SE_EVENT_BUS_HOST=selenium-hub
    - SE_EVENT_BUS_PUBLISH_PORT=4442
    - SE_EVENT_BUS_SUBSCRIBE_PORT=4443
    - SE_NODE_MAX_SESSIONS=5
    - SE_NODE_SESSION_TIMEOUT=300
    - TZ=America/New_York
  depends_on:
    - selenium-hub
```

### WebDriver Creation

```python
def _create_browser_session(self, user_id: int) -> Optional[webdriver.Remote]:
    """
    Create a new browser session using Selenium Grid.
    
    Args:
        user_id (int): The ID of the user.
        
    Returns:
        Optional[webdriver.Remote]: The WebDriver instance, or None if the session could not be created.
    """
    # Try to use Selenium Grid first
    # Fall back to local WebDriver if Selenium Grid is unavailable
```

## Security Considerations

### Credential Handling

- LinkedIn credentials are never stored in the database
- Authentication happens directly between the user and LinkedIn
- Only session cookies are stored, not passwords

### Session Isolation

- Each user's LinkedIn session is isolated from others
- Sessions are managed with proper locking to prevent race conditions
- Session cookies are stored securely in the user's database record

### Error Handling

- Authentication errors are logged and reported
- Failed authentication attempts are tracked
- Users are notified of authentication issues

## Subscription Plan Limitations

Free Trial users are limited to:
- 1 resume
- 1 job configuration
- 1 concurrent session

These limits are enforced in the API layer:

```python
# Check if user has reached the maximum number of job configs
subscription = user.subscription
if subscription and subscription.is_active():
    # Get the subscription plan
    plan = SubscriptionPlan.query.filter_by(name=subscription.plan).first()
    if plan and plan.features:
        import json
        try:
            features = json.loads(plan.features)
            max_configs = features.get('max_job_configs')
            
            # Special case for Free Trial plan - limit to 1 job config
            if plan.name == 'Free Trial' and user.job_configs.count() >= 1:
                return jsonify({
                    'error': 'Free Trial plan is limited to 1 job configuration. Please upgrade your plan to create more.'
                }), 403
```

## Troubleshooting

### Common Issues

1. **LinkedIn Authentication Fails**
   - Check if the Selenium Grid is running
   - Verify that the user has a valid LinkedIn account
   - Check for LinkedIn security challenges

2. **Session Management Issues**
   - Check if the maximum number of sessions has been reached
   - Verify that the user's subscription is active
   - Check for browser crashes or timeouts

3. **Multi-User Conflicts**
   - Ensure that session isolation is working correctly
   - Check for resource contention
   - Verify that subscription plan limits are being enforced

### Debugging

1. **VNC Access**
   - Selenium Grid provides VNC access for debugging at port 7900
   - Use VNC to view the browser session in real-time

2. **Logging**
   - Check the application logs for authentication issues
   - Look for errors in the Selenium Grid logs
   - Monitor session creation and cleanup

3. **Database Inspection**
   - Check the `linkedin_session` field in the user's record
   - Verify that the `linkedin_authenticated` flag is set correctly
   - Check for session timeout issues
