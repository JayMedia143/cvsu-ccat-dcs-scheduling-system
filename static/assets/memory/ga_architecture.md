---
name: GA Architecture Summary
description: Thesis-defense level breakdown of the Genetic Algorithm — Gene, Chromosome, population, evolution phases, mutation, repair, penalties
type: project
---

## Gene (11 fields)
course_id, section_id, faculty_id, room_id, day_idx, start_idx, duration_slots, end_idx, gene_type (Lec/Lab/Async), is_fixed, bitmask

## Chromosome (9 fields)
genes, fitness, hard_conflicts, soft_score, conflicting_indices, rank, crowding_distance, sc1_violations, sc2_violations

## Population Size
Dynamic: max(40, min(150, n_genes x 0.35)). Computed from total gene estimate at runtime.

## Initialization
- Warm start: 1 seed + 60% perturbed variants (5-20%) + 40% fresh
- Fresh start: all random via create_genome()

## Two-Phase Evolution
- Hard phase: hard-only fitness, 20 crossover + 15 LNS offspring/gen, up to 20 min
- Soft phase: full fitness (HC+SC-I+SC-II), 20 offspring/gen, up to 5 min after HC=0

## Crossover
Greedy conflict-aware: fixed genes first, then non-fixed in random order. Try P1, then P2, then exhaustive scan. Produces HC=0 children often.

## Mutation (Proportional)
- HC > 0: mutate ALL conflicting genes (60 attempts each, adaptive faculty swap)
- HC = 0: 40% target soft violations, 15% random gene
- Adaptive rate: 20%-80% (hard), 50%-80% (soft), scales with stagnation

## Repair (_hard_conflict_repair)
DSatur-inspired graph coloring: build conflict graph -> sort by degree (most constrained first) -> place each in clean space -> exhaustive fallback

## LNS
Hard phase only: copy best + repair only conflicting_indices genes (targeted, fast)

## Stagnation
- Mild (15 gens): replace 25% of population (70% elite+repair, 30% fresh)
- Severe (40 gens): keep 3 elites + repair 5 elites + fill fresh
- Diversity inject: >=85% same fingerprint, 20-gen cooldown -> 30/30/40 split

## Penalties
- HC: 1,000,000 per violation
- SC-I: weight x 100
- SC-II: weight x 10

## HC=2 GA vs HC=21 Checker gap
- HC-25 (missing pairs) not detectable by GA (no gene index to repair)
- HC-08/09/10/11 duration: warm-start gene_type inferred from room type, not exact
- 19 checker-only violations expected

## GA Architecture Doc
Saved to: static/assets/GA_Architecture_Explanation.docx (plain black Word doc, all tables)
