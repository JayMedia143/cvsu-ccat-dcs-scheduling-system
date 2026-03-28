---
name: Security Fixes — Full System Audit 2026-03-25
description: 10 security fixes applied after full system audit; replaces the old project_security_plan.md (PLANNED status)
type: project
---

## Status: IMPLEMENTED (2026-03-25)

**Why:** After adding the Student Masterlist feature (Phase 2 Item 1), a full security scan was done across the entire system to verify new student routes were secure and no regressions existed.

**How to apply:** All fixes are in app.py. No template changes were needed for security.

## Fixes Applied

### F-1 — Secret key (CRITICAL) — app.py line 57
Was: `os.environ.get('SECRET_KEY') or os.urandom(24).hex()`
Now: `os.environ.get('SECRET_KEY') or 'cvsu-ccat-dev-secret-key-change-in-prod'`
- `os.urandom()` generated a new key on every restart, invalidating all sessions

### F-2 — Session fixation (CRITICAL) — app.py login route
Added `session.clear()` BEFORE `session.permanent = True` on successful login.
- Prevents attacker pre-seeding a session ID before the victim logs in

### F-3 — Exception message leak (HIGH) — import_students_xlsx
Changed `flash(f'Error processing file: {e}')` to generic message.
- `str(e)` exposed Python internals (DB column names, file paths) to users

### F-4 — Open redirect (HIGH) — app.py ~line 8272
Was: `return redirect(request.referrer)`
Now: validates referrer starts with `request.host_url`, falls back to dashboard
- Only one bare `redirect(request.referrer)` existed — in the move-schedule route

### F-5 — year_level range (MEDIUM) — add_student + update_student
Added `if year not in (1, 2, 3, 4): flash error + redirect`
- Backend now enforces 1-4 regardless of frontend dropdown

### F-6 — view_schedule_modal access (MEDIUM) — app.py line 4182
Added `@role_required('admin', 'superadmin')` below existing `@login_required`
- Previously any logged-in user could browse all schedule data

### F-7 — Rate limit check (MEDIUM)
Verified ALREADY CORRECT — `>= _LOGIN_MAX_ATTEMPTS` fires after 5 failed attempts (count=5, check on 6th request). No change needed.

### F-8 — Student portal rate limiting (MEDIUM) — student_portal route
Added `_portal_attempts` dict + 10-attempt / 5-min lockout per IP
- Public endpoint was unprotected against student_id enumeration

### F-9 — student_id length (LOW) — add_student + update_student
Added `if len(sid) > 20: flash error + redirect`
- DB column is VARCHAR(20); backend now enforces this

### F-10 — Email format (LOW) — add_student + update_student
Added `re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email)` check
- `re` was already imported in app.py

## Confirmed SAFE (no action needed)
- CSRF: Flask-WTF CSRFProtect active on all forms
- SQL injection: all ORM, no raw SQL
- Jinja2 XSS: auto-escaping on, no `| safe` on user fields
- Password hashing: generate/check_password_hash correct
- Session flags: HTTPONLY, SAMESITE=Lax, 8h lifetime
