---
name: Student Masterlist — Phase 2 Item 1
description: Full student CRUD, archive, portal, schedule view, and Excel import feature added 2026-03-25
type: project
---

## What was built
Phase 2, Item 1: Student Masterlist Directory — completed 2026-03-25.

**Why:** System needed a way to manage student enrollment data and let students look up their own class schedule without logging in.

**How to apply:** All student routes are in app.py. Templates are in templates/. The student portal is public (no auth). Admin routes require `@role_required('admin', 'superadmin')`.

## DB Model — Student
```python
class Student(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    student_id  = db.Column(db.String(20), unique=True, nullable=False)
    full_name   = db.Column(db.String(120), nullable=False)
    year_level  = db.Column(db.Integer, nullable=False)
    section_id  = db.Column(db.Integer, db.ForeignKey('section.id'), nullable=True)
    email       = db.Column(db.String(120), nullable=True)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at  = db.Column(db.DateTime, nullable=True)
    section     = db.relationship('Section', backref='students')
```
**Note:** This table needs to be created on new installations (`db.create_all()` or migration).

## Routes added (app.py)
- `manage_students` — paginated list + filters (name/ID, section, year, sort)
- `add_student`, `update_student` — CRUD with validation (year_level 1-4, student_id ≤20 chars, email regex)
- `archive_student`, `bulk_archive_students` — soft archive
- `students_archive` — recycle bin page
- `restore_student`, `bulk_restore_students`, `delete_student`, `bulk_delete_students` — archive management
- `download_student_template` — styled .xlsx template with header/sample/notes rows
- `import_students_xlsx` — bulk Excel import (columns: student_id, full_name, year_level, section_name, email)
- `student_portal` (GET/POST, **PUBLIC**) — enter student ID, redirect to schedule
- `student_schedule` (GET, **PUBLIC**) — shows student info + section timetable iframe
- `public_section_timetable` (GET, **PUBLIC**) — mirrors section_timetable_html without @login_required

## Templates added
- `templates/manage_students.html` — full CRUD table with pagination + jump-to + modals
- `templates/students_archive.html` — recycle bin
- `templates/student_portal.html` — public portal login form (standalone, not extending base.html)
- `templates/student_schedule.html` — public schedule view, matches admin nav theme

## view_schedule_modal extension
Added 'student' type support in `view_schedule_modal` (app.py):
- Looks up student → gets section_id → delegates to section viewer
- If no section assigned: returns warning HTML

## Portal URL sharing
Added Portal dropdown in base.html nav for admin/superadmin:
- "Open Student Portal" link
- Copyable URL input showing `request.host_url + 'student-portal'`

## Rate limiter for student portal
`_portal_attempts` dict added at module level (near `_login_attempts`):
- `_PORTAL_MAX_ATTEMPTS = 10`, `_PORTAL_LOCKOUT_MINUTES = 5`
- Per-IP rate limiting on student_portal POST
