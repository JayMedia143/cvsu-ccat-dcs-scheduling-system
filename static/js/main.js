// main.js (Kumpletong Bersyon)

document.addEventListener('DOMContentLoaded', () => {
    // I-check kung nasa 'Generate Schedule' page tayo sa pamamagitan ng ID ng isang element
    if (document.getElementById('generateBtn')) {
        initializeGeneratePage();
    }

    function initializeGeneratePage() {
        // Kunin lahat ng kailangang elements
        const setupContainer = document.getElementById('setupContainer');
        const progressContainer = document.getElementById('progressContainer');
        const successContainer = document.getElementById('successContainer');

        const generateBtn = document.getElementById('generateBtn');
        const generateAgainBtn = document.getElementById('generateAgainBtn');

        const progressBar = document.getElementById('progressBar');
        const generationCountSpan = document.getElementById('generationCount');
        const hardCountSpan = document.getElementById('hardCount');
        const softCountSpan = document.getElementById('softCount');

        const finalScoreSpan = document.getElementById('finalScore');
        const timeTakenSpan = document.getElementById('timeTaken');

        // Itago lahat at ipakita lang ang setup sa simula
        function resetToInitialState() {
            progressContainer.style.display = 'none';
            successContainer.style.display = 'none';
            setupContainer.style.display = 'block';
        }

        // Function para i-trigger ang simulation
        function startGeneration() {
            setupContainer.style.display = 'none';
            progressContainer.style.display = 'block';

            // Start Server-Side Generation via AJAX
            fetch('/generate-schedule-action', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                }
            })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        // Done! Show Result
                        progressContainer.style.display = 'none';
                        successContainer.style.display = 'block';
                        hardCountSpan.textContent = data.hard_conflicts;
                        finalScoreSpan.textContent = data.score;
                    } else {
                        alert('Error generating schedule: ' + (data.message || 'Unknown error'));
                        resetToInitialState();
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('Something went wrong.');
                    resetToInitialState();
                });
        }

        // Ikabit ang event listeners sa mga buttons
        if (generateBtn) generateBtn.addEventListener('click', startGeneration);
        if (generateAgainBtn) generateAgainBtn.addEventListener('click', resetToInitialState);
    }

    // Helper: Get CSRF Token from meta tag
    function getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    }

    // I-check kung nasa 'Reports' page tayo sa pamamagitan ng ID ng isang chart
    if (document.getElementById('roomUtilizationChart')) {
        initializeReportsPage();
    }

    // 2. SIDEBAR FILTER: Initialize logic
    initializeSemesterFilter();

    // ==========================================
    // DAGDAG DITO: AUTO-DISMISS FLASH MESSAGES (Alerts & Toasts)
    // ==========================================
    setTimeout(function () {
        // Handle standard Alerts
        let alertElements = document.querySelectorAll('.alert');
        alertElements.forEach(function (alertNode) {
            if (typeof bootstrap !== 'undefined') {
                let bsAlert = new bootstrap.Alert(alertNode);
                bsAlert.close();
            } else {
                alertNode.style.display = 'none';
            }
        });

        // Handle modern Toasts
        let toastElements = document.querySelectorAll('.toast');
        toastElements.forEach(function (toastNode) {
            if (typeof bootstrap !== 'undefined') {
                let bsToast = bootstrap.Toast.getOrCreateInstance(toastNode);
                bsToast.hide();
            } else {
                toastNode.style.display = 'none';
            }
        });
    }, 5000); // 5 seconds
});

// --- Function for Reports Charts ---
function initializeReportsPage() {
    // Chart 1: Room Utilization
    const roomCtx = document.getElementById('roomUtilizationChart').getContext('2d');
    new Chart(roomCtx, {
        type: 'bar',
        data: {
            labels: ['A1', 'A2', 'A3', 'B1', 'B2', 'B3', 'B4', 'B5', 'B6'],
            datasets: [{
                label: 'Scheduled Hours per Week',
                data: [35, 32, 40, 45, 38, 42, 33, 41, 39],
                backgroundColor: 'rgba(54, 162, 235, 0.6)',
                borderColor: 'rgba(54, 162, 235, 1)',
                borderWidth: 1
            }]
        },
        options: {
            scales: { y: { beginAtZero: true, title: { display: true, text: 'Hours' } } },
            plugins: { legend: { display: false } }
        }
    });

    // Chart 2: Faculty Load Distribution
    const facultyCtx = document.getElementById('facultyLoadChart').getContext('2d');
    new Chart(facultyCtx, {
        type: 'line',
        data: {
            labels: ['Reyes', 'Gonzales', 'Carpio', 'Fernandez', 'Santos', 'Aquino', 'Ramos', 'Estrada', 'Duterte', 'Marcos'],
            datasets: [{
                label: 'Total Units Assigned',
                data: [18, 21, 15, 24, 18, 21, 12, 18, 21, 24],
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                borderColor: 'rgba(75, 192, 192, 1)',
                fill: true,
                tension: 0.1
            }]
        },
        options: {
            scales: { y: { beginAtZero: true, title: { display: true, text: 'Units' } } },
            plugins: { legend: { display: false } }
        }
    });
}

// --- Function for Semester Filter Persistence ---
function initializeSemesterFilter() {
    const collapseElement = document.getElementById('semesterCollapse');
    const triggerElement = document.getElementById('semFilterTrigger');

    // Safety check kung nasa page ba ang sidebar
    if (collapseElement && triggerElement) {

        // 1. LOAD STATE: Basahin ang memory pagkabukas ng page
        const savedState = localStorage.getItem('semFilterState');

        if (savedState === 'open') {
            collapseElement.classList.add('show');
            triggerElement.classList.remove('collapsed');
            triggerElement.setAttribute('aria-expanded', 'true');
        } else {
            collapseElement.classList.remove('show');
            triggerElement.classList.add('collapsed');
            triggerElement.setAttribute('aria-expanded', 'false');
        }

        // 2. SAVE STATE: Makinig sa pag-bukas o pag-sara
        collapseElement.addEventListener('shown.bs.collapse', function () {
            localStorage.setItem('semFilterState', 'open');
        });

        collapseElement.addEventListener('hidden.bs.collapse', function () {
            localStorage.setItem('semFilterState', 'closed');
        });
    }
}

// // ── GLOBAL SCHEDULE PRESENTER (NEW FULLSCREEN VIEW) ──────
window.GlobalSchedulePresenter = {
    type: null,
    id: null,
    scale: 1.0,
    tx: 0,
    ty: 0,
    isDragging: false,
    startX: 0,
    startY: 0,
    currentSemester: null,

    // Touch support variables
    lastTouchDistance: 0,
    isPinching: false,

    init() {
        const overlay = document.getElementById('global-schedule-presenter');
        const iframe = document.getElementById('pres-iframe');
        if (!overlay) return;

        // --- MOUSE EVENTS (Desktop) ---
        overlay.addEventListener('mousedown', (e) => {
            if (e.target.closest('.pres-nav-btn') || e.target.closest('.pres-close')) return;
            this.isDragging = true;
            this.startX = e.clientX - this.tx;
            this.startY = e.clientY - this.ty;
            overlay.style.cursor = 'grabbing';
        });

        overlay.addEventListener('click', (e) => {
            if (e.target.id === 'global-schedule-presenter' || e.target.id === 'pres-backdrop') {
                this.close();
            }
        });

        window.addEventListener('mousemove', (e) => {
            if (!this.isDragging || !overlay.classList.contains('active')) return;
            this.tx = e.clientX - this.startX;
            this.ty = e.clientY - this.startY;
            this.applyTransform();
        });

        window.addEventListener('mouseup', () => {
            this.isDragging = false;
            overlay.style.cursor = 'grab';
        });

        overlay.addEventListener('wheel', (e) => {
            if (!overlay.classList.contains('active')) return;
            e.preventDefault();
            const zoomSpeed = 0.0015;
            const delta = -e.deltaY * zoomSpeed;
            this.scale = Math.max(0.1, Math.min(4.0, this.scale + delta));
            this.applyTransform();
        }, { passive: false });

        // --- TOUCH EVENTS (Mobile) ---
        overlay.addEventListener('touchstart', (e) => {
            if (e.target.closest('.pres-nav-btn') || e.target.closest('.pres-close')) return;

            if (e.touches.length === 1) {
                // Pan Start
                this.isDragging = true;
                this.isPinching = false;
                this.startX = e.touches[0].clientX - this.tx;
                this.startY = e.touches[0].clientY - this.ty;
            } else if (e.touches.length === 2) {
                // Pinch Start
                this.isPinching = true;
                this.isDragging = false;
                this.lastTouchDistance = this.getTouchDistance(e.touches);
            }
        }, { passive: true });

        overlay.addEventListener('touchmove', (e) => {
            if (!overlay.classList.contains('active')) return;

            if (e.touches.length === 1 && this.isDragging) {
                // Pan Move
                this.tx = e.touches[0].clientX - this.startX;
                this.ty = e.touches[0].clientY - this.startY;
                this.applyTransform();
            } else if (e.touches.length === 2 && this.isPinching) {
                // Pinch Move
                const dist = this.getTouchDistance(e.touches);
                const delta = (dist - this.lastTouchDistance) * 0.005;
                this.scale = Math.max(0.1, Math.min(4.0, this.scale + delta));
                this.lastTouchDistance = dist;
                this.applyTransform();
            }
        }, { passive: true });

        overlay.addEventListener('touchend', () => {
            this.isDragging = false;
            this.isPinching = false;
        });

        // Relay from Iframe (If focus is inside)
        window.addEventListener('message', (e) => {
            if (e.data && e.data.type === 'keydown' && overlay.classList.contains('active')) {
                if (e.data.key === 'ArrowRight') this.showNext();
                if (e.data.key === 'ArrowLeft') this.showPrev();
                if (e.data.key === 'Escape') this.close();
            }
        });

        // --- IFRAME LOAD HANDLER (SMART SIZING) ---
        if (iframe) {
            iframe.addEventListener('load', () => {
                if (!overlay.classList.contains('active')) return;
                try {
                    const doc = iframe.contentDocument || iframe.contentWindow.document;
                    const paper = doc.querySelector('.a4') || doc.getElementById('a4Paper') || doc.body;

                    if (paper) {
                        const wrap = document.getElementById('pres-wrap');
                        // Wait a tiny bit for layout to settle
                        setTimeout(() => {
                            const actualW = paper.offsetWidth;
                            const actualH = paper.offsetHeight;

                            if (wrap) {
                                wrap.style.width = actualW + 'px';
                                wrap.style.height = actualH + 'px';
                                iframe.style.width = actualW + 'px';
                                iframe.style.height = actualH + 'px';
                            }

                            // Re-calculate zoom for mobile based on ACTUAL paper width
                            if (window.innerWidth <= 767) {
                                this.scale = (window.innerWidth * 0.95) / actualW;
                                this.tx = 0;
                                this.ty = 0;
                                this.applyTransform();
                            }
                        }, 50);
                    }
                } catch (e) { console.warn("Iframe measurement error:", e); }
            });
        }

        // Semester retrieval
        const semEl = document.querySelector('.sem-btn-tool.active');
        this.currentSemester = semEl ? semEl.textContent.trim() : "All";
    },

    getTouchDistance(touches) {
        return Math.hypot(touches[0].clientX - touches[1].clientX, touches[0].clientY - touches[1].clientY);
    },

    open(type, id) {
        this.type = type;
        this.id = id;

        const overlay = document.getElementById('global-schedule-presenter');
        const iframe = document.getElementById('pres-iframe');
        const labelEl = document.getElementById('pres-label');
        const wrap = document.getElementById('pres-wrap');

        if (!overlay || !iframe) return;

        // Reset dimensions for next load
        if (wrap) {
            wrap.style.width = '800px';
            wrap.style.height = 'auto';
        }

        // Default Desktop zoom
        this.scale = 0.4;
        this.tx = 0;
        this.ty = 0;
        this.applyTransform();

        if (labelEl) {
            const activeRow = document.querySelector(`tr[data-id="${id}"]`);
            if (activeRow) {
                const nameCell = activeRow.querySelector('td.fw-bold') || activeRow.cells[1];
                labelEl.textContent = nameCell ? nameCell.textContent.trim() : `Loading...`;
            } else {
                labelEl.textContent = (type === 'preview') ? `Template Preview` : "Loading...";
            }
        }

        const urlParams = new URLSearchParams(window.location.search);
        const termId = urlParams.get('term_id') || 'live';
        const semester = this.currentSemester || "All";

        const urlMap = {
            section: id => `/section-timetable-html/${id}?semester=${encodeURIComponent(semester)}&canvas=true&t=${Date.now()}`,
            faculty: id => `/faculty-timetable-html/${id}?semester=${encodeURIComponent(semester)}&canvas=true&t=${Date.now()}`,
            room: id => `/room-timetable-html/${id}?semester=${encodeURIComponent(semester)}&canvas=true&t=${Date.now()}`,
            course: id => `/course-timetable-html/${id}?semester=${encodeURIComponent(semester)}&canvas=true&t=${Date.now()}`,
            student: id => {
                if (termId !== 'live') {
                    return `/public/archived-timetable-html/${termId}/${id}?canvas=true&t=${Date.now()}`;
                }
                return `/public/student-timetable-html/${id}?semester=${encodeURIComponent(semester)}&canvas=true&t=${Date.now()}`;
            },
            preview: type => `/preview-layout/${type}?t=${Date.now()}`
        };

        const navBtns = document.querySelectorAll('.pres-nav-btn');
        navBtns.forEach(btn => btn.style.display = (type === 'preview' ? 'none' : ''));

        iframe.src = urlMap[type](id);
        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
    },

    close() {
        const overlay = document.getElementById('global-schedule-presenter');
        const iframe = document.getElementById('pres-iframe');
        if (overlay) overlay.classList.remove('active');
        if (iframe) iframe.src = '';
        document.body.style.overflow = 'auto';
    },

    applyTransform() {
        const wrap = document.getElementById('pres-wrap');
        if (wrap) {
            wrap.style.transform = `translate(${this.tx}px, ${this.ty}px) scale(${this.scale})`;
        }
        this.updateZoomBadge();
    },

    updateZoomBadge() {
        const badge = document.getElementById('pres-zoom-val');
        const footer = document.querySelector('.pres-footer');

        if (badge) {
            if (window.innerWidth <= 767) {
                badge.textContent = Math.round(this.scale * 100) + '% Fit';
            } else {
                badge.textContent = Math.round(this.scale * 100) + '%';
            }
        }
    },

    showNext() {
        const rows = Array.from(document.querySelectorAll('tr[data-id]')).filter(r => r.style.display !== 'none');
        if (rows.length === 0) return;
        const idx = rows.findIndex(r => r.getAttribute('data-id') == this.id);
        if (idx !== -1 && idx < rows.length - 1) {
            this.open(this.type, rows[idx + 1].getAttribute('data-id'));
        } else if (rows.length > 0) {
            this.open(this.type, rows[0].getAttribute('data-id'));
        }
    },

    showPrev() {
        const rows = Array.from(document.querySelectorAll('tr[data-id]')).filter(r => r.style.display !== 'none');
        if (rows.length === 0) return;
        const idx = rows.findIndex(r => r.getAttribute('data-id') == this.id);
        if (idx !== -1 && idx > 0) {
            this.open(this.type, rows[idx - 1].getAttribute('data-id'));
        } else if (rows.length > 0) {
            this.open(this.type, rows[rows.length - 1].getAttribute('data-id'));
        }
    }
};

// Global hooks
window.viewSchedule = (type, id) => window.GlobalSchedulePresenter.open(type, id);
window.closeSchedulePresenter = () => window.GlobalSchedulePresenter.close();
document.addEventListener('DOMContentLoaded', () => window.GlobalSchedulePresenter.init());

// ── Shared Pagination ──────────────────────────────────────
window.jumpToPage = function () {
    const input = document.getElementById('pageJumpInput');
    if (!input) return;
    const n = parseInt(input.value);
    const max = parseInt(input.max) || 1;
    if (isNaN(n) || n < 1 || n > max) return;
    const url = new URL(window.location.href);
    url.searchParams.set('page', n);
    window.location.href = url.toString();
};

document.addEventListener('keydown', function (e) {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight' && e.key !== 'Escape') return;
    // Skip if a modal is open
    if (document.querySelector('.modal.show')) return;
    // ── PAGINATION KEYBOARD NAVIGATION ──────────────────────────
    // Skip if user is typing in an input/textarea/select
    const tag = document.activeElement ? document.activeElement.tagName : '';
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

    // Skip if the schedule presenter is active (let it handle its own arrows)
    const presenterEl = document.getElementById('global-schedule-presenter');
    if (presenterEl && presenterEl.classList.contains('active')) {
        const pres = window.GlobalSchedulePresenter;
        if (pres) {
            if (e.key === 'ArrowLeft') pres.showPrev();
            if (e.key === 'ArrowRight') pres.showNext();
            if (e.key === 'Escape') pres.close();
        }
        return;
    }

    const input = document.getElementById('pageJumpInput');
    if (!input) return;   // page has no pagination → do nothing

    const url = new URL(window.location.href);
    const current = parseInt(url.searchParams.get('page') || '1');
    const max = parseInt(input.max) || 1;

    if (e.key === 'ArrowLeft' && current > 1) {
        url.searchParams.set('page', current - 1);
        window.location.href = url.toString();
    } else if (e.key === 'ArrowRight' && current < max) {
        url.searchParams.set('page', current + 1);
        window.location.href = url.toString();
    }
});

// Enter key on pageJumpInput (for pages that don't wire it manually)
document.addEventListener('DOMContentLoaded', function () {
    const input = document.getElementById('pageJumpInput');
    if (input) {
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') window.jumpToPage();
        });
    }
});

/**
 * Toggles the visibility of a password input field.
 * Expects a button inside a container along with the input.
 */
function togglePasswordVisibility(btn) {
    const container = btn.parentElement;
    const input = container.querySelector('input');
    const icon = btn.querySelector('i');

    if (input.type === 'password') {
        input.type = 'text';
        icon.classList.replace('bi-eye-slash-fill', 'bi-eye-fill');
    } else {
        input.type = 'password';
        icon.classList.replace('bi-eye-fill', 'bi-eye-slash-fill');
    }
}