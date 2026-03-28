---
name: Bug Fixes & Features — 2026-03-22 Session
description: Split-aware workload hours, HC-09 group-sum fix, preferred_room sibling pairing, stale fa_map semester filter, faculty profile split rows, Teachable Subjects icon hidden
type: project
---

## Session Summary — 2026-03-22

### Workload Map — Split-Aware Hours (Fix A/B/C)
**Why:** workload_map showed full course hours instead of actual split hours; weekly load counter in Assign Final Load modal didn't update live when split inputs changed.
**Fix (app.py ~line 1725):**
- **Fix B** (SC-based): `_sc_hours()` helper computes `(end_min - start_min) / 60`; workload_map built from actual ScheduledClass start/end times
- **Fix A** (FA-based): `_fa_objs` queried with `.join(Course)`; split columns used when set (`split_lec_hours_1/2`, `split_hours_1/2`), else fall back to course hours
- **Fix C** (fa_split_hours_map): `{str(faculty_id): {"course_id-section_id": {lec, lab}}}` — effective hours per faculty+pair; passed as `fa_split_hours_map=` to `render_template()`

**manage_faculty.html:**
- `const faSplitHoursMap = {{ fa_split_hours_map | tojson | safe }};` added at ~line 792
- `updateTotal()` reads `.split-hrs-1`/`.split-hrs-2` input values dynamically (not static `data-hours`)
- `input` listener on `sectionListDiv` retriggers counter when split hour fields change
- Step 2 header and per-section badges use `faSplitHoursMap` lookup (with fallback)

### HC-09 / HC-08 Constraint Checker — Group-Sum Fix
**Why:** FILI101 Lab split 3+3 fired HC-09 "3h, expected 6h" because each ScheduledClass row was checked independently.
**Fix (app.py ~line 4195):**
```python
_lab_dur_sum = defaultdict(float)  # key: (course_id, section_id)
_lec_dur_sum = defaultdict(float)
# pre-compute sum of all Lab/Lec durations per course-section pair
_hc09_seen = set()
_hc08_seen = set()
```
HC-09 block uses `_lab_dur_sum[(course_id, section_id)]` (total across all Lab rows) vs `req_slab_d`. Fires at most once per (course_id, section_id) pair.

### Split Gene Room Retention — preferred_room Sibling Pairing
**Why:** GA split pairs (two sub-genes for same course on different days) often got different rooms — one real dept room, one T.B.A.
**Fix (genetic_algorithm.py):**
- `randomize_gene_fast()` gains `preferred_room=None` param; `_use_preferred_room` flag used in Phase 1 (35 attempts) + Phase 2 (10 attempts) of the 60-attempt loop
- `create_genome()` split loop: `_split_room` tracker — after Gene 1 placed with real room, `preferred_room=_split_room` passed to Gene 2's call
- preferred_room only used if not in `tba_room_ids` and in `primary_rooms`

### Stale fa_map Semester Filter
**Why:** `raw_splits = FacultyAssignment.query.all()` returned ALL semesters — stale FacultyAssignment rows forced wrong faculty (e.g., MATH101 → Prof Mabini) onto courses in unrelated semesters.
**Fix (app.py ~line 3609):**
```python
raw_splits = (
    FacultyAssignment.query
    .join(Course, FacultyAssignment.course_id == Course.id)
    .filter(Course.semester_offered == target_semester)
    .all()
)
```

### Faculty Profile — Assigned Courses: Individual Split Rows
**Why:** User wants each split sub-gene shown as a separate row (e.g., FILI101 Lab 3+3 → two rows of "Lab 3h") so it's visually clear how many sessions exist.
**Fix (app.py ~line 1833):** Removed `_seen_asgn`/`_dedup_asgn` dedup loop. Replaced with flat `_asgn_list` — every ScheduledClass row becomes its own entry. Each entry has:
- `session_type` (Lab/Lec/Async from `sc.session_type`)
- `duration_hours` = `round((end_min - start_min) / 60, 1)` from `sc.start_time`/`sc.end_time`; fallback to course hours if no time data

**Fix (manage_faculty.html ~line 1296):** Badge rendering uses `a.session_type` + `a.duration_hours` directly — no faSplitHoursMap lookup needed:
```javascript
const _dur = a.duration_hours || 0;
if (a.session_type === 'Lab')   badges.push(`...Lab ${_dur}h...`);
else if (a.session_type === 'Async') badges.push(`...Async ${_dur}h...`);
else badges.push(`...Lec ${_dur}h...`);
```

### NameError '_dedup_asgn' — Stale __pycache__
**Why:** After renaming `_dedup_asgn` → `_asgn_list`, Flask threw NameError referencing the old name. Source code was already correct.
**Root cause:** Python `__pycache__` cached old `.pyc` bytecode. Evidence: underline `^^^^^^^^^^^` = 11 chars = `_dedup_asgn` length, not 10 chars = `_asgn_list`.
**Fix:** Restart Flask — forces `.pyc` recompile from updated source. No code changes needed.

### Teachable Subjects Modal — Hide Checkbox Icon
**Why:** `bi bi-app` square icon beside each course card was visually distracting as a fake checkbox.
**Fix (manage_faculty.html line 635):** Added `d-none` to the icon:
```html
<i class="bi bi-app text-muted fs-5 check-indicator d-none"></i>
```
Selection still works via label click + CSS border highlight on `.course-readable-card input:checked + label`.
