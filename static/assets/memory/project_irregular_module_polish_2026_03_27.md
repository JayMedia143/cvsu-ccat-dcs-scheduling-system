---
name: Irregular Module Polish — Rounds 2–4 (2026-03-27)
description: UI/UX polish, bug fixes, and renames for the Irregular Student Module (manage_irregular, manage_students, irregular_pathfinder, student_schedule)
type: project
---

Completed 4 rounds of polish on the Irregular Student Module after initial build.

**Why:** User reported cosmetic bugs (purple icons, missing CSS, wrong confirm text, stale "Pathfinder" labels) across multiple pages.

**How to apply:** These are finalized. Do not re-introduce `active` class on mark-as-irregular buttons, do not re-add purple to puzzle icons, do not use "Pathfinder" as user-visible text anywhere.

---

## Round 2 — Functional + cosmetic fixes

| File | Change |
|------|--------|
| `manage_students.html` | Bulk "Mark as Irregular" button added to `#bulkActionBar` (no purple); `#irregConfirmModal` with 5-min suppress; JS: `isSuppressed()`, `maybeSuppressFor5Min()`, `bulkMarkIrreg()`, `doIrregConfirm()`, `executeIrregApi()` |
| `manage_students.html` | Removed `{% if student.is_irregular %}active{% endif %}` from per-row mark-as-irregular btn (was causing unwanted box/border via CSS) |
| `manage_students.html` | Per-row puzzle link title → "Open Schedule Finder" |
| `manage_irregular.html` | Gray tab icons + ghost cancel button via `<style>` block; `.modal-cancel-btn` class on Cancel buttons |
| `manage_irregular.html` | Removed purple (`style="color:#7c3aed;"`) from bulk bar puzzle button; title → "Batch Schedule Finder" |
| `manage_irregular.html` | Removed purple from per-row puzzle `<a>`; title → "Open Schedule Finder" |
| `manage_irregular.html` | `submitAddIrreg()` updated with `showAddIrregError()` inline error helper; uses `window.location.href` instead of `location.reload()` |
| `app.py` | `add_student()`: returns `jsonify({'error': msg})` + 400 when `is_irregular=1`; returns `jsonify({'ok': True})` on success; regular path (flash+redirect) unchanged |
| `base.html` | Removed `style="color:#7c3aed;"` from "Irregular Students" nav icon |
| `app.py` | `irregular_timetable_html()`: `entity_name=student.full_name` (not 'Irregular Schedule') |

---

## CSS Fixes (style.css)

- Added `.irreg-row.selected td` green highlight (mirrors `.student-row.selected td`)
- Added base `.bulk-btn` rule (before `.bulk-btn.delete-icon`) — was missing, caused browser-default box on puzzle + person-exclamation bulk buttons:
  ```css
  .bulk-btn { border:none; background:transparent; width:36px; height:36px; border-radius:50%;
      display:flex; align-items:center; justify-content:center; color:#5f6368;
      transition:background 0.2s,color 0.2s; font-size:1.1rem; cursor:pointer; }
  .bulk-btn:hover { background-color:#f1f3f4; color:#3c4043; }
  ```

---

## Round 3 — irregular_pathfinder.html full rewrite

- Renamed page: "Irregular Schedule Finder" (title, h1, all labels)
- Full-cover section results: entire card is clickable (not just a button inside)
- Non-full-cover results: stacked option cards grouped by section (not accordion + flat table)
- Added `#confirmAssignModal` with schedule preview HTML before saving
- `doConfirm()` redirects to `manage_irregular` page (not student_schedule) after save
- Key JS functions: `runFinder()`, `renderResults()`, `buildSectionGroups()`, `showFullCoverConfirmModal()`, `showComboConfirmModal()`, `doConfirmFromModal()`, `doConfirm()`

---

## Round 4 — Batch modal rename + smart confirm text

| File | Change |
|------|--------|
| `manage_irregular.html` | Batch modal title: "Batch Pathfinder" → "Batch Schedule Finder"; removed purple from modal title puzzle icon |
| `manage_irregular.html` | Batch results link in `runBatch()` JS: "Open Pathfinder" → "Open Schedule Finder" |
| `student_schedule.html:219` | Empty-state text: "Irregular Pathfinder" → "Irregular Schedule Finder" |
| `manage_students.html:171` | Added `data-irregular="{{ '1' if student.is_irregular else '0' }}"` to `<tr class="student-row">` |
| `manage_students.html` | `bulkMarkIrreg()` reads `data-irregular` from each row's `<tr>` to build context-aware confirm message: all-regular → "Mark N as irregular?", all-irregular → "Remove flag from N?", mixed → "Toggle for N: X will be marked, Y will have flag removed." |

---

## Key Gotchas

- `fromjson` Jinja2 filter does NOT exist — use static badge text instead of `assignments_json | fromjson | length`
- Flash messages consumed by `fetch()` silently — must return JSON errors from Flask when called via fetch
- `.bulk-btn` base CSS rule MUST exist before `.bulk-btn.delete-icon` override — absence causes browser-default box
- `active` class on mark-as-irregular button caused a border/box via CSS `.btn-icon.active` — removed
- Internal route names (`/irregular-pathfinder/`) were NOT renamed — only user-visible text says "Schedule Finder"
