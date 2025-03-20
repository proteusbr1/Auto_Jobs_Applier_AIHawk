/**
 * Test script for API authentication
 */

document.addEventListener('DOMContentLoaded', function () {
    // Create a test button
    const testButton = document.createElement('button');
    testButton.textContent = 'Test API Authentication';
    testButton.className = 'btn btn-sm btn-info position-fixed';
    testButton.style.bottom = '20px';
    testButton.style.right = '20px';
    testButton.style.zIndex = '1000';

    // Create a result container
    const resultContainer = document.createElement('div');
    resultContainer.className = 'position-fixed bg-light p-3 border rounded';
    resultContainer.style.bottom = '70px';
    resultContainer.style.right = '20px';
    resultContainer.style.zIndex = '1000';
    resultContainer.style.maxWidth = '400px';
    resultContainer.style.maxHeight = '300px';
    resultContainer.style.overflow = 'auto';
    resultContainer.style.display = 'none';

    // Add elements to the body
    document.body.appendChild(testButton);
    document.body.appendChild(resultContainer);

    // Add click event to the test button
    testButton.addEventListener('click', function () {
        // Show the result container
        resultContainer.style.display = 'block';
        resultContainer.innerHTML = '<p>Testing API authentication...</p>';

        // Check if the API client is authenticated
        const isAuthenticated = apiClient.isAuthenticated();
        resultContainer.innerHTML += `<p>API Client authenticated: ${isAuthenticated}</p>`;

        if (isAuthenticated) {
            resultContainer.innerHTML += `<p>JWT Token: ${apiClient.token.substring(0, 20)}...</p>`;
        } else {
            resultContainer.innerHTML += `<p>No JWT token found</p>`;
        }

        // Try to get job configurations
        fetch('/api/job-configs', {
            method: 'GET',
            headers: apiClient.getHeaders()
        })
            .then(response => {
                resultContainer.innerHTML += `<p>Response status: ${response.status} ${response.statusText}</p>`;
                return response.json().catch(() => ({}));
            })
            .then(data => {
                if (data.error) {
                    resultContainer.innerHTML += `<p>Error: ${data.error}</p>`;
                } else if (data.job_configs) {
                    resultContainer.innerHTML += `<p>Success! Found ${data.job_configs.length} job configurations</p>`;
                    resultContainer.innerHTML += `<pre>${JSON.stringify(data, null, 2).substring(0, 200)}...</pre>`;
                } else {
                    resultContainer.innerHTML += `<p>Unexpected response: ${JSON.stringify(data)}</p>`;
                }
            })
            .catch(error => {
                resultContainer.innerHTML += `<p>Fetch error: ${error.message}</p>`;
            });

        // Add a close button
        const closeButton = document.createElement('button');
        closeButton.textContent = 'Close';
        closeButton.className = 'btn btn-sm btn-secondary mt-2';
        closeButton.addEventListener('click', function () {
            resultContainer.style.display = 'none';
        });
        resultContainer.appendChild(closeButton);
    });
});
