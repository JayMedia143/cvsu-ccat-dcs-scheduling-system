---
name: Module 3 — Multi-Department Drafting & Manual Overrides (2026-03-27)
description: Global AI-Lock, Draft Layer system, interactive Schedule Editor page, real-time conflict guard, and visual entry status distinction
type: project
---

Phase 2, Module 3 fully implemented. All routes added to app.py, new template schedule_editor.html created, base.html updated, style.css updated.

**Why:** Allows multi-department collaborative schedule editing with a lock system to protect GA-generated entries, and a draft sandbox so non-admin users can propose schedules without touching the live master DB.

**How to apply:** Do not re-add lock enforcement elsewhere — it's already in `api_move_class`. Do not re-create DraftVersion — it exists. All Module 3 routes are grouped under the `# MODULE 3` comment block in app.py.

---

## DB Changes

### New columns on `ScheduledClass` (app.py ~line 373)
- `source` VARCHAR(10) DEFAULT 'ga' — 'ga' = GA-generated, 'manual' = manually added
- `is_draft` BOOLEAN DEFAULT 0 — True = belongs to a draft, not yet published
- `draft_version_id` INTEGER FK → draft_version(id) — NULL = master record

### New column on `SystemSettings` (app.py ~line 159)
- `schedule_lock` BOOLEAN DEFAULT 0 — True = GA entries protected from user edits

### New model `DraftVersion` (app.py, after IrregularAssignment)
```python
class DraftVersion(db.Model):
    __tablename__ = 'draft_version'
    id, name, semester, department, created_by (FK user.id),
    created_at, updated_at, is_published (bool), notes
```

### Migrations (app.py, migration block ~line 9960)
- All 4 ALTER TABLE statements added (source, is_draft, draft_version_id, schedule_lock)
- `db.create_all()` called after migration block to create draft_version table

---

## New Routes (all in app.py, grouped under MODULE 3 comment)

| Method | Path | Roles | Purpose |
|--------|------|-------|---------|
| POST | `/api/settings/schedule-lock` | admin, superadmin | Toggle global lock |
| GET | `/api/conflicts/check` | all logged-in | Single-slot conflict check (room/faculty/section) |
| GET | `/api/schedule/entries` | all logged-in | Master entries for editor grid |
| POST | `/api/schedule/add` | all logged-in | Add manual entry (draft-aware) |
| DELETE | `/api/schedule/<id>` | all logged-in | Delete entry (with role guards) |
| POST | `/api/draft/create` | all logged-in | Create draft version |
| GET | `/api/draft/<id>/entries` | all logged-in | Get draft entries |
| POST | `/api/draft/<id>/publish` | admin, superadmin | Publish draft → master |
| DELETE | `/api/draft/<id>` | all logged-in | Delete draft + entries |
| GET | `/schedule-editor` | all logged-in | Schedule Editor page |

## Modified Routes
- `POST /api/move-class` — removed `@role_required('admin','superadmin')`, now `@login_required` only. Enforces lock: user role blocked from moving GA entries when locked. Also blocks user from moving master entries they don't own.

---

## base.html Changes
- Lock toggle switch in Global Settings modal (admin/superadmin only, ~line 316)
- `.lock-badge-nav` red badge in right side of nav when lock_status is True
- "Schedule Editor" link added to Scheduling dropdown (admin)
- "Schedule Editor" link added to user-only nav section
- `toggleScheduleLock()` JS function added — updates label + nav badge without page reload

## context_processor Change
- `inject_settings()` now also returns `lock_status=bool(settings.schedule_lock)` for all templates

---

## schedule_editor.html (new file)

Full interactive grid editor:
- **Top bar**: semester/viewType/entity/draft selectors, New Draft, Publish, Delete Draft, Refresh buttons
- **Legend bar**: GA Finalized (green), Draft (blue dashed), Manual Live (purple)
- **Left panel**: Add New Schedule form (course, section, faculty, room, day, time, type) + drafts list
- **Grid**: HTML `<table>` — rows = 30-min slots from START_HOUR to END_HOUR, columns = ALLOWED_DAYS
  - Each slot cell: click → quick-fills add form; drag-over → highlights green; drop → conflict check then move
  - Each `.sched-block`: draggable, shows course_code + section_name, delete button on hover
  - Lock icon shown on GA blocks when LOCK_STATUS is true
- **Drag-drop flow**: dragstart saves entry data → drop calls `/api/conflicts/check` → if clean calls `/api/move-class` → `loadGrid()` refresh
- **Conflict toast**: fixed bottom-center, auto-hides after 3.5s
- **New Draft modal**: name, semester, dept, notes → POST `/api/draft/create`
- **Delete confirm modal**: shows entry ID, calls DELETE `/api/schedule/<id>`

### Key JS functions in schedule_editor.html
- `loadGrid()` — fetches master + draft entries, calls `renderGrid()`
- `renderGrid()` — builds table, calls `placeBlock()` per entry
- `placeBlock(entry)` — creates `.sched-block` div, positions it by slotIndex + span
- `handleDrop(cell)` — conflict check → move-class API → reload
- `checkConflicts(params)` — fetch wrapper for `/api/conflicts/check`
- `submitAddSchedule()` — conflict check → `/api/schedule/add` → reload
- `submitNewDraft()` — creates draft via API, updates selector + panel
- `publishDraft()` / `deleteDraft()` — admin actions with confirm

---

## style.css Additions (at end of file)
- `.lock-badge-nav` — red pill badge in nav
- `.draft-mode-bar` — blue bar indicator
- `.editor-grid-table` styles — th, td.time-cell, td.slot-cell, drag-over, conflict-target
- `.sched-block` base + `.source-ga` (green) + `.source-manual.is-draft` (blue dashed) + `.source-manual:not(.is-draft)` (purple)
- `.has-conflict` + `@keyframes conflictPulse`
- `.editor-left-panel`, `.draft-item`, `.conflict-toast`, `.editor-legend`, `.legend-swatch`

---

## Key Implementation Notes
- `api_move_class` now accessible to all logged-in users (not just admin) — lock guards inside
- Draft entries stay invisible on main `view_timetable.html` because timetable routes query `is_draft=False` implicitly (they query all ScheduledClass for the entity — need to ensure timetable queries filter `is_draft=False`)
- `KNOWN_DEPARTMENTS` list defined before `schedule_editor` route (reused from elsewhere in app.py)
- Regular users max 3 active drafts per department (enforced in `/api/draft/create`)
- Publish pre-checks for hard conflicts before merging draft → master
