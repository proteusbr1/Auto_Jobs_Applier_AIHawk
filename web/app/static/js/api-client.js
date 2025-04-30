/**
 * AIHawk - API Client
 * Handles API requests with JWT authentication
 */

class ApiClient {
    constructor() {
        this.baseUrl = '/api';
        this.token = localStorage.getItem('jwt_token');
    }

    /**
     * Set the JWT token for authentication
     * @param {string} token - JWT token
     */
    setToken(token) {
        this.token = token;
        localStorage.setItem('jwt_token', token);
    }

    /**
     * Clear the JWT token
     */
    clearToken() {
        this.token = null;
        localStorage.removeItem('jwt_token');
    }

    /**
     * Check if the user is authenticated
     * @returns {boolean} - True if authenticated, false otherwise
     */
    isAuthenticated() {
        return !!this.token;
    }

    /**
     * Get the headers for API requests
     * @returns {Object} - Headers object
     */
    getHeaders() {
        const headers = {
            'Content-Type': 'application/json'
        };

        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        return headers;
    }

    /**
     * Handle API response
     * @param {Response} response - Fetch API response
     * @returns {Promise} - Promise that resolves to the response data
     */
    async handleResponse(response) {
        // Check if the response is a redirect
        if (response.redirected) {
            // Always follow redirects
            window.location.href = response.url;
            return {};
        }

        // Check if the response is JSON
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            const data = await response.json();

            if (!response.ok) {
                // Handle 401 Unauthorized - token expired or invalid
                if (response.status === 401) {
                    this.clearToken();
                    // Always redirect to login page if not already there
                    if (!window.location.pathname.includes('/login')) {
                        window.location.href = '/login';
                    }
                }

                throw new Error(data.error || 'API request failed');
            }

            return data;
        } else {
            // Not a JSON response
            if (!response.ok) {
                // Handle 401 Unauthorized - token expired or invalid
                if (response.status === 401) {
                    this.clearToken();
                    // Always redirect to login page if not already there
                    if (!window.location.pathname.includes('/login')) {
                        window.location.href = '/login';
                    }
                }

                throw new Error(`API request failed with status: ${response.status}`);
            }

            return {};
        }
    }

    /**
     * Login user and get JWT token
     * @param {string} email - User email
     * @param {string} password - User password
     * @returns {Promise} - Promise that resolves to the login response
     */
    async login(email, password) {
        const response = await fetch(`${this.baseUrl}/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ email, password })
        });

        const data = await this.handleResponse(response);

        if (data.access_token) {
            this.setToken(data.access_token);
        }

        return data;
    }

    /**
     * Logout user
     * @returns {Promise} - Promise that resolves to the logout response
     */
    async logout() {
        if (!this.isAuthenticated()) {
            return { message: 'Already logged out' };
        }

        try {
            const response = await fetch(`${this.baseUrl}/auth/logout`, {
                method: 'POST',
                headers: this.getHeaders()
            });

            const data = await this.handleResponse(response);
            this.clearToken();
            return data;
        } catch (error) {
            this.clearToken();
            throw error;
        }
    }

    /**
     * Register a new user
     * @param {Object} userData - User registration data
     * @returns {Promise} - Promise that resolves to the registration response
     */
    async register(userData) {
        const response = await fetch(`${this.baseUrl}/auth/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(userData)
        });

        return await this.handleResponse(response);
    }

    /**
     * Refresh the JWT token
     * @returns {Promise} - Promise that resolves to the refresh response
     */
    async refreshToken() {
        const refreshToken = localStorage.getItem('jwt_refresh_token');

        if (!refreshToken) {
            throw new Error('No refresh token available');
        }

        const response = await fetch(`${this.baseUrl}/auth/refresh`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${refreshToken}`
            }
        });

        const data = await this.handleResponse(response);

        if (data.access_token) {
            this.setToken(data.access_token);
        }

        return data;
    }

    /**
     * Get all job configurations
     * @returns {Promise} - Promise that resolves to the job configurations
     */
    async getJobConfigs() {
        const response = await fetch(`${this.baseUrl}/job-configs`, {
            method: 'GET',
            headers: this.getHeaders()
        });

        return await this.handleResponse(response);
    }

    /**
     * Get a specific job configuration
     * @param {number} configId - Job configuration ID
     * @returns {Promise} - Promise that resolves to the job configuration
     */
    async getJobConfig(configId) {
        const response = await fetch(`${this.baseUrl}/job-configs/${configId}`, {
            method: 'GET',
            headers: this.getHeaders()
        });

        return await this.handleResponse(response);
    }

    /**
     * Create a new job configuration
     * @param {Object} configData - Job configuration data
     * @returns {Promise} - Promise that resolves to the created job configuration
     */
    async createJobConfig(configData) {
        const response = await fetch(`${this.baseUrl}/job-configs`, {
            method: 'POST',
            headers: this.getHeaders(),
            body: JSON.stringify(configData)
        });

        return await this.handleResponse(response);
    }

    /**
     * Update a job configuration
     * @param {number} configId - Job configuration ID
     * @param {Object} configData - Job configuration data
     * @returns {Promise} - Promise that resolves to the updated job configuration
     */
    async updateJobConfig(configId, configData) {
        const response = await fetch(`${this.baseUrl}/job-configs/${configId}`, {
            method: 'PUT',
            headers: this.getHeaders(),
            body: JSON.stringify(configData)
        });

        return await this.handleResponse(response);
    }

    /**
     * Delete a job configuration
     * @param {number} configId - Job configuration ID
     * @returns {Promise} - Promise that resolves to the delete response
     */
    async deleteJobConfig(configId) {
        const response = await fetch(`${this.baseUrl}/job-configs/${configId}`, {
            method: 'DELETE',
            headers: this.getHeaders()
        });

        return await this.handleResponse(response);
    }

    /**
     * Set a job configuration as the default
     * @param {number} configId - Job configuration ID
     * @returns {Promise} - Promise that resolves to the response
     */
    async setDefaultJobConfig(configId) {
        const response = await fetch(`${this.baseUrl}/job-configs/${configId}/set-default`, {
            method: 'POST',
            headers: this.getHeaders()
        });

        return await this.handleResponse(response);
    }

    /**
     * Get a job task status
     * @param {string} taskId - Task ID
     * @returns {Promise} - Promise that resolves to the task status
     */
    async getJobTask(taskId) {
        const response = await fetch(`${this.baseUrl}/job-tasks/${taskId}`, {
            method: 'GET',
            headers: this.getHeaders()
        });

        return await this.handleResponse(response);
    }
}

// Create a global instance of the API client
const apiClient = new ApiClient();

// Initialize the API client with the JWT token from localStorage
document.addEventListener('DOMContentLoaded', function () {
    // Check if there's a JWT token in the URL (for OAuth callbacks)
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token');

    if (token) {
        // Store the token and remove it from the URL
        apiClient.setToken(token);

        // Remove the token from the URL
        const newUrl = window.location.pathname +
            (urlParams.toString() ? '?' + urlParams.toString() : '') +
            window.location.hash;

        window.history.replaceState({}, document.title, newUrl);
    }

    // Log authentication status for debugging
    console.log('API Client initialized. Authenticated:', apiClient.isAuthenticated());
});
