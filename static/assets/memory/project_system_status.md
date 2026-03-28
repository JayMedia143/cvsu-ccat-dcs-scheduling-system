---
name: System Status Before Regeneration
description: Snapshot of system state before user triggers new schedule generation (2026-03-13)
type: project
---

State of the system as of 2026-03-13 before regeneration:

**DB State:**
- 70 Lec sessions in A1–A5 (lec-only rooms)
- 28 div4 violations (HC-28) — slots at 10AM/12PM/2PM/4PM/6PM
- All 8 NSTP 1 sections → University Field, Friday 7AM (correct)
- NSTP 2: 0 sections assigned

**GA Configuration (verified correct):**
- `_use_div4_for_lec = True` (8 NSTP1 ≤ 8+5=13 → div4 ON)
- 3-phase optimization: HC→0, SC-I→0, SC-II→0
- Hard phase: 20min, SC-I: 10min, SC-II: 10min
- `SOFT_REFINE_GENS = 800`, SC-I stagnation timeout = 60 gens

**Expected after regeneration:**
- HC-28 violations should be 0 (div4 is ON)
- SC-I violations should be 0 or near 0 (placement-based constraints)
- Victory modal shows "Perfect Schedule!" only if HC=SC-I=SC-II=0

**Why:** User initiated regeneration to verify the 3-phase GA + HC-28 fix works correctly in practice.
