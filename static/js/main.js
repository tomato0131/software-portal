/**
 * 企业内网软件分发平台 - 前端交互
 */

// Auto-dismiss flash messages
document.addEventListener('DOMContentLoaded', () => {
    const msgs = document.querySelectorAll('.flash-msg');
    msgs.forEach(msg => {
        setTimeout(() => {
            msg.style.transition = 'opacity 0.3s ease';
            msg.style.opacity = '0';
            setTimeout(() => msg.remove(), 300);
        }, 5000);
    });
});

// Smooth scroll to top on page load
if (window.location.hash) {
    window.scrollTo(0, 0);
}

// Admin sidebar active link sync (highlight based on URL)
(function syncSidebarActive() {
    const links = document.querySelectorAll('.sidebar-link');
    if (!links.length) return;
    const current = window.location.pathname;
    links.forEach(link => {
        if (link.classList.contains('active')) return;
        if (current === new URL(link.href).pathname) {
            link.classList.add('active');
        }
    });
})();

// Keyboard shortcut: Ctrl/Cmd + K to focus search
document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        const search = document.getElementById('searchInput');
        if (search) search.focus();
    }
});

// Download confirmation
document.querySelectorAll('.btn-download').forEach(btn => {
    if (btn.tagName !== 'A') return;
    btn.addEventListener('click', function(e) {
        // Show a brief loading state
        const original = this.innerHTML;
        this.innerHTML = '<span style="display:inline-flex;align-items:center;gap:6px;">准备下载...</span>';
        this.style.pointerEvents = 'none';
        // Re-enable after a moment (in case download doesn't trigger navigation)
        setTimeout(() => {
            this.innerHTML = original;
            this.style.pointerEvents = '';
        }, 3000);
    });
});
