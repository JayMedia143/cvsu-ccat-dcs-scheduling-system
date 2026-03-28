---
name: System Cleanup & File Audit — 2026-03-23
description: Full system scan (17 findings fixed), code cleanup across 4 files, and deletion of 16 unused Python files
type: project
---

## System Scan + Cleanup — 2026-03-23

### Full System Scan Findings (17 issues fixed)

**genetic_algorithm.py — 6 fixes**
- Deleted dead constant `ROOM_UTIL_PENALTY = 60`
- Fixed stale "outdoor/NSTP" comment → "outdoor/special use"
- Removed stale "(was 30-60%, cap 8)" comment from `_guided_soft_mutate`
- `randomize_gene_fast()` now returns `True` on success — callers' `if not placed:` was always True before (None is falsy), causing unnecessary `_exhaustive_place_gene()` calls 100% of the time
- `_build_seed_chromosome()` now builds `_seed_lec_fac` lookup before fill loop; Lab fill-in genes now get `preferred_faculty` → fixes HC-04 violation in warm-start path
- `proportional_mutate()` soft path now uses `randomize_gene_fast` + `lec_fac_lookup` instead of bare `randomize_gene` (no pairing)

**app.py — 5 fixes**
- Secret key → `os.environ.get('SECRET_KEY', 'isang-napaka-sikretong-susi')`
- All 10 Tagalog `I-*` placeholder comments removed (lines 764, 767, 1060, 1365, 1560, 1622, 2017, 2075, 3706, 5074, 5127, 5140)
- Bare `except:` → `except (ValueError, TypeError):` / `except Exception:` on all 4 blocks
- `int()` form inputs wrapped in try/except on 5 routes: add/update course, update room, add/update section, update faculty
- Duplicate `import re` (line 5185) + stale Tagalog comment removed

**seed_db.py — 3 fixes**
- Faculty: all 32 entries now have sex/academic_rank/highest_educational_attainment/available_days; Faculty() constructor updated
- Constraints: HC-27 EARLY_START, HC-28 DIV4_SLOT_ALIGNMENT, HC-29 FACULTY_DAY_SPLIT added (now 29 HCs)
- Rooms: B1–B6 now have `room_departments='Department of Computer Studies'`; Room() constructor updated

**Templates — 3 fixes**
- `check_constraints.html`: "37 constraints" → "40 constraints"
- `manage_sections.html`: `console.log` removed
- `login.html` + `signup.html`: "CvSU-CCAT DCS Scheduling System" → "CvSU Scheduling System"

### File Audit — 16 files deleted

Deleted from project root (none imported by app.py or genetic_algorithm.py):
- `patch_fix.py`, `patch_add_teachable.py`, `patch_all_workloads.py`, `patch_all_workloads_fix.py`, `patch_dynamic_faculty.py`, `patch_seeders.py` — one-time patch scripts
- `check_fac.py`, `check_labs.py`, `check_tba.py` — debug inspection utilities
- `genetic_algorithm_backup.py`, `genetic_algorithm_hybrid.py` — old/experimental GA versions
- `grant_admin.py` — one-time admin setup (hardcoded credentials)
- `populate_dcs.py`, `populate_dcs_full.py` — one-time Excel template generators
- `test_borders.py` — LuckySheet dev utility (imports deleted functions → broken)
- `tba_output.txt` — debug output file

**Remaining .py files in root:** app.py, genetic_algorithm.py, seed_db.py, seeder1–9.py (12 total)

**Why:** `test_borders.py` note in MEMORY.md ("dev utility only, will break") is now irrelevant — file deleted.
