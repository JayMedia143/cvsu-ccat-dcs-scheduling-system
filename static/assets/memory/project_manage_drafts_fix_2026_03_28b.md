---
name: Manage Drafts Fix — Browser Cache + Null Guards (2026-03-28)
description: Root cause and fix for New Draft / Edit buttons not working in manageDraftsModal; browser cache issue + dead code removal
type: project
---

## What was fixed

**Left panel draft card changes:**
- Max cards shown: 4 → 2 (`drafts[:2]` in template, `shown = DRAFTS_DATA.slice(0,2)` in JS)
- Card colors changed to green theme (`.draft-item` border/hover/active/name all use `#137333` / `#e6f4ea` / `#b7dfcc`)
- "Manage drafts →" / "View all N drafts →" link updated to show count when >2

**Two-panel in-modal approach (no stacked modals):**
- `#manageDraftsModal` has two panels: `#mdListView` (default) and `#mdFormView` (hidden)
- `openMdfCreate()` — shows form panel, used for New Draft
- `openMdfEdit(id)` — shows form panel pre-filled, used for Edit
- `closeMdfForm()` — returns to list panel
- `submitMdfForm()` — async POST/PATCH, calls closeMdfForm on success
- Buttons wired in DOMContentLoaded: mdNewDraftBtn → openMdfCreate, mdBackBtn → closeMdfForm, mdCancelFormBtn → closeMdfForm

**Root cause of TypeError (lines 2210/2230):**
The browser was caching an old version of schedule_editor.html (file was 2086 lines but browser's cached version was longer with old code at those line numbers). Hard-refresh (Ctrl+Shift+R) fixed it temporarily but browser re-cached old version on subsequent loads.

**Permanent fix (app.py — schedule_editor route):**
```python
response = make_response(render_template('schedule_editor.html', ...))
response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
response.headers['Pragma'] = 'no-cache'
return response
```

**Null guards added (schedule_editor.html):**
`openMdfCreate` and `openMdfEdit` both check `document.getElementById('mdfError')` first — if null, log `console.error` with "stale cached page? Hard-refresh" message and return early.

**Dead code removed (schedule_editor.html):**
- `openEditDraftModal(id)` — old stacking-modal approach, was never called
- `openNewDraftFromManage()` — old stacking-modal approach, was never called

**Why:** These old functions hid `manageDraftsModal` and showed `newDraftModal` with stacked modal approach — confirmed as dead code. Removing prevents accidental future invocation.

**How to apply:** For any Flask route serving dynamic HTML that's been recently modified — add Cache-Control: no-store to prevent stale browser caching.
