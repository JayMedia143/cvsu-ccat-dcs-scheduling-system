---
name: Schedule Overlay Feature
description: Details of build_schedule_overlays(), detect_schedule_grid(), build_static_cell_overrides(), cell styling, faculty sex field, overlap tooltip, phantom skip_cells fix, neutral vtypes — all changes to plot DB schedules onto Excel templates
type: project
---

# Schedule Overlay Feature — Updated 2026-03-20

Plots `ScheduledClass` DB records onto Excel layout templates rendered as HTML. Used by Schedule Viewer modal (manage_faculty, manage_sections, manage_rooms, manage_courses) and Master Schedule (view_timetable).

---

## Key Functions in `app.py`

### `detect_schedule_grid(ws)` (~line 5855)
Auto-detects which cells are the time column and day header columns in an Excel template.

- `time_re` / `simple_time_re`: capture optional AM/PM in time strings
- `_to24(time_str, period)`: converts 12h → 24h
- `_normalize_12h_wrap(slots)`: fixes implicit 12h wrap — Philippine templates use bare "1:00" after "12:30" which means 13:00. Detects backwards jump (drop > 360 min) and adds +720 offset to all subsequent slots.
- Multi-row header search: tries `offset in range(1,4)` above first time slot via `_scan_day_names(hrow)` helper
- `col_range_counts` (range-format "8:00–8:30") scored higher signal than `col_time_counts` (bare "HH:MM")

### `build_schedule_overlays(schedules, grid_info, view_type)` (~line 6073)
Two-pass approach:

**Pass 1** — collect `cell_data = {(start_row, col): [(rowspan, lines, entry_dict), ...]}`
- `physical_rows(start_row, start_min, end_min)`: uses `last_slot_row - start_row + 1` for accurate HTML rowspan when templates have empty/spacer rows between time slots (NOT just count of slots)
- `fmt_faculty(full_name, sex)`: extracts last word as surname (uppercase), prefixes MR./MS./PROF. based on `sex` field
- `faculty_name = fmt_faculty(sched.faculty.full_name, getattr(sched.faculty, 'sex', None))`
- view_type lines:
  - `section`: [course_code (sess_type), faculty_name, room_name]
  - `faculty`: [course_code (sess_type), section_name, room_name]
  - `course`: [section_name or course_code, faculty_name, room_name]
  - `room`: [course_code (sess_type), section_name, faculty_name]

**Pass 2** — build HTML — **MUST iterate `sorted(cell_data.items())`** (ascending row order)

Reason: If a later-time schedule is inserted in DB before an earlier-time one, its skip_cells get
added first. When the earlier schedule is then processed, its start_row is already in skip_cells
and gets incorrectly skipped ("phantom skip_cells" bug). `sorted()` ensures row-ascending order.

---

## `_vtype_for_badge` — Neutral Overlap Types (2026-03-20)

Controls overlap badge/tooltip color and title. Two neutral vtypes added:

```python
_vtype_for_badge = view_type
# NSTP/University Field room — capacity 999 is sentinel for "shared room, no real conflict"
if view_type == 'room' and schedules:
    _first_room = getattr(schedules[0], 'room', None)
    if _first_room and getattr(_first_room, 'capacity', 0) == 999:
        _vtype_for_badge = 'room_neutral'
# T.B.A. faculty — not a real physical teacher, overlaps are not real conflicts
if view_type == 'faculty' and schedules:
    _first_faculty = getattr(schedules[0], 'faculty', None)
    if _first_faculty:
        _fname = (getattr(_first_faculty, 'full_name', '') or '').strip().upper()
        if 'T.B.A' in _fname or _fname == 'TBA':
            _vtype_for_badge = 'faculty_neutral'
```

**vtype → tooltip mapping (JS in `render_a4_page()`):**
| vtype | Title | Color |
|-------|-------|-------|
| `course` | "Overlapping Courses" | neutral (no red) |
| `room_neutral` | "Overlapping Rooms" | neutral (no red) |
| `faculty_neutral` | "Overlapping Faculty" | neutral (no red) |
| `section` / `faculty` / `room` | "⚠ Schedule Conflict" | red warning |

**Why:** University Field (capacity=999) is a special shared room used by NSTP. Multiple classes
truly share it simultaneously — it's expected, not a real conflict. T.B.A. is a placeholder, not
a physical teacher, so overlaps with it are also not real conflicts.

**Important:** `room.department` does NOT exist on the Room model — use `capacity == 999` alone.

---

## Cell Style (current state — 2026-03-20)

- Font size: **11px**
- Bold: **none**
- Padding: **3px** (all sides) inside the cell div
- Top/bottom border: `1px solid #aaa` (single), `1px solid #c00` (overlap)
- No left/right border on inner div — relies on Excel template's `<td>` border
- Vertical centering via `display:table-cell`
- Overlap: subtle `rgba(220,53,69,0.06)` red tint background + badge

Single cell HTML:
```python
'<div style="display:table;width:100%;height:100%;'
'border-top:1px solid #aaa;border-bottom:1px solid #aaa;overflow:hidden;">'
'<div style="display:table-cell;vertical-align:middle;text-align:center;'
'padding:3px;font-size:11px;line-height:1.3;color:#000;">'
```

---

## Overlap Badge (current state — 2026-03-20)

- Size: 18×18px, font 10px
- Position: `top:3px;right:3px` — inside the 3px padding area
- Red: `background:#dc3545` for real conflicts; neutral gray for room_neutral/faculty_neutral/course

```python
f'style="position:absolute;top:3px;right:3px;background:#dc3545;'
f'color:#fff;font-size:9px;font-weight:bold;min-width:16px;height:16px;'
```

---

## Overlap Tooltip (current state — 2026-03-20)

HTML structure in `render_a4_page()`:
```html
<div id="overlapTip" style="display:none;position:fixed;z-index:9999;
  background:#fff;border:1.5px solid #dc3545;border-radius:7px;
  padding:9px 12px;font-size:11px;min-width:240px;max-width:340px;
  box-shadow:0 4px 18px rgba(0,0,0,0.22);font-family:Calibri,Arial,sans-serif;">
  <div id="overlapTipTitle" style="font-weight:700;margin-bottom:5px;font-size:12px;"></div>
  <div id="overlapTipBody" style="max-height:260px;overflow-y:auto;"></div>
</div>
```

**JS behavior:**
- `hideTimer` hover bridge: badge `mouseleave` → `setTimeout(hide, 150)` — gives 150ms to move mouse to tooltip
- Tooltip `mouseenter` → `clearTimeout(hideTimer)` — cancels hide if mouse enters tooltip
- Tooltip `mouseleave` → hide immediately
- Position set **once** on badge `mouseenter` — NO `mousemove` repositioning (removing mousemove fixed "tooltip chasing cursor" bug)
- `max-height:260px; overflow-y:auto` on body div — scrollable when many overlaps

---

## `build_static_cell_overrides()` — Entity Name Fix (~line 6463)

Scans every Excel template cell and swaps anchor strings with DB values. Used by section/room/course timetable routes.

**Bug fixed (2026-03-19):** Entity name (course name, room name, section name) was not appearing in the template header.

**Root cause:** Template has label cell "COURSE" (or "CLASS"/"ROOM"). Strategy 1 (exact match) matched it → `matched = True` → Strategy 3 (entity label injection, gated by `not matched`) was skipped → adjacent cell with actual name stayed blank.

**Fix:** Inside Strategy 1's exact-match branch, also inject `entity_name` into `(r, c+1)` when `val_lower in {'class', 'room', 'course'}`:
```python
if entity_name and not entity_label_found and val_lower in {'class', 'room', 'course'}:
    overrides[(r, c + 1)] = entity_name
    entity_label_found = True
```

---

## Faculty `sex` Field — Added 2026-03-19

**Model** (`app.py` ~line 274):
```python
sex = db.Column(db.String(1), nullable=True)  # 'M' or 'F'
```

**Routes:** `add_faculty` + `update_faculty` both read `request.form.get('sex', '') or None`

**Form** (`manage_faculty.html`): Sex radio buttons (Male/Female) added after Academic Rank.

---

## Subject Table Totals Row Fix (2026-03-20)

`build_subject_table_overlays()` — faculty schedule viewer subject list.

**Problem:** Totals row showed 0 instead of computed values.

**Root cause:** Template loaded with `data_only=True` → formula cells return `None`. Detection tried to find formula cells in `subj_col`, which never triggered.

**Fix:** Scan for "Consultation:" label string in col 1 (always static text, detectable with data_only=True):
```python
for r_idx in range(data_start, data_start + 25):
    cell_val = ws.cell(row=r_idx, column=subj_col).value
    val_str = str(cell_val or '').strip().lower()
    if 'consultation' in val_str or 'designation' in val_str or 'research' in val_str:
        totals_row = r_idx - 1
        data_rows = [r for r in data_rows if r < totals_row]
        break
```

---

## Important Fixes History

| Bug | Fix |
|-----|-----|
| PM schedules (1:00 PM+) not plotted | `_normalize_12h_wrap()` — template "1:00" was 60 min, DB "13:00" = 780 min |
| Wrong rowspan | `physical_rows()` using `last_slot_row - start_row + 1` instead of slot count |
| Schedule cells had floating inner box | Removed `border:1px solid #000` from inner div; rely on `<td>` border |
| `_fmt_time_12h()` route error | Helper was placed between `@app.route` and `@login_required` — moved above decorator |
| Room/Course/Section names blank in header | Strategy 1 set `matched=True`, blocking Strategy 3; fixed by injecting entity_name in Strategy 1 when label is "CLASS"/"ROOM"/"COURSE" |
| Missing cells in schedule viewers (phantom skip_cells) | `cell_data.items()` iteration was DB insertion order → skip_cells from a later-time schedule blocked earlier-time schedules. Fixed: `sorted(cell_data.items())` |
| NSTP/University Field showed red overlap warning | capacity==999 is sentinel → use `room_neutral` vtype → neutral tooltip, no red |
| T.B.A. faculty showed red overlap warning | T.B.A. is not a real teacher → use `faculty_neutral` vtype → neutral tooltip, no red |
| Tooltip chasing cursor as mouse moved | `mousemove` kept repositioning tooltip. Removed mousemove — position set once on mouseenter |
| Tooltip disappeared before mouse reached it | No hover bridge. Added `hideTimer = setTimeout(hide, 150)` on badge mouseleave; tooltip mouseenter clears it |
| Subject table totals showing 0 | `data_only=True` → formulas=None. Fixed: scan for "Consultation:" label string instead |
| 3px padding missing in cells | Inner div had no padding. Added `padding:3px` to single-cell div |
| Badge overlapping cell content | Badge was `top:0;right:0`. Moved to `top:3px;right:3px` to stay within padded area |
