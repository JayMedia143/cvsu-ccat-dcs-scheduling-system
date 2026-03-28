---
name: User-Side Bug Fixes 2026-03-25
description: 3 bugs fixed in user role view and student portal after user-side audit
type: project
---

## Status: FIXED (2026-03-25)

**Why:** User reported that school logos disappeared in section/room timetables. Full user-side audit was done covering 'user' role (view_timetable) and public student portal.

**How to apply:** Changes in app.py, base.html, student_schedule.html.

## B-1 — Section/Room timetable logo invisible (HIGH) — app.py line 6377

**Root cause:** Inside `render_excel_to_html()`, images from the Excel template are positioned using:
```
left_pct = (left_ref + left_offset_px) / total_w_px * 100
```
The school logo sits in column A (before the schedule grid which starts at column B).
`_col_ref()` maps pre-table columns to key -1 in col_offsets → returns 0.
So `left_ref ≈ 0`.

- Section/Room was using `left_offset_px=-30`: `left_pct = -30/600*100 = -5%` → **invisible** (clipped left)
- Faculty uses `left_offset_px=20`: `left_pct = 20/600*100 = 3.3%` → **visible**

**Fix:** Changed `left_offset_px=-30` to `left_offset_px=20` for section/room/course block (line 6377).

**Key architecture note:** `_extract_ws_images_html()` handles all embedded Excel images. The `left_offset_px` parameter compensates for column positioning when the logo is in a pre-table column. The value must be ≥ 0 to keep the logo inside the visible container.

## B-2 — Semester filter broken for 'user' role (MEDIUM) — base.html

**Root cause:** Semester filter toolbar in base.html was shown to all roles, but the route `/set-semester-filter/<semester>` has `@role_required('admin', 'superadmin')`. Clicking it as 'user' role silently redirected back to view_timetable without setting the semester.

**Additional note:** view_timetable does NOT use `session['selected_semester']` — it has its own semester selector via URL params and `switchSemester()` JS. The nav semester filter is only for admin CRUD pages.

**Fix:** Wrapped semester toolbar in `{% if session.get('role') in ['admin', 'superadmin'] %}` in base.html.

## B-3 — Print button silent error in student_schedule.html (LOW) — student_schedule.html

**Root cause:** `document.getElementById('scheduleFrame').contentWindow.print()` has no try-catch. If iframe not loaded yet, JS throws an unhandled error with no user feedback.

**Fix:** Wrapped in try-catch with `alert('Please wait for the schedule to load before printing.')`.

## Non-issues found during audit
- 'user' role redirect fallback (change_password etc. → dashboard) auto-corrects via role_required decorator — double redirect only, no crash
- All timetable HTML routes (section/faculty/room/course-timetable-html) have @login_required only — accessible to 'user' role correctly
- Student portal CSRF, rate limiting, template variables — all verified correct
