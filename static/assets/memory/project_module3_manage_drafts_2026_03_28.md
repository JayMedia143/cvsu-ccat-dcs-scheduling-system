---
name: Module 3 Manage Drafts & Draft UX Polish (2026-03-28)
description: All draft-related UX improvements to schedule_editor.html and app.py done after the initial Module 3 scan — mode picker, draft selection fixes, manage drafts modal, unified create/edit modal, nav fix, button UI
type: project
---

# Module 3 — Draft UX Polish (2026-03-28)

## Why
After the Module 3 scan pass, user continued refining the draft workflow across several rounds.

## How to apply
Module 3 draft system is now feature-complete. All draft operations go through DRAFTS_DATA (client-side JS array). The unified `#newDraftModal` handles both create and edit — check `draftFormEditId` to know which mode.

---

## Round 1 — Draft Selection Bug Fixes

**Root cause**: `{{ dv.name|tojson }}` and `JSON.stringify(d.name)` both wrap names in double-quotes. Inside `onclick="..."` (also double-quoted), the HTML attribute closes early → onclick broken.

**Fix 1 — Step 2 draft-pick-item**: Changed to `data-name` attribute + `this.dataset.name` in onclick.
**Fix 2 — All-drafts modal Select button**: Changed from inline onclick to `addEventListener` with JS closure capturing `d.name`.

---

## Round 2 — Mode Picker & All-Drafts Modal

- **Mode picker step 2**: Limited Jinja loop to `unpublished[:2]`; added "View all N drafts →" link (`openAllDrafts()`)
- **All-drafts modal**: Replaced simple cards with google-search-bar, dropdown sort/sem/dept, Bootstrap table, pagination (8 per page)
- **`openAllDrafts()`**: Fixed Bootstrap two-modal conflict — hides `editorModeModal` first, waits for `hidden.bs.modal` event, then shows `allDraftsModal`
- **`selectFromAll()`**: Same pattern — hides `allDraftsModal`, waits for hidden, then calls `chooseDraft()`
- **`chooseDraft()`**: Guards against calling `onDraftChange()` before modal hidden; handles case where modal is already hidden (called from `selectFromAll`)
- **`DRAFTS_DATA`**: Client-side JS array of all drafts serialized from Jinja (id, name, semester, department, notes, is_published)

---

## Round 3 — Manage Drafts Feature

### app.py
- Added `PATCH /api/draft/<int:draft_id>` route (`api_draft_edit`) — edit name, semester, department, notes
- Placed after existing `DELETE /api/draft/<id>` route

### schedule_editor.html — HTML
- **Topbar**: Removed `#newDraftTopBtn` (New Draft) and `#deleteDraftBtn` (Delete Draft); only `#publishDraftBtn` remains
- **Left panel `#draftList`**: Max 4 drafts shown (Jinja `[:4]`); added `#viewAllDraftsLink` ("View all N drafts →" / "Manage drafts →") that calls `openManageDrafts()`
- **`#manageDraftsModal`**: Full manage modal (modal-xl) with search/sort/sem/dept filters, Bootstrap table (Name | Semester | Department | Edit | Delete), pagination
- **`#editDraftModal`**: Initially separate; later removed and merged into `#newDraftModal`

### schedule_editor.html — JS
- `updateModeBadge()`: Simplified — only manages `publishDraftBtn` now
- `refreshLeftPanel()`: Re-renders `#draftList` from DRAFTS_DATA (max 4), updates `#viewAllDraftsLink` count
- `openManageDrafts()`: Resets filters, calls `renderManageDrafts()`, shows modal
- `renderManageDrafts()`: Search/sort/filter/paginate all DRAFTS_DATA (no is_published filter), renders edit+delete buttons via `addEventListener`
- `deleteDraftFromManage(id)`: confirm → DELETE → update DRAFTS_DATA + draftSel → reset mode if active draft deleted → refreshLeftPanel + renderManageDrafts
- State vars: `_mdPage`, `_mdSort`, `_mdSem`, `_mdDept`, `_editDraftId`, `_newDraftCtx`

---

## Round 4 — Unified Create/Edit Modal + Nav Fix + Button UI

### Nav fix (base.html)
- Removed `{% if request.endpoint == 'schedule_editor' %}active{% endif %}` from both nav locations (admin dropdown-item line 84; user menu-item line 162)
- Pending Sections, Pending Faculty, Pending Room already had no active class — no change needed

### Button UI (schedule_editor.html)
- "Create New Draft" button in `#manageDraftsModal` header: changed to `btn-google-action` class (matches courses page "+ New Course" button)
- "Create New Draft" button in `#allDraftsModal` header: same change

### Unified modal (schedule_editor.html)
- `#editDraftModal` removed entirely
- `#newDraftModal` updated: added `data-bs-backdrop="static"`, hidden input `#draftFormEditId`, `#draftFormTitle`, `#draftFormIcon`, `#draftFormSubmitLabel`; Cancel button → `closeDraftForm()`
- `openEditDraftModal(id)`: fills `#newDraftModal` with draft data, sets `draftFormEditId`, shows "Edit Draft" title
- `openNewDraftFromManage()` / `openNewDraftModal()`: clear `draftFormEditId`, set "Create New Draft" title
- `submitNewDraft()`: branches on `draftFormEditId` — if filled → PATCH; if empty → POST create
- `cancelEditDraft()`: hides `#newDraftModal`, re-opens `#manageDraftsModal` after `hidden.bs.modal`
- `closeDraftForm()`: helper — if edit mode calls `cancelEditDraft()`, else just hides modal
- `submitEditDraft()`: removed (merged into `submitNewDraft()`)

### DRAFTS_DATA notes field
- Added `notes:{{ (dv.notes or '')|tojson }}` to DRAFTS_DATA Jinja serialization so edit pre-fills notes textarea
