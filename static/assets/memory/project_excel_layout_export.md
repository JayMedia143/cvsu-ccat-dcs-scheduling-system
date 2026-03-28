---
name: Excel Layout Export Feature — IMPLEMENTED
description: Template-based schedule view system using LuckySheet editor + openpyxl renderer — now fully built
type: project
---

## Status: IMPLEMENTED as of 2026-03-14

This feature was implemented as the **Layout Designer** (manage_layouts.html).
Full implementation details → see [project_layout_designer.md](project_layout_designer.md)

**Why:** User wanted full design control of Excel layout, not system-generated formatting.

## What Was Built
- LuckySheet in-browser Excel editor at `/manage/layouts`
- Per-type templates: section / faculty / room / course
- `{{placeholder}}` variables replaced at render time in `get_schedule_modal()`
- Schedule data plotted into the template grid (day × time cells)
- HTML rendering via `render_excel_to_html_exact()` (openpyxl → pixel-perfect HTML)
- Fallback basic timetable when no template is uploaded
- Delete layout per type via `POST /delete-layout/<type>`

## Placeholders Available (implemented)
- `{{name}}` / `{{NAME}}` / `{{SECTION}}` etc. → entity name
- `{{semester}}`, `{{acad_year}}`, `{{department}}`, `{{school}}`, `{{generated}}`
- `{{sig1}}`, `{{sig1_title}}` ... `{{sig3_title}}` — signatories from SystemSettings
- Faculty: `{{employee_id}}`, `{{employment_status}}`, `{{highest_education}}`, `{{max_weekly_hours}}`, `{{total_contact_hours}}`, `{{num_preparations}}`, `{{daily_Mon}}` etc.
- Section: `{{year_level}}`, `{{num_students}}`
- Room: `{{building}}`, `{{capacity}}`, `{{capabilities}}`
- Course: `{{course_name}}`, `{{lec_units}}`, `{{lab_units}}`, `{{program}}`

## Pending
- Manage signatories UI in Global Settings (add/remove rows per type)
- Image rendering for XLSX-embedded images in faculty/room/course layouts
