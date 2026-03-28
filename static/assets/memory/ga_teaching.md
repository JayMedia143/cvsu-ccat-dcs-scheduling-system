---
name: GA Teaching Session Progress
description: Step-by-step GA teaching progress in Taglish — which parts have been explained and what's next
type: project
---

Teaching the GA step by step in layman's terms (Taglish, one concept at a time, with live code line references and sample computations).

## Progress
- **Part 1.1 DONE** — Gene class (11 fields), bitmask explained (bit shifting, AND operation, conflict detection)
- **Part 1.2 DONE** — Chromosome class (9 fields: genes, fitness, hard_conflicts, soft_score, conflicting_indices, rank, crowding_distance, sc1_violations, sc2_violations)
- **Part 2 DONE** — Initialization (__init__): basic data load, quick-lookup maps, faculty available days, room categories, pre-cached constraint data, fixed genes
- **Part 3 DONE** — Creating Initial Population:
  - create_genome() — random schedule, guaranteed no hard conflict, greedy placement, 60 fast attempts + exhaustive fallback
  - _build_seed_chromosome() — galing sa nakaraang saved schedule sa DB, kulang na genes pinupunan ng create_genome logic
  - _perturb_chromosome() — kumukopya ng seed tapos binabago 5-20% ng genes para gumawa ng diverse variants
  - Population composition: 1 seed + 60% perturbed + 40% fresh random

## NEXT
Part 4 — Fitness Evaluation (calculate_fitness)
