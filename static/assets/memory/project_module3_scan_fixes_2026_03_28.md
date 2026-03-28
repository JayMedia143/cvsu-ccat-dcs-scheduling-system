---
name: Module 3 Scan & Fixes (2026-03-28)
description: All 12 non-functional issues found in the Schedule Editor (Module 3) after the initial build, and the fixes applied to app.py and schedule_editor.html
type: project
---

# Module 3 Scan Results & Fixes — 2026-03-28

Scan identified 12 issues (2 broken, 7 UX gaps, 3 minor). All 12 fixed.

## app.py fixes

**Fix 9 — api_move_class response key standardized**
- Changed `{success: True/False}` → `{ok: True/False}` to match all other Module 3 routes
- JS `handleDrop()` updated: `if (!res.success)` → `if (!res.ok)`

**Fix 10 — User.department column**
- Added `department = db.Column(db.String(100), nullable=True)` to `User` model
- Added DB migration: `ALTER TABLE user ADD COLUMN department VARCHAR(100)`
- Updated `schedule_editor` route: reads `user.department` directly, falls back to Faculty ilike only if NULL

## schedule_editor.html fixes

**Fix 1 — Room auto-fill when view type = Room**
- In `loadGrid()`, added: `else if (vt === 'room') document.getElementById('addRoom').value = entityId;`

**Fix 2 — AI-Lock toggle button**
- Added `#lockToggleBtn` in topbar (admin-only, hidden from users)
- Button shows green "Lock Schedule" or red "Unlock Schedule" based on current state
- `toggleLock()` calls `POST /api/schedule/toggle-lock`, updates `lockStatus` var + button UI + reloads grid
- Added `let lockStatus = LOCK_STATUS;` as mutable state alongside `const LOCK_STATUS`

**Fix 3 — Locked GA entries: edit modal disabled**
- In `openEditModal()`: if `lockStatus && entry.source === 'ga' && USER_ROLE === 'user'` → disable all inputs, hide Save button, show `#editLockWarning` message

**Fix 4 — publishDraft() alert → toast**
- Replaced `alert('Publish failed: ...')` with `showToast(...)` for consistent UX

**Fix 6 — Entry count in draft panel**
- After `loadGrid()` fetch succeeds, updates matching `.draft-item[data-id]` `.draft-meta` with `(N entries)` badge

**Fix 7 — Dead error check removed in submitEditEntry()**
- Removed unreachable `if (!res.ok)` block after PATCH fetch (errors already caught by `.catch()`)

**Fix 8 — End time auto-adjusts when start time changes**
- Added `addEventListener('change')` on `#addStart` that sets `#addEnd` to `start + 3h` (clamped to END_HOUR)

**Fix 11 — Short block (30min) overflow**
- Added `.sched-block.block-tiny` CSS: hides `.blk-sub` and `.blk-time`, adds `overflow:hidden`
- `placeBlock()` applies class `block-tiny` when `height < 35`

**Fix 12 — Empty state message**
- After `renderGrid()`, if `masterEntries.length + draftEntries.length === 0`, shows centered "No scheduled classes found." overlay in `#calGrid`
- Overlay removed at start of next `renderGrid()` call

## Why
User scanned Module 3 after initial build and found parts non-functional. Full fix pass applied in one session.

## How to apply
Module 3 is now feature-complete. Future work on schedule_editor.html should be bug fixes or UX polish only.
