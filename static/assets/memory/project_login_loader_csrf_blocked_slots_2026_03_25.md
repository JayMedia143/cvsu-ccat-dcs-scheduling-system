---
name: Login Loader Flash Fix + Generate CSRF Fix + Blocked Time Slots Feature
description: Fixed login content flash, fixed generate schedule 400 error (CSRF), added Blocked Time Slots to global settings with GA enforcement
type: project
---

## Status: IMPLEMENTED (2026-03-25)

---

## Fix 1 — Login page content flash (all roles)

**Problem:** After login, dashboard content was briefly visible before the loader overlay appeared.

**Root cause:** `#page-loader` div has `style="display:none"` inline. The body `<script>` that shows it runs AFTER the browser already painted the body HTML (100-200ms gap).

**Fix — base.html + style.css:**
1. Added synchronous `<script>` in `<head>` (just before `</head>`):
   `if(sessionStorage.getItem('loginPending')){document.documentElement.classList.add('login-loading');}`
2. Added CSS rule: `html.login-loading #page-loader { display: flex !important; }`
3. Body script adds `document.documentElement.classList.remove('login-loading')` before the setTimeout

**Why this works:** `<script>` in `<head>` is synchronous — runs before any body content renders. The CSS class is active before the first body pixel is painted.

---

## Fix 2 — Generate Schedule 400 error (start-generation + stop-generation)

**Root cause:** `CSRFProtect(app)` is active globally (app.py line 69). The fetch calls in `generate_schedule.html` sent no CSRF token → Flask-WTF returned 400 before the route handler ran.

The CSRF meta tag IS in base.html: `<meta name="csrf-token" content="{{ csrf_token() }}">` but was never read by the JS.

**Fix — generate_schedule.html (2 fetch calls):**
- start-generation: added `'X-CSRFToken': document.querySelector('meta[name=csrf-token]').content` to headers
- stop-generation: same header added

**Important pattern:** All AJAX POST/PUT/DELETE fetch calls need this header if CSRFProtect is active.

---

## Feature — Blocked Time Slots in Global Settings

**What it does:** Admin/superadmin can block specific day + time ranges in Global Settings modal. The GA hard-rejects (HC_PENALTY = 1,000,000) any class placement overlapping a blocked slot. Not a toggleable constraint — always enforced.

**DB:** `system_settings.blocked_slots_json TEXT` column added + migrated.
Format: `[{"day": "Monday", "start": "07:00", "end": "09:00"}, ...]`

**GA implementation (genetic_algorithm.py):**
- `GeneticScheduler.__init__` accepts `blocked_slots=None`
- Builds `self._blocked_bitmasks = {day_idx: combined_bitmask}` using same bitmask approach as room/faculty/section conflict detection
- HC check added after HC-03: `if g.bitmask & _day_blocked → HC_PENALTY`

**Bitmask math verification:**
- Block "07:00–09:00" with start_hour=7 → slots 0–3 → bitmask=0b1111
- Gene at 9:00 AM (slot 4) → bitmask=0b...110000 → `& 0b1111 == 0` → NOT blocked ✓
- Gene at 8:00 AM (slot 2) → bitmask overlaps → BLOCKED ✓
- Only the specific time range is blocked, not the whole day

**UI (base.html settings modal):**
- Day dropdown + Start/End time dropdowns (30-min granularity, built from start_hour/end_hour)
- "Add" button → adds badge; overlap/duplicate validation prevents conflicting blocks
- Overlap check: `s.start < end && start < s.end` (works on zero-padded HH:MM strings)
- Hidden input `blocked_slots_json` submits JSON with the form

**app.py changes:**
- `save_settings`: `settings.blocked_slots_json = request.form.get('blocked_slots_json', '[]') or '[]'`
- `start_generation`: parses `_blocked_slots` from settings, passes `blocked_slots=_blocked_slots` to GeneticScheduler
