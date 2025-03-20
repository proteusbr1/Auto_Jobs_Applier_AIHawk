/**
 * AIHawk - LinkedIn Job Application Automation
 * Main JavaScript File
 */

document.addEventListener('DOMContentLoaded', function () {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Flash message auto-dismiss
    const flashMessages = document.querySelectorAll('.alert-dismissible');
    flashMessages.forEach(function (message) {
        setTimeout(function () {
            const closeButton = message.querySelector('.btn-close');
            if (closeButton) {
                closeButton.click();
            }
        }, 5000); // Auto-dismiss after 5 seconds
    });

    // Form validation
    const forms = document.querySelectorAll('.needs-validation');
    Array.from(forms).forEach(function (form) {
        form.addEventListener('submit', function (event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        }, false);
    });

    // Loading spinner
    setupLoadingSpinner();

    // Task status polling
    setupTaskPolling();

    // Resume file upload preview
    setupResumeUpload();

    // Job config form
    setupJobConfigForm();
});

/**
 * Setup loading spinner for form submissions and AJAX requests
 */
function setupLoadingSpinner() {
    // Create spinner element
    const spinnerHtml = `
        <div class="spinner-overlay" id="loadingSpinner" style="display: none;">
            <div class="spinner-border text-primary" role="status" style="width: 3rem; height: 3rem;">
                <span class="visually-hidden">Loading...</span>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', spinnerHtml);

    // Show spinner on form submission
    const forms = document.querySelectorAll('form:not(.no-spinner)');
    forms.forEach(form => {
        form.addEventListener('submit', function () {
            if (this.checkValidity()) {
                document.getElementById('loadingSpinner').style.display = 'flex';
            }
        });
    });

    // Show spinner on AJAX requests
    // Check if fetch was already wrapped by debug tools
    const debugFetch = window.fetch;
    window.fetch = function () {
        document.getElementById('loadingSpinner').style.display = 'flex';
        return debugFetch.apply(this, arguments)
            .finally(() => {
                document.getElementById('loadingSpinner').style.display = 'none';
            });
    };
}

/**
 * Setup polling for task status updates
 */
function setupTaskPolling() {
    const taskStatusElements = document.querySelectorAll('[data-task-id]');

    if (taskStatusElements.length === 0) {
        return;
    }

    // Poll for task status updates
    const pollTasks = () => {
        taskStatusElements.forEach(element => {
            const taskId = element.getAttribute('data-task-id');

            apiClient.getJobTask(taskId)
                .then(data => {
                    // Update status
                    const statusElement = element.querySelector('.task-status');
                    if (statusElement) {
                        statusElement.textContent = data.status;

                        // Update status class
                        statusElement.className = 'task-status badge';
                        if (data.status === 'SUCCESS') {
                            statusElement.classList.add('bg-success');
                        } else if (data.status === 'FAILURE') {
                            statusElement.classList.add('bg-danger');
                        } else if (data.status === 'REVOKED') {
                            statusElement.classList.add('bg-warning');
                        } else {
                            statusElement.classList.add('bg-info');
                        }
                    }

                    // If task is complete, stop polling and update UI
                    if (['SUCCESS', 'FAILURE', 'REVOKED'].includes(data.status)) {
                        // Update result
                        const resultElement = element.querySelector('.task-result');
                        if (resultElement && data.result) {
                            resultElement.textContent = data.result.message || JSON.stringify(data.result);
                        }

                        // Show/hide action buttons
                        const actionButtons = element.querySelectorAll('.task-action');
                        actionButtons.forEach(button => {
                            if (button.classList.contains('task-view-result')) {
                                button.style.display = data.status === 'SUCCESS' ? 'inline-block' : 'none';
                            } else if (button.classList.contains('task-cancel')) {
                                button.style.display = 'none';
                            }
                        });

                        // Remove from polling
                        element.removeAttribute('data-task-id');
                    }
                })
                .catch(error => {
                    console.error('Error polling task status:', error);
                });
        });

        // Continue polling if there are still tasks to poll
        if (document.querySelectorAll('[data-task-id]').length > 0) {
            setTimeout(pollTasks, 5000); // Poll every 5 seconds
        }
    };

    // Start polling
    pollTasks();
}

/**
 * Setup resume file upload preview
 */
function setupResumeUpload() {
    const resumeFileInput = document.getElementById('resumeFile');
    const resumePreview = document.getElementById('resumePreview');

    if (!resumeFileInput || !resumePreview) {
        return;
    }

    resumeFileInput.addEventListener('change', function () {
        const file = this.files[0];
        if (!file) {
            return;
        }

        // Check file type
        const fileType = file.type;
        if (fileType !== 'application/pdf' &&
            fileType !== 'application/msword' &&
            fileType !== 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') {
            alert('Please upload a PDF or Word document.');
            this.value = '';
            return;
        }

        // Check file size (max 5MB)
        if (file.size > 5 * 1024 * 1024) {
            alert('File size should not exceed 5MB.');
            this.value = '';
            return;
        }

        // Update preview
        if (fileType === 'application/pdf') {
            // PDF preview
            const objectElement = document.createElement('object');
            objectElement.data = URL.createObjectURL(file);
            objectElement.type = 'application/pdf';
            objectElement.width = '100%';
            objectElement.height = '100%';

            resumePreview.innerHTML = '';
            resumePreview.appendChild(objectElement);
        } else {
            // Word document preview (just show icon)
            resumePreview.innerHTML = `
                <div class="text-center py-5">
                    <i class="fas fa-file-word text-primary fa-5x mb-3"></i>
                    <p>${file.name}</p>
                </div>
            `;
        }
    });
}

/**
 * Setup job configuration form
 */
function setupJobConfigForm() {
    const jobConfigForm = document.getElementById('jobConfigForm');

    if (!jobConfigForm) {
        return;
    }

    // Add search criteria
    const addSearchButton = document.getElementById('addSearchCriteria');
    const searchCriteriaContainer = document.getElementById('searchCriteriaContainer');
    const searchCriteriaTemplate = document.getElementById('searchCriteriaTemplate');

    if (addSearchButton && searchCriteriaContainer && searchCriteriaTemplate) {
        addSearchButton.addEventListener('click', function () {
            const index = document.querySelectorAll('.search-criteria-item').length;
            const newItem = searchCriteriaTemplate.content.cloneNode(true);

            // Update IDs and names
            const inputs = newItem.querySelectorAll('input, select');
            inputs.forEach(input => {
                const name = input.getAttribute('name');
                if (name) {
                    input.setAttribute('name', name.replace('INDEX', index));
                }

                const id = input.getAttribute('id');
                if (id) {
                    input.setAttribute('id', id.replace('INDEX', index));
                }
            });

            // Update labels
            const labels = newItem.querySelectorAll('label');
            labels.forEach(label => {
                const forAttr = label.getAttribute('for');
                if (forAttr) {
                    label.setAttribute('for', forAttr.replace('INDEX', index));
                }
            });

            // Add remove button functionality
            const removeButton = newItem.querySelector('.remove-search-criteria');
            if (removeButton) {
                removeButton.addEventListener('click', function () {
                    this.closest('.search-criteria-item').remove();
                });
            }

            // Add to container
            searchCriteriaContainer.appendChild(newItem);
        });
    }

    // Add keyword
    const addKeywordButton = document.getElementById('addKeyword');
    const keywordsContainer = document.getElementById('keywordsContainer');

    if (addKeywordButton && keywordsContainer) {
        addKeywordButton.addEventListener('click', function () {
            const keywordInput = document.getElementById('newKeyword');
            const keyword = keywordInput.value.trim();

            if (keyword) {
                const keywordBadge = document.createElement('span');
                keywordBadge.className = 'badge bg-primary me-2 mb-2';
                keywordBadge.innerHTML = `
                    ${keyword}
                    <input type="hidden" name="keywords[]" value="${keyword}">
                    <button type="button" class="btn-close btn-close-white ms-2" aria-label="Remove"></button>
                `;

                const removeButton = keywordBadge.querySelector('.btn-close');
                removeButton.addEventListener('click', function () {
                    keywordBadge.remove();
                });

                keywordsContainer.appendChild(keywordBadge);
                keywordInput.value = '';
            }
        });
    }

    // Add blacklist keyword
    const addBlacklistButton = document.getElementById('addBlacklistKeyword');
    const blacklistContainer = document.getElementById('blacklistContainer');

    if (addBlacklistButton && blacklistContainer) {
        addBlacklistButton.addEventListener('click', function () {
            const blacklistInput = document.getElementById('newBlacklistKeyword');
            const keyword = blacklistInput.value.trim();

            if (keyword) {
                const keywordBadge = document.createElement('span');
                keywordBadge.className = 'badge bg-danger me-2 mb-2';
                keywordBadge.innerHTML = `
                    ${keyword}
                    <input type="hidden" name="blacklist[]" value="${keyword}">
                    <button type="button" class="btn-close btn-close-white ms-2" aria-label="Remove"></button>
                `;

                const removeButton = keywordBadge.querySelector('.btn-close');
                removeButton.addEventListener('click', function () {
                    keywordBadge.remove();
                });

                blacklistContainer.appendChild(keywordBadge);
                blacklistInput.value = '';
            }
        });
    }
}
