---
name: Security Audit & Improvement Plan
description: Login and system security findings + implementation plan — CSRF, secret key, rate limiting, session flags
type: project
---

# Security Audit & Improvement Plan

**Why:** User requested a full security scan of the login system and all related parts to check for SQL injection and other vulnerabilities. Findings documented here for future implementation.

**How to apply:** When user says "gawin na natin ung security", execute this plan.

---

## Status: PLANNED — Not yet implemented

---

## Findings Summary

### SQL Injection — SAFE ✅
All queries use SQLAlchemy ORM or parameterized queries with named placeholders. No raw string interpolation in SQL.

### Password Hashing — SAFE ✅
Uses Werkzeug `generate_password_hash` / `check_password_hash` (pbkdf2:sha256). Good.

### Auth Decorators — SAFE ✅
`@login_required` and `@role_required` properly implemented with `@wraps`.

---

## Issues Found

### 🔴 CRITICAL

**1. No CSRF Protection — ALL forms**
- No Flask-WTF, no csrf_token in any template, no CSRFProtect(app)
- Affects: ALL ~28+ form templates with `method="POST"`

**2. Hardcoded SECRET_KEY**
- `app.secret_key = 'isang-napaka-sikretong-susi'` literally in source (app.py ~line 56)
- Anyone with source code access can forge sessions

### 🟡 HIGH

**3. No Rate Limiting on Login**
- No brute-force protection on `POST /` (login route)
- Unlimited password attempts allowed

**4. Session Cookie — Missing Security Flags**
- Missing: `SESSION_COOKIE_HTTPONLY = True`
- Missing: `SESSION_COOKIE_SAMESITE = 'Lax'`
- Missing: `PERMANENT_SESSION_LIFETIME` (no session expiry)

### 🟢 MEDIUM / LOW

**5. `debug=True` hardcoded** — app.py line 8474. Should be env var.
**6. File uploads: no MIME type check** — only extension checked (.pdf, .xlsx, .png). Low risk for intranet.
**7. No session timeout** — user stays logged in indefinitely.

---

## Implementation Plan

### app.py changes
1. **SECRET_KEY** → `os.environ.get('SECRET_KEY', os.urandom(24).hex())` (generated per-run as fallback)
2. **Session Cookie Flags** → add to config block:
   ```python
   app.config['SESSION_COOKIE_HTTPONLY'] = True
   app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
   app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
   ```
3. **Login Rate Limiting** → in-memory dict tracking `{ip: (attempts, first_attempt_time)}`. After 5 failed attempts within 5 min → block for 15 min. No new packages needed.
4. **debug flag** → `debug = os.environ.get('FLASK_DEBUG', 'False') == 'True'`

### New package
- Add `Flask-WTF` to `requirements.txt`
- Add `from flask_wtf.csrf import CSRFProtect` + `csrf = CSRFProtect(app)` to app.py

### Templates (~28+ files with POST forms)
- Add `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` inside every `<form method="POST">`
- Add `<meta name="csrf-token" content="{{ csrf_token() }}">` to `base.html` <head> for JS fetch calls

### Files to edit
| File | Change |
|------|--------|
| `app.py` | SECRET_KEY env var, session flags, rate limiting, debug flag, CSRFProtect init |
| `requirements.txt` | Add Flask-WTF |
| `templates/base.html` | Add csrf meta tag in <head> |
| `templates/login.html` | Add csrf_token hidden input |
| All ~28 other templates | Add csrf_token hidden input to POST forms |

### NOT doing (low priority for intranet)
- MIME type validation on file uploads
- Session timeout UI warning
- Login attempt logging to DB

---

## Verification Steps
1. After 5 wrong passwords → login blocked for 15 min
2. Browser inspect cookies → HttpOnly flag visible
3. SECRET_KEY not visible in source code
4. All forms have hidden `csrf_token` field
5. Manual form submission without token → 400 error
