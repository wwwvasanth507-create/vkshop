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
        
        socket.on('new_product_notification', function(data) {
            // Show red color dot badge on notification bell
            showRedDotBadge();
            // Show toast notification
            showNotification(data.title || 'New Product Added', data.message, 'info');
            // Trigger native browser push notification
            triggerNativePushNotification(data.title || 'New Product Added', data.message);
        });

        socket.on('notification', function(data) {
            showRedDotBadge();
            showNotification(data.title, data.message, data.type);
            triggerNativePushNotification(data.title, data.message);
        });
        
        socket.on('order_update', function(data) {
            showRedDotBadge();
            showNotification('Order Status Update', `Order ${data.order_number} is now ${data.status}`, 'info');
            triggerNativePushNotification('Order Update', `Order ${data.order_number} is now ${data.status}`);
            if (document.querySelector('[data-order-row-id="' + data.order_id + '"]')) {
                console.log('Order updated:', data.order_number, data.status);
            }
        });
        
        socket.on('commission_update', function(data) {
            showRedDotBadge();
            showNotification('Commission Update', `Commission status changed to: ${data.status}`, 'alert');
            triggerNativePushNotification('Commission Update', `Commission status changed to: ${data.status}`);
        });
        
        socket.on('analytics_update', function(data) {
            if (document.getElementById('analytics-sales-chart')) {
                fetchWeeklySalesData();
            }
        });
        
        socket.on('settings_update', function(data) {
            showNotification('Settings Updated', 'Global settings have been changed by admin.', 'info');
        });
        
        socket.on('force_logout', function(data) {
            showNotification('Session Terminated', data.reason || 'Your session has been terminated by the Main Admin.', 'alert');
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

// Show Red Color Dot Badge on Notification Bell
function showRedDotBadge() {
    const redDot = document.getElementById('notif-red-dot');
    if (redDot) {
        redDot.style.display = 'block';
    }
}

// Hide Red Color Dot Badge
function hideRedDotBadge() {
    const redDot = document.getElementById('notif-red-dot');
    if (redDot) {
        redDot.style.display = 'none';
    }
}

// Fetch unread status on page load
function checkUnreadNotifications() {
    const redDot = document.getElementById('notif-red-dot');
    if (!redDot) return;

    fetch('/api/notifications/unread-count')
        .then(r => r.json())
        .then(data => {
            if (data.has_unread) {
                showRedDotBadge();
            } else {
                hideRedDotBadge();
            }
        })
        .catch(err => console.debug('Unread count check skipped:', err));
}

// Native Browser Push Notification Trigger
function triggerNativePushNotification(title, message) {
    if (!("Notification" in window)) return;
    
    if (Notification.permission === "granted") {
        try {
            new Notification(title, {
                body: message,
                icon: '/static/logo.jpeg'
            });
        } catch (e) {
            console.debug('Web push trigger error:', e);
        }
    } else if (Notification.permission !== "denied") {
        Notification.requestPermission().then(permission => {
            if (permission === "granted") {
                try {
                    new Notification(title, {
                        body: message,
                        icon: '/static/logo.jpeg'
                    });
                } catch (e) {}
            }
        });
    }
}

// Render Toast Notification
function showNotification(title, message, type) {
    let container = document.getElementById('toast-notification-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-notification-container';
        container.style.cssText = 'position: fixed; bottom: 20px; right: 20px; z-index: 99999; display: flex; flex-direction: column; gap: 10px; max-width: 360px; width: 100%; pointer-events: none;';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.style.cssText = 'background: rgba(15, 23, 42, 0.92); color: #ffffff; padding: 14px 18px; border-radius: 12px; backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.15); box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3); font-family: sans-serif; pointer-events: auto; opacity: 0; transform: translateY(20px); transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1); border-left: 4px solid ' + (type === 'alert' ? '#ef4444' : (type === 'product' ? '#3b82f6' : '#10b981')) + ';';

    toast.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;">
            <div style="font-weight: 700; font-size: 0.95rem; color: #60a5fa;">${title}</div>
            <button onclick="this.parentElement.parentElement.remove()" style="background: none; border: none; color: #94a3b8; cursor: pointer; font-size: 1rem; padding: 0;">&times;</button>
        </div>
        <div style="font-size: 0.85rem; color: #e2e8f0; margin-top: 4px; line-height: 1.4;">${message}</div>
    `;

    container.appendChild(toast);

    requestAnimationFrame(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateY(0)';
    });

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        setTimeout(() => toast.remove(), 300);
    }, 6000);
}

// Rest of existing app.js code...
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Socket.IO
    initSocketIO();
    
    // Check unread notifications and request push permission
    checkUnreadNotifications();
    if ("Notification" in window && Notification.permission === "default") {
        Notification.requestPermission();
    }

    // Add click handler to notification bell to mark read
    const notifBell = document.getElementById('nav-notif-bell');
    if (notifBell) {
        notifBell.addEventListener('click', function() {
            hideRedDotBadge();
            fetch('/api/notifications/mark-read', { method: 'POST', headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || '' } })
                .catch(e => console.debug('Mark read error:', e));
        });
    }
    
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