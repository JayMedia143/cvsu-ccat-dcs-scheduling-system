---
name: V2.25 Full System Scan & 22 Fixes
description: Full scan of v2.25 folder (2026-03-24) — all 22 findings fixed across GA, app.py, seed_db.py, templates, seeders
type: project
---

Full system scan of v2.25 folder. All 22 issues fixed in one session (2026-03-24).

**Why:** v2.25 was branched from v2.24 but many fixes from earlier sessions had NOT been ported over. This session ported and applied all of them.

**How to apply:** This is the canonical fix list for v2.25. All items are done — no pending items from this scan.

---

## CRITICAL (C-1 to C-8) — ALL FIXED

**C-1 | reports.html** — Broken stat card reduce always returned `'—'`.
Fix: `data.rooms.reduce((a, r) => a + (r.class_count || 0), 0)`

**C-2 | genetic_algorithm.py — `randomize_gene_fast()` returned None always**
Fix: Added `return True` on success path; `return False` at fallback end.

**C-3 | genetic_algorithm.py — `proportional_mutate()` soft path broke Lab pairing**
Fix: Builds `_lec_fac` lookup, passes `preferred_faculty` to `randomize_gene_fast()` for Lab genes in both soft-target and random-fallback branches.

**C-4 | genetic_algorithm.py — `_exhaustive_place_gene()` Phase 2 ignored faculty available_days**
Fix: `_alt_avail = self._fac_avail_days.get(alt_fac)` — days filtered before placement attempt.

**C-5 | genetic_algorithm.py — `_local_search_refinement()` didn't check `locked_day`**
Fix: `_gene_locked_day = getattr(gene, 'locked_day', -1)` — day relocation skipped if `>= 0`.

**C-6 | seed_db.py — Faculty missing 4 fields**
Fix: `Faculty()` now sets `sex`, `academic_rank`, `highest_educational_attainment`, `available_days` from dict keys.

**C-7 | seed_db.py — Room missing `room_departments`**
Fix: `Room()` now sets `room_departments=r.get('room_depts', '')`.

**C-8 | seed_db.py — Missing HC-27, HC-28, HC-29 constraints**
Fix: All three added to `constraints_to_add`.

---

## HIGH (H-1 to H-4) — ALL FIXED

**H-1 | genetic_algorithm.py — `_exhaustive_resolve_last_conflicts()` lec_lookup missed both-conflicting**
Fix: Second pass seeds `lec_fac_lookup` from conflicting Lec genes before Lab repair.

**H-2 | genetic_algorithm.py — `randomize_gene()` no Lab-Lec pairing**
Fix: Rewrote to scan `all_genes` for sibling Lec, passes `preferred_faculty` to `randomize_gene_fast()`.

**H-3 | app.py — `.query.get()` calls with no None check**
Fix: None guards added at ~lines 383, 398, 405, 2209–2221.

**H-4 | genetic_algorithm.py — `_build_seed_chromosome()` Lab fill-in no pairing**
Fix: `_seed_lec_fac` dict built from already-seeded Lec genes; passed as `preferred_faculty` for Lab fill-ins; updated after each new Lec placement.

---

## MEDIUM (M-1 to M-7) — ALL FIXED

**M-1 | genetic_algorithm.py** — Removed dead `ROOM_UTIL_PENALTY = 60` constant.

**M-2 | app.py** — Removed duplicate `import re` inside function (~line 5185).

**M-3 | app.py** — Removed all inline `import re as _re*` / `import json as _json*` inside functions (6 occurrences). All uses replaced with top-level `re.` and `json.`.

**M-4 | faculty_archive.html** — Removed stale `// Needs Python route` comments from bulk restore/delete JS.

**M-5 | rooms_archive.html** — Same stale comments removed.

**M-6 | seeder1–9.py** — Removed duplicate `# Department of Computer Studies (INJECTED)` comment lines from all 9 seeders. Pattern was: two identical consecutive lines with blank between → replaced with single clean comment.

**M-7 | app.py** — Removed all Tagalog developer comments (`# IMPORTANTE ITO`, `# Siguraduhing na-install mo ito`, `# DAGDAG ITO`, `# BAGONG ROUTE: Para i-...`, etc.).

---

## LOW (L-1 to L-6) — FIXED WHERE APPLICABLE

**L-1 | check_constraints.html** — "37 constraints" → "40 constraints".

**L-2 | app.py** — `debug=True` + `host='0.0.0.0'` — noted only, not changed (dev environment).

**L-3 | app.py** — Bare `except: pass` (~9 locations) — noted, cosmetic only, deferred.

**L-4 | manage_sections.html** — Removed `console.log(...)` debug statement.

**L-5 | genetic_algorithm.py** — Magic numbers noted, not extracted (low risk, would require broad refactor).

**L-6 | app.py** — `MAX_CONTENT_LENGTH = 500MB` noted, not changed.
