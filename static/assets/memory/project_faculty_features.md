---
name: Faculty Features — Day Split, Lec/Lab Separation, Profile Offcanvas
description: Faculty workload split by day, Lec/Lab separation in modal, View Profile offcanvas with assignments list
type: project
---

## Faculty Day Split — COMPLETED 2026-03-19

Allows faculty to pin specific courses to specific days (e.g., Lab on Tuesday + Wednesday).

**Why:** Faculty may only be on campus certain days; they need to control which day each course session falls on.

### DB changes (FacultyAssignment model)
8 new columns added via migration at app startup:
- `split_day_1`, `split_hours_1`, `split_day_2`, `split_hours_2` — Lab session splits
- `split_lec_day_1`, `split_lec_hours_1`, `split_lec_day_2`, `split_lec_hours_2` — Lec session splits

### Gene class (genetic_algorithm.py)
- Added `locked_day` to `__slots__`, default `-1` (no lock)
- `-1` = normal random placement; `>= 0` = must be placed on that `day_idx`

### GA split_map (GeneticScheduler.__init__)
- Keyed by `(course_id, section_id, gtype)` — Lab and Lec splits are independent
- Old bug: keyed by `(course_id, section_id)` → both types got split treatment; fixed by adding `gtype`

### GA placement
- `create_genome()`: If split pairs exist for a gene's `(course_id, sec_id, gtype)`, creates sub-genes (one per split pair) with `locked_day` set; skips normal single-gene path
- `randomize_gene_fast()`: Uses `locked_day` as day when `>= 0`
- `_exhaustive_place_gene()`: Restricts day list to `[locked_day]` when set
- `_copy_gene()`: Copies `locked_day`

### HC-29 FACULTY_DAY_SPLIT constraint
- Added to DEFAULT_CONSTRAINTS in app.py
- GA fitness: penalizes any non-fixed gene where `gene.day_idx != gene.locked_day`
- Constraint checker: pre-built `_split_map_cc` from FacultyAssignment table

### Generate route (app.py)
- Queries FacultyAssignment, builds separate Lab and Lec split entries
- Passes `split_assignments` to `GeneticScheduler(...)`

---

## Lec/Lab Separation in Assign Final Workload Modal — COMPLETED 2026-03-19

**Why:** Old modal showed "5h" badge combining Lec+Lab — faculty couldn't tell which sessions to split independently.

### manage_faculty.html
- Teachable course checkboxes now have separate `data-lec-hours`, `data-lab-hours`, `data-async-hours` attributes
- JS `nextBtn` handler creates separate rows per session type (Lec = blue border, Lab = yellow, Async = gray)
- Each row has an independent `buildSplitPanel()` split panel (day dropdowns + hours inputs)
- Panel IDs: `splitpanel_{facultyId}_{pair}_{sfx}` where sfx = `lec_` for Lec, `` for Lab
- `toggleSessionPanels()`: shows/hides `.session-panels-{facultyId}-{pairKey}` divs per checkbox state
- JS finalize: collects both Lab (sfx='') and Lec (sfx='lec_') split data per assignment

---

## Faculty Profile Offcanvas — COMPLETED 2026-03-19

Non-blocking side panel showing faculty details and assigned courses.

### Offcanvas config (manage_faculty.html)
- `data-bs-backdrop="false" data-bs-scroll="true"` — no dark overlay, page stays clickable
- Width: 380px, slides from right
- Header icon: `bi-eye text-muted` (was `bi-person-lines-fill text-primary`)
- Navigation arrows (prev/next) to browse all faculty

### View Profile button
- Icon: `bi-eye` (was `bi-person-lines-fill`)
- No blue color (was `style="color:#0d6efd;"` — removed)

### Academic Rank field
- Added to Add Faculty modal and Edit Faculty modal (after Educational Attainment)
- `add_faculty` route: saves `academic_rank=request.form.get('academic_rank', '')`
- `update_faculty` route: sets `faculty.academic_rank = request.form.get('academic_rank', '')`
- DB migration: `faculty.academic_rank VARCHAR(100)` already existed

### Assignments list in offcanvas body
- `manage_faculty` route: `faculty_profiles` builder now includes `assignments` list per faculty
  - Each entry: `course_code`, `course_name`, `section_name`, `lec_hours`, `lab_hours`, `async_hours`, `semester`
- `openFacultyProfile` JS renders "Assigned Courses" section at bottom of offcanvas
  - Section badge (gray), Lec badge (blue), Lab badge (yellow), Async badge (gray)
  - Only shows badges where hours > 0
  - Empty state: "No assignments yet"

---

## Constraint count — UPDATED 2026-03-19
- **27 Hard constraints**: HC-01–HC-27 (was HC-26 before), now also HC-28 (Div4), HC-29 (Day Split)
- Total: 29 HC + 5 SC-I + 6 SC-II = 40 constraints
