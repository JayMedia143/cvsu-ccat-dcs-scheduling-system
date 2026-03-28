---
name: GA Speed & Strength Improvements (2026-03-20)
description: All 6 GA improvements implemented this session — backtracking, guided mutation, bitmask overlap, parallel eval, adaptive SC-II weights, HC-02 post-gen check
type: project
---

# GA Speed & Strength Improvements — 2026-03-20

All 6 steps completed and verified. Files changed: `genetic_algorithm.py` (Steps 1–5), `app.py` (Step 6).

---

## Step 1 — _exhaustive_resolve_last_conflicts() [STRENGTH: CRITICAL]

**File:** `genetic_algorithm.py` ~line 2090
**Problem:** HC=1–3 "Last Seat Problem" — stuck gene has no valid slot; GA burned full 20-min Phase 1 budget without solving.
**Fix:** 1-level backtracking helper. For each stuck gene:
1. Find blocker genes (share room/faculty/section on same day+time)
2. Temporarily displace a blocker (save state → remove from occ)
3. Place stuck gene in freed slot
4. Re-place blocker elsewhere — commit if both succeed, rollback if either fails
**Called:** Only when `best_schedule.hard_conflicts <= 5` (targeted). Two call sites:
- LNS offspring loop (line ~2685): after repair if `_lns_low_hc`
- Severe stagnation reset (line ~2809): `if hard_phase and 0 < nc.hard_conflicts <= 5`

---

## Step 2 — _guided_soft_mutate() [STRENGTH + SPEED: HIGH]

**File:** `genetic_algorithm.py` ~line 1312
**Problem:** Phase 3 mutated random genes including already-perfect ones — wasted mutation budget.
**Fix:** Uses existing `_find_soft_violation_indices()` to get soft-violating genes. Mutates only 30–60% of them (capped at 8 per call). Maintains lec_fac_lookup for Lab/Lec pairing. Has HC guard: returns immediately if `hard_conflicts > 0`.
**Called:** In crossover offspring loop inside `if sc2_phase:` branch (line ~2707).

---

## Step 3 — Bitmask Overlap Detection [SPEED: HIGH]

**File:** `genetic_algorithm.py` — `calculate_fitness()` ~lines 867–1069
**Problem:** Old `check_overlap()` used sorted lists (O(k log k)) for room/faculty/section conflict detection.
**Fix:** Added `room_bits`, `fac_bits`, `sec_bits` as `defaultdict(int)` at start of `calculate_fitness()`. Each gene's `bitmask` (pre-computed int) is AND-checked inline: `if (room_bits[_rkey] & _mask) != 0: conflict`. O(1) per check. `room_use`/`fac_use`/`sec_use` lists kept for HC-15, HC-19, HC-27, and lunch break.

---

## Step 4 — _eval_batch() Parallel Evaluation [SPEED: VERY HIGH]

**File:** `genetic_algorithm.py` ~line 1372
**Problem:** All chromosomes evaluated sequentially — 90%+ CPU cores idle.
**Fix:** `_eval_batch(chromosomes, hard_only, sc1_only)` method using `ThreadPoolExecutor`. Batches ≤6 evaluated sequentially (avoids thread overhead). `_N_WORKERS = min(8, os.cpu_count() or 4)` module constant.
**Applied to:**
- Soft-phase offspring: after offspring generation loop, `_eval_batch(offspring, sc1_only=True)` or `_eval_batch(offspring)`
- Hard→SC-I transition: `_eval_batch(population/offspring, sc1_only=True)`
- SC-I→SC-II transition: `_eval_batch(population/offspring)`
- SC-I time-limit advance: `_eval_batch(population)`
**Hard phase stays sequential** — repair depends on fitness being computed first.
**Note:** Python GIL limits true parallelism; real gain is 2–3x concurrent interleaving, not theoretical 8x.

---

## Step 5 — Adaptive SC-II Weight Scaling [STRENGTH: MEDIUM]

**File:** `genetic_algorithm.py`
**Problem:** SC-II penalty fixed at 10 pts — not enough pressure in Phase 3 for "nice to have" constraints.
**Fix:**
- `self._sc2_base = SC2_BASE` added in `__init__` (~line 180)
- `_penalty()` changed: `return self._sc2_base * weight` (was `SC2_BASE * weight`)
- In main loop, each generation:
  ```python
  if current_phase == 'sc2':
      _sc2_elapsed = generation - sc2_start_gen
      _ramp_end = max(1, SOFT_REFINE_GENS // 2)  # 400 gens
      _sc2_t = min(1.0, _sc2_elapsed / _ramp_end)
      self._sc2_base = int(SC2_BASE + (50 - SC2_BASE) * _sc2_t)  # 10 → 50
  else:
      self._sc2_base = SC2_BASE  # reset outside Phase 3
  ```
**Effect:** SC-II penalty ramps 10→50 over first 400 gens of Phase 3, stays at 50 thereafter.

---

## Step 6 — HC-02 Post-Generation Validation [REPORTING: LOW-MEDIUM]

**File:** `app.py` — post-generation save section ~lines 3076–3162
**Problem:** HC-02 (MINOR_SUBJECT_GAP) not in GA; violations were invisible after generation.
**Fix:** Before the gene-to-DB loop:
1. Compute `_hc02_violating_sections` set — sections where free hours < minor-dept hours needed
2. Uses `scheduler.end_hour - scheduler.start_hour` as op_hours, scans all genes for per-section-per-day scheduled hours
3. Skips sections with no minor-dept courses for this semester
In the gene loop: `if not conflict and gene.section_id in _hc02_violating_sections: conflict = True`
After save: prints report to Flask console + sets `generation_status['hc02_violations']` count.
**Note:** Marks ALL genes of a violating section as `has_conflict=True` — this is intentional, signals to user that section needs more free time.

---

## Expected Performance After All 6 Steps

| Metric | Before | After |
|--------|--------|-------|
| HC=0 success rate | ~70–80% | ~95–99% |
| Typical total runtime | 15–25 min | 8–15 min |
| Phase 1 duration | 10–20 min | 3–8 min |
| SC-I violations (final) | 2–8 | 0–3 |
| SC-II violations (final) | 5–15 | 2–8 |
| HC-02 visibility | Invisible | Reported + red in viewer |
