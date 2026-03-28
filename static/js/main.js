// main.js (Kumpletong Bersyon)

document.addEventListener('DOMContentLoaded', () => {
    /*--    // I-check kung nasa 'Generate Schedule' page tayo sa pamamagitan ng ID ng isang element
        if (document.getElementById('generateBtn')) {
            initializeGeneratePage();
        }
    });
    
    
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
                method: 'POST'
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
                    alert('Error generating schedule.');
                    resetToInitialState();
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Something went wrong.');
                resetToInitialState();
            });
            
            // Note: The progress bar here will just be a "loading" animation 
            // since Flask blocks during processing unless we use Celery/Async.
        }
    
        // Ikabit ang event listeners sa mga buttons
        generateBtn.addEventListener('click', startGeneration);
        generateAgainBtn.addEventListener('click', resetToInitialState);
    }
    
    
    
    // main.js (Idagdag ito sa pinakababa)
    
    document.addEventListener('DOMContentLoaded', () => {
        // I-check kung nasa 'Generate Schedule' page tayo
        if (document.getElementById('generateBtn')) {
            initializeGeneratePage();
        }
    -*/
    // I-check kung nasa 'Reports' page tayo sa pamamagitan ng ID ng isang chart
    if (document.getElementById('roomUtilizationChart')) {
        initializeReportsPage();
    }

    // 2. SIDEBAR FILTER: Initialize logic
    initializeSemesterFilter();

    // ==========================================
    // DAGDAG DITO: AUTO-DISMISS FLASH MESSAGES 
    // ==========================================
    setTimeout(function () {
        let alertElements = document.querySelectorAll('.alert');
        alertElements.forEach(function (alertNode) {
            if (typeof bootstrap !== 'undefined') {
                let bsAlert = new bootstrap.Alert(alertNode);
                bsAlert.close(); // Fade-out animation
            } else {
                alertNode.style.display = 'none'; // Fallback
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

// ==========================================
// UNIVERSAL SCHEDULE MODAL LOGIC
// ==========================================
let currentSchedType = null;
let currentSchedId = null;

window.viewSchedule = function (type, id) {
    currentSchedType = type;
    currentSchedId = id;

    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('universalScheduleModal'));
    const contentDiv = document.getElementById('dynamicScheduleContent');

    // Update label based on row text
    const activeRow = document.querySelector(`tr[data-id="${id}"]`);
    if (activeRow) {
        const nameCell = activeRow.querySelector('td.fw-bold') || activeRow.cells[1];
        document.getElementById('universalScheduleLabel').textContent = nameCell ? nameCell.textContent.trim() : `ID: ${id}`;
    }

    // Show loading state
    contentDiv.innerHTML = `
        <div class="text-center py-5">
            <div class="spinner-border text-primary" role="status"></div>
            <p class="mt-2 text-muted small">Loading schedule...</p>
        </div>`;
    modal.show();

    // Fetch schedule
    fetch(`/view-schedule-modal/${type}/${id}`)
        .then(response => response.text())
        .then(html => {
            contentDiv.innerHTML = html;
            // Execute any scripts inside the fetched HTML (like drag-and-drop initialize)
            contentDiv.querySelectorAll('script').forEach(function (oldScript) {
                const newScript = document.createElement('script');
                if (oldScript.src) newScript.src = oldScript.src;
                else newScript.textContent = oldScript.textContent;
                document.head.appendChild(newScript);
                document.head.removeChild(newScript);
            });
        })
        .catch(err => {
            console.error('Failed to load schedule:', err);
            contentDiv.innerHTML = `<div class="alert alert-danger m-3">Failed to load schedule.</div>`;
        });
};

// Handle Arrow Key Navigation for the Modal
document.addEventListener('keydown', function (e) {
    const modalEl = document.getElementById('universalScheduleModal');
    if (!modalEl || !modalEl.classList.contains('show')) return;

    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        const rows = Array.from(document.querySelectorAll('tr[data-id]')).filter(row => row.style.display !== 'none');
        if (rows.length === 0) return;

        const currentIndex = rows.findIndex(row => row.getAttribute('data-id') == currentSchedId);
        if (currentIndex === -1) return;

        let nextIndex = currentIndex;
        if (e.key === 'ArrowLeft' && currentIndex > 0) {
            nextIndex = currentIndex - 1;
        } else if (e.key === 'ArrowRight' && currentIndex < rows.length - 1) {
            nextIndex = currentIndex + 1;
        }

        if (nextIndex !== currentIndex) {
            const nextId = rows[nextIndex].getAttribute('data-id');
            viewSchedule(currentSchedType, parseInt(nextId));
        }
    }
});

// ── Shared Pagination: jumpToPage + Arrow Key Navigation ─────────────────────
// Used by: manage_courses, manage_sections, manage_faculty, manage_rooms,
//          manage_constraints, check_constraints, courses_archive
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