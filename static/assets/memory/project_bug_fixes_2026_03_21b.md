---
name: Bug Fixes & Features — 2026-03-21 Session B
description: Assign Workload TBA persistence fix, GA fa_map enforcement, available days enforcement, Quick Add TBA buttons, TBA room protection
type: project
---

## Session Summary — 2026-03-21 (Session B)

### Assign Workload — TBA Persistence Fix
**Why:** After clicking Finalize Load, ScheduledClass.faculty_id was never updated — only FacultyAssignment was written. All timetable views and profile displays read from ScheduledClass, so TBA persisted.
**Fix:** `save_faculty_assignments` route (`app.py`) now queries TBA faculty IDs and bulk-updates `ScheduledClass.faculty_id` for all matching `(course_id, section_id)` pairs where faculty was TBA. Also added success flash message.

### Assign Workload — UI Fixes (from session start)
- Dead `teachableForm` event listener removed (was crashing with null reference)
- `set_teachable_courses` fetch removed from Finalize JS → direct `form2.submit()`
- Step 2 card header now shows `${course.code} — ${course.name}` (both code and name)
- `currentAssignmentPairs` deduplicated with `[...new Set([...])]`
- Green highlight CSS added for Step 2 section rows (`.assignment-row input:checked + label`)
- Checkbox icons hidden via `display:none` on both Step 1 and Step 2
- Unique section assignment enforced: `others_taken_by_faculty` dict + JS filter + backend conflict check

### GA fa_map — Respect FacultyAssignment During Generation
**Why:** GA only used FacultyAssignment to filter eligible faculty pool. Actual course-to-faculty mapping was ignored — GA picked faculty randomly, often landing on TBA.
**Fix:**
- `app.py`: builds `fa_map = {(course_id, section_id): faculty_id}` from FacultyAssignment (using already-queried `raw_splits`), passes to `GeneticScheduler(fa_map=fa_map)`
- `genetic_algorithm.py __init__`: accepts `fa_map=None`, stores as `self.fa_map = fa_map or {}`
- `create_genome()` line ~776: checks `self.fa_map.get((course_id, sec_id))` before `random.choice(faculty_ids)`; uses fa_map faculty if still in eligible pool

### GA fa_map — Strict Protection During Mutation & Repair
**Why:** create_genome used fa_map but 8+ mutation/repair functions (proportional_mutate, _guided_soft_mutate, _perturb_chromosome, _repair_chromosome, _hard_conflict_repair, _exhaustive_place_gene, _exhaustive_resolve_last_conflicts, crossover) could override it with random or TBA faculty.
**Fix (3 changes in genetic_algorithm.py):**
1. `randomize_gene_fast()` (~line 1440): promotes fa_map assignment to `preferred_faculty` if not already set — this automatically protects ALL callers since they all call this function
2. `_exhaustive_place_gene()` Phase 2 (~line 2073): returns False immediately if gene has fa_map assignment (no alt-faculty swap)
3. `_exhaustive_resolve_last_conflicts()` HC-18 bypass (~line 2197): skips TBA bypass if gene has fa_map assignment

### GA Available Days Enforcement
**Why:** `randomize_gene_fast()` and `_exhaustive_place_gene()` picked days completely randomly — no check against faculty's `available_days`. A faculty with Mon-Tue only could end up on Friday (HC-18 violation placed but not prevented at placement time).
**Fix (4 changes in genetic_algorithm.py):**
1. After fa_map/preferred_faculty setup: compute `_pref_avail_days = self._fac_avail_days.get(preferred_faculty)` if faculty has restrictions
2. Day selection in 60-attempt loop: if `_pref_avail_days` set, pick only from those day indices; else random
3. Fallback path (after 60 failed attempts): same restriction applied
4. `_exhaustive_place_gene()` Phase 1 days list: filtered to `[d for d in range(...) if d in _fa_avail]`

**Key note:** `_fac_avail_days[faculty_id]` = set of valid day indices. Built in `__init__` from `faculty.available_days` string. Multi-assignment faculty (TBA) are excluded from day restriction.

### Quick Add T.B.A. Faculty
- New route `POST /manage/faculty/quick-add-tba`: auto-generates next TBA-XX (finds max existing), creates Faculty with `full_name='T.B.A.'`, `max_weekly_hours=999`, all days available
- Button "+ T.B.A." added beside "New Faculty" in manage_faculty.html

### Quick Add T.B.A. Room
- New route `POST /manage/room/quick-add-tba`: checks if T.B.A. room exists (unique name); creates with `capacity=999`, `building='Virtual'`; warns if duplicate
- Button "+ T.B.A." added beside "New Room" in manage_rooms.html
- **Only ONE T.B.A. room needed** — it is a multi-assignment room (capacity=999), can be assigned to unlimited simultaneous classes. T.B.A. faculty are different (one slot each), hence multiple needed.

### T.B.A. Room Protection
**Why:** T.B.A. room detection relies on `room_name == 'T.B.A.'` and `capacity == 999`. Editing breaks GA multi-assignment bypass, special_rooms checks, conflict skipping.
**Fix:**
- `manage_rooms.html`: edit + delete buttons hidden for T.B.A. room (`{% if room.room_name != 'T.B.A.' %}`)
- `app.py`: guards in `update_room`, `archive_room`, `delete_room` — flash warning + redirect if room is T.B.A.
- **T.B.A. faculty NOT protected** — admin can freely edit/delete TBA-XX faculty records (intentional)

### Display Days Removal
- `display_days` column removed from SystemSettings model and all related routes/templates
- All timetable routes now use `settings.allowed_days` directly (no display_days fallback)
- Removed from `inject_settings` context processor, `/settings` POST, `_blank_timetable.html`, all seeders
