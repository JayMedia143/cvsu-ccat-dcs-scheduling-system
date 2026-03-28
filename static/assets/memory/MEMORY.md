# CvSU Scheduling System — Session Memory

## Project
- CvSU Scheduling System Version 2 (antigravity_2_claude branch)
- **Active folder (v2.25):** `c:\WFH\jeremy\12. CvSU_Scheduling_System-Version-2.25_send\CvSU_Scheduling_System-Version-2 - antigravity_2_claude - Copy`
- Previous folder (v2.24): `c:\WFH\jeremy\10. CvSU_Scheduling_System-Version-2.24_send\...` — do NOT edit this one
- CLAUDE.md at project root

## Stack
- Python + Flask 3.1.1, SQLite (site.db), Jinja2 templates
- Genetic Algorithm in genetic_algorithm.py
- Frontend: Vanilla JS + custom CSS (no framework)
- venv at ./venv/

## Key Files
- `app.py` — all routes + DB models
- `genetic_algorithm.py` — scheduling engine
- `site.db` — SQLite DB

## User Preferences
- Communicates in Taglish (Tagalog + English mix)
- Prefers concise responses

## Pending / Deferred
- `session_type` tracking in Gene class — low risk, optional
- Bare `except: pass` in `app.py` — cosmetic only (~9 locations)
- `debug=True` + `host='0.0.0.0'` in app.py — dev only, not a bug

## New DB models (2026-03-27)
- `student.is_irregular` BOOLEAN DEFAULT 0 (migration added)
- `IrregularAssignment` table: student_id_fk, semester, assignments_json, requested_json, created_at, updated_at

## New Routes (2026-03-27)
- `GET /manage/irregular-students` → manage_irregular.html
- `POST /manage/student/toggle-irregular/<id>` → toggle is_irregular flag
- `GET /irregular-pathfinder/<id>` → irregular_pathfinder.html
- `POST /api/irregular-pathfinder/<id>` → runs solver, returns JSON
- `POST /api/irregular-confirm/<id>` → saves confirmed assignment
- `POST /api/irregular-batch` → batch solver for multiple students

## Unresolved Bugs (as of 2026-03-26) — [details](project_bugs_2026_03_26.md)
- **Images disappear on 2nd view** — BytesIO exhausted in cached openpyxl ws; fix: pre-cache bytes in `_get_cached_template` into `ws._cached_img_bytes`
- **Z-order "Below Text" still on top** — need `isolation:isolate` + z-index:0/1/2 layers in `render_excel_to_html`
- **Login flash** — dashboard visible split-second before loader; fix: body starts hidden, JS reveals after loader shown
- **Generate schedule 400** — CSRF token missing in fetch() calls in `generate_schedule.html`

## New Routes Added (2026-03-26)
- `GET /download/faculty-loading-template` → downloads Faculty Loading Template.xlsx (on-the-fly)
- `GET /download/curriculum-template` → downloads Curriculum Import Template.docx (BSCoS sample, on-the-fly)
- `POST /import_courses_docx` → imports curriculum from .docx Word file (python-docx parser)

## DB Migrations Done (site.db)
- `faculty.available_days` TEXT
- `faculty.academic_rank` VARCHAR(100)
- `faculty.sex` VARCHAR(1) — 'M' or 'F', nullable
- `faculty_assignment`: 8 split columns
- `system_settings` layout columns (margins, paper_size, fac_* columns, signatory fields)
- `scheduled_class.session_type` VARCHAR(10) DEFAULT 'Lec'
- Constraint table: 29 HC + 5 SC-I + 6 SC-II = 40 total
- `pre_assignment.deleted_at` DATETIME nullable (added 2026-03-24)
- `system_settings.section/faculty/room/course_img_settings` TEXT (4 columns, per-image x/y/scale/z-order)
- `system_settings.blocked_slots_json` TEXT (blocked time slots JSON array)
- `user.department` VARCHAR(100) nullable (added 2026-03-28 — used by schedule_editor route for reliable dept detection)

## Important Notes
- `room.special_course_ids` always blank — use pre_assignments for special course detection
- Lec-only rooms subject to div4: A1–A5 only (University Field = NSTP special room)
- After GA/Pending Faculty, only `ScheduledClass` has data — all "what faculty teaches" must read from it
- Only ONE T.B.A. room needed (capacity=999, multi-assignment)
- 16 unused .py files deleted from both v2.24 and v2.25 (patch_*.py, check_*.py, GA backup/hybrid, grant_admin, populate_dcs*, test_borders, tba_output.txt)

## Feedback
- [feedback_css_in_html_quotes.md](feedback_css_in_html_quotes.md) — Never double-quote CSS values inside `style="..."` HTML attributes
- [feedback_openpyxl_bytesio.md](feedback_openpyxl_bytesio.md) — Never call img._data() twice on cached openpyxl Image; PIL closes BytesIO permanently

## Completed Work — Chronological Index

| Date | File | Summary |
|------|------|---------|
| 2026-03-13 | — | [project_system_status.md](project_system_status.md) — Pre-regen snapshot |
| 2026-03-16 | app.py + templates | [project_fixed_layout_overhaul.md](project_fixed_layout_overhaul.md) — LuckySheet removed, openpyxl→HTML, iframe timetable |
| 2026-03-17 | app.py + CSS | [project_section_preview_pixel_perfect.md](project_section_preview_pixel_perfect.md) — Pixel-perfect style engine |
| 2026-03-17 | app.py | Static text swapping: `build_static_cell_overrides()`, `build_faculty_cell_overrides()` |
| 2026-03-19 | app.py + GA | [project_faculty_features.md](project_faculty_features.md) — Day Split, Lec/Lab separation, Profile Offcanvas, HC-29 |
| 2026-03-20 | GA | [project_ga_improvements.md](project_ga_improvements.md) — 6 GA speed/strength improvements |
| 2026-03-20 | app.py | [project_schedule_overlays.md](project_schedule_overlays.md) — Schedule overlay feature |
| 2026-03-20 | app.py | [project_performance_fixes.md](project_performance_fixes.md) — Template cache + joinedload N+1 fix |
| 2026-03-20 | app.py + GA | [project_bug_fixes_2026_03_20b.md](project_bug_fixes_2026_03_20b.md) — schedule-issues page, HC-16, HC=1 stagnation, victory panel, GA init stall |
| 2026-03-20 | templates | [project_viewtimetable_zoom.md](project_viewtimetable_zoom.md) — Ctrl+Scroll zoom (pointer-events passthrough) |
| 2026-03-20 | app.py + GA | [project_system_scan_fixes.md](project_system_scan_fixes.md) — System scan: faculty.sex migration, crossover pairing, locked_day fallback |
| 2026-03-21 | app.py + GA + seeders | [project_bug_fixes_2026_03_21.md](project_bug_fixes_2026_03_21.md) — seeder semester fix, GA faculty filter, TBA fill, Pending Faculty, WORKLOAD |
| 2026-03-21 | app.py + GA | [project_bug_fixes_2026_03_21b.md](project_bug_fixes_2026_03_21b.md) — TBA persistence, fa_map enforcement, available days, Quick Add TBA, TBA room protection |
| 2026-03-22 | app.py + GA + templates | [project_bug_fixes_2026_03_22.md](project_bug_fixes_2026_03_22.md) — Split-aware workload, HC-09 group-sum, preferred_room sibling pairing |
| 2026-03-22 | seeder1–9 | [project_bug_fixes_2026_03_22b.md](project_bug_fixes_2026_03_22b.md) — Faculty 4 fields, HC-27/28/29, B-room dept restriction |
| 2026-03-23 | v2.24 folder | [project_cleanup_2026_03_23.md](project_cleanup_2026_03_23.md) — 17 code fixes + 16 file deletions (applied to v2.24) |
| 2026-03-24 | v2.25 folder | [project_v225_scan_fixes_2026_03_24.md](project_v225_scan_fixes_2026_03_24.md) — Full v2.25 scan: all 22 findings fixed (C-1–C-8, H-1–H-4, M-1–M-7, L-1/L-4) |
| 2026-03-24 | app.py + templates | [project_bug_fixes_2026_03_24b.md](project_bug_fixes_2026_03_24b.md) — Recycle Bin modal fixes, PreAssignment deleted_at migration, nav reordering, duplicate copyCurriculum fix |
| 2026-03-24 | app.py + templates | [project_bug_fixes_2026_03_24c.md](project_bug_fixes_2026_03_24c.md) — Pending pages: sort dropdowns, pagination style, redirect fix, room deletion orphan fix, TBA timetable fallback, conflict detection on all 3 pending saves, fake "All Set!" removed |
| 2026-03-24 | login.html + signup.html + style.css | [project_auth_ui_redesign_2026_03_24.md](project_auth_ui_redesign_2026_03_24.md) — Full auth page redesign: dark left panel, 3D floating schedule card (9-col × 6-row, 40px slots, 680px max-width, perspective 900px), horizontal brand group, space-between 3-child layout; subtitle "Semi-automated…", footer "© 2025–2026 CvSU-CCAT Scheduling System" — **FINALIZED** |
| 2026-03-25 | requirements.txt | [project_requirements_cleanup_2026_03_25.md](project_requirements_cleanup_2026_03_25.md) — Cleaned 157-pkg pip-freeze dump → 11 direct deps; added missing pdfplumber==0.11.9, fixed Pillow 11→12.1.1, removed tensorflow/keras/jupyter/Flask-SSE/redis bloat |
| 2026-03-25 | app.py + 4 templates | [project_student_masterlist_2026_03_25.md](project_student_masterlist_2026_03_25.md) — Phase 2 Item 1: Student model, CRUD, archive, portal, schedule view, Excel import, Portal URL sharing, view_schedule_modal 'student' type |
| 2026-03-25 | app.py | [project_security_fixes_2026_03_25.md](project_security_fixes_2026_03_25.md) — 10 security fixes: session fixation, secret key, open redirect, exception leak, year_level validation, view_schedule_modal @role_required, student portal rate limiting, student_id/email validation |
| 2026-03-25 | app.py + base.html + student_schedule.html | [project_user_side_bugs_2026_03_25.md](project_user_side_bugs_2026_03_25.md) — 3 bugs: section/room timetable logo invisible (left_offset_px=-30→20), semester filter hidden from user role, print button try-catch |
| 2026-03-25 | app.py + genetic_algorithm.py | [project_image_zorder_bytesio_2026_03_25.md](project_image_zorder_bytesio_2026_03_25.md) — Z-order fix (isolation:isolate + z-index layers); BytesIO exhaustion fix (pre-cache bytes in _get_cached_template) |
| 2026-03-25 | base.html + style.css + generate_schedule.html + app.py + genetic_algorithm.py | [project_login_loader_csrf_blocked_slots_2026_03_25.md](project_login_loader_csrf_blocked_slots_2026_03_25.md) — Login flash fix (head script + CSS class); Generate 400 fix (X-CSRFToken headers); Blocked Time Slots feature (global settings + GA bitmask enforcement) |
| 2026-03-26 | base.html | Blocked slots overlap validation — JS `addBlockedSlot()` already had overlap check; confirmed correct |
| 2026-03-26 | — | requirements.txt: 11 direct deps (added python-docx==1.2.0) — now complete |
| 2026-03-26 | style.css + student_portal.html | Student page: added `.student-row.selected td` green highlight CSS; removed "Are you an admin? Sign in" from student portal |
| 2026-03-26 | app.py + manage_faculty.html | Faculty Loading import: new `GET /download/faculty-loading-template` route (on-the-fly xlsx with sample data + notes); Download Template button added to importLoadingModal |
| 2026-03-26 | app.py + manage_courses.html | Curriculum: restored `import_courses_pdf` to pdfplumber (PDF); added new `POST /import_courses_docx` + `GET /download/curriculum-template` (BSCoS sample .docx); added Word import button + `#importWordModal` |
| 2026-03-26 | manage_courses.html + manage_faculty.html | Button design consistency: removed `text-*` + `border-*` color modifiers from all import buttons to match plain `btn-google-action` style of student page |
| 2026-03-26 | requirements.txt | Added `python-docx==1.2.0` (used by import_courses_docx + download_curriculum_template; was installed in venv but missing from requirements.txt) |
| 2026-03-27 | app.py + 4 templates | [project_irregular_pathfinder_2026_03_27.md](project_irregular_pathfinder_2026_03_27.md) — Phase 2 Module 2: Irregular Student Pathfinder — IrregularAssignment model, solver algorithm (majority-rule anchor + backtracking), manage_irregular.html, irregular_pathfinder.html, student_schedule.html (irreg branch), manage_students.html (toggle + puzzle icon), base.html nav link |
| 2026-03-27 | 5 files (templates + style.css) | [project_irregular_module_polish_2026_03_27.md](project_irregular_module_polish_2026_03_27.md) — Rounds 2–4 polish: purple icon removal, `.bulk-btn` CSS fix, inline error in add modal, `active` class box fix, irregular_pathfinder full rewrite (clickable cards, grouped results, confirm modal, redirect to manage_irregular), batch modal rename, smart bulk-confirm message using `data-irregular` |
| 2026-03-27 | app.py + base.html + style.css + schedule_editor.html (new) | [project_module3_drafting_overrides_2026_03_27.md](project_module3_drafting_overrides_2026_03_27.md) — Phase 2 Module 3: Global AI-Lock toggle, DraftVersion model, 10 new API routes, interactive Schedule Editor grid (drag-drop + conflict guard + draft layer), CSS for block states |
| 2026-03-27 | app.py + schedule_editor.html | Module 3 fully functional: N+1 fix (joinedload in entries routes + conflict check), detailed conflict labels (course+time), PATCH /api/schedule/<id>, full grid redesign → calendar-column layout (1px=1min, position:absolute blocks), CSRF hidden input fix, hover tooltip, click-to-edit modal, loading spinner, auto-fill add form, draft entry counter, network error handling |
| 2026-03-28 | app.py + schedule_editor.html | [project_module3_scan_fixes_2026_03_28.md](project_module3_scan_fixes_2026_03_28.md) — Module 3 scan: all 12 issues fixed (Fix 1: room auto-fill, Fix 2: AI-Lock toggle button, Fix 3: locked GA modal disabling, Fix 4: publishDraft alert→toast, Fix 6: entry count in draft panel, Fix 7: dead error check removed, Fix 8: end time auto-adjust, Fix 9: api_move_class success→ok, Fix 10: User.department column+migration, Fix 11: block-tiny CSS, Fix 12: empty state message) |
| 2026-03-28 | app.py + schedule_editor.html + base.html | [project_module3_manage_drafts_2026_03_28.md](project_module3_manage_drafts_2026_03_28.md) — Draft UX: selection bug fixes (data-name attr + addEventListener), all-drafts modal redesign (table+search+pagination), manage drafts modal (edit/delete/create per row), PATCH /api/draft/<id> route, topbar cleanup (removed New Draft + Delete Draft buttons), left panel max-4 + "View all" link, unified create/edit modal (#newDraftModal handles both), nav active state removed from Schedule Editor, btn-google-action for New Draft buttons |
| 2026-03-28 | app.py + schedule_editor.html | [project_manage_drafts_fix_2026_03_28b.md](project_manage_drafts_fix_2026_03_28b.md) — Manage Drafts fix: left panel max 2 cards + green theme, two-panel in-modal (openMdfCreate/openMdfEdit/closeMdfForm/submitMdfForm), Cache-Control: no-store on schedule_editor route (permanent browser cache fix), null guards in openMdfCreate/openMdfEdit, removed dead openEditDraftModal + openNewDraftFromManage |

## Security
- [project_security_plan.md](project_security_plan.md) — Old plan (superseded)
- [project_security_fixes_2026_03_25.md](project_security_fixes_2026_03_25.md) — **IMPLEMENTED** 2026-03-25 — 10 fixes applied

## GA Architecture References
- [ga_architecture.md](ga_architecture.md) — GA internals, thesis defense level
- [ga_teaching.md](ga_teaching.md) — Teaching session progress
