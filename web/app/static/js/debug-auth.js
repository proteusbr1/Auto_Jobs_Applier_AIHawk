/**
 * Debug Authentication Script
 * This script helps diagnose authentication issues with the API
 */

// Self-executing function to avoid polluting global namespace
(function () {
    // Create debug output element if it doesn't exist
    function createDebugOutput() {
        if (document.getElementById('debug-output')) {
            return;
        }

        const debugContainer = document.createElement('div');
        debugContainer.id = 'debug-container';
        debugContainer.style.position = 'fixed';
        debugContainer.style.bottom = '0';
        debugContainer.style.right = '0';
        debugContainer.style.width = '400px';
        debugContainer.style.maxHeight = '300px';
        debugContainer.style.backgroundColor = 'rgba(0, 0, 0, 0.8)';
        debugContainer.style.color = '#fff';
        debugContainer.style.padding = '10px';
        debugContainer.style.zIndex = '9999';
        debugContainer.style.overflow = 'auto';
        debugContainer.style.fontSize = '12px';
        debugContainer.style.fontFamily = 'monospace';
        debugContainer.style.borderTopLeftRadius = '5px';

        const debugHeader = document.createElement('div');
        debugHeader.style.display = 'flex';
        debugHeader.style.justifyContent = 'space-between';
        debugHeader.style.marginBottom = '10px';

        const debugTitle = document.createElement('h4');
        debugTitle.textContent = 'Auth Debug Console';
        debugTitle.style.margin = '0';
        debugTitle.style.color = '#fff';

        const closeButton = document.createElement('button');
        closeButton.textContent = 'Close';
        closeButton.style.backgroundColor = '#f44336';
        closeButton.style.color = 'white';
        closeButton.style.border = 'none';
        closeButton.style.padding = '2px 5px';
        closeButton.style.cursor = 'pointer';
        closeButton.style.borderRadius = '3px';
        closeButton.onclick = function () {
            document.body.removeChild(debugContainer);
        };

        const clearButton = document.createElement('button');
        clearButton.textContent = 'Clear';
        clearButton.style.backgroundColor = '#2196F3';
        clearButton.style.color = 'white';
        clearButton.style.border = 'none';
        clearButton.style.padding = '2px 5px';
        clearButton.style.cursor = 'pointer';
        clearButton.style.borderRadius = '3px';
        clearButton.style.marginRight = '5px';
        clearButton.onclick = function () {
            debugOutput.innerHTML = '';
        };

        const buttonContainer = document.createElement('div');
        buttonContainer.appendChild(clearButton);
        buttonContainer.appendChild(closeButton);

        debugHeader.appendChild(debugTitle);
        debugHeader.appendChild(buttonContainer);

        const debugOutput = document.createElement('div');
        debugOutput.id = 'debug-output';
        debugOutput.style.maxHeight = '250px';
        debugOutput.style.overflow = 'auto';

        debugContainer.appendChild(debugHeader);
        debugContainer.appendChild(debugOutput);
        document.body.appendChild(debugContainer);
    }

    // Log message to debug output
    function logDebug(message, type = 'info') {
        createDebugOutput();
        const debugOutput = document.getElementById('debug-output');

        const logEntry = document.createElement('div');
        logEntry.style.marginBottom = '5px';
        logEntry.style.borderLeft = '3px solid';
        logEntry.style.paddingLeft = '5px';

        // Set color based on log type
        switch (type) {
            case 'error':
                logEntry.style.borderColor = '#f44336';
                break;
            case 'warning':
                logEntry.style.borderColor = '#ff9800';
                break;
            case 'success':
                logEntry.style.borderColor = '#4CAF50';
                break;
            default:
                logEntry.style.borderColor = '#2196F3';
        }

        const timestamp = new Date().toLocaleTimeString();

        // Format objects and arrays
        if (typeof message === 'object') {
            try {
                message = JSON.stringify(message, null, 2);
            } catch (e) {
                message = message.toString();
            }
        }

        logEntry.innerHTML = `<span style="color: #888;">[${timestamp}]</span> ${message}`;
        debugOutput.appendChild(logEntry);
        debugOutput.scrollTop = debugOutput.scrollHeight;
    }

    // Debug the authentication state
    function debugAuth() {
        logDebug('Starting authentication debug...', 'info');

        // Check if JWT token exists in localStorage
        const token = localStorage.getItem('jwt_token');
        if (token) {
            logDebug('JWT token found in localStorage', 'success');

            // Decode JWT token to check expiration
            try {
                const base64Url = token.split('.')[1];
                const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
                const jsonPayload = decodeURIComponent(atob(base64).split('').map(function (c) {
                    return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
                }).join(''));

                const payload = JSON.parse(jsonPayload);
                logDebug('JWT payload:', 'info');
                logDebug(payload, 'info');

                // Check token expiration
                const expirationTime = new Date(payload.exp * 1000);
                const now = new Date();

                if (expirationTime > now) {
                    const timeRemaining = Math.floor((expirationTime - now) / 1000 / 60);
                    logDebug(`Token is valid. Expires in ${timeRemaining} minutes.`, 'success');
                } else {
                    logDebug(`Token has expired at ${expirationTime.toLocaleString()}`, 'error');
                }
            } catch (e) {
                logDebug(`Error decoding JWT token: ${e.message}`, 'error');
            }
        } else {
            logDebug('No JWT token found in localStorage', 'error');
        }

        // Check if apiClient is initialized
        if (typeof apiClient !== 'undefined') {
            logDebug('apiClient is available', 'success');
            logDebug(`apiClient.isAuthenticated(): ${apiClient.isAuthenticated()}`, apiClient.isAuthenticated() ? 'success' : 'error');
        } else {
            logDebug('apiClient is not available', 'error');
        }

        // Test API connection
        logDebug('Testing API connection...', 'info');
        fetch('/api/status')
            .then(response => response.json())
            .then(data => {
                logDebug('API status endpoint response:', 'success');
                logDebug(data, 'info');
            })
            .catch(error => {
                logDebug(`API status endpoint error: ${error.message}`, 'error');
            });

        // Test server-side auth debug endpoint
        logDebug('Testing server-side auth debug endpoint...', 'info');
        fetch('/api/auth/debug', {
            headers: token ? { 'Authorization': `Bearer ${token}` } : {}
        })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Server returned ${response.status} ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                logDebug('Server auth debug info:', 'info');

                // Log token validity
                if (data.has_token) {
                    if (data.token_info.valid) {
                        logDebug('Token is valid according to server', 'success');

                        // Show expiration time
                        const expiresAt = new Date(data.token_info.expires_at);
                        const expiresIn = Math.floor(data.token_info.expires_in_seconds / 60);
                        logDebug(`Token expires at ${expiresAt.toLocaleString()} (in ${expiresIn} minutes)`, 'info');

                        // Show user info
                        if (Object.keys(data.user_info).length > 0) {
                            logDebug('User info:', 'info');
                            logDebug(data.user_info, 'info');
                        }
                    } else {
                        logDebug('Token is invalid according to server', 'error');
                        logDebug(`Error: ${data.token_info.error}`, 'error');
                        logDebug(`Error type: ${data.token_info.error_type}`, 'error');
                    }
                } else {
                    logDebug('No token provided to server', 'warning');
                }

                // Log JWT config
                logDebug('JWT Configuration:', 'info');
                logDebug(data.env_info.jwt_config, 'info');
            })
            .catch(error => {
                logDebug(`Server auth debug endpoint error: ${error.message}`, 'error');
                logDebug('Continuing with client-side debug only...', 'warning');
            });

        // Test check-auth endpoint
        logDebug('Testing check-auth endpoint...', 'info');
        fetch('/api/check-auth', {
            headers: token ? { 'Authorization': `Bearer ${token}` } : {}
        })
            .then(response => response.json())
            .then(data => {
                if (data.authenticated) {
                    logDebug('User is authenticated according to server', 'success');
                    logDebug(`User ID: ${data.user_id}`, 'info');
                    logDebug(`User Email: ${data.user_email}`, 'info');
                } else {
                    logDebug('User is NOT authenticated according to server', 'error');
                    logDebug(`Reason: ${data.message}`, 'error');
                }
            })
            .catch(error => {
                logDebug(`Check-auth endpoint error: ${error.message}`, 'error');
            });

        // Test protected endpoint
        if (token) {
            logDebug('Testing protected endpoint...', 'info');
            fetch('/api/user', {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            })
                .then(response => {
                    if (response.ok) {
                        return response.json().then(data => {
                            logDebug('Protected endpoint access successful:', 'success');
                            logDebug(data, 'info');
                        });
                    } else {
                        return response.json().then(data => {
                            logDebug('Protected endpoint access failed:', 'error');
                            logDebug(data, 'error');
                        }).catch(() => {
                            logDebug(`Protected endpoint access failed with status: ${response.status}`, 'error');
                        });
                    }
                })
                .catch(error => {
                    logDebug(`Protected endpoint error: ${error.message}`, 'error');
                });
        }
    }

    // Add debug button to the page
    function addDebugButton() {
        const button = document.createElement('button');
        button.textContent = 'Debug Auth';
        button.style.position = 'fixed';
        button.style.bottom = '10px';
        button.style.right = '10px';
        button.style.zIndex = '9998';
        button.style.backgroundColor = '#2196F3';
        button.style.color = 'white';
        button.style.border = 'none';
        button.style.padding = '5px 10px';
        button.style.borderRadius = '3px';
        button.style.cursor = 'pointer';
        button.onclick = debugAuth;

        document.body.appendChild(button);
    }

    // Initialize when DOM is loaded
    document.addEventListener('DOMContentLoaded', function () {
        addDebugButton();

        // Monkey patch fetch to log API calls
        const originalFetch = window.fetch;
        window.fetch = function (url, options) {
            // Only log API calls
            if (typeof url === 'string' && url.startsWith('/api')) {
                const method = options && options.method ? options.method : 'GET';
                logDebug(`API Call: ${method} ${url}`, 'info');

                if (options && options.headers) {
                    logDebug('Headers:', 'info');
                    logDebug(options.headers, 'info');
                }

                if (options && options.body) {
                    try {
                        const body = JSON.parse(options.body);
                        logDebug('Request Body:', 'info');
                        logDebug(body, 'info');
                    } catch (e) {
                        logDebug(`Request Body: ${options.body}`, 'info');
                    }
                }
            }

            return originalFetch.apply(this, arguments).then(response => {
                if (typeof url === 'string' && url.startsWith('/api')) {
                    logDebug(`Response Status: ${response.status} ${response.statusText}`, response.ok ? 'success' : 'error');
                }
                return response;
            }).catch(error => {
                if (typeof url === 'string' && url.startsWith('/api')) {
                    logDebug(`Fetch Error: ${error.message}`, 'error');
                }
                throw error;
            });
        };

        // Monkey patch apiClient methods
        if (typeof apiClient !== 'undefined') {
            const originalLogin = apiClient.login;
            apiClient.login = function (email, password) {
                logDebug(`apiClient.login called for email: ${email}`, 'info');
                return originalLogin.call(this, email, password)
                    .then(data => {
                        logDebug('Login successful', 'success');
                        logDebug(`Token stored: ${!!data.access_token}`, 'success');
                        return data;
                    })
                    .catch(error => {
                        logDebug(`Login failed: ${error.message}`, 'error');
                        throw error;
                    });
            };

            const originalSetToken = apiClient.setToken;
            apiClient.setToken = function (token) {
                logDebug(`apiClient.setToken called with token: ${token ? token.substring(0, 10) + '...' : 'null'}`, 'info');
                return originalSetToken.call(this, token);
            };
        }
    });

    // Run initial debug if on a page that needs authentication
    if (window.location.pathname.includes('/job-configs') ||
        window.location.pathname.includes('/resumes') ||
        window.location.pathname.includes('/dashboard')) {
        setTimeout(debugAuth, 1000);
    }
})();
