---
name: Pending Pages Overhaul + Conflict Detection — 2026-03-24 (Session C)
description: Sort dropdowns, pagination style, redirects, room/section/faculty deletion orphan handling, conflict detection on all 3 pending saves, TBA fallback in timetable, fake "All Set!" removed
type: project
---

# Pending Pages Overhaul + Conflict Detection — 2026-03-24 (Session C)

## Sort Dropdowns Added

**Why:** Pending Sections and Pending Room had no sort — inconsistent with Pending Faculty which already had Sort by Course (A-Z / Z-A).

**Changes:**
- `templates/schedule_issues.html`: removed semester filter pills from header, added sort dropdown (same style as resolve_unassigned.html)
- `templates/pending_sections.html`: added sort dropdown
- `app.py` — `schedule_issues()`: replaced `semester` param with `sort` param; removed semester filter; sorts by `Course.course_code` asc/desc; removed `semesters`/`current_semester` from render_template, added `current_sort`
- `app.py` — `pending_sections()`: added `sort` param; joins Course for ordering; passes `current_sort`

## Pagination Style Update (all 3 Pending pages)

**Why:** Old pagination was simple Prev/Next pill buttons — inconsistent with Course page style (numbered pages, Jump to, Go, arrow keys).

**Changes (templates only — kept client-side pagination to preserve live search):**
- `paginationControls` block replaced in all 3 templates with Bootstrap `<ul class="pagination">` + Jump to input + Go button + arrow key hint
- JS `renderPagination()` rewritten to build numbered page buttons dynamically with ellipsis (`buildPageRange()` helper)
- Added Jump to + Go handler, ArrowLeft/ArrowRight keydown handler in each template

## Redirect After Save Fix

**Why:** All 3 pending save routes redirected to `view_timetable` — should go to the relevant manage page.

| Route | Old | New |
|---|---|---|
| `run_pending_sections()` | `view_timetable` | `manage_sections` |
| `run_unassigned_resolver()` | `view_timetable` | `manage_faculty` |
| `run_pending_rooms()` | `view_timetable` | `manage_rooms` |

Also added `flash('Faculty assignments saved.', 'success')` to `run_unassigned_resolver()` which had no flash.

## Room Deletion → Orphan Classes Fix

**Why:** `delete_room()` and `bulk_delete_rooms()` deleted rooms without nullifying `room_id` on affected `ScheduledClass` records. Those classes became invisible — not showing in Pending Room.

**Fix (app.py):**
- `delete_room()`: added `ScheduledClass.query.filter_by(room_id=room_id).update({'room_id': None}, synchronize_session=False)` before `db.session.delete(room)`
- `bulk_delete_rooms()`: added `ScheduledClass.query.filter(ScheduledClass.room_id.in_(int_ids)).update({'room_id': None}, synchronize_session=False)` before bulk delete

**Note:** Section deletion already reassigned to T.B.A. section ✅. Faculty deletion already nullified faculty_id ✅.

## T.B.A. Fallback in Timetable When Room is NULL

**Why:** `get_schedule_grid()` and `build_schedule_overlays()` showed blank when `sc.room` is None — inconsistent with faculty which shows 'T.B.A.'.

**Fix (app.py):**
- `get_schedule_grid()` lines ~3963, 3967, 3975: `else ''` → `else 'T.B.A.'` (section, faculty, course views)
- `build_schedule_overlays()` line ~6697: `else ''` → `else 'T.B.A.'`

## Conflict Detection on All 3 Pending Save Routes

**Why:** All three routes blindly saved assignments with no conflict checking. Double-booking a room/section/faculty caused timetable cells to show a red overlap badge (looked like content "disappeared").

**Pattern for all three:** collect assignments → check each against DB + within batch → if any conflict: flash danger per conflict, no commit, redirect back to pending page. No partial saves.

**`run_pending_rooms()`:**
- Skip T.B.A. room (multi-bookable)
- Check: same `room_id` + same `day` + overlapping time vs existing ScheduledClass + vs batch

**`run_pending_sections()`:**
- Check: same `section_id` + same `day` + overlapping time vs existing ScheduledClass + vs batch

**`run_unassigned_resolver()`:**
- Skip faculty with `full_name == 'T.B.A.'`
- Check: same `faculty_id` + same `day` + overlapping time vs existing ScheduledClass + vs batch

**How to apply:** The existing `check_conflict()` function only checks PreAssignment records — do NOT reuse it for ScheduledClass conflict checking.

## Fake "All Set!" Animation Removed from Pending Faculty

**Why:** `resolve_unassigned.html` had a fake client-side loading animation that showed "All Set!" success screen BEFORE the form was submitted. If the server detected a conflict and redirected back, the user had already seen "All Set!" — very confusing.

**Fix (`templates/resolve_unassigned.html`):**
- Removed `loadingContainer` HTML block (spinner + progress bar)
- Removed `successContainer` HTML block ("All Set!" screen + View Final Timetable button)
- Replaced multi-step animation JS with direct `resolverForm.submit()` — same pattern as Pending Sections and Pending Room
