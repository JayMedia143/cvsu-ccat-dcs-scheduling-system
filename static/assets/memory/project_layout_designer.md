---
name: Layout Designer Feature
description: Full implementation details of the Excel Layout Designer (manage_layouts.html) and schedule view rendering (get_schedule_modal)
type: project
---

# Layout Designer — Completed Implementation

## Feature Overview
- Users upload an Excel template per type (section/faculty/room/course)
- Edited in-browser via LuckySheet (manage_layouts.html)
- Schedule views render the template filled with real schedule data
- Variables like `{{name}}`, `{{semester}}`, `{{sig1}}` etc. are replaced at render time

## Key Files
- `templates/manage_layouts.html` — LuckySheet-based layout editor
- `app.py: get_schedule_modal()` — renders schedule into HTML using XLSX + JSON
- `app.py: render_excel_to_html_exact()` — openpyxl → HTML pixel-perfect renderer
- `app.py: lucky_json_to_cell_overrides()` — extracts text from LuckySheet JSON
- `app.py: lucky_json_to_cell_styles()` — extracts formatting from LuckySheet JSON
- `static/assets/section_state.json` etc. — saved LuckySheet state per type
- `static/assets/section_template.xlsx` etc. — saved Excel template per type

## manage_layouts.html — JS Features Implemented

### Tab Switching (`changeTab()`)
```javascript
function changeTab(type) {
    if (activeType === type) return;
    fileBlob = null;
    _overlayPositions = [];
    initSheet(type);
    const panel = document.getElementById('var-panel');
    if (panel && panel.classList.contains('open')) loadVarPanel(type);
}
```
Reloads the variable panel when switching between section/faculty/room/course tabs.

### Delete Layout Button
- Button: `btn-outline-danger` with `trash3` Bootstrap icon, in controls bar
- Calls `deleteLayout()` JS → `POST /delete-layout/${activeType}`
- Route `/delete-layout/<layout_type>` in app.py deletes: `{type}_template.xlsx`, `{type}_state.json`, `{type}_layout.json`
- After delete: clears grid, resets state

### Image Delete with Ctrl+Z Undo
- `_imgUndoStack = []` — tracks deleted image states
- `_deleteImage()` pushes to undo stack (no confirm dialog)
- ESC listener: `capture: true` (so Ctrl+Z handler catches before LuckySheet)
- Ctrl+Z: calls `_undoImageDelete()` → `removeImageOverlays()` + `placeImageOverlays(images)`

### LuckySheet Load Timeout Fix
- 20-second timeout with `_loadDone` flag prevents infinite "Restoring Layout..." spinner
```javascript
let _loadDone = false;
const _loadTimeout = setTimeout(() => {
    if (!_loadDone) {
        _loadDone = true;
        renderGrid(null);
        loader(false);
        _setStatus('Layout load timed out. Try re-importing the Excel file.');
    }
}, 20000);
```

### Cleared Cells Fix (`_saveToDraft`)
- When `cell.v === null` AND `_originalCells.has(r_c)`, saves `{r, c, v: {v:'', m:''}}`
- Prevents formula restore from un-doing user's explicit cell clears

## app.py — get_schedule_modal() Render Pipeline

### Phase Flow
1. **Load**: `wb = load_workbook(template_path)`, `ws = wb.active`
2. **Load JSON**: `cell_overrides`, `cell_styles`, `img_positions` from `{type}_state.json`
3. **Phase 2** (always runs, outside `if entity_name:`):
   - Apply text overrides: `_mc2.value = _override_text`
   - Apply styles: `_mc2.font = _OFont(...)`, `_mc2.alignment = _OAlignment(...)`
4. **Phase 3** (inside `if entity_name:`):
   - Scan ws for `{{SECTION}}`, `{{NAME}}`, `{{name}}` placeholders → replace with entity_name
5. **Phase 3b**: Replace all `{{variables}}` with real data (semester, dept, signatories, etc.)
6. **Phase 4**: Fallback anchor-based name injection if no placeholders found
7. **Render**: `render_excel_to_html_exact(ws, cell_overrides=None, ...)`
   - `cell_overrides=None` is CRITICAL — Phase 2 already baked everything into ws

### Variables Supported
- `{{name}}` / `{{NAME}}` / `{{SECTION}}` / `{{FACULTY}}` / `{{ROOM}}` / `{{COURSE}}` → entity name
- `{{semester}}`, `{{acad_year}}`, `{{department}}`, `{{school}}`, `{{generated}}`
- `{{sig1}}`, `{{sig1_title}}`, `{{sig2}}`, `{{sig2_title}}`, `{{sig3}}`, `{{sig3_title}}`
- Faculty: `{{employee_id}}`, `{{employment_status}}`, `{{highest_education}}`, `{{max_weekly_hours}}`, `{{total_contact_hours}}`, `{{num_preparations}}`, `{{daily_Mon}}` etc.
- Section: `{{year_level}}`, `{{num_students}}`
- Room: `{{building}}`, `{{capacity}}`, `{{capabilities}}`
- Course: `{{course_name}}`, `{{lec_units}}`, `{{lab_units}}`, `{{program}}`

### Fallback Timetable (no template)
When no `{type}_template.xlsx` exists, renders a basic Bootstrap HTML table showing the schedule. Warning links to `/manage/layouts`.

### lucky_json_to_cell_styles() — LuckySheet → openpyxl Style Mapping
```python
_ht_map = {0: 'center', 1: 'left', 2: 'right', 3: 'justify'}
_vt_map = {0: 'center', 1: 'top',  2: 'bottom'}
# bl → bold, it → italic, un → underline, fs → size, ff → font_name
# fc → color, bg → bg, ht → align, vt → valign, tb==2 → wrap
```

### Phase 2 Style Application — IMPORTANT
- Uses `_OFont`, `_OAlignment`, `_OFill`, `_OColor` (underscore aliases)
  - WHY: avoids `UnboundLocalError` from `Alignment` already used at line 3827 in the same function
- Color fix: pad to ARGB format: `'FF' + color.zfill(6)` (openpyxl requires 8-char ARGB, bare 6-char creates transparent black `00000000`)
- Errors now print to console instead of silent `except: pass`

```python
_fc_argb = ('FF' + _fc_raw.zfill(6)) if _fc_raw else None
_mc2.font = _OFont(..., color=_OColor(_fc_argb) if _fc_argb else _bf.color)
```

### Merged Cell Handling
- `get_master_cell(ws, r, c)` returns top-left of merged range for style/value assignment
- LuckySheet JSON `mc: {r, c, rs, cs}` — rs=rows, cs=cols (merged range size)

## Routes Added
- `POST /delete-layout/<layout_type>` — deletes layout files for section/faculty/room/course

## Known Issues / Notes
- `room.special_course_ids` always blank — `_special_cids` built from pre_assignments
- `timetable_for_pdf.html` still a placeholder
- Image `src` may not be in JSON for XLSX-embedded images (not yet fixed for faculty/room/course)
- LuckySheet `ht:2` = right alignment (not justify). Alignment mapping: 0=center, 1=left, 2=right, 3=justify
- After any app.py change, Flask server MUST be restarted for get_schedule_modal to use new code

## Pending / Not Yet Built
- Manage signatories UI in Global Settings (add/remove signatory rows per type)
- Image rendering for faculty/room/course layout types (XLSX-embedded image src issue)
