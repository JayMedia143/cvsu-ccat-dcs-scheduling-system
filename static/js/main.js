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

// ── UNIVERSAL SCHEDULE MODAL MANAGER (NUCLEAR CLEAN) ──────
const UniversalModalManager = {
    type: null,
    id: null,
    scale: 1.0,
    tx: 0,
    ty: 0,
    isDragging: false,
    startX: 0,
    startY: 0,
    lastPinchDist: null,
    touchStartX: 0,
    touchStartY: 0,
    isSwiping: false,

    init() {
        const modalEl = document.getElementById('universalScheduleModal');
        if (!modalEl) return;

        // ── ATTACH LISTENERS ONLY ONCE ──

        // Arrow Key Support
        document.addEventListener('keydown', (e) => {
            if (!modalEl.classList.contains('show')) return;
            if (e.key === 'ArrowLeft') this.navigate('prev');
            if (e.key === 'ArrowRight') this.navigate('next');
        });

        // Global Mouse Up
        window.addEventListener('mouseup', () => {
            this.isDragging = false;
            const container = document.getElementById('schedGridContainer');
            if (container) container.style.cursor = 'grab';
        });

        // Global Mouse Move
        window.addEventListener('mousemove', (e) => {
            if (!this.isDragging || !this.modalIsVisible()) return;
            this.tx = e.clientX - this.startX;
            this.ty = e.clientY - this.startY;
            this.applyTransform();
        });

        // Handle Panning/Zooming via delegation from the container
        modalEl.addEventListener('mousedown', (e) => {
            const container = e.target.closest('#schedGridContainer');
            if (!container) return;
            this.isDragging = true;
            this.startX = e.clientX - this.tx;
            this.startY = e.clientY - this.ty;
            container.style.cursor = 'grabbing';
        });

        // Touch Interaction (Pan + Zoom + Swipe)
        modalEl.addEventListener('touchstart', (e) => {
            const container = e.target.closest('#schedGridContainer');
            if (!container) return;

            if (e.touches.length === 1) {
                this.isDragging = true;
                this.touchStartX = e.touches[0].clientX;
                this.touchStartY = e.touches[0].clientY;
                this.startX = this.touchStartX - this.tx;
                this.startY = this.touchStartY - this.ty;
                this.isSwiping = true;
            } else if (e.touches.length === 2) {
                this.isDragging = false;
                this.isSwiping = false;
                this.lastPinchDist = Math.hypot(
                    e.touches[0].clientX - e.touches[1].clientX,
                    e.touches[0].clientY - e.touches[1].clientY
                );
            }
        }, { passive: false });

        modalEl.addEventListener('touchmove', (e) => {
            if (!this.modalIsVisible()) return;
            const container = e.target.closest('#schedGridContainer');
            if (!container) return;

            e.preventDefault(); 
            if (e.touches.length === 1 && this.isDragging) {
                this.tx = e.touches[0].clientX - this.startX;
                this.ty = e.touches[0].clientY - this.startY;
                this.applyTransform();
            } else if (e.touches.length === 2 && this.lastPinchDist) {
                const dist = Math.hypot(
                    e.touches[0].clientX - e.touches[1].clientX,
                    e.touches[0].clientY - e.touches[1].clientY
                );
                const delta = dist / this.lastPinchDist;
                const oldScale = this.scale;
                this.scale = Math.max(0.08, Math.min(5.0, this.scale * delta));

                const rect = container.getBoundingClientRect();
                const midX = (e.touches[0].clientX + e.touches[1].clientX) / 2 - rect.left;
                const midY = (e.touches[0].clientY + e.touches[1].clientY) / 2 - rect.top;

                this.tx -= (midX - this.tx) * (this.scale / oldScale - 1);
                this.ty -= (midY - this.ty) * (this.scale / oldScale - 1);

                this.lastPinchDist = dist;
                this.applyTransform();
            }
        }, { passive: false });

        modalEl.addEventListener('touchend', (e) => {
            if (this.isSwiping && e.changedTouches.length === 1) {
                const dx = e.changedTouches[0].clientX - this.touchStartX;
                const dy = e.changedTouches[0].clientY - this.touchStartY;
                if (Math.abs(dx) > 50 && Math.abs(dy) < 50) {
                    this.navigate(dx > 0 ? 'prev' : 'next');
                }
            }
            this.isDragging = false;
            this.lastPinchDist = null;
            this.isSwiping = false;
        });
    },

    modalIsVisible() {
        return document.getElementById('universalScheduleModal').classList.contains('show');
    },

    open(type, id) {
        this.type = type;
        this.id = id;
        this.scale = 1.0;
        this.tx = 0;
        this.ty = 0;

        const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('universalScheduleModal'));
        const container = document.getElementById('schedGridContainer');
        const labelEl = document.getElementById('universalScheduleLabel');

        if (!container) return;

        const activeRow = document.querySelector(`tr[data-id="${id}"]`);
        if (activeRow) {
            const nameCell = activeRow.querySelector('td.fw-bold') || activeRow.cells[1];
            labelEl.textContent = nameCell ? nameCell.textContent.trim() : `ID: ${id}`;
        }

        container.innerHTML = `<div class="text-center py-5"><div class="spinner-border text-primary"></div><p class="mt-2 text-muted small">Loading...</p></div>`;
        modal.show();

        fetch(`/view-schedule-modal/${type}/${id}`)
            .then(r => {
                if (!r.ok) throw new Error(`HTTP error! status: ${r.status}`);
                return r.text();
            })
            .then(html => {
                // Wrap in Virtual Canvas for Infinite Feel
                container.innerHTML = `
                    <div class="modal-paper-wrapper" id="modalPaperWrapper">
                        <div class="modal-paper-content" id="modalPaperContent">
                            ${html}
                        </div>
                    </div>`;
                
                const wrapper = container.querySelector('.dynamic-paper-wrapper');
                const paperContent = document.getElementById('modalPaperContent');
                
                if (wrapper && paperContent) {
                    const dw = parseInt(wrapper.getAttribute('data-width')) || 800;
                    const dh = parseInt(wrapper.getAttribute('data-height')) || 1150;
                    
                    paperContent.style.width = dw + 'px';
                    paperContent.style.height = dh + 'px';
                    
                    // Force wrapper to fill
                    wrapper.style.width = '100%';
                    wrapper.style.height = '100%';

                    // Special case for iframes
                    const iframe = paperContent.querySelector('iframe');
                    if (iframe) {
                        iframe.setAttribute('scrolling', 'no');
                        iframe.style.pointerEvents = 'none'; 
                        iframe.style.width = '100%';
                        iframe.style.height = '100%';
                        iframe.style.display = 'block';
                        iframe.style.border = 'none';
                    }
                }

                this.autoFit();
            })
            .catch(err => {
                console.error('Schedule Load Error:', err);
                container.innerHTML = `<div class="alert alert-danger m-3">Failed to load schedule.</div>`;
            });
    },

    autoFit() {
        const container = document.getElementById('schedGridContainer');
        const wrapper = document.getElementById('modalPaperWrapper');
        const content = document.getElementById('modalPaperContent');
        if (!container || !wrapper || !content) return;
        
        setTimeout(() => {
            const cw = container.clientWidth;
            const ch = container.clientHeight;
            const gw = content.offsetWidth || 800;
            const gh = content.offsetHeight || 1150;

            // Scale to fit width with safety margin
            this.scale = Math.min(1.2, (cw - 40) / gw);
            
            // Adjust padding based on device
            const wrapperPadding = window.innerWidth <= 768 ? 80 : 200;
            
            // Center Horizontally
            this.tx = (cw / 2) - (gw / 2 * this.scale) - (wrapperPadding * this.scale);
            
            // Align exactly to top (0px) to avoid gray bar
            this.ty = -(wrapperPadding * this.scale);
            
            this.applyTransform();
        }, 350);
    },

    zoomManual(delta) {
        const oldScale = this.scale;
        this.scale = Math.max(0.1, Math.min(3.0, this.scale + delta));
        
        // Zoom relative to container center
        const container = document.getElementById('schedGridContainer');
        if (container) {
            const cx = container.clientWidth / 2;
            const cy = container.clientHeight / 2;
            this.tx -= (cx - this.tx) * (this.scale / oldScale - 1);
            this.ty -= (cy - this.ty) * (this.scale / oldScale - 1);
        }
        this.applyTransform();
    },

    applyTransform() {
        const wrapper = document.getElementById('modalPaperWrapper');
        if (wrapper) {
            // Round coordinates to prevent sub-pixel blurring
            const rtx = Math.round(this.tx);
            const rty = Math.round(this.ty);
            // Use translate3d/translateZ for sharper hardware acceleration
            // Add a tiny scale offset (1.00001) to force Chrome to re-rasterize sharply
            wrapper.style.transform = `translate3d(${rtx}px, ${rty}px, 0) scale(${this.scale * 1.00001})`;
        }
        // Update Zoom Percentage Badge
        const zoomEl = document.getElementById('modal-zoom-percent');
        if (zoomEl) {
            zoomEl.textContent = Math.round(this.scale * 100) + '%';
        }
    },

    navigate(dir) {
        const rows = Array.from(document.querySelectorAll('tr[data-id]')).filter(r => r.style.display !== 'none');
        const idx = rows.findIndex(r => r.getAttribute('data-id') == this.id);
        if (idx === -1) return;

        let nIdx = idx;
        if (dir === 'prev' && idx > 0) nIdx = idx - 1;
        if (dir === 'next' && idx < rows.length - 1) nIdx = idx + 1;

        if (nIdx !== idx) {
            this.open(this.type, rows[nIdx].getAttribute('data-id'));
        }
    }
};

// Map global functions to Manager
window.viewSchedule = (type, id) => UniversalModalManager.open(type, id);
document.addEventListener('DOMContentLoaded', () => UniversalModalManager.init());

// ── Shared Pagination ──────────────────────────────────────
window.jumpToPage = function () {
    const input = document.getElementById('pageJumpInput');
    if (!input) return;
    const n   = parseInt(input.value);
    const max = parseInt(input.max) || 1;
    if (isNaN(n) || n < 1 || n > max) return;
    const url = new URL(window.location.href);
    url.searchParams.set('page', n);
    window.location.href = url.toString();
};

document.addEventListener('keydown', function (e) {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    // Skip if a modal is open
    if (document.querySelector('.modal.show')) return;
    // Skip if user is typing in an input/textarea/select
    const tag = document.activeElement ? document.activeElement.tagName : '';
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

    const input = document.getElementById('pageJumpInput');
    if (!input) return;   // page has no pagination → do nothing

    const url     = new URL(window.location.href);
    const current = parseInt(url.searchParams.get('page') || '1');
    const max     = parseInt(input.max) || 1;

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