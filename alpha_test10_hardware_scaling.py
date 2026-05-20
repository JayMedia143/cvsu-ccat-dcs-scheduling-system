import os
import sys
sys.path.append(os.getcwd())
import random
import psutil
from concurrent.futures import ThreadPoolExecutor
import time
import copy
from collections import defaultdict

# --- CONFIGURATION ---

def get_hardware_profile():
    import os
    cpu_count = os.cpu_count() or 4
    if cpu_count >= 8: return {'label': f"High-End ({cpu_count} Cores)", 'pop_size': 120, 'max_workers': min(cpu_count, 8), 'target_gens': 6000}
    elif cpu_count >= 4: return {'label': f"Mid-Range ({cpu_count} Cores)", 'pop_size': 85, 'max_workers': min(cpu_count, 4), 'target_gens': 4500}
    else: return {'label': f"Low-End ({cpu_count} Cores)", 'pop_size': 65, 'max_workers': min(cpu_count, 2), 'target_gens': 3000}


ELITISM_COUNT = 5

HC_PENALTY = 10000
SC_PENALTY = 1

class Gene:
    def __init__(self, course_id, section_id, faculty_id, room_id, day_idx, start_idx, duration_slots, gene_type='Lec', is_fixed=False):
        self.course_id = course_id
        self.section_id = section_id
        self.faculty_id = faculty_id
        self.room_id = room_id
        self.day_idx = day_idx
        self.start_idx = start_idx
        self.duration_slots = duration_slots
        self.end_idx = start_idx + duration_slots
        self.gene_type = gene_type
        self.is_fixed = is_fixed
        self.locked_day = -1
        self.bitmask = ((1 << duration_slots) - 1) << start_idx

class Chromosome:
    def __init__(self, genes):
        self.genes = genes
        self.fitness = 0
        self.hard_conflicts = 0
        self.soft_score = 0
        self.conflicting_indices = []
        self.soft_violators = []
        self.rank = 0
        self.crowding_distance = 0.0

class GeneticSchedulerTC10:
    def __init__(self, courses, sections, faculty, rooms, pre_assignments=None, constraints_config=None, start_time=7, end_time=21, allowed_days=None):
        self.courses = courses
        self.sections = sections
        self.faculty = faculty
        self.rooms = rooms
        self.constraints = constraints_config or {}
        
        if allowed_days:
            self.days = allowed_days
        else:
            self.days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
            
        self.day_map = {day: i for i, day in enumerate(self.days)}
        self.start_hour = start_time
        self.end_hour = end_time
        self.total_slots = (end_time - start_time) * 2
        self.seven_pm_slot = (19 - start_time) * 2
        
        self.room_map = {r['id']: r for r in rooms}
        self.course_map = {c['id']: c for c in courses}
        self.faculty_ids = [f['id'] for f in faculty]
        self.fixed_genes = []
        
        self._blocked_bitmasks = {}
        self.tba_room_ids = {r['id'] for r in rooms if r.get('room_name', '') == 'T.B.A.'}
        self.online_room_ids = {r['id'] for r in rooms if r.get('room_name', '') == 'Online Room'}
        
        available = [r['id'] for r in rooms if r.get('status') == 'Available' and r['id'] not in self.tba_room_ids and r['id'] not in self.online_room_ids]
        lab_rooms = [r['id'] for r in rooms if r.get('status') == 'Available' and 'Computer Lab' in r.get('capabilities', '') and r['id'] not in self.tba_room_ids and r['id'] not in self.online_room_ids]
        all_rooms = [r['id'] for r in rooms if r['id'] not in self.tba_room_ids and r['id'] not in self.online_room_ids]
        
        self._valid_rooms_lec = available if available else all_rooms
        self._valid_rooms_lab = lab_rooms if lab_rooms else (available if available else all_rooms)
        
        self._expected_duration = {}
        for c in courses:
            cid = c['id']
            lec = (c.get('synchronous_lec_hours', 0) or c.get('lec_units', 0)) or 0
            lab = (c.get('synchronous_lab_hours', 0) or c.get('lab_units', 0)) or 0
            asy = (c.get('asynchronous_lec_hours', 0) or 0) + (c.get('asynchronous_lab_hours', 0) or 0)
            if lec > 0: self._expected_duration[(cid, 'Lec')] = int(lec * 2)
            if lab > 0: self._expected_duration[(cid, 'Lab')] = int(lab * 2)

        if pre_assignments:
            for pa in pre_assignments:
                if getattr(pa, 'day', '') not in self.day_map: continue
                try:
                    s_h, s_m = map(int, pa.start_time.split(':'))
                    e_h, e_m = map(int, pa.end_time.split(':'))
                    start_slot = ((s_h - self.start_hour) * 2) + (1 if s_m >= 30 else 0)
                    end_slot = ((e_h - self.start_hour) * 2) + (1 if e_m >= 30 else 0)
                    duration = end_slot - start_slot
                    self.fixed_genes.append(Gene(
                        pa.course_id, pa.section_id, pa.faculty_id, pa.room_id,
                        self.day_map[pa.day], start_slot, duration, 'Fixed', True
                    ))
                except Exception:
                    continue
                    
        # CEE
        self.pending_injections = []
        self.is_paused = False

    def get_valid_rooms(self, gene_type):
        valid_rooms = []
        for room in self.rooms:
            if room.get('status') != 'Available': continue
            caps = room.get('capabilities', '')
            if gene_type == 'Lab':
                if 'Computer Lab' in caps: valid_rooms.append(room['id'])
            else:
                valid_rooms.append(room['id'])
        return valid_rooms if valid_rooms else [r['id'] for r in self.rooms]

    def _get_density_guided_days(self, section_id, genes):
        day_counts = defaultdict(int)
        for g in genes:
            if g.section_id == section_id:
                day_counts[g.day_idx] += g.duration_slots
        return sorted(range(len(self.days)), key=lambda d: day_counts[d], reverse=True)

    def _best_room(self, valid_rooms, day_idx, genes):
        room_counts = defaultdict(int)
        for g in genes:
            if g.day_idx == day_idx:
                room_counts[g.room_id] += g.duration_slots
        if not valid_rooms: return None
        sorted_rooms = sorted(valid_rooms, key=lambda r: room_counts[r], reverse=True)
        if room_counts[sorted_rooms[0]] > 0: return sorted_rooms[0]
        return random.choice(valid_rooms)

    def create_genome(self):
        genes = copy.deepcopy(self.fixed_genes)
        for section in self.sections:
            for course_id in section.get('course_ids', []):
                if any(g.course_id == course_id and g.section_id == section['id'] and g.is_fixed for g in genes):
                    continue
                course = self.course_map.get(course_id)
                if not course: continue

                loads = []
                lec = course.get('synchronous_lec_hours', 0) or course.get('lec_units', 0)
                if lec > 0: loads.append((lec, 'Lec'))
                lab = course.get('synchronous_lab_hours', 0) or course.get('lab_units', 0)
                if lab > 0: loads.append((lab, 'Lab'))
                
                for hours, gtype in loads:
                    slots_needed = int(hours * 2)
                    valid_rooms = self.get_valid_rooms(gtype)
                    faculty = random.choice(self.faculty_ids) if self.faculty_ids else None
                    sorted_days = self._get_density_guided_days(section['id'], genes)
                    day = sorted_days[0]
                    max_start = max(0, self.total_slots - slots_needed)
                    start = random.randint(0, max_start)
                    room = self._best_room(valid_rooms, day, genes)
                    genes.append(Gene(course_id, section['id'], faculty, room, day, start, slots_needed, gtype))
        return Chromosome(genes)

    def calculate_fitness(self, chromosome, hard_only=False, sc1_only=False):
        penalty = 0
        hard_conflicts = 0
        soft_score = 0
        conflicting_indices = set()
        soft_violators = set()
        genes = chromosome.genes
        
        room_bits = defaultdict(int)
        faculty_bits = defaultdict(int)
        section_bits = defaultdict(int)
        
        for i, g in enumerate(genes):
            if not g.is_fixed:
                room_info = self.room_map.get(g.room_id)
                if room_info and room_info.get('status') != 'Available':
                    penalty += HC_PENALTY; hard_conflicts += 1; conflicting_indices.add(i)
                if g.gene_type == 'Lab' and room_info and 'Computer Lab' not in room_info.get('capabilities', ''):
                    penalty += HC_PENALTY; hard_conflicts += 1; conflicting_indices.add(i)

            if g.faculty_id:
                fac = next((f for f in self.faculty if f['id'] == g.faculty_id), None)
                if fac:
                    fac_avail = fac.get('available_days', '')
                    current_day = self.days[g.day_idx] if hasattr(self, 'days') else str(g.day_idx)
                    if fac_avail and current_day not in fac_avail:
                        penalty += HC_PENALTY; hard_conflicts += 1; conflicting_indices.add(i)

            if g.start_idx < 12 and g.end_idx > 10:
                penalty += HC_PENALTY; hard_conflicts += 1; conflicting_indices.add(i)
                
            if not hard_only:
                if g.start_idx >= self.seven_pm_slot:
                    penalty += SC_PENALTY; soft_score += SC_PENALTY; soft_violators.add(i)

            _mask = g.bitmask
            _d = g.day_idx
            
            if g.room_id:
                _rkey = (g.room_id, _d)
                if (room_bits[_rkey] & _mask) != 0:
                    penalty += HC_PENALTY; hard_conflicts += 1; conflicting_indices.add(i)
                room_bits[_rkey] |= _mask
                
            if g.faculty_id:
                _fkey = (g.faculty_id, _d)
                if (faculty_bits[_fkey] & _mask) != 0:
                    penalty += HC_PENALTY; hard_conflicts += 1; conflicting_indices.add(i)
                faculty_bits[_fkey] |= _mask
                
            _skey = (g.section_id, _d)
            if (section_bits[_skey] & _mask) != 0:
                penalty += HC_PENALTY; hard_conflicts += 1; conflicting_indices.add(i)
            section_bits[_skey] |= _mask

        chromosome.fitness = penalty
        chromosome.hard_conflicts = hard_conflicts
        chromosome.soft_score = soft_score
        chromosome.conflicting_indices = list(conflicting_indices)
        chromosome.soft_violators = list(soft_violators)
        return chromosome

    # ---------------------------------------------------------
    # GENETIC OPERATORS: OCCUPANCY HELPERS
    # ---------------------------------------------------------
    def _add_to_occ(self, gene, occ_room, occ_fac, occ_sec):
        if gene.is_fixed: return
        mask = getattr(gene, 'bitmask', ((1 << gene.duration_slots) - 1) << gene.start_idx)
        d = gene.day_idx
        if gene.room_id: occ_room[(gene.room_id, d)] |= mask
        if gene.faculty_id: occ_fac[(gene.faculty_id, d)] |= mask
        occ_sec[(gene.section_id, d)] |= mask

    def _remove_from_occ(self, gene, occ_room, occ_fac, occ_sec):
        if gene.is_fixed: return
        mask = getattr(gene, 'bitmask', ((1 << gene.duration_slots) - 1) << gene.start_idx)
        d = gene.day_idx
        if gene.room_id: occ_room[(gene.room_id, d)] &= ~mask
        if gene.faculty_id: occ_fac[(gene.faculty_id, d)] &= ~mask
        occ_sec[(gene.section_id, d)] &= ~mask

    def _copy_gene(self, g):
        ng = Gene(g.course_id, g.section_id, g.faculty_id, g.room_id, g.day_idx, g.start_idx, g.duration_slots, g.gene_type, g.is_fixed)
        ng.locked_day = g.locked_day
        ng.bitmask = g.bitmask
        return ng

    def _build_occ_sets(self, genes):
        occ_room = defaultdict(int)
        occ_fac = defaultdict(int)
        occ_sec = defaultdict(int)
        for g in genes: self._add_to_occ(g, occ_room, occ_fac, occ_sec)
        return occ_room, occ_fac, occ_sec

    def randomize_gene_fast(self, gene, occ_room, occ_fac, occ_sec):
        valid_rooms = self.get_valid_rooms(gene.gene_type)
        slots_needed = gene.duration_slots
        n_days = len(self.days)
        for _ in range(20):
            test_day = random.randint(0, n_days - 1)
            test_start = random.randint(0, max(0, self.total_slots - slots_needed))
            test_room = random.choice(valid_rooms) if valid_rooms else None
            mask = ((1 << slots_needed) - 1) << test_start
            conflict = False
            if test_room and (occ_room.get((test_room, test_day), 0) & mask) != 0: conflict = True
            if not conflict and gene.faculty_id and (occ_fac.get((gene.faculty_id, test_day), 0) & mask) != 0: conflict = True
            if not conflict and (occ_sec.get((gene.section_id, test_day), 0) & mask) != 0: conflict = True
            if not conflict:
                gene.day_idx, gene.start_idx, gene.end_idx, gene.room_id, gene.bitmask = test_day, test_start, test_start + slots_needed, test_room, mask
                return
        gene.day_idx, gene.start_idx = random.randint(0, n_days - 1), random.randint(0, max(0, self.total_slots - slots_needed))
        gene.end_idx, gene.bitmask, gene.room_id = gene.start_idx + slots_needed, ((1 << slots_needed) - 1) << gene.start_idx, random.choice(valid_rooms) if valid_rooms else None

    # ---------------------------------------------------------
    # CEE: CONTINUOUS EVOLUTIONARY ENGINE (DYNAMIC INJECTION)
    # ---------------------------------------------------------
    def inject_new_data(self, new_course=None, new_section=None):
        if new_course:
            self.courses.append(new_course)
            self.course_map[new_course['id']] = new_course
            _lec = (new_course.get('synchronous_lec_hours', 0) or new_course.get('lec_units', 0)) or 0
            _lab = (new_course.get('synchronous_lab_hours', 0) or new_course.get('lab_units', 0)) or 0
            if _lec > 0: self._expected_duration[(new_course['id'], 'Lec')] = int(_lec * 2)
            if _lab > 0: self._expected_duration[(new_course['id'], 'Lab')] = int(_lab * 2)
        if new_section:
            self.sections.append(new_section)

        self.pending_injections.append({'course': new_course, 'section': new_section})
        print(f"💉 Injection Queued: {new_course['course_code'] if new_course else 'Section Update'}")

    def _process_injections(self, population):
        if not self.pending_injections: return population
        self.is_paused = True
        print(f"🔄 CEE: Processing {len(self.pending_injections)} injections...")
        
        best_chrom = Chromosome([self._copy_gene(g) for g in population[0].genes])
        occ_room, occ_fac, occ_sec = self._build_occ_sets(best_chrom.genes)
        
        while self.pending_injections:
            data = self.pending_injections.pop(0)
            sec = data['section']
            if sec:
                for cid in sec.get('course_ids', []):
                    if any(g.course_id == cid and g.section_id == sec['id'] for g in best_chrom.genes): continue
                    course = self.course_map.get(cid)
                    if not course: continue
                    
                    lec_dur = self._expected_duration.get((cid, 'Lec'))
                    if lec_dur:
                        new_g = Gene(cid, sec['id'], None, None, 0, 0, lec_dur, 'Lec', False)
                        self.randomize_gene_fast(new_g, occ_room, occ_fac, occ_sec)
                        best_chrom.genes.append(new_g)
                        self._add_to_occ(new_g, occ_room, occ_fac, occ_sec)

                    lab_dur = self._expected_duration.get((cid, 'Lab'))
                    if lab_dur:
                        new_g = Gene(cid, sec['id'], None, None, 0, 0, lab_dur, 'Lab', False)
                        self.randomize_gene_fast(new_g, occ_room, occ_fac, occ_sec)
                        best_chrom.genes.append(new_g)
                        self._add_to_occ(new_g, occ_room, occ_fac, occ_sec)

        self.calculate_fitness(best_chrom)
        
        new_population = [best_chrom]
        while len(new_population) < len(population):
            variant = self._perturb_chromosome(best_chrom, fraction=0.15)
            self.calculate_fitness(variant)
            new_population.append(variant)
            
        print(f"✅ CEE: Population synchronized to new gene count ({len(best_chrom.genes)})")
        self.is_paused = False
        return new_population

    def _perturb_chromosome(self, base_chrom, fraction=0.15):
        nc = Chromosome([self._copy_gene(g) for g in base_chrom.genes])
        non_fixed = [i for i, g in enumerate(nc.genes) if not g.is_fixed]
        if not non_fixed: return nc
        perturb_count = max(1, int(len(non_fixed) * fraction))
        indices = random.sample(non_fixed, min(perturb_count, len(non_fixed)))
        occ_room, occ_fac, occ_sec = self._build_occ_sets(nc.genes)
        for idx in indices:
            gene = nc.genes[idx]
            self._remove_from_occ(gene, occ_room, occ_fac, occ_sec)
            self.randomize_gene_fast(gene, occ_room, occ_fac, occ_sec)
            self._add_to_occ(gene, occ_room, occ_fac, occ_sec)
        return nc

    # ---------------------------------------------------------
    # NSGA-II SORTING & CROWDING DISTANCE
    # ---------------------------------------------------------
    @staticmethod
    def _constrained_dominates(a, b):
        a_ok = a.hard_conflicts == 0
        b_ok = b.hard_conflicts == 0
        if a_ok and not b_ok: return True
        if not a_ok and b_ok: return False
        if a_ok: return a.soft_score < b.soft_score
        else:
            if a.hard_conflicts != b.hard_conflicts: return a.hard_conflicts < b.hard_conflicts
            return a.soft_score < b.soft_score

    def fast_non_dominated_sort(self, population):
        n = len(population)
        dominated_by   = [[] for _ in range(n)]
        domination_cnt = [0] * n
        dom = GeneticSchedulerTC10._constrained_dominates

        for i in range(n):
            pi = population[i]
            for j in range(i + 1, n):
                pj = population[j]
                if dom(pi, pj):
                    dominated_by[i].append(j)
                    domination_cnt[j] += 1
                elif dom(pj, pi):
                    dominated_by[j].append(i)
                    domination_cnt[i] += 1

        fronts = [[]]
        for i in range(n):
            if domination_cnt[i] == 0:
                population[i].rank = 1
                fronts[0].append(i)

        fi = 0
        while fronts[fi]:
            next_front = []
            for i in fronts[fi]:
                for j in dominated_by[i]:
                    domination_cnt[j] -= 1
                    if domination_cnt[j] == 0:
                        population[j].rank = fi + 2
                        next_front.append(j)
            fi += 1
            fronts.append(next_front)

        return [[population[i] for i in front] for front in fronts if front]

    def crowding_distance_assignment(self, front):
        l = len(front)
        if l == 0: return
        if l == 1:
            front[0].crowding_distance = float('inf')
            return

        for c in front:
            c.crowding_distance = 0.0

        for get_obj in (lambda c: c.hard_conflicts, lambda c: c.soft_score):
            front_sorted = sorted(front, key=get_obj)
            min_val = get_obj(front_sorted[0])
            max_val = get_obj(front_sorted[-1])
            front_sorted[0].crowding_distance  = float('inf')
            front_sorted[-1].crowding_distance = float('inf')
            rng = max_val - min_val
            if rng == 0: continue
            for i in range(1, l - 1):
                front_sorted[i].crowding_distance += (get_obj(front_sorted[i + 1]) - get_obj(front_sorted[i - 1])) / rng

    def _hard_phase_select(self, population):
        pop_size = len(population)
        a, b = population[random.randint(0, pop_size - 1)], population[random.randint(0, pop_size - 1)]
        if a.hard_conflicts < b.hard_conflicts: return a
        if a.hard_conflicts > b.hard_conflicts: return b
        return a if a.soft_score <= b.soft_score else b
        
    def nsga2_tournament_select(self, population):
        pop_size = len(population)
        i, j = random.randint(0, pop_size - 1), random.randint(0, pop_size - 1)
        a, b = population[i], population[j]
        if (a.rank < b.rank or (a.rank == b.rank and a.crowding_distance > b.crowding_distance)): return a
        return b

    def select_parents(self, population, current_phase):
        if current_phase == 'hard': return self._hard_phase_select(population), self._hard_phase_select(population)
        else: return self.nsga2_tournament_select(population), self.nsga2_tournament_select(population)

    def proportional_mutate(self, chromosome, rank):
        if rank < ELITISM_COUNT: return
        targets = list(set(chromosome.conflicting_indices))
        occ_room, occ_fac, occ_sec = self._build_occ_sets(chromosome.genes)

        if not targets:
            if random.random() < 0.1:
                idx = random.randint(0, len(chromosome.genes) - 1)
                gene = chromosome.genes[idx]
                if not gene.is_fixed:
                    self._remove_from_occ(gene, occ_room, occ_fac, occ_sec)
                    self.randomize_gene_fast(gene, occ_room, occ_fac, occ_sec)
                    self._add_to_occ(gene, occ_room, occ_fac, occ_sec)
            return

        random.shuffle(targets)
        count = max(1, int(len(targets) * 0.5))
        for _ in range(count):
            if not targets: break
            idx = targets.pop()
            gene = chromosome.genes[idx]
            if not gene.is_fixed:
                self._remove_from_occ(gene, occ_room, occ_fac, occ_sec)
                self.randomize_gene_fast(gene, occ_room, occ_fac, occ_sec)
                self._add_to_occ(gene, occ_room, occ_fac, occ_sec)

    def crossover(self, p1, p2):
        child_genes = [None] * len(p1.genes)
        occ_room, occ_fac, occ_sec = defaultdict(int), defaultdict(int), defaultdict(int)
        for i, g in enumerate(p1.genes):
            if g.is_fixed:
                child_genes[i] = self._copy_gene(g)
                self._add_to_occ(g, occ_room, occ_fac, occ_sec)

        non_fixed = [i for i in range(len(p1.genes)) if not p1.genes[i].is_fixed]
        random.shuffle(non_fixed)

        for i in non_fixed:
            g1, g2 = p1.genes[i], p2.genes[i]
            d1, mask1 = g1.day_idx, g1.bitmask
            if not ((g1.room_id and occ_room.get((g1.room_id, d1), 0) & mask1) or (g1.faculty_id and occ_fac.get((g1.faculty_id, d1), 0) & mask1) or (occ_sec.get((g1.section_id, d1), 0) & mask1)): chosen = self._copy_gene(g1)
            else:
                d2, mask2 = g2.day_idx, g2.bitmask
                if not ((g2.room_id and occ_room.get((g2.room_id, d2), 0) & mask2) or (g2.faculty_id and occ_fac.get((g2.faculty_id, d2), 0) & mask2) or (occ_sec.get((g2.section_id, d2), 0) & mask2)): chosen = self._copy_gene(g2)
                else:
                    chosen = self._copy_gene(g1)
                    self.randomize_gene_fast(chosen, occ_room, occ_fac, occ_sec)
            child_genes[i] = chosen
            self._add_to_occ(chosen, occ_room, occ_fac, occ_sec)
        return Chromosome(child_genes)

    def run_algorithm(self, progress_callback=None):
        hw = get_hardware_profile()
        pop_size = hw['pop_size']
        max_workers = hw['max_workers']
        target_gens = hw['target_gens']

        start_t0 = time.time()
        print("=== RUNNING ALPHA TEST CASE 10: HARDWARE-AWARE SCALING & PARALLEL PROCESSING ===")
        print("Telemetry: Continuous Execution Engine (CEE) Active.")
        
        
        with ThreadPoolExecutor(max_workers=max_workers) as exe:
            population = list(exe.map(lambda _: self.create_genome(), range(pop_size)))

        best_schedule = None
        current_phase = 'hard'
        
        for generation in range(1, target_gens + 1):
            if self.pending_injections:
                population = self._process_injections(population)
                current_phase = 'hard' # Reset phase if necessary
            
            hard_phase = (current_phase == 'hard')
            sc1_phase  = (current_phase == 'sc1')
            

            with ThreadPoolExecutor(max_workers=max_workers) as exe:
                if hard_phase: population = list(exe.map(lambda c: self.calculate_fitness(c, hard_only=True), population))
                elif sc1_phase: population = list(exe.map(lambda c: self.calculate_fitness(c, sc1_only=True), population))
                else: population = list(exe.map(self.calculate_fitness, population))

                
            if hard_phase:
                population.sort(key=lambda x: (x.hard_conflicts, x.soft_score))
            else:
                fronts = self.fast_non_dominated_sort(population)
                for f in fronts: self.crowding_distance_assignment(f)
                population = []
                for f in fronts:
                    f.sort(key=lambda x: x.crowding_distance, reverse=True)
                    population.extend(f)
                
            current_best = population[0]
            if best_schedule is None or current_best.fitness < best_schedule.fitness:
                best_schedule = copy.deepcopy(current_best)
                
            if current_best.hard_conflicts == 0 and current_phase == 'hard':
                current_phase = 'sc1'
                print(f"\n🔄 Phase Shift: Hard Conflicts resolved. Entering SC1 Phase.")
            elif current_best.hard_conflicts == 0 and current_best.soft_score == 0 and current_phase == 'sc1':
                current_phase = 'sc2'
                print(f"\n🔄 Phase Shift: SC1 resolved. Entering SC2 Phase.")
            
            if generation % 10 == 0:
                elapsed = time.time() - start_t0
                print(f"Gen {generation:04d} [{current_phase.upper()}] | Elapsed: {elapsed:.1f}s | Speed: {elapsed/generation:.4f}s/gen | HC: {current_best.hard_conflicts} | SS: {current_best.soft_score}")

            # SIMULATING DYNAMIC INJECTION
            if generation == 50:
                print("\n[SIMULATION] Admin added a new Course & Section while GA is running!")
                new_course = {'id': 999, 'course_code': 'INJECTED_101', 'lec_units': 3, 'lab_units': 0}
                new_section = {'id': 999, 'course_ids': [999], 'number_of_students': 30}
                self.inject_new_data(new_course=new_course, new_section=new_section)

            if current_best.hard_conflicts == 0 and current_best.soft_score == 0:
                print(f"\n✅ Perfect Schedule Found at Gen {generation}! Elapsed: {time.time() - start_t0:.1f}s")
                break

            new_population = [copy.deepcopy(population[i]) for i in range(ELITISM_COUNT)]
            while len(new_population) < pop_size:
                p1, p2 = self.select_parents(population, current_phase)
                new_population.append(self.crossover(p1, p2))
            
            for rank, chrom in enumerate(new_population):
                self.proportional_mutate(chrom, rank)
            population = new_population

        return best_schedule

if __name__ == '__main__':
    print("================================================================")
    print("🧪 ALPHA TESTING: TEST CASE 10 (HARDWARE SCALING & PARALLEL)")
    print("================================================================")
    
    from app import app, Course, Section, Room, Faculty, PreAssignment, Constraint, get_settings
    
    class SafePA:
        def __init__(self, course_id, section_id, faculty_id, room_id, day, start_time, end_time):
            self.course_id = course_id
            self.section_id = section_id
            self.faculty_id = faculty_id
            self.room_id = room_id
            self.day = day
            self.start_time = start_time
            self.end_time = end_time

    with app.app_context():
        target_semester = '1st Semester'
        settings_db = get_settings()
        _adays_str = settings_db.allowed_days or 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'
        active_days = [d.strip() for d in _adays_str.split(',') if d.strip()]
        
        raw_courses = Course.query.filter_by(is_archived=False, semester_offered=target_semester).all()
        courses = [{'id': c.id, 'course_code': c.course_code, 'department': c.department or '', 'lec_units': c.lec_units or 0, 'lab_units': c.lab_units or 0, 'synchronous_lec_hours': c.synchronous_lec_hours or 0, 'synchronous_lab_hours': c.synchronous_lab_hours or 0, 'asynchronous_lec_hours': c.asynchronous_lec_hours or 0, 'asynchronous_lab_hours': c.asynchronous_lab_hours or 0} for c in raw_courses]
        
        raw_rooms = Room.query.filter_by(is_archived=False).all()
        rooms = [{'id': r.id, 'room_name': r.room_name, 'capabilities': r.capabilities, 'status': r.status, 'capacity': r.capacity} for r in raw_rooms]
        
        raw_faculty = Faculty.query.filter_by(is_archived=False).all()
        faculty = [{'id': f.id, 'full_name': f.full_name, 'available_days': f.available_days or ''} for f in raw_faculty]
        
        raw_sections = Section.query.filter_by(is_archived=False).all()
        sections = [{'id': s.id, 'course_ids': [c.id for c in s.courses], 'number_of_students': s.number_of_students, 'available_days': s.available_days} for s in raw_sections]
        
        valid_course_ids = {c['id'] for c in courses}
        raw_pre = PreAssignment.query.filter_by(is_archived=False).all()
        pre_assignments = [SafePA(pa.course_id, pa.section_id, pa.faculty_id, room_id=pa.room_id, day=pa.day, start_time=pa.start_time, end_time=pa.end_time) for pa in raw_pre if pa.course_id in valid_course_ids]
        
        scheduler = GeneticSchedulerTC10(courses, sections, faculty, rooms, pre_assignments, {}, start_time=7, end_time=21, allowed_days=active_days)
        best = scheduler.run_algorithm()
