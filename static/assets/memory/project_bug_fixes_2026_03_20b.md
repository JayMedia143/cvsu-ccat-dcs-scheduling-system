---
name: Bug Fixes & UI Improvements (2026-03-20 Session B)
description: HC=1 stagnation fixes, schedule-issues page fix, section overlap flagging, victory panel timing, GA init stall fix
type: project
---

# Bug Fixes & UI Improvements — 2026-03-20 (Session B)

---

## 1. `/schedule-issues` page was always empty (CRITICAL BUG)

**File:** `app.py` ~line 7816
**Problem:** `schedule_issues()` route hardcoded `issues=[]` — the Hard Conflicts section was permanently empty for ALL users on ALL runs.
**Fix:** Now queries `ScheduledClass.query.filter_by(has_conflict=True, semester=semester)` with `joinedload` for course/section/faculty/room. Added semester filter pills. Card header updated to show count + conflict types.

---

## 2. Section overlap (HC-16) not flagged in post-gen save

**File:** `app.py` — post-generation save loop
**Problem:** Save code only checked room overlap and faculty overlap. Section double-booking (same section at same time) was saved without `has_conflict=True`.
**Fix:** Added `sec_slots_seen = defaultdict(set)` check alongside `room_slots_seen` and `fac_slots_seen`. Check 3 in save loop: `if slots_used & sec_slots_seen[sec_key]: conflict = True`.

---

## 3. HC=1 stagnation — improved `_exhaustive_resolve_last_conflicts()`

**File:** `genetic_algorithm.py` — `_exhaustive_resolve_last_conflicts()` ~line 2090

**Fix C-1 — Broadened blocker search:**
If primary search (room OR faculty OR section) finds no blockers, does a second pass: any gene in the same room on the same day (regardless of section/faculty). Catches the "different-section, same-room" block scenario.

**Fix C-2 — HC-18 T.B.A. bypass:**
If stuck gene's faculty has `_fac_avail_days` restrictions, tries reassigning to T.B.A. (multi-assignment faculty). T.B.A. has no availability restrictions so HC-18 can't fire. Prints warning: `"⚠️ HC-18 bypass: gene (...) reassigned to T.B.A."`.

**Fix C-3 — Diagnostic print when HC > 0 at end of run:**
In `run_ga_in_background` after `run_algorithm()` returns, if `best_schedule.hard_conflicts > 0`, prints each stuck gene: course code, faculty name, room, day/time, and flags HC-18 if faculty availability is the cause.

---

## 4. Victory panel: total generations + total time

**Files:** `app.py` + `templates/generate_schedule.html`
- Backend: `_gen_start_time = time.time()` at thread start; `generation_status['total_time']` and `generation_status['total_generations']` set in `finally` block
- Frontend: victory modal now shows e.g. "1,247 gens · 8m 32s" below HC/SC-I/SC-II line
- `pop_size` also passed via progress_callback and exposed in `generation_status`

---

## 5. GA initialization stall (generation=0 for 5–15 min)

**File:** `genetic_algorithm.py` — `run_algorithm()` lines 2619–2654
**Problem:** Initial population of 40–150 chromosomes was created AND fitness-evaluated SEQUENTIALLY before the main loop. `_eval_batch()` (ThreadPoolExecutor) was only used inside the main loop, not during initialization.

**Fix — Warm-start path:**
```python
# Create all chromosomes first
pending = []
for i in range(pop_size - 1):
    nc = perturb or create_genome()
    pending.append(nc)
# Then batch-eval in parallel
self._eval_batch(pending, hard_only=True)
# Repair those with conflicts, batch re-eval
needs_repair = [nc for nc in pending if nc.hard_conflicts > 0]
for nc in needs_repair:
    self._hard_conflict_repair(nc)
if needs_repair:
    self._eval_batch(needs_repair, hard_only=True)
population.extend(pending)
```

**Fix — Cold-start path:**
```python
population = [self.create_genome() for _ in range(pop_size)]
self._eval_batch(population, hard_only=True)
```

**Expected speedup:** 4–8x faster init. Was: 5–15 min. Now: ~1–3 min.

---

## 6. Canvas blank + UI frozen during init

**Files:** `app.py`, `templates/generate_schedule.html`

**Problem:** Canvas showed blank white because `visual_matrix` is never populated during initialization (before main loop). Log showed only "System ready. Waiting for input..." forever.

**Fixes:**
- `app.py`: `generation_status['phase'] = 'init'` set before `run_algorithm()` call; `pop_size` passed via progress_callback
- `generate_schedule.html` canvas `draw()`: when `mat` is null, shows gray background with "Initializing population..." + subtitle text instead of blank
- `generate_schedule.html` polling: adds "⚙ Building initial population..." log entry when `d.generation === 0 && !d.done && log.children.length === 0`; removes it once gen > 0
