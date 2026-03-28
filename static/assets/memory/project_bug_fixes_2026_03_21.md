---
name: Bug Fixes & Features — 2026-03-21
description: All fixes and features completed in the 2026-03-21 session: seeder fix, GA faculty filter, TBA consolidation, Pending Faculty dept filtering, WORKLOAD display, room dept enforcement, faculty profile, teachable subjects, assign final load.
type: project
---

# Bug Fixes & Features — 2026-03-21

## 1. Seeder `semester_offered` Bug Fix
All 9 seeders (seeder1–9) had `semester_offered='1st'` but GA query uses `'1st Semester'`. Result: 0 genes found → instant "Perfect Schedule" with no actual schedule.
**Fix:** Changed to `'1st Semester'` in all 9 seeders via replace_all.

## 2. GA Faculty Filter — Exclude No-Workload Faculty
**Problem:** Faculty with no `FacultyAssignment` records for the current semester were still being included in the GA pool (causing classes to be assigned to teachers with nothing planned).
**Fix:** `app.py` ~line 3326 — subquery filters to only faculty who have `FacultyAssignment` records for courses in `target_semester` OR are T.B.A.:
```python
_fa_faculty_ids = (
    db.session.query(FacultyAssignment.faculty_id)
    .join(Course, FacultyAssignment.course_id == Course.id)
    .filter(Course.semester_offered == target_semester)
    .distinct()
)
raw_faculty = Faculty.query.filter(
    Faculty.is_archived == False,
    Faculty.max_weekly_hours > 0,
    or_(Faculty.full_name == 'T.B.A.', Faculty.id.in_(_fa_faculty_ids))
).all()
```

## 3. T.B.A. Sequential Filling
**Problem:** GA scattered assignments across TBA-01, TBA-02, TBA-03 randomly.
**Fix:** Post-gen consolidation block in `app.py` ~line 3233 — sorts TBA faculty by numeric suffix, redistributes all T.B.A. `ScheduledClass` records so TBA-01 fills to 80% of `max_weekly_hours / 3` threshold before overflow to TBA-02.

## 4. Pending Faculty T.B.A. Detection Fix
**Problem:** `/resolve-unassigned` only checked the first T.B.A. record's ID — classes assigned to TBA-02/03 were invisible.
**Fix:** `app.py` ~line 3437 — uses `.in_(tba_ids)` with all T.B.A. IDs:
```python
tba_ids = [f.id for f in Faculty.query.filter_by(full_name='T.B.A.').all()]
.filter(or_(ScheduledClass.faculty_id == None, ScheduledClass.faculty_id.in_(tba_ids) if tba_ids else ...))
```

## 5. WORKLOAD Column Fix
**Problem:** Faculty WORKLOAD column in `manage_faculty.html` always showed 0 — was reading from `FacultyAssignment` (empty after GA).
**Fix:** `app.py` ~line 1696 — `workload_map` from `ScheduledClass` GROUP BY query:
```python
workload_map = {row[0]: int(row[1] or 0) for row in _sc_rows}
```
Template uses `workload_map.get(faculty.id, 0)`.

## 6. Pending Faculty Dept Filtering
**Problem:** Faculty dropdown on `/resolve-unassigned` showed ALL faculty regardless of department.
**Fix:** `app.py` ~line 3520 — `_norm_dept()` helper normalizes dept names (strips "Department of", replaces " & " with " and "); `sc_faculty_options = {sc.id: dept_filtered_faculty}` passed to template. Template uses `sc_faculty_options.get(sc.id, all_faculty)`.

## 7. Confirmation Dialog Before Finalize (resolve_unassigned.html)
Added Bootstrap confirm modal before submitting Pending Faculty assignments. JS triggers form submit only after user confirms via `#confirmFinalizeBtn` click. Warning: "This action cannot be undone."

## 8. Room Dept Enforcement + T.B.A. Room as Universal Fallback
**Problem:** GA room pool was dept-filtered but T.B.A. room was excluded. No fallback when dept had no matching room.
**Fix:**
- `app.py` ~line 3367: Removed `room_name != 'T.B.A.'` filter — T.B.A. room now in GA pool
- `genetic_algorithm.py` ~line 247: `tba_room_ids` set; T.B.A. rooms added to `multi_assignment_rooms` (bypasses HC room-conflict check)
- `genetic_algorithm.py` ~line 314: Dept pool fallback chain: dept rooms → T.B.A. room list → all valid rooms
- T.B.A. rooms explicitly added to `_valid_rooms_lec_only` (capacity 999, so capability filter would exclude them)

## 9. Faculty Profile "Assigned Courses" Fix
**Problem:** View Profile offcanvas "Assigned Courses" list read from `f.assignments` (FacultyAssignment — empty after GA).
**Fix:** `app.py` ~line 1713 — pre-fetch `ScheduledClass` records into `sc_assignments_map = {faculty_id: [sc_list]}` using single joinedload query. `faculty_profiles` `'assignments'` list now uses `sc_assignments_map.get(f.id, [])`.

## 10. Teachable Subjects + Assign Final Workload Pre-Population Fix
**Problem:** After Pending Faculty assigns classes, Teachable Subjects modal checkboxes and Assign Final Load Step 2 sections remained empty — both read from `faculty.courses` (many-to-many) and `faculty.assignments` (FacultyAssignment), both empty post-GA.
**Fix:**
- `app.py` ~line 1724: Build `sc_course_ids_by_faculty = {fid: set(course_ids)}` and `sc_pairs_by_faculty = {str(fid): ["cid-sid", ...]}` from existing `sc_assignments_map` (no extra DB query)
- `app.py` ~line 1787: Pass both dicts to `render_template`
- `manage_faculty.html` ~line 619: Teachable checkbox adds `or course.id in sc_course_ids_by_faculty.get(faculty.id, [])` condition
- `manage_faculty.html` ~lines 941–945: `currentAssignmentPairs` JS array also includes `{% for pair in sc_pairs_by_faculty.get(faculty.id|string, []) %}`

## Key Architecture Note
Three separate tables serve different purposes:
- `ScheduledClass` — GA output (the actual generated schedule)
- `FacultyAssignment` — manual workload planning (split days, pre-GA sections)
- `faculty_courses` — many-to-many teachable subjects
After GA/Pending Faculty, only `ScheduledClass` has data. All display features that show "what faculty teaches" must read from `ScheduledClass`, not `FacultyAssignment`.
