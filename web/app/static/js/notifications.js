/**
 * Notifications JavaScript for AIHawk application.
 * Handles real-time notification updates and UI interactions.
 */

class NotificationManager {
    constructor(options = {}) {
        // Configuration
        this.options = {
            countSelector: '#notification-count',
            dropdownSelector: '#notification-dropdown',
            dropdownContentSelector: '#notification-dropdown-content',
            bellIconSelector: '#notification-bell',
            pollingInterval: 30000, // 30 seconds
            maxNotifications: 5,
            ...options
        };

        // Elements
        this.countElement = document.querySelector(this.options.countSelector);
        this.dropdownElement = document.querySelector(this.options.dropdownSelector);
        this.dropdownContentElement = document.querySelector(this.options.dropdownContentSelector);
        this.bellIconElement = document.querySelector(this.options.bellIconSelector);

        // State
        this.isPolling = false;
        this.pollingTimer = null;
        this.lastCount = 0;

        // Initialize
        this.init();
    }

    /**
     * Initialize the notification manager.
     */
    init() {
        // Initial fetch
        this.fetchNotificationCount();
        this.fetchRecentNotifications();

        // Set up polling
        this.startPolling();

        // Set up event listeners
        this.setupEventListeners();
    }

    /**
     * Set up event listeners for notification interactions.
     */
    setupEventListeners() {
        // Toggle dropdown when bell icon is clicked
        if (this.bellIconElement) {
            this.bellIconElement.addEventListener('click', (e) => {
                e.preventDefault();
                this.toggleDropdown();
            });
        }

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (this.dropdownElement &&
                !this.dropdownElement.contains(e.target) &&
                !this.bellIconElement.contains(e.target)) {
                this.closeDropdown();
            }
        });

        // Handle mark as read actions in dropdown
        if (this.dropdownContentElement) {
            this.dropdownContentElement.addEventListener('click', (e) => {
                const markReadBtn = e.target.closest('.notification-mark-read');
                if (markReadBtn) {
                    e.preventDefault();
                    const notificationId = markReadBtn.dataset.id;
                    this.markAsRead(notificationId);
                }
            });
        }
    }

    /**
     * Start polling for new notifications.
     */
    startPolling() {
        if (this.isPolling) return;

        this.isPolling = true;
        this.pollingTimer = setInterval(() => {
            this.fetchNotificationCount();

            // Only fetch recent notifications if the dropdown is open
            if (this.dropdownElement && this.dropdownElement.classList.contains('show')) {
                this.fetchRecentNotifications();
            }
        }, this.options.pollingInterval);
    }

    /**
     * Stop polling for new notifications.
     */
    stopPolling() {
        if (!this.isPolling) return;

        this.isPolling = false;
        clearInterval(this.pollingTimer);
        this.pollingTimer = null;
    }

    /**
     * Fetch the count of unread notifications.
     */
    fetchNotificationCount() {
        fetch('/notifications/api/count')
            .then(response => response.json())
            .then(data => {
                this.updateNotificationCount(data.count);
            })
            .catch(error => {
                console.error('Error fetching notification count:', error);
            });
    }

    /**
     * Fetch recent unread notifications.
     */
    fetchRecentNotifications() {
        fetch(`/notifications/api/recent?limit=${this.options.maxNotifications}`)
            .then(response => response.json())
            .then(data => {
                this.updateNotificationDropdown(data.notifications);
            })
            .catch(error => {
                console.error('Error fetching recent notifications:', error);
            });
    }

    /**
     * Update the notification count in the UI.
     * @param {number} count - The number of unread notifications.
     */
    updateNotificationCount(count) {
        if (!this.countElement) return;

        // Update the count
        this.countElement.textContent = count;

        // Show/hide the count badge
        if (count > 0) {
            this.countElement.classList.remove('d-none');

            // Add animation if count increased
            if (count > this.lastCount) {
                this.bellIconElement.classList.add('notification-pulse');
                setTimeout(() => {
                    this.bellIconElement.classList.remove('notification-pulse');
                }, 1000);
            }
        } else {
            this.countElement.classList.add('d-none');
        }

        this.lastCount = count;
    }

    /**
     * Update the notification dropdown with recent notifications.
     * @param {Array} notifications - Array of notification objects.
     */
    updateNotificationDropdown(notifications) {
        if (!this.dropdownContentElement) return;

        if (notifications.length === 0) {
            this.dropdownContentElement.innerHTML = `
                <div class="text-center p-3">
                    <p class="text-muted mb-0">No new notifications</p>
                </div>
            `;
            return;
        }

        let html = '';

        notifications.forEach(notification => {
            let iconClass = 'bi-info-circle text-info';

            if (notification.category === 'success') {
                iconClass = 'bi-check-circle text-success';
            } else if (notification.category === 'warning') {
                iconClass = 'bi-exclamation-triangle text-warning';
            } else if (notification.category === 'error') {
                iconClass = 'bi-x-circle text-danger';
            }

            const date = new Date(notification.created_at);
            const formattedDate = date.toLocaleString();

            html += `
                <div class="dropdown-item notification-item">
                    <div class="d-flex align-items-center">
                        <div class="flex-shrink-0">
                            <i class="bi ${iconClass} fs-4"></i>
                        </div>
                        <div class="flex-grow-1 ms-3">
                            <h6 class="mb-0">${notification.title}</h6>
                            <p class="mb-1 small">${notification.message}</p>
                            <div class="d-flex justify-content-between align-items-center">
                                <small class="text-muted">${formattedDate}</small>
                                <button class="btn btn-sm btn-link p-0 notification-mark-read" data-id="${notification.id}">
                                    Mark as read
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="dropdown-divider"></div>
            `;
        });

        // Add view all link
        html += `
            <a class="dropdown-item text-center" href="/notifications">
                View all notifications
            </a>
        `;

        this.dropdownContentElement.innerHTML = html;
    }

    /**
     * Toggle the notification dropdown.
     */
    toggleDropdown() {
        if (!this.dropdownElement) return;

        if (this.dropdownElement.classList.contains('show')) {
            this.closeDropdown();
        } else {
            this.openDropdown();
        }
    }

    /**
     * Open the notification dropdown.
     */
    openDropdown() {
        if (!this.dropdownElement) return;

        this.dropdownElement.classList.add('show');
        this.fetchRecentNotifications();
    }

    /**
     * Close the notification dropdown.
     */
    closeDropdown() {
        if (!this.dropdownElement) return;

        this.dropdownElement.classList.remove('show');
    }

    /**
     * Mark a notification as read.
     * @param {string} notificationId - The ID of the notification to mark as read.
     */
    markAsRead(notificationId) {
        fetch(`/notifications/mark-read/${notificationId}`, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Refresh notifications
                    this.fetchNotificationCount();
                    this.fetchRecentNotifications();
                }
            })
            .catch(error => {
                console.error('Error marking notification as read:', error);
            });
    }
}

// Initialize when the DOM is ready
document.addEventListener('DOMContentLoaded', function () {
    // Initialize the notification manager
    window.notificationManager = new NotificationManager();
});
