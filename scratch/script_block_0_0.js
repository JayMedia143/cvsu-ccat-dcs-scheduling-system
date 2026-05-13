
    function makeDraggable(el) {
        var p1 = 0, p2 = 0, p3 = 0, p4 = 0, hdr = document.getElementById('dragHeader');
        if (!hdr) return;

        function startDragging(e) {
            e = e || window.event;
            var clientX = e.type === 'touchstart' ? e.touches[0].clientX : e.clientX;
            var clientY = e.type === 'touchstart' ? e.touches[0].clientY : e.clientY;
            p3 = clientX; p4 = clientY;
            document.onmouseup = stopDragging;
            document.ontouchend = stopDragging;
            document.onmousemove = moveElement;
            document.ontouchmove = moveElement;
        }

        function moveElement(e) {
            e = e || window.event;
            if (e.type === 'touchmove') e.preventDefault(); // Prevent scrolling
            var clientX = e.type === 'touchmove' ? e.touches[0].clientX : e.clientX;
            var clientY = e.type === 'touchmove' ? e.touches[0].clientY : e.clientY;
            p1 = p3 - clientX; p2 = p4 - clientY;
            p3 = clientX; p4 = clientY;
            var nL = el.offsetLeft - p1, nT = el.offsetTop - p2;
            var pr = document.querySelector('.grid-stage').getBoundingClientRect(), er = el.getBoundingClientRect();
            nL = Math.max(0, Math.min(nL, pr.width - er.width));
            nT = Math.max(0, Math.min(nT, pr.height - er.height));
            el.style.left = nL + 'px'; el.style.top = nT + 'px';
        }

        function stopDragging() {
            document.onmouseup = null; document.ontouchend = null;
            document.onmousemove = null; document.ontouchmove = null;
        }

        hdr.onmousedown = startDragging;
        hdr.ontouchstart = startDragging;
    }
    makeDraggable(document.getElementById('dragPanel'));

    function selectSemester(val, el) {
        const label = document.getElementById('selectedSemesterLabel');
        const input = document.getElementById('semesterSelect');
        if (label) label.innerText = val;
        if (input) input.value = val;

        // Clear other active states in semester menu
        if (el) {
            const menu = el.closest('.dropdown-menu');
            if (menu) {
                menu.querySelectorAll('.dropdown-item').forEach(item => {
                    item.classList.remove('active-selection');
                });
                el.classList.add('active-selection');
            }
        }
    }

    function selectDraft(id, label, el) {
        const dLabel = document.getElementById('selectedDraftLabel');
        const dInput = document.getElementById('draftSelect');
        if (dLabel) dLabel.innerText = label;
        if (dInput) dInput.value = id;

        // Clear other active states in draft menu
        if (el) {
            const menu = el.closest('.dropdown-menu');
            if (menu) {
                menu.querySelectorAll('.dropdown-item').forEach(item => {
                    item.classList.remove('active-selection');
                });
                el.classList.add('active-selection');
            }
        }
    }

    function showCreateDraftModal() {
        document.getElementById('createDraftError').style.display = 'none';
        document.getElementById('newDraftNameInput').value = '';
        document.getElementById('newDraftNotesInput').value = '';
        document.getElementById('createDraftModal').style.display = 'flex';
    }

    function hideCreateDraftModal() {
        document.getElementById('createDraftModal').style.display = 'none';
    }

    function submitCreateDraftOnTheFly() {
        const name = document.getElementById('newDraftNameInput').value.trim();
        const notes = document.getElementById('newDraftNotesInput').value.trim();
        const sem = document.getElementById('semesterSelect').value;
        const errorDiv = document.getElementById('createDraftError');
        
        if (!name) {
            errorDiv.innerText = "Draft name is required.";
            errorDiv.style.display = 'block';
            return;
        }
        
        fetch('/api/draft/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name=csrf-token]').content
            },
            body: JSON.stringify({
                name: name,
                semester: sem,
                department: "",
                notes: notes
            })
        })
        .then(res => res.json())
        .then(data => {
            if (!data.ok) {
                errorDiv.innerText = data.error || "An error occurred while creating draft.";
                errorDiv.style.display = 'block';
            } else {
                hideCreateDraftModal();
                const menu = document.getElementById('draftDropdownMenu');
                const label = `${data.draft.name} (${data.draft.semester})`;
                const header = menu.querySelector('.dropdown-header');
                if (header) header.remove();
                
                const li = document.createElement('li');
                li.innerHTML = `<a class="dropdown-item" href="#" onclick="selectDraft('${data.draft.id}', '${label}', this); return false;">${label}</a>`;
                
                const divider = menu.querySelector('.dropdown-divider');
                menu.insertBefore(li, divider);
                selectDraft(data.draft.id, label, li.querySelector('a'));
                
                const badge = document.getElementById('draftCountBadge');
                if (badge) {
                    const count = menu.querySelectorAll('li:not(.dropdown-divider):not(.dropdown-header):not(:last-child)').length;
                    badge.innerText = `${count} Drafts available`;
                }
            }
        })
        .catch(err => {
            errorDiv.innerText = "Connection error: " + err;
            errorDiv.style.display = 'block';
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var cvs = document.getElementById('mainCanvas'), ctx = cvs.getContext('2d');
        var ov = document.getElementById('appOverlay'), ss = document.getElementById('startScreen');
        var hG = document.getElementById('hudGen'), hH = document.getElementById('hudHard');
        var wG = document.getElementById('widGen'), wC = document.getElementById('widConf');
        var log = document.getElementById('logStream'), tmr = document.getElementById('timer');
        var fx = document.getElementById('formulaText'), vs = document.getElementById('victoryScreen');
        var stat = document.getElementById('sysStatus');
        var running = false, mat = null, t0, tInt, pInt, vP = 0, wC2 = 0;
        var SH = parseInt(cvs.dataset.startHour) || 7;
        var LOGS = ["Evaluating population fitness...", "Checking constraints HC-01 to HC-28...", "Resolving Room Overlaps...", "Optimizing Faculty Load...", "Mutating Gene Sequence...", "Calculating Penalty Score...", "Verifying Section Time Blocks...", "Swapping Time Slots...", "Cross-over phase initiated..."];
        var fakeBlocks = [], lastFakeUpdate = 0;

        // Update Dept Selection Count & Row Styling
        function updateDeptCount() {
            const checkboxes = document.querySelectorAll('.dept-checkbox');
            let count = 0;
            checkboxes.forEach(cb => {
                const row = cb.closest('.dropdown-item');
                if (cb.checked) {
                    count++;
                    if (row) row.classList.add('active-selection');
                } else {
                    if (row) row.classList.remove('active-selection');
                }
            });
            const badge = document.getElementById('deptCountBadge');
            if (badge) {
                badge.innerText = count;
                badge.style.display = count > 0 ? 'inline-block' : 'none';
            }
        }
        updateDeptCount();
        document.querySelectorAll('.dept-checkbox').forEach(cb => {
            cb.addEventListener('change', updateDeptCount);
        });

        window.toggleView = function () { ov.classList.toggle('minimized'); setTimeout(rsz, 400); };
        window.confirmAbort = function () {
            if (confirm('Stop generation?')) {
                if (pInt) clearInterval(pInt);
                if (tInt) clearInterval(tInt);
                fetch('/stop-generation', {
                    method: 'POST',
                    headers: { 'X-CSRFToken': document.querySelector('meta[name=csrf-token]').content },
                    keepalive: true
                });
                location.reload();
            }
        };

        function rsz() {
            var par = cvs.offsetParent || cvs.parentElement; if (!par) return;
            var d = window.devicePixelRatio || 1, r = par.getBoundingClientRect();
            cvs.width = r.width * d; cvs.height = r.height * d; cvs.style.width = r.width + 'px'; cvs.style.height = r.height + 'px';
            ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.scale(d, d);
        }
        new ResizeObserver(rsz).observe(cvs.offsetParent || cvs.parentElement); rsz();

        function draw() {
            var d = window.devicePixelRatio || 1, W = cvs.width / d, H = cvs.height / d;
            var isMobile = window.innerWidth < 768;
            var rHW = isMobile ? 40 : 80;
            var hH2 = 30;
            ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, W, H);
            if (!mat) {
                var fRows = 12, fCols = 28;
                var fcW = (W - rHW) / fCols, fcH = (H - hH2) / fRows;

                if (Date.now() - lastFakeUpdate > 300) {
                    fakeBlocks = [];
                    for (var i = 0; i < 25; i++) {
                        var fr = Math.floor(Math.random() * fRows);
                        var fs = Math.floor(Math.random() * (fCols - 4));
                        var fl = 2 + Math.floor(Math.random() * 4);
                        fakeBlocks.push({ r: fr, s: fs, e: fs + fl });
                    }
                    lastFakeUpdate = Date.now();
                }

                ctx.fillStyle = '#f8f9fa'; ctx.fillRect(0, 0, W, H);
                ctx.strokeStyle = '#eee';
                for (var r = 0; r < fRows; r++) for (var c = 0; c < fCols; c++) ctx.strokeRect(rHW + c * fcW, hH2 + r * fcH, fcW, fcH);

                ctx.strokeStyle = '#c5221f'; ctx.fillStyle = '#fce8e6';
                fakeBlocks.forEach(b => {
                    ctx.fillRect(rHW + b.s * fcW + 1, hH2 + b.r * fcH + 1, (b.e - b.s) * fcW - 2, fcH - 2);
                    ctx.strokeRect(rHW + b.s * fcW, hH2 + b.r * fcH, (b.e - b.s) * fcW, fcH);
                });

                ctx.fillStyle = 'rgba(255,255,255,0.6)'; ctx.fillRect(0, 0, W, H);
                ctx.fillStyle = '#c5221f'; ctx.font = 'bold 14px monospace'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
                ctx.fillText('INITIALIZING POPULATION...', W / 2, H / 2 - 10);
                ctx.fillStyle = '#666'; ctx.font = '11px monospace';
                ctx.fillText('Building chromosomes and evaluating fitness', W / 2, H / 2 + 12);
                requestAnimationFrame(draw); return;
            }
            var rows = mat.rooms, cols = mat.cols, rNames = mat.room_names || [];
            var cW = (W - rHW) / cols, cH = (H - hH2) / rows;
            ctx.lineWidth = 1; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';

            // ── Hour header ──
            ctx.fillStyle = '#f8f9fa'; ctx.fillRect(0, 0, W, hH2);
            ctx.fillStyle = '#5f6368'; ctx.font = '10px Roboto';
            for (var c = 0; c < cols; c++) {
                var x = rHW + c * cW;
                ctx.strokeStyle = '#e0e0e0'; ctx.strokeRect(x, 0, cW, hH2);
                if (c % 2 === 0) {
                    var h24 = SH + c * 0.5, h12 = h24 === 12 ? 12 : h24 % 12 || 12, ap = h24 < 12 ? 'AM' : 'PM';
                    var timeText = Math.floor(h12) + (isMobile ? '' : ap);
                    ctx.fillText(timeText, x + cW / 2, hH2 / 2);
                }
            }

            // ── Room label column ──
            ctx.fillStyle = '#f8f9fa'; ctx.fillRect(0, hH2, rHW, H);
            for (var r = 0; r < rows; r++) {
                var y = hH2 + r * cH;
                ctx.strokeStyle = '#e0e0e0'; ctx.strokeRect(0, y, rHW, cH);
                ctx.fillStyle = '#5f6368';
                ctx.font = isMobile ? '8px Roboto' : '9px Roboto';
                var rLabel = rNames[r] || ('RM ' + (r + 1));
                // Truncate long names
                var maxLen = isMobile ? 6 : 12;
                if (rLabel.length > maxLen) rLabel = rLabel.substring(0, maxLen - 1) + '…';
                ctx.fillText(rLabel, rHW / 2, y + cH / 2);
            }

            // ── Empty grid lines ──
            ctx.strokeStyle = '#e0e0e0';
            for (var r = 0; r < rows; r++) {
                for (var c = 0; c < cols; c++) {
                    ctx.strokeRect(rHW + c * cW, hH2 + r * cH, cW, cH);
                }
            }

            // ── Draw blocks (real GA data) ──
            for (var r = 0; r < rows; r++) {
                var roomBlocks = mat.blocks[r] || [];
                var y = hH2 + r * cH;
                for (var bi = 0; bi < roomBlocks.length; bi++) {
                    var blk = roomBlocks[bi];
                    var st = blk.start, en = blk.end;
                    // victory sweep animation
                    if (vP === 1 && st > wC2) continue;
                    var bx = rHW + st * cW, bw = (en - st) * cW;
                    var v = blk.status;
                    var bg, fg, bc;
                    if (v === 2) { bg = '#fce8e6'; fg = '#c5221f'; bc = '#c5221f'; }
                    else if (v === 3) { bg = '#e8f0fe'; fg = '#1a73e8'; bc = '#1a73e8'; }
                    else { bg = '#e6f4ea'; fg = '#137333'; bc = '#137333'; }
                    ctx.fillStyle = bg; ctx.fillRect(bx + 1, y + 1, bw - 2, cH - 2);
                    // Conflict corner marker
                    if (v === 2) {
                        ctx.fillStyle = fg;
                        ctx.beginPath(); ctx.moveTo(bx + bw - 8, y + 4); ctx.lineTo(bx + bw - 2, y + 4); ctx.lineTo(bx + bw - 2, y + 10); ctx.fill();
                    }
                    ctx.strokeStyle = bc; ctx.strokeRect(bx, y, bw, cH);
                    // Labels — only if cell is tall enough and wide enough
                    if (cH > 20 && bw > 30) {
                        ctx.fillStyle = fg;
                        ctx.font = 'bold 9px Roboto';
                        ctx.fillText(blk.course, bx + bw / 2, y + cH / 2 - 6);
                        ctx.font = 'normal 8px Roboto';
                        ctx.fillText(blk.faculty, bx + bw / 2, y + cH / 2 + 6);
                    }
                }
            }
            if (vP === 1) { wC2 += 0.5; if (wC2 > cols) vP = 2; }
            requestAnimationFrame(draw);
        }

        window.closeFeasibility = function () {
            document.getElementById('feasibilityModal').style.display = 'none';
            document.getElementById('igniteBtn').disabled = false;
            document.getElementById('igniteBtn').innerText = 'Check Room Capacity';
        };

        document.getElementById('igniteBtn').addEventListener('click', function () {
            var btn = this;
            var sem = document.getElementById('semesterSelect').value;
            var isFresh = document.getElementById('freshStartCheck').checked;
            var selectedDepts = Array.from(document.querySelectorAll('.dept-checkbox:checked')).map(function (cb) { return cb.value; });
            var draftId = document.getElementById('draftSelect') ? document.getElementById('draftSelect').value : null;

            if (selectedDepts.length === 0) {
                alert("Please select at least one department.");
                return;
            }

            if (!draftId) {
                alert("Please select or create an Active Draft Version before proceeding.");
                return;
            }

            btn.disabled = true;
            btn.innerText = 'Validating...';

            // ── Step 1: Pre-Feasibility Check (Gatekeeper) ──────────────────
            document.getElementById('checkLoadingOverlay').style.display = 'flex';

            fetch('/api/check-feasibility', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name=csrf-token]').content },
                body: JSON.stringify({ semester: sem, scheduled_depts: selectedDepts, draft_version_id: draftId })
            })
                .then(r => r.json())
                .then(report => {
                    document.getElementById('checkLoadingOverlay').style.display = 'none';
                    btn.innerText = 'Check Room Capacity'; // Reset text
                    btn.disabled = false;
                    try {
                        showFeasibilityReport(report, sem, isFresh, selectedDepts);
                    } catch (uiErr) {
                        console.error("UI Render Error:", uiErr);
                    }
                })
                .catch(err => {
                    document.getElementById('checkLoadingOverlay').style.display = 'none';
                    btn.innerText = 'Check Room Capacity';
                    btn.disabled = false;
                    console.error("Network/Server Error:", err);
                    alert("Feasibility Check failed. Please check your connection or server logs.");
                });
        });

        let currentFeasibilityReport = null;

        window.switchFeasibilityLevel = function (lvlKey) {
            if (!currentFeasibilityReport) return;
            const lvls = currentFeasibilityReport.levels;
            const data = lvls[lvlKey];

            // Toggle Card State
            ['l1', 'l2', 'l3'].forEach(k => {
                const c = document.getElementById(`card-${k}`);
                if (c) c.classList.toggle('active', k === lvlKey);
            });

            // Update Titles
            const ut = document.getElementById('utilTitle');
            const ot = document.getElementById('overflowTitle');
            if (ut) ut.innerText = `Room Utilization (${data.label})`;
            if (ot) ot.innerText = `Overflow Subjects (${data.label})`;

            // Render Utilization
            const utilList = document.getElementById('utilizationList');
            if (utilList) {
                utilList.innerHTML = '';
                const sortedRooms = Object.entries(data.utilization).sort((a, b) => b[1].utilization - a[1].utilization);
                sortedRooms.forEach(([rid, roomData]) => {
                    const pct = roomData.utilization;
                    const color = pct > 90 ? 'bg-crit' : (pct > 70 ? 'bg-warn' : 'bg-safe');
                    const row = document.createElement('div');
                    row.className = 'util-row';
                    row.innerHTML = `
                        <div class="d-flex justify-content-between small">
                            <span>${roomData.name}</span>
                            <span class="fw-bold">${pct}%</span>
                        </div>
                        <div class="util-bar-bg">
                            <div class="util-bar-fill ${color}" style="width: ${pct}%"></div>
                        </div>
                    `;
                    utilList.appendChild(row);
                });
            }

            // Render Overflow
            const list = document.getElementById('overflowList');
            const sec = document.getElementById('overflowSection');
            const noMsg = document.getElementById('noOverflowMsg');
            if (list) {
                list.innerHTML = '';
                if (data.overflow > 0) {
                    if (sec) sec.style.display = 'block';
                    if (noMsg) noMsg.style.display = 'none';
                    for (let course in data.details) {
                        const li = document.createElement('li');
                        li.className = 'mb-1';
                        li.innerHTML = `<span class="badge bg-light text-dark border me-1">${course}</span> ${data.details[course].join(', ')}`;
                        list.appendChild(li);
                    }
                } else {
                    if (sec) sec.style.display = 'none';
                    if (noMsg) noMsg.style.display = 'block';
                }
            }
        };

        function showFeasibilityReport(report, sem, isFresh, depts) {
            const modal = document.getElementById('feasibilityModal');
            const mainContent = document.getElementById('feasibilityMainContent');
            const errorContent = document.getElementById('feasibilityErrorContent');
            const footer = document.getElementById('feasibilityFooter');
            const contBtn = document.getElementById('confirmContinueBtn');

            modal.style.display = 'flex';

            try {
                // If the report is invalid, has no levels, or has a server error status
                if (!report || report.error || !report.levels || (report.summary && report.summary.status === 'RED' && report.summary.message && report.summary.message.includes('Server Error'))) {
                    throw new Error(report ? (report.error || (report.summary ? report.summary.message : "")) : "Invalid feasibility data");
                }

                currentFeasibilityReport = report;
                const summary = report.summary;
                const lvls = report.levels;

                if (mainContent) mainContent.style.display = 'block';
                if (errorContent) errorContent.style.display = 'none';
                if (footer) footer.style.display = 'flex';
                if (contBtn) contBtn.style.display = 'block';

                document.getElementById('statTotal').innerText = report.total_sessions;

                // 1. Overall Summary Verdict
                const alertBox = document.getElementById('feasibilityAlert');
                const statusLabel = document.getElementById('summaryStatus');
                const messageLabel = document.getElementById('summaryMessage');
                const iconBox = document.getElementById('summaryIcon');

                statusLabel.innerText = summary.status;
                messageLabel.innerText = summary.message;

                let colorClass = 'alert-success';
                let icon = '<i class="bi bi-check-circle-fill text-success"></i>';
                if (summary.status === 'YELLOW') colorClass = 'alert-info';
                if (summary.status === 'ORANGE') { colorClass = 'alert-warning'; icon = '<i class="bi bi-exclamation-triangle-fill text-warning"></i>'; }
                if (summary.status === 'RED') { colorClass = 'alert-danger'; icon = '<i class="bi bi-x-circle-fill text-danger"></i>'; }

                alertBox.className = `alert mb-4 shadow-sm ${colorClass}`;
                iconBox.innerHTML = icon;

                // 2. Levels Summary Badges
                const setLevelBadge = (id, data) => {
                    const badge = document.getElementById(id + 'Badge');
                    const overflow = document.getElementById(id + 'Overflow');
                    badge.className = data.feasible ? 'badge badge-feasible' : 'badge badge-overflow';
                    badge.innerText = data.feasible ? 'FEASIBLE' : 'OVERFLOW';
                    overflow.innerText = data.overflow;
                };
                setLevelBadge('lvl1', lvls.l1);
                setLevelBadge('lvl2', lvls.l2);
                setLevelBadge('lvl3', lvls.l3);

                // Level 2 Extra Needs (Specific to Realistic)
                const needBox = document.getElementById('lvl2Needed');
                if (lvls.l2.needed && (lvls.l2.needed.lec > 0 || lvls.l2.needed.lab > 0)) {
                    needBox.style.display = 'block';
                    let txt = 'Need: ';
                    if (lvls.l2.needed.lec > 0) txt += `+${lvls.l2.needed.lec} Lec `;
                    if (lvls.l2.needed.lab > 0) txt += `+${lvls.l2.needed.lab} Lab`;
                    needBox.innerText = txt;
                } else {
                    needBox.style.display = 'none';
                }

                // Default to Level 2 view
                switchFeasibilityLevel('l2');

                // Confirm Button (Step 2)
                const hasOverflow = lvls.l2.overflow > 0;

                if (!hasOverflow) {
                    contBtn.innerHTML = '<i class="bi bi-play-fill"></i> Start AI Generation';
                    contBtn.className = 'btn btn-success fw-bold p-3';
                    contBtn.style.flex = '1';
                } else {
                    contBtn.innerHTML = '<i class="bi bi-exclamation-triangle"></i> Continue with TBA';
                    contBtn.className = 'btn btn-warning fw-bold p-3';
                    contBtn.style.flex = '1';
                }

                contBtn.onclick = function () {
                    modal.style.display = 'none';
                    igniteGeneration(sem, isFresh, depts);
                };

            } catch (err) {
                console.error("Feasibility UI Render Error, showing idle fallback:", err);

                if (mainContent) mainContent.style.display = 'none';
                if (errorContent) errorContent.style.display = 'flex';
                if (contBtn) contBtn.style.display = 'none';

                // Bind the Reconnect Button
                const recBtn = document.getElementById('feasibilityReconnectBtn');
                if (recBtn) {
                    recBtn.onclick = function () {
                        try {
                            // Store the current user's selections to automatically restore them on page refresh
                            localStorage.setItem('retry_semester', document.getElementById('semesterSelect').value);
                            localStorage.setItem('retry_fresh', document.getElementById('freshStartCheck').checked);

                            var selectedDepts = Array.from(document.querySelectorAll('.dept-checkbox:checked')).map(function (cb) { return cb.value; });
                            localStorage.setItem('retry_depts', JSON.stringify(selectedDepts));
                            localStorage.setItem('autoTriggerFeasibility', 'true');
                        } catch (storageErr) {
                            console.error("Failed to write state to localStorage:", storageErr);
                        }

                        modal.style.display = 'none';
                        window.location.reload();
                    };
                }
            }
        }



        function igniteGeneration(sem, isFresh, selectedDepts) {
            var draftId = document.getElementById('draftSelect') ? document.getElementById('draftSelect').value : null;
            if (!draftId) {
                alert("Please select or create an Active Draft Version before proceeding.");
                return;
            }
            ss.style.display = 'none'; running = true; stat.innerText = 'Running...'; rsz(); requestAnimationFrame(draw);
            while (log.firstChild) log.removeChild(log.firstChild);
            t0 = Date.now(); tInt = setInterval(function () { var d = Date.now() - t0, dt = new Date(d); tmr.innerText = dt.toISOString().substr(11, 8); }, 1000);

            fetch('/start-generation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name=csrf-token]').content },
                body: JSON.stringify({ semester: sem, fresh_start: isFresh, scheduled_depts: selectedDepts, draft_version_id: draftId })
            })
                .then(r => r.json())
                .then(function () {
                    var lastG = 0;
                    pInt = setInterval(function () {
                        fetch('/get-generation-status').then(r => r.json()).then(d => {
                            if (d.visual_matrix) mat = d.visual_matrix;
                            var hc = d.hard_conflicts || 0, sc1 = d.sc1_violations || 0, sc2 = d.sc2_violations || 0;
                            hG.innerText = d.generation;
                            hH.innerText = hc;
                            hH.className = hc > 0 ? 'metric-val text-red' : 'metric-val text-green';
                            wG.innerText = 'Gen ' + d.generation;
                            wC.innerText = hc > 0 ? hc + ' HC' : (sc1 + sc2 > 0 ? (sc1 + sc2) + ' SC' : '✓ 0');
                            var bd = document.getElementById('hudConflictBreakdown');
                            if (bd) bd.innerText = 'HC:' + hc + '  SC-I:' + sc1 + '  SC-II:' + sc2;

                            if (d.hardware) {
                                var hw = d.hardware;
                                var b = document.getElementById('hwBadge');
                                var l = document.getElementById('hwLabel');
                                var t = document.getElementById('hudTarget');
                                var g = document.getElementById('hudGPS');

                                if (b) {
                                    b.innerText = hw.mode + ' Mode';
                                    b.className = 'hw-badge ' + (hw.mode === 'Performance' ? 'hw-perf' : (hw.mode === 'Balanced' ? 'hw-bal' : 'hw-eff'));
                                }
                                if (l) l.innerText = hw.label;
                                if (t && hw.target_gens) t.innerText = hw.target_gens.toLocaleString();
                                if (g) g.innerText = (d.gen_per_sec || 0).toFixed(1);
                            }

                            if (d.generation === 0 && !d.done) {
                                fx.innerText = '=INITIALIZE(population=' + (d.pop_size || '...') + ')';
                                if (!document.getElementById('initLogEntry')) {
                                    var iv = document.createElement('div'); iv.className = 'log-item'; iv.id = 'initLogEntry';
                                    iv.innerText = '⚙ Building initial population — evaluating chromosomes in parallel...';
                                    log.appendChild(iv);
                                }
                            }
                            if (d.generation > 0 && document.getElementById('initLogEntry')) {
                                document.getElementById('initLogEntry').remove();
                            }
                            if (d.generation > lastG) {
                                var div = document.createElement('div'); div.className = 'log-item';
                                div.innerText = 'Gen ' + d.generation + ': ' + LOGS[Math.floor(Math.random() * LOGS.length)];
                                log.appendChild(div); while (log.children.length > 60) log.removeChild(log.firstChild);
                                log.scrollTop = log.scrollHeight;
                                fx.innerText = hc === 0 ? '=SOFT_OPTIMIZE(gen=' + d.generation + ',sc=' + (sc1 + sc2) + ')' : '=RESOLVE_HC(gen=' + d.generation + ',hc=' + hc + ')';
                                lastG = d.generation;
                            }
                            if (d.done) {
                                clearInterval(pInt); clearInterval(tInt); running = false; stat.innerText = 'Saved'; fx.innerText = '=COMPLETE()';
                                document.getElementById('finalConflictCount').innerText = hc;
                                var fb = document.getElementById('finalConflictBreakdown');
                                if (fb) fb.innerText = 'HC: ' + hc + '  |  SC-I: ' + sc1 + '  |  SC-II: ' + sc2;
                                document.querySelector('#victoryScreen h2').innerText = (hc === 0 && sc1 === 0 && sc2 === 0) ? 'Perfect Schedule!' : 'Optimization Complete';
                                var ic = document.querySelector('#victoryScreen .bi-check-circle-fill,#victoryScreen .bi-exclamation-circle-fill');
                                if (ic) ic.className = (hc === 0 && sc1 === 0 && sc2 === 0) ? 'bi bi-check-circle-fill display-2' : 'bi bi-exclamation-circle-fill display-2 text-warning';
                                var fgen = document.getElementById('finalGenerations');
                                if (fgen) fgen.innerText = ((d.total_generations || d.generation || 0)).toLocaleString() + ' gens';
                                var ftm = document.getElementById('finalTime');
                                if (ftm) { var secs = d.total_time ? Math.round(d.total_time) : Math.round((Date.now() - t0) / 1000); ftm.innerText = Math.floor(secs / 60) + 'm ' + (secs % 60) + 's'; }
                                vP = 1; setTimeout(function () { vs.style.display = 'flex'; }, 3000);
                            }
                        });
                    }, 100);
                });
        }
    });

    // ── Auto-trigger Feasibility Check on page reload (state restoration) ──────────────────
    document.addEventListener('DOMContentLoaded', function () {
        try {
            if (localStorage.getItem('autoTriggerFeasibility') === 'true') {
                localStorage.removeItem('autoTriggerFeasibility'); // Prevent infinite loops

                var savedSem = localStorage.getItem('retry_semester');
                var savedFresh = localStorage.getItem('retry_fresh');
                var savedDeptsStr = localStorage.getItem('retry_depts');

                if (savedSem && document.getElementById('semesterSelect')) {
                    document.getElementById('semesterSelect').value = savedSem;
                }
                if (savedFresh && document.getElementById('freshStartCheck')) {
                    document.getElementById('freshStartCheck').checked = (savedFresh === 'true');
                }
                if (savedDeptsStr) {
                    var savedDepts = JSON.parse(savedDeptsStr);
                    document.querySelectorAll('.dept-checkbox').forEach(function (cb) {
                        cb.checked = savedDepts.includes(cb.value);
                    });
                    if (typeof updateDeptCount === 'function') {
                        updateDeptCount();
                    }
                }

                // Trigger the check after a short delay to let the page fully settle
                setTimeout(function () {
                    var igniteBtn = document.getElementById('igniteBtn');
                    if (igniteBtn) {
                        console.log("Automatically auto-triggering Capacity Assessment after reload...");
                        igniteBtn.click();
                    }
                }, 400);
            }
        } catch (err) {
            console.error("Error during auto-trigger restoration:", err);
        }
    });
