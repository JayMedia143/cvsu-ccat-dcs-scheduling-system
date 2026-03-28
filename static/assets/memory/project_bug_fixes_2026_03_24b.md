---
name: Bug Fixes & UI Consistency — 2026-03-24 (Session B)
description: Recycle Bin modal fixes, PreAssignment deleted_at migration, nav reordering, duplicate copyCurriculum fix
type: project
---

# Bug Fixes & UI Consistency — 2026-03-24 (Session B)

## Manage Page Modal Fixes (manage_preassignments.html + app.py)

**Why:** Locked Schedules manage page had yellow button, count showing "0", old text "Yes, Archive", helper text "(They will be moved to deleted list)", and JS updating wrong element IDs.

**Changes:**
- Bulk modal: count color `text-warning` → `text-danger`, removed helper text, "Yes, Archive" → "Yes, Move to Recycle Bin"
- JS `updateSelectionState()`: was updating non-existent `modalDeleteCount`/`modalRestoreCount` — fixed to update `modalArchiveCount`
- Single row modal button: `type="button" btn-warning` → `type="submit" btn-archive-confirm`
- `bulk_archive_preassignments` flash: `'warning'` → `'success'`, "Deleted list" → "Recycle Bin"; also sets `deleted_at`
- `archive_preassignment`: added `pa.deleted_at = datetime.utcnow()` + green flash

**Grammar fixes:**
- `manage_faculty.html`: "Are you sure Move the" → "Are you sure you want to move the"
- `manage_sections.html`: same fix

## PreAssignment `deleted_at` Column (app.py + site.db)

**Why:** `PreAssignment` model was the only archivable model without `deleted_at`. Adding it to routes caused `AttributeError`.

**Fix:**
- Added `deleted_at = db.Column(db.DateTime, nullable=True)` to `PreAssignment` model in app.py
- Ran SQLite migration: `ALTER TABLE pre_assignment ADD COLUMN deleted_at DATETIME`

## `now` Undefined in preassignments_archive.html

**Why:** `preassignments_archive` route was the only archive route not passing `now=datetime.utcnow()` to `render_template`, but the template uses `{% set days = (now - pa.deleted_at).days %}`.

**Fix:** Added `now=datetime.utcnow()` to `render_template(...)` call in `preassignments_archive` route.

## Navigation Order Standardization

**Why:** All menus should follow the Data dropdown order: Courses → Sections → Faculty → Rooms.

**Changes (templates/base.html):**
- Recycle Bin sidebar: Courses, Faculty, Rooms, Sections → Courses, Sections, Faculty, Rooms, Schedules, Code Rules
- Scheduling dropdown Pending items: Faculty → Sections → Room → **Sections → Faculty → Room**

**Changes (templates/dashboard.html):**
- Stat cards: Courses, Faculty, Rooms, Sections → **Courses, Sections, Faculty, Rooms**

**Changes (templates/manage_layouts.html):**
- Layout type buttons: Section, Faculty, Room, Course → **Course, Section, Faculty, Room**
- Default active tab stays on **Section** (not Course) to match right panel default

## Duplicate copyCurriculum Function (manage_sections.html)

**Why:** Two `copyCurriculum` definitions existed. The second (active) one had no `.catch()`, so if the fetch failed, the spinner icon stayed stuck forever.

**Fix:**
- Deleted the first (dead) definition (~lines 948–980)
- Added `.catch(() => { icon.className = originalClass; })` to the active second definition

**How to apply:** If you ever see a JS function defined twice in a template, the second one wins — the first is dead code and should be removed.
