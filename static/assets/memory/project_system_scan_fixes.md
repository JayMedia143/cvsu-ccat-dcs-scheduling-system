---
name: System-Wide Scan Fixes (2026-03-20)
description: Results of full system scan across app.py, genetic_algorithm.py, templates, and static files — what was fixed, what was confirmed OK, and what is deferred
type: project
---

# System-Wide Scan & Fixes — 2026-03-20

Full scan of `app.py`, `genetic_algorithm.py`, all templates, and static files.

---

## FIXED IN THIS SESSION

### C-1 — `faculty.sex` missing from DB auto-migration (CRITICAL)
**File:** `app.py` ~line 7687
**Problem:** `_fac_cols_needed` only had `academic_rank`. Old databases without `sex` column crashed when saving/reading faculty sex field.
**Fix applied:**
```python
_fac_cols_needed = {'academic_rank': 'VARCHAR(100)', 'sex': 'VARCHAR(1)'}
```
Flask startup now auto-migrates the `sex` column on old databases.

---

### M-1 — Crossover does NOT maintain Lec/Lab faculty pairing (MEDIUM)
**File:** `genetic_algorithm.py` — `crossover()` function (~line 1781)
**Problem:** `crossover()` placed genes in random order without tracking which faculty was assigned to the Lec gene. Lab siblings could get a different faculty, violating the pairing invariant maintained by all other paths (create_genome, proportional_mutate, _perturb_chromosome, _repair_chromosome, _hard_conflict_repair).

**Fix applied:**
- Added `lec_fac_lookup = {}` dict inside `crossover()`
- Fixed genes seed the lookup on load
- As each non-fixed gene is placed: Lec updates the lookup; Lab reads it and overrides `faculty_id`
- **Second pass** after all genes placed fixes the Lab-placed-before-Lec case:
```python
for i, g in enumerate(child_genes):
    if g and g.gene_type == 'Lab' and not g.is_fixed:
        _pf = lec_fac_lookup.get((g.section_id, g.course_id))
        if _pf is not None and g.faculty_id != _pf:
            self._remove_from_occ(g, occ_room, occ_fac, occ_sec)
            g.faculty_id = _pf
            self._add_to_occ(g, occ_room, occ_fac, occ_sec)
```

---

### L-1 — Outdated log message in generate_schedule.html (LOW)
**File:** `templates/generate_schedule.html` ~line 570
**Fix:** Changed `"Checking constraints HC-01 to HC-24..."` → `"Checking constraints HC-01 to HC-29..."`

---

### L-3 — `randomize_gene_fast()` fallback ignored `locked_day` (LOW)
**File:** `genetic_algorithm.py` ~line 1400
**Problem:** 60-attempt exhaustion fallback used `random.randint(0, days_count-1)`, ignoring `locked_day`, transiently violating HC-29.
**Fix applied:**
```python
_ld_fb = getattr(gene, 'locked_day', -1)
gene.day_idx = _ld_fb if _ld_fb >= 0 else random.randint(0, days_count - 1)
```

---

## DEFERRED (not yet implemented)

### M-2 — Stagnation fix at HC=1-3 ("Last Seat Problem")
**File:** `genetic_algorithm.py`
**Status:** Diagnosed, fix design known, but NOT yet coded.
**Problem:** When repair fills almost all slots, remaining conflicting gene has nowhere to go → GA stagnates at HC=1-3 indefinitely.
**Proposed fix:** `_exhaustive_resolve_last_conflicts()` with 1-level backtracking — temporarily displace a non-conflicting gene, place the problem gene, re-place displaced gene.
**Why deferred:** Large implementation, warrants its own session.

### L-2 — `session_type` not tracked in Gene class
**File:** `genetic_algorithm.py`
**Status:** Noted, low risk.
**Problem:** `session_type` inferred at save time from room capability (`'Lab' if 'Computer Lab' in caps else 'Lec'`). Could drift during warm-start if room changes.
**Proposed fix:** Add `session_type` attribute to Gene and carry through save/load.

### L-4 — Bare `except: pass` blocks (code smell)
**File:** `app.py` — lines 2543, 2583, 3760, 4457, 4517, 5135, 7148, 7208, 7712
**Status:** Not functional bugs. Optional cleanup.

---

## CONFIRMED OK — No Action Needed

| Area | Status |
|------|--------|
| All 40 constraints in GA (HC-01–HC-29, SC-I×5, SC-II×6) | All implemented correctly |
| HC-02 excluded from GA | Intentional — needs full room grid scan |
| HC-29 FACULTY_DAY_SPLIT in GA | Consistent across all paths |
| PE keywords = ('PE', 'FITT') only | Correct |
| LEC_LAB_PROXIMITY threshold > 3 | Correct |
| Room dept filtering in all GA paths | Consistent via `_get_rooms_for_gene()` |
| 3-Phase GA with STAG_SC1_TIMEOUT=60 | Correct |
| All 8 timetable routes use `_get_cached_template` | Correct |
| All 8 timetable routes use `joinedload` | Correct |
| `build_schedule_overlays()` uses `sorted(cell_data.items())` | Correct |
| `room_neutral`/`faculty_neutral` vtypes | Correct |
| Subject table totals via "Consultation:" scan | Correct |
| Tooltip hideTimer hover bridge | Correct |
| Ctrl+Scroll zoom with pointer-events passthrough | Correct |
| manage_faculty: sex + academic_rank in Add/Edit modals | Correct |
| base.html: universalScheduleModal, z-index, dropdown links | Correct |
| LuckySheet: fully removed | Clean |
| manage_constraints.html: all 40 constraints | Dynamic from DB — correct |
| NSTP University Field capacity==999 multi-assignment handling in GA | Correct |
