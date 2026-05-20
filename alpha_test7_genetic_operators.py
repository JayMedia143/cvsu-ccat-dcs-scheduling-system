import os
import sys
sys.path.append(os.getcwd())
import random
import time
import copy
from collections import defaultdict

# --- CONFIGURATION ---
POPULATION_SIZE = 100
MAX_GENERATIONS = 9999999
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
        self.rank = 0
        self.crowding_distance = 0.0

class GeneticSchedulerTC7:
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
        
        lec_only = [r['id'] for r in rooms if r.get('status') == 'Available' and 'Computer Lab' not in r.get('capabilities', '') and r.get('room_name', '') != 'T.B.A.']
        self._valid_rooms_lec_only = lec_only if lec_only else (available if available else all_rooms)
        
        self._expected_duration = {}
        for c in courses:
            cid = c['id']
            lec = (c.get('synchronous_lec_hours', 0) or c.get('lec_units', 0)) or 0
            lab = (c.get('synchronous_lab_hours', 0) or c.get('lab_units', 0)) or 0
            asy = (c.get('asynchronous_lec_hours', 0) or 0) + (c.get('asynchronous_lab_hours', 0) or 0)
            if lec > 0: self._expected_duration[(cid, 'Lec')] = int(lec * 2)
            if lab > 0: self._expected_duration[(cid, 'Lab')] = int(lab * 2)
            if asy > 0: self._expected_duration[(cid, 'Async')] = int(asy * 2)

        _sec_total_slots = defaultdict(int)
        for sec in sections:
            sid = sec['id']
            for cid in sec.get('course_ids', []):
                _sec_total_slots[sid] += self._expected_duration.get((cid, 'Lec'), 0)
                _sec_total_slots[sid] += self._expected_duration.get((cid, 'Lab'), 0)
        self._hc24_exempt_sections = frozenset(sid for sid, slots in _sec_total_slots.items() if slots < 12)

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

    def check_room_feasibility(self):
        return {'status': 'GREEN', 'message': 'All sessions fit comfortably. Sufficient capacity.'}

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
                    penalty += SC_PENALTY; soft_score += SC_PENALTY

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
        return penalty

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

    def randomize_gene_fast(self, gene, occ_room, occ_fac, occ_sec):
        valid_rooms = self.get_valid_rooms(gene.gene_type)
        slots_needed = gene.duration_slots
        n_days = len(self.days)
        
        # Try to find a conflict-free slot (guaranteed placement approximation)
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
                gene.day_idx = test_day
                gene.start_idx = test_start
                gene.end_idx = test_start + slots_needed
                gene.room_id = test_room
                gene.bitmask = mask
                return
        
        # Fallback if no clear slot
        gene.day_idx = random.randint(0, n_days - 1)
        gene.start_idx = random.randint(0, max(0, self.total_slots - slots_needed))
        gene.end_idx = gene.start_idx + slots_needed
        gene.bitmask = ((1 << slots_needed) - 1) << gene.start_idx
        gene.room_id = random.choice(valid_rooms) if valid_rooms else None

    # ---------------------------------------------------------
    # GENETIC OPERATORS: MUTATION & CROSSOVER
    # ---------------------------------------------------------
    def proportional_mutate(self, chromosome, rank):
        if rank < ELITISM_COUNT: return
        targets = list(set(chromosome.conflicting_indices))
        
        # Build Occupancy
        occ_room = defaultdict(int)
        occ_fac = defaultdict(int)
        occ_sec = defaultdict(int)
        for g in chromosome.genes: self._add_to_occ(g, occ_room, occ_fac, occ_sec)

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
        """Greedy conflict-aware crossover from the original code."""
        child_genes = [None] * len(p1.genes)
        occ_room = defaultdict(int)
        occ_fac = defaultdict(int)
        occ_sec = defaultdict(int)

        for i, g in enumerate(p1.genes):
            if g.is_fixed:
                child_genes[i] = self._copy_gene(g)
                self._add_to_occ(g, occ_room, occ_fac, occ_sec)

        non_fixed = [i for i in range(len(p1.genes)) if not p1.genes[i].is_fixed]
        random.shuffle(non_fixed)

        for i in non_fixed:
            g1 = p1.genes[i]
            g2 = p2.genes[i]

            # Try g1
            d1 = g1.day_idx
            mask1 = g1.bitmask
            g1_conflict = ((g1.room_id and occ_room.get((g1.room_id, d1), 0) & mask1) or
                           (g1.faculty_id and occ_fac.get((g1.faculty_id, d1), 0) & mask1) or
                           (occ_sec.get((g1.section_id, d1), 0) & mask1))

            if not g1_conflict:
                chosen = self._copy_gene(g1)
            else:
                # Try g2
                d2 = g2.day_idx
                mask2 = g2.bitmask
                g2_conflict = ((g2.room_id and occ_room.get((g2.room_id, d2), 0) & mask2) or
                               (g2.faculty_id and occ_fac.get((g2.faculty_id, d2), 0) & mask2) or
                               (occ_sec.get((g2.section_id, d2), 0) & mask2))
                
                if not g2_conflict:
                    chosen = self._copy_gene(g2)
                else:
                    # Both conflict, force a new slot
                    chosen = self._copy_gene(g1)
                    self.randomize_gene_fast(chosen, occ_room, occ_fac, occ_sec)

            child_genes[i] = chosen
            self._add_to_occ(chosen, occ_room, occ_fac, occ_sec)

        return Chromosome(child_genes)

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
        dom = GeneticSchedulerTC7._constrained_dominates

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
        i, j = random.randint(0, pop_size - 1), random.randint(0, pop_size - 1)
        a, b = population[i], population[j]
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
        if current_phase == 'hard':
            p1 = self._hard_phase_select(population)
            p2 = self._hard_phase_select(population)
        else:
            p1 = self.nsga2_tournament_select(population)
            p2 = self.nsga2_tournament_select(population)
        return p1, p2

    def run_algorithm(self, progress_callback=None):
        start_t0 = time.time()
        print("=== RUNNING ALPHA TEST CASE 7: GENETIC OPERATORS (CROSSOVER & MUTATION) ===")
        print("Telemetry: Greedy conflict-aware crossover active.")
        
        population = [self.create_genome() for _ in range(POPULATION_SIZE)]
        best_schedule = None
        current_phase = 'hard'
        
        for generation in range(1, MAX_GENERATIONS + 1):
            hard_phase = (current_phase == 'hard')
            sc1_phase  = (current_phase == 'sc1')
            
            for chrom in population: 
                if hard_phase: self.calculate_fitness(chrom, hard_only=True)
                elif sc1_phase: self.calculate_fitness(chrom, sc1_only=True)
                else: self.calculate_fitness(chrom)
                
            if hard_phase:
                population.sort(key=lambda x: (x.hard_conflicts, x.soft_score))
                fronts_count = 1
            else:
                fronts = self.fast_non_dominated_sort(population)
                fronts_count = len(fronts)
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
                print(f"\n🔄 Phase Shift: Hard Conflicts resolved. Entering SC1 Phase (NSGA-II Active).")
            elif current_best.hard_conflicts == 0 and current_best.soft_score == 0 and current_phase == 'sc1':
                current_phase = 'sc2'
                print(f"\n🔄 Phase Shift: SC1 resolved. Entering SC2 Phase.")
            
            if generation % 10 == 0:
                elapsed = time.time() - start_t0
                print(f"Gen {generation:04d} [{current_phase.upper()}] | Elapsed: {elapsed:.1f}s | Speed: {elapsed/generation:.4f}s/gen | HC: {current_best.hard_conflicts} | SS: {current_best.soft_score} | Fronts: {fronts_count}")

            if current_best.hard_conflicts == 0 and current_best.soft_score == 0:
                print(f"\n✅ Perfect Schedule Found at Gen {generation}! Elapsed: {time.time() - start_t0:.1f}s")
                break

            new_population = [copy.deepcopy(population[i]) for i in range(ELITISM_COUNT)]
            while len(new_population) < POPULATION_SIZE:
                p1, p2 = self.select_parents(population, current_phase)
                new_population.append(self.crossover(p1, p2))
            
            for rank, chrom in enumerate(new_population):
                self.proportional_mutate(chrom, rank)
            population = new_population

        return best_schedule

if __name__ == '__main__':
    print("================================================================")
    print("🧪 ALPHA TESTING: TEST CASE 7 (GENETIC OPERATORS: CROSSOVER & MUTATION)")
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
        
        scheduler = GeneticSchedulerTC7(courses, sections, faculty, rooms, pre_assignments, {}, start_time=7, end_time=21, allowed_days=active_days)
        best = scheduler.run_algorithm()
