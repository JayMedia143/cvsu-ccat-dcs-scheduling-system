---
name: Fixed Layout Overhaul (Phases 1–6 + UI Refinements)
description: Complete removal of LuckySheet and replacement with Fixed Excel-Based Template System — all phases + manage_layouts.html UI refinements COMPLETED 2026-03-16
type: project
---

# Fixed Layout Overhaul — COMPLETED 2026-03-16

## Mission
Completely removed LuckySheet from the project. Replaced with a Fixed Excel-Based Template System where:
- Admin uploads a `.xlsx` file as visual template
- System renders it as pixel-perfect static HTML (borders, fonts, merged cells, colors, logo)
- Dynamic text injected via `{{token}}` placeholders from SystemSettings
- Schedule grid data overlaid via cell_overrides (no worksheet mutation)
- PDF export via WeasyPrint

**Why:** LuckySheet was unreliable — JSON state files, broken CDN dependencies, fragile rendering.

---

## 19 SystemSettings Variables (Section Layout)

| Token | Field | Default |
|---|---|---|
| `{{republic_text}}` | republic_text | "Republic of the Philippines" |
| `{{university_name}}` | section_school_name | "CAVITE STATE UNIVERSITY" |
| `{{campus_name}}` | section_campus_name | "CCAT Campus" |
| `{{address}}` | section_address | "Rosario, Cavite" |
| `{{contact_details}}` | contact_details | "(046) 437-9505 / (046) 437-6659" |
| `{{email}}` | email | "cvsurosario@cvsu.edu.ph" |
| `{{website}}` | website | "www.cvsu-rosario.edu.ph" |
| `{{section_name}}` | (dynamic per entity) | e.g. "BSIT 401-A" |
| `{{class_label}}` | (static) | "CLASS" |
| `{{sem_ay}}` | (dynamic per semester) | e.g. "Second / 2023-2024" |
| `{{sem_ay_label}}` | (static) | "Semester / Academic Year" |
| `{{prepared_by_label}}` | prepared_by_label | "Prepared by:" |
| `{{rec_approval_label}}` | rec_approval_label | "Recommending Approval:" |
| `{{approved_label}}` | approved_label | "APPROVED:" |
| `{{signatory_1_name}}` | section_sig1_name | "SCHEDULE COMMITTEE" |
| `{{signatory_2_name}}` | section_sig2_name | "ARIEL G. SANTOS, EdD" |
| `{{signatory_2_title}}` | section_sig2_title | "Director, Instruction" |
| `{{signatory_3_name}}` | section_sig3_name | "LAURO B. PASCUA, EdD" |
| `{{signatory_3_title}}` | section_sig3_title | "Campus Administrator" |

Faculty/Room/Course layouts use `faculty_school_name`, `room_school_name`, `course_school_name` respectively (see `build_variable_map()`).

---

## Phase 1 — Foundation & Cleanup (manage_layouts.html rewrite)

**Files changed:** `app.py`, `manage_layouts.html`

- `SystemSettings` model: 9 new columns added after `course_signatories_json`:
  `republic_text`, `contact_details`, `email`, `website`, `prepared_by_label`,
  `rec_approval_label`, `approved_label`, `section_sig2_title`, `section_sig3_title`
- Startup migration block: 9 `ALTER TABLE system_settings ADD COLUMN` statements
- `manage_layouts.html` fully rewritten (was 1558 lines of LuckySheet):
  - 4 tabs: Section / Faculty / Room / Course
  - Upload cards with status badges per type
  - Settings form with all 19 variables
  - Sticky save bar
  - Preview modal with iframe
  - PDF export controls (semester + section dropdowns, visible only on Section tab)
- `manage_layouts()` route updated to save all 19 variables, passes `template_exists` dict + `all_semesters`

---

## Phase 2 — Visual Mirroring Engine

**Files changed:** `app.py`

New function: `render_excel_to_html(ws, cell_overrides=None, max_col=None, max_row=None, variable_map=None, extra_merge_map=None, extra_skip_cells=None)`

Key features:
- ARGB→CSS color conversion (`'FF' + color.zfill(6)` — bare 6-char = transparent black)
- Full border style map (thin/medium/thick/dashed/dotted/double → CSS)
- `cell.fill.fgColor.rgb` for background colors
- Raw HTML detection: if `val.strip().startswith('<')` → inject as `| safe`
- Phase 3 token substitution (from `variable_map`)
- Phase 4 merge injection (`extra_merge_map`, `extra_skip_cells`)
- Returns `(html_string, total_px_width)`

---

## Phase 3 — Dynamic Text Injection

**Files changed:** `app.py`

New function: `build_variable_map(layout_type, settings, section_name=None, sem_ay=None, entity_name=None)`

- Branches on `layout_type` → uses correct `school_name` and signatories per type
- Section: `section_school_name`, `section_sig1/2/3_name`, etc.
- Faculty: `faculty_school_name`, `faculty_sig1/2/3_name`, etc.
- Room/Course: similar branching
- Includes `{{entity_name}}` token for any type
- Token substitution done inside `render_excel_to_html()` by scanning all cells for `{{...}}`

`preview_layout(layout_type)` route updated to use `render_excel_to_html()` + `build_variable_map()` + `render_a4_page()`.

---

## Phase 4 — Grid Data Population

**Files changed:** `app.py`

New functions:
- `detect_schedule_grid(ws)` — scans worksheet for day-name header row and time-string rows. Returns `{header_row, base_row, time_col, day_col_map, time_row_map}` or `None`
- `build_schedule_overlays(schedules, grid_info, layout_type)` — produces `(cell_overrides, extra_merge_map, extra_skip_cells)` without mutating ws. Builds `<div style="background:#dbeafe;...">` HTML per cell
- `render_a4_page(html_content, table_px)` — standalone HTML with gray background + white paper box with shadow (for screen display)
- `render_pdf_page(html_content, orientation='landscape')` — WeasyPrint HTML with `@page { size: A4 landscape; margin: 1cm; }`, no shadow, table forced 100%

New route: `GET /section-timetable-html/<int:section_id>?semester=&sem_ay=`

---

## Phase 5 — PDF Export

**Files changed:** `app.py`, `view_timetable.html`

New route: `GET /section-timetable-pdf/<int:section_id>?semester=&orientation=`
- Uses `render_pdf_page()` → WeasyPrint → PDF response

`view_timetable.html`:
- Added PDF icon button `#pdfExportLink`
- `updatePdfBtn()` called on init, semester switch, type change, entity change

---

## Phase 6 — Faculty/Room Routes + iframe Switch + Cleanup (2026-03-16)

**Files changed:** `app.py`, `view_timetable.html`
**Files deleted:** `templates/_dynamic_timetable.html`, `static/assets/faculty_state.json`, `static/assets/room_state.json`

### New routes added:
- `GET /faculty-timetable-html/<int:faculty_id>?semester=`
- `GET /faculty-timetable-pdf/<int:faculty_id>?semester=`
- `GET /room-timetable-html/<int:room_id>?semester=`
- `GET /room-timetable-pdf/<int:room_id>?semester=`
- `export_pdf()` updated with `route_map` to redirect to per-type PDF routes

### view_timetable.html — switched to iframe:
- `<div id="scheduleContent">` → `<iframe id="scheduleFrame">`
- `htmlRouteMap` + `pdfRouteMap` + `buildTimetableUrl()` helper
- `loadSchedule()` sets `iframe.src` (no more fetch+innerHTML injection)
- `loadAllSchedules()` creates `<iframe>` per entity in scroll mode
- `updatePdfBtn()` now works for all types (section/faculty/room)
- `autoResizeIframe()` resizes iframe to content height on load

### Removed from app.py (~2100 lines total):
- `render_excel_to_html_exact()` — old LuckySheet renderer
- `lucky_json_to_cell_overrides()`, `lucky_json_to_cell_styles()`, `lucky_json_to_image_positions()`, `lucky_json_to_dimensions()` — LuckySheet helpers
- `get_schedule_modal()` route+function — replaced by new per-type HTML routes
- 8 old LuckySheet routes: `/get-layout-json`, `/get-xlsx-dimensions`, `/get-saved-layout`, `/get-layout-image`, `/save-full-layout`, `/upload-layout-logo`, `/save-layout-json`, `/get-layout-state`

---

## DB Migrations Added (Phase 1)
```sql
ALTER TABLE system_settings ADD COLUMN republic_text VARCHAR(255) DEFAULT 'Republic of the Philippines'
ALTER TABLE system_settings ADD COLUMN contact_details VARCHAR(255) DEFAULT '(046) 437-9505 / (046) 437-6659'
ALTER TABLE system_settings ADD COLUMN email VARCHAR(255) DEFAULT 'cvsurosario@cvsu.edu.ph'
ALTER TABLE system_settings ADD COLUMN website VARCHAR(255) DEFAULT 'www.cvsu-rosario.edu.ph'
ALTER TABLE system_settings ADD COLUMN prepared_by_label VARCHAR(100) DEFAULT 'Prepared by:'
ALTER TABLE system_settings ADD COLUMN rec_approval_label VARCHAR(100) DEFAULT 'Recommending Approval:'
ALTER TABLE system_settings ADD COLUMN approved_label VARCHAR(100) DEFAULT 'APPROVED:'
ALTER TABLE system_settings ADD COLUMN section_sig2_title VARCHAR(100) DEFAULT 'Director, Instruction'
ALTER TABLE system_settings ADD COLUMN section_sig3_title VARCHAR(100) DEFAULT 'Campus Administrator'
```

---

## Phase 1 & 2 Refinements — manage_layouts.html UI (2026-03-16)

**Files changed:** `app.py`, `manage_layouts.html`

### New SystemSettings columns (7 more, with ALTER TABLE migrations):
- `room_sig2_title`, `room_sig3_title` — Room signatory titles
- `course_sig2_title`, `course_sig3_title` — Course signatory titles
- `class_label` (default "CLASS") — editable, saved to DB
- `sem_ay_label` (default "Semester / Academic Year") — editable, saved to DB
- `sem_ay_value` (default "2nd Semester / 2024-2025") — editable, saved to DB

### manage_layouts.html redesign:
- **Wide 25%/75% horizontal split** — vertical tab nav on left, form on right
- **Single upload card** in left column — dynamically updates badge, delete URL, and Preview/Delete button visibility via JS `updateUploadCard()` based on active tab
- **Tab restoration** — JS reads `?tab=X` from URL on load; upload and delete routes now redirect with `?tab={type}` to preserve active tab
- **Preview + Delete buttons** always in DOM, shown/hidden by `_templateExists` JS map — no server round-trip
- **`delete_layout()` fixed** — was returning `jsonify()` (broken); now returns `redirect()` with flash
- **`upload_template()` fixed** — redirect now includes `?tab={template_type}`
- `class_label`, `sem_ay_label`, `sem_ay_value` — fully editable with `name=` attrs, saved to DB
- `section_name_value` — readonly with hint "Auto-filled from the Section Name during export."

### UI Refinements (header, grid, premium cards):
- **Header**: removed `padding: 16px 24px 0` wrapper — now uses `.main-content`'s natural `2rem` padding, matching Dashboard Overview vertical position exactly
- **Duplicate flash removed**: deleted template's own `{% with messages %}` block — `base.html` already handles all flash messages
- **Schedule Details 2×2 grid** (Section, Room, Course tabs):
  - Row 1: Entity Name (auto/readonly) | Sem/AY Value (editable on Section, readonly on Room/Course)
  - Row 2: Class Label | Sem/AY Label
- **Premium card design**: 4 `.settings-card` white cards per tab (Header Info, Schedule Details, Signatory Block Labels, Signatories); green `.section-label` headers with Bootstrap icons; `.auto-field` dashed readonly styling
- **Room & Course tabs** mirror Section structure; shared fields shown readonly with `(shared)` hint; only University Name + Signatories are tab-unique
- **Faculty tab**: 2 cards only (Header Info + Signatories) — no Schedule Details card

### Save Settings button — final placement (2026-03-16):
- **Removed** sticky bottom save bar entirely (was `position:fixed` with viewport-relative `left:` calc — too fragile)
- **Moved** to page header, right-aligned: `d-flex justify-content-between` with title/subtitle on left, `<button form="settingsForm">` on right
- Uses `form="settingsForm"` HTML attribute to associate the external button with the `<form id="settingsForm">` inside `.layout-right`
- `.layout-right` padding-bottom: `100px → 24px` (no longer needs clearance for fixed bar)
- CSS: `.save-btn { transition: ... }` + `.save-btn:hover { background:#157347; box-shadow; transform:translateY(-1px) }`

---

## Phase 3 — Excel Preview Renderer (2026-03-17)

### 6 new helper functions added to app.py (before `preview_layout` route):

| Function | Purpose |
|----------|---------|
| `build_variable_map(layout_type, settings, ...)` | Builds `{{token}}: value` dict from SystemSettings + entity name |
| `_argb_to_css(color_obj)` | openpyxl Color → CSS hex |
| `_border_side_css(side)` | openpyxl border side → CSS string |
| `detect_content_bounds(ws)` | Scans worksheet → `(min_r, min_c, max_r, max_c)` tight bounding box |
| `render_excel_to_html(ws, ..., bounds=None)` | openpyxl worksheet → `(html_table, table_px)` |
| `render_a4_page(html_content, table_px, margins=None)` | Full iframe preview HTML page |
| `render_pdf_page(html_content, orientation, margins=None)` | Full WeasyPrint HTML page |
| `detect_schedule_grid(ws)` | Finds `{{GRID_TIME}}` anchor → grid geometry dict |
| `build_schedule_overlays(schedules, grid_info, view_type)` | Maps ScheduledClass → cell_overrides + merge info |
| `_get_margins(settings)` | Extracts margin+paper dict from SystemSettings |
| `PAPER_SIZES` | Dict of 11 paper sizes: A4/Letter/Legal/Folio/A3/A5/B4/B5/Executive/Tabloid/Statement |

### Content bounds / Smart Crop:
- `detect_content_bounds(ws)` — cell is "content" if: non-empty value OR visible fill OR visible border
- `render_excel_to_html` loops only `range(min_r, max_r+1)` × `range(min_c, max_c+1)` when bounds passed
- `bounds` passed in all 4 HTML routes: `preview_layout`, `section_timetable_html`, `faculty_timetable_html`, `room_timetable_html`

### A4 preview page:
- Paper container: `width:{pw}in; min-height:{ph}in` (dynamic from PAPER_SIZES)
- Gray background (`#c8c8c8`), white paper, double-layer shadow
- Debug grid: `outline: 0.5px solid rgba(0,0,0,0.10)` on all `td/th`
- JS auto-scale: `Math.min(1.0, paperContent / tableW)` — shrinks only, never zooms in

### Page Margins & Paper Size (SystemSettings):
- 4 new Float columns: `margin_top/bottom/left/right` (default 1.0 inch)
- 1 new String column: `paper_size` (default 'A4')
- Margins clamp: 0.0–5.0 inches; paper_size validated against PAPER_SIZES keys
- `render_a4_page` uses `{mt}in {mr}in {mb}in {ml}in` for CSS padding
- `render_pdf_page` uses same for `@page { margin: ... }` — screen matches PDF exactly
- `render_pdf_page` landscape: swaps `pw/ph` for correct `@page { size: ... }`
- UI: "Paper Size & Margins" card at top of each tab — paper dropdown + 4 `step="0.1"` inch inputs

### Variable token `{{class_label}}` — tab-specific resolution:
- Section → `settings.class_label` (default "CLASS")
- Room → `settings.room_label` (default "ROOM")  ← new column
- Course → `settings.course_label` (default "COURSE")  ← new column
- Token name stays `{{class_label}}` in all Excel templates — no template changes needed
- Room/Course tab Schedule Details card: label input is now editable (own field), Sem/AY fields readonly with "Edit in Section tab" hint

### DB migrations added (system_settings):
- `margin_top`, `margin_bottom`, `margin_left`, `margin_right` — REAL DEFAULT 1.0
- `paper_size` — VARCHAR(30) DEFAULT 'A4'
- `room_label` — VARCHAR(100) DEFAULT 'ROOM'
- `course_label` — VARCHAR(100) DEFAULT 'COURSE'

---

## Notes / Gotchas
- `timetable_for_pdf.html` still exists but is now used by `render_pdf_page()` (WeasyPrint)
- `test_borders.py` still imports deleted functions — it will break, but it's a dev utility not part of the app
- Scroll mode iframe height: fixed at 700px default, auto-resizes on load via `autoResizeIframe()`
- `room.special_course_ids` always blank — use pre_assignments for special course detection
- Workflow for this overhaul: Plan → User approval ("go signal") → Code — repeated for all 6 phases
- `campus_name` and `address` fields are shared but only have `name=` attrs in Section tab — other tabs show them readonly; saving from any tab updates shared values
- `detect_content_bounds` uses `_argb_to_css` internally — must be defined before it
- `PAPER_SIZES` dict is module-level (not inside a function) — safe to reference in routes and `manage_layouts()` render call
- `paper_sizes=PAPER_SIZES` passed to `render_template('manage_layouts.html', ...)` so the dropdown can loop over it
