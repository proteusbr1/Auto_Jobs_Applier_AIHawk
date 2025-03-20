document.addEventListener('DOMContentLoaded', function () {
    // Check if the charts container exists
    if (document.getElementById('userGrowthChart')) {
        // User Growth Chart
        const userGrowthCtx = document.getElementById('userGrowthChart').getContext('2d');
        const userGrowthChart = new Chart(userGrowthCtx, {
            type: 'line',
            data: {
                labels: userGrowthDates,
                datasets: [{
                    label: 'New Users',
                    data: userGrowthCounts,
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    borderColor: 'rgba(75, 192, 192, 1)',
                    borderWidth: 2,
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            precision: 0
                        }
                    }
                }
            }
        });

        // Subscription Growth Chart
        const subscriptionGrowthCtx = document.getElementById('subscriptionGrowthChart').getContext('2d');
        const subscriptionGrowthChart = new Chart(subscriptionGrowthCtx, {
            type: 'line',
            data: {
                labels: subscriptionGrowthDates,
                datasets: [{
                    label: 'New Subscriptions',
                    data: subscriptionGrowthCounts,
                    backgroundColor: 'rgba(54, 162, 235, 0.2)',
                    borderColor: 'rgba(54, 162, 235, 1)',
                    borderWidth: 2,
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            precision: 0
                        }
                    }
                }
            }
        });

        // Application Growth Chart
        const applicationGrowthCtx = document.getElementById('applicationGrowthChart').getContext('2d');
        const applicationGrowthChart = new Chart(applicationGrowthCtx, {
            type: 'line',
            data: {
                labels: applicationGrowthDates,
                datasets: [{
                    label: 'Applications',
                    data: applicationGrowthCounts,
                    backgroundColor: 'rgba(255, 159, 64, 0.2)',
                    borderColor: 'rgba(255, 159, 64, 1)',
                    borderWidth: 2,
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            precision: 0
                        }
                    }
                }
            }
        });
    }
});
