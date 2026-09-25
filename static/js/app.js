// Global Socket.IO Connection
let socket = null;

function initSocketIO() {
    if (typeof io !== 'undefined') {
        try {
            socket = io({
                transports: ['websocket', 'polling'],
                reconnection: true,
                reconnectionAttempts: 5,
                reconnectionDelay: 5000,
                reconnectionDelayMax: 15000,
                timeout: 10000
            });
            
            socket.on('connect', function() {
                console.log('Socket.IO connected');
            });

            socket.on('connect_error', function(err) {
                console.warn('Socket.IO connection warning:', err.message);
            });
        
        socket.on('notification', function(data) {
            // Show notification toast
            showNotification(data.title, data.message, data.type);
        });
        
        socket.on('order_update', function(data) {
            // Refresh order sections
            if (document.querySelector('[data-order-row-id="' + data.order_id + '"]')) {
                // Update the order status without full refresh
                console.log('Order updated:', data.order_number, data.status);
            }
        });
        
        socket.on('commission_update', function(data) {
            showNotification('Commission Update', 
                `Commission status changed to: ${data.status}`, 'alert');
        });
        
        socket.on('analytics_update', function(data) {
            // Refresh charts if on analytics page
            if (document.getElementById('analytics-sales-chart')) {
                fetchWeeklySalesData();
            }
        });
        
        socket.on('settings_update', function(data) {
            showNotification('Settings Updated', 
                'Global settings have been changed by admin.', 'info');
        });
        
        socket.on('force_logout', function(data) {
            // Session has been terminated by main admin (blocked/deleted)
            showNotification('Session Terminated', data.reason || 'Your session has been terminated by the Main Admin.', 'alert');
            // Redirect to logout after a short delay
            setTimeout(function() {
                window.location.href = '/logout';
            }, 2000);
        });
        
        socket.on('disconnect', function() {
            console.log('Socket.IO disconnected');
        });
        } catch (err) {
            console.warn('Socket.IO initialization skipped:', err);
        }
    }
}

function showNotification(title, message, type) {
    // Disabled globally per user request
    return;
}

// Rest of existing app.js code...
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Socket.IO
    initSocketIO();
    
    // Theme toggle
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', function() {
            const html = document.documentElement;
            const currentTheme = html.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            this.querySelector('i').className = newTheme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
        });
        
        // Restore theme
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
        themeToggle.querySelector('i').className = savedTheme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
    }
    
    // Auto-hide flash messages after 5 seconds
    document.querySelectorAll('.alert').forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.5s';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 500);
        }, 5000);
    });
});

function fetchWeeklySalesData() {
    if (!document.getElementById('analytics-sales-chart')) return;
    
    const weekOffset = new URLSearchParams(window.location.search).get('week_offset') || 0;
    
    fetch(`/seller/analytics/api/weekly-sales?week_offset=${weekOffset}`)
        .then(r => r.json())
        .then(data => {
            if (window.CanvasCharts) {
                CanvasCharts.drawBarChart('analytics-sales-chart', data.labels, data.data, 'Weekly Store Sales (INR)');
            }
            // Update total
            const totalEl = document.getElementById('total-weekly-sales');
            if (totalEl) totalEl.textContent = 'INR ' + data.total.toFixed(2);
        })
        .catch(err => console.error('Failed to fetch weekly sales:', err));
}

// Add keyframe animation for notifications
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
`;
document.head.appendChild(style);

// Global Modal Functions
function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
        modal.classList.add('open');
        if (modal.style.display === 'none') {
            modal.style.display = 'flex';
        }
    }
}

function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
        modal.classList.remove('open');
        if (modal.style.display === 'flex' || modal.style.display === 'block') {
            modal.style.display = 'none';
        }
    }
}

// Close modals when clicking on the overlay background
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal-overlay')) {
        const modalId = e.target.id;
        if (modalId === 'edit-sub-admin-modal') {
            if (typeof closeEditSubAdminModal === 'function') {
                closeEditSubAdminModal();
                return;
            }
        } else if (modalId === 'reset-password-modal') {
            if (typeof closeResetPasswordModal === 'function') {
                closeResetPasswordModal();
                return;
            }
        } else if (modalId === 'reject-commission-modal') {
            if (typeof closeRejectCommissionModal === 'function') {
                closeRejectCommissionModal();
                return;
            }
        } else if (modalId === 'seller-info-modal') {
            if (typeof closeSellerModal === 'function') {
                closeSellerModal();
                return;
            }
        }
        closeModal(modalId);
    }
});

// Copy to clipboard helper with fallback for non-HTTPS environments
function copyToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
        return navigator.clipboard.writeText(text);
    } else {
        return new Promise((resolve, reject) => {
            try {
                const textArea = document.createElement('textarea');
                textArea.value = text;
                textArea.style.position = 'fixed';
                textArea.style.left = '-999999px';
                textArea.style.top = '-999999px';
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();
                const successful = document.execCommand('copy');
                document.body.removeChild(textArea);
                if (successful) {
                    resolve();
                } else {
                    reject(new Error('execCommand copy failed'));
                }
            } catch (err) {
                reject(err);
            }
        });
    }
}

// Global Product Share Function
function shareProduct(event, name, url) {
    if (event && typeof event.preventDefault === 'function') {
        event.preventDefault();
        event.stopPropagation();
    }
    const target = event ? (event.currentTarget || event.target) : null;
    const btn = target ? (target.closest ? target.closest('[data-share-title], button, a') : target) : null;

    const shareTitle = (typeof name === 'string' && name) ? name : (btn ? btn.getAttribute('data-share-title') : null) || document.title || 'Product';
    let rawUrl = (typeof url === 'string' && url) ? url : (btn ? btn.getAttribute('data-share-url') : null) || window.location.href;

    // Dynamically resolve URL relative to current browser domain (Cloudflare Tunnel / custom domain)
    let shareUrl = window.location.href;
    try {
        if (rawUrl) {
            let path = rawUrl;
            if (rawUrl.startsWith('http://') || rawUrl.startsWith('https://')) {
                const tempUrl = new URL(rawUrl);
                path = tempUrl.pathname + tempUrl.search + tempUrl.hash;
            }
            shareUrl = new URL(path, window.location.origin).href;
        }
    } catch (e) {
        shareUrl = window.location.href;
    }

    // Always prioritize copying to clipboard directly for a consistent user experience
    copyToClipboard(shareUrl).then(() => {
        showNotification('Link Copied', 'Product link copied to clipboard!', 'success');
    }).catch(() => {
        // Fallback to navigator.share if clipboard fails
        if (navigator.share) {
            navigator.share({
                title: shareTitle,
                text: shareTitle,
                url: shareUrl
            }).catch(() => {
                prompt('Copy product link:', shareUrl);
            });
        } else {
            prompt('Copy product link:', shareUrl);
        }
    });
}

// Global Wishlist Toggle Function
function toggleWishlist(productId) {
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';
    
    fetch(`/api/wishlist/toggle/${productId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        }
    })
    .then(response => {
        if (response.status === 401) {
            // User not authenticated, redirect to login page
            window.location.href = '/login';
            return;
        }
        return response.json();
    })
    .then(data => {
        if (data && data.success) {
            // Find all wishlist buttons for this product ID and update their heart icons
            const buttons = document.querySelectorAll(`button[onclick^="toggleWishlist(${productId})"], button[onclick*="toggleWishlist(${productId})"]`);
            buttons.forEach(btn => {
                const icon = btn.querySelector('i');
                if (icon) {
                    if (data.action === 'added') {
                        icon.className = 'fa-solid fa-heart';
                        icon.style.color = 'var(--danger)';
                    } else {
                        icon.className = 'fa-regular fa-heart';
                        icon.style.color = '';
                    }
                }
            });
            showNotification('Wishlist', data.message, 'success');
        } else if (data && data.message) {
            showNotification('Error', data.message, 'alert');
        }
    })
    .catch(err => {
        console.error('Error toggling wishlist:', err);
    });
}