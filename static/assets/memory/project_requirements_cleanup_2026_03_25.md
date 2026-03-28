---
name: requirements.txt Cleanup — v2.25
description: Replaced bloated 157-package pip-freeze dump with clean 11-package minimal requirements.txt
type: project
---

# requirements.txt Cleanup — 2026-03-25

Replaced the full `pip freeze` dump (157 packages) with a clean minimal list of only what the app actually imports.

**Why:** Old file included tensorflow, keras, jupyter, matplotlib, seaborn, scipy, Flask-SSE, redis, and 140+ other unrelated packages. Would cause anyone doing a fresh install to download hundreds of MB of irrelevant packages. Also had `pdfplumber` missing entirely and wrong Pillow version.

**How to apply:** If adding new packages to the project, only add what is directly imported in Python files — no transitive deps (they auto-install).

---

## Final requirements.txt (11 packages)

```
Flask==3.1.1
Flask-SQLAlchemy==3.1.1
Flask-WTF==1.2.2
Werkzeug==3.1.3
SQLAlchemy==2.0.41
WeasyPrint==67.0
Pillow==12.1.1
openpyxl==3.1.5
pandas==2.3.3
pdfplumber==0.11.9
```

## Key Fixes Made

| Issue | Detail |
|-------|--------|
| `pdfplumber` missing | Imported in app.py but was not listed at all — fresh install would break |
| `Pillow` version wrong | Was `11.2.1`, actual venv has `12.1.1` |
| 140+ irrelevant packages removed | tensorflow, keras, jupyter, Flask-SSE, redis, etc. |

## Package Source Verification

Actual imports scanned from `app.py` top-of-file:
- `flask`, `flask_wtf`, `flask_sqlalchemy`, `sqlalchemy`, `werkzeug` — web stack
- `weasyprint` — PDF export
- `openpyxl` — Excel export/import
- `pandas` — CSV handling
- `pdfplumber` — PDF curriculum import

`genetic_algorithm.py`, `seed_db.py`, `seeder1–9.py` — stdlib only (werkzeug already covered)

## GLib-GIO Warning (harmless)

When running `python app.py`, this warning may appear:
```
(process:XXXX): GLib-GIO-WARNING **: Unexpectedly, UWP app `Microsoft.OutlookForWindows_...' supports 4 extensions but has no verbs
```
- Source: Windows GIO subsystem used by WeasyPrint
- Cause: Microsoft Outlook UWP has broken registry entries on Windows
- Effect: None — Flask still runs normally. Safe to ignore.
