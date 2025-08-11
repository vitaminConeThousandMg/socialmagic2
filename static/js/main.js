// Mobile menu toggle
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
        sidebar.classList.toggle('open');
    }
}

// Close sidebar on outside click (mobile)
document.addEventListener('click', (e) => {
    const sidebar = document.getElementById('sidebar');
    const mobileToggle = document.querySelector('.mobile-toggle');
    
    if (window.innerWidth <= 768 && 
        sidebar &&
        !sidebar.contains(e.target) && 
        !e.target.closest('.mobile-toggle')) {
        sidebar.classList.remove('open');
    }
});

// Auto-hide flash messages
document.addEventListener('DOMContentLoaded', function() {
    const messages = document.querySelectorAll('.message');
    messages.forEach(message => {
        setTimeout(() => {
            message.style.opacity = '0';
            setTimeout(() => {
                if (message.parentNode) {
                    message.parentNode.removeChild(message);
                }
            }, 300);
        }, 5000);
    });
});

// Upload functionality for forms with file inputs
document.addEventListener('DOMContentLoaded', function() {
    const fileInputs = document.querySelectorAll('input[type="file"]');
    
    fileInputs.forEach(input => {
        if (input.hasAttribute('multiple')) {
            setupMultipleFileUpload(input);
        }
    });
});

function setupMultipleFileUpload(fileInput) {
    const form = fileInput.closest('form');
    if (!form) return;
    
    let selectedFiles = [];
    
    fileInput.addEventListener('change', function(e) {
        const files = Array.from(e.target.files);
        selectedFiles = files;
        
        // Update UI to show selected files
        updateFileDisplay(files, fileInput);
    });
}

function updateFileDisplay(files, fileInput) {
    // Create or update file display
    let fileDisplay = fileInput.parentElement.querySelector('.file-display');
    
    if (!fileDisplay) {
        fileDisplay = document.createElement('div');
        fileDisplay.className = 'file-display';
        fileInput.parentElement.appendChild(fileDisplay);
    }
    
    if (files.length === 0) {
        fileDisplay.innerHTML = '';
        return;
    }
    
    fileDisplay.innerHTML = `
        <div style="margin-top: 10px; padding: 10px; background: var(--light-gray); border-radius: 6px;">
            <strong>${files.length} file${files.length > 1 ? 's' : ''} selected:</strong>
            <ul style="margin: 5px 0 0 20px; font-size: 14px; color: var(--gray);">
                ${files.map(file => `<li>${file.name} (${formatFileSize(file.size)})</li>`).join('')}
            </ul>
        </div>
    `;
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    const p = Math.pow(k, i);
    const s = Math.round((bytes / p) * 100) / 100;
    return s + ' ' + sizes[i];
}

// API helpers
function showMessage(message, type = 'info') {
    const messageArea = document.getElementById('messageArea') || document.querySelector('.content');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    messageDiv.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
            ${type === 'success' 
                ? '<path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>'
                : '<path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>'}
        </svg>
        ${message}
    `;
    
    if (messageArea.id === 'messageArea') {
        messageArea.innerHTML = '';
        messageArea.appendChild(messageDiv);
    } else {
        messageArea.insertBefore(messageDiv, messageArea.firstChild);
    }
    
    setTimeout(() => {
        messageDiv.style.opacity = '0';
        setTimeout(() => {
            if (messageDiv.parentNode) {
                messageDiv.parentNode.removeChild(messageDiv);
            }
        }, 300);
    }, 5000);
}

// AJAX form submission helper
function submitFormAjax(form, onSuccess, onError) {
    const formData = new FormData(form);
    const submitBtn = form.querySelector('button[type="submit"]');
    const originalText = submitBtn ? submitBtn.innerHTML : '';
    
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="loading-spinner"></span> Processing...';
    }
    
    fetch(form.action || '', {
        method: 'POST',
        body: formData,
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            if (onSuccess) onSuccess(data);
            else showMessage(data.message || 'Success!', 'success');
        } else {
            if (onError) onError(data);
            else showMessage(data.error || 'An error occurred', 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        if (onError) onError(error);
        else showMessage('Network error occurred', 'error');
    })
    .finally(() => {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        }
    });
}

// Real-time stats updates (optional)
function updateDashboardStats() {
    fetch('/api/stats')
        .then(response => response.json())
        .then(data => {
            // Update stat values in the DOM
            const statValues = document.querySelectorAll('.stat-value');
            if (statValues.length >= 4) {
                statValues[0].textContent = data.total_posts;
                statValues[1].textContent = data.total_reach.toLocaleString();
                statValues[2].textContent = data.scheduled;
                statValues[3].textContent = data.total_media;
            }
        })
        .catch(error => console.error('Error updating stats:', error));
}

// Initialize dashboard updates if on dashboard page
if (window.location.pathname === '/dashboard' || window.location.pathname === '/') {
    // Update stats every 30 seconds
    setInterval(updateDashboardStats, 30000);
}