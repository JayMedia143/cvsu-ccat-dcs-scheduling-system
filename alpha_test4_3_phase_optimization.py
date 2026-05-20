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

class GeneticSchedulerTC4:
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
        
        self._dept_rooms_lec = {}
        self._dept_rooms_lab = {}
        self._dept_rooms_lec_only = {}
        
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
        n_days = len(self.days)
        total_slots = self.total_slots
        sessions = []
        for section in self.sections:
            sec_id = section['id']
            sec_name = section.get('section_name', '?')
            for course_id in section.get('course_ids', []):
                course = self.course_map.get(course_id)
                if not course: continue
                dept = course.get('department', '')
                ccode = course.get('course_code', '?')
                lec = (course.get('synchronous_lec_hours', 0) or course.get('lec_units', 0)) or 0
                lab = (course.get('synchronous_lab_hours', 0) or course.get('lab_units', 0)) or 0

                if lec > 0: sessions.append({'course_id': course_id, 'section_id': sec_id, 'course_code': ccode, 'sec_name': sec_name, 'type': 'Lec', 'slots': int(lec * 2), 'dept': dept})
                if lab > 0: sessions.append({'course_id': course_id, 'section_id': sec_id, 'course_code': ccode, 'sec_name': sec_name, 'type': 'Lab', 'slots': int(lab * 2), 'dept': dept})

        sessions.sort(key=lambda s: -s['slots'])
        total_sessions = len(sessions)

        def _build_room_occ(cap_ratio=1.0):
            occ = {}
            for r in self.rooms:
                if (r.get('status') != 'Available' or r['id'] in self.tba_room_ids): continue
                day_masks = [self._blocked_bitmasks.get(d, 0) for d in range(n_days)]
                if cap_ratio < 1.0:
                    usable = int(total_slots * cap_ratio)
                    if usable < total_slots:
                        block_mask = ((1 << (total_slots - usable)) - 1) << usable
                        for d in range(n_days): day_masks[d] |= block_mask
                occ[r['id']] = day_masks
            return occ

        def _greedy_place(occ_rooms, sec_day_slots=None, sec_consec_cap=None):
            placed = []; overflow = []
            for sess in sessions:
                slots_needed = sess['slots']
                gtype = sess['type']
                sec_id = sess['section_id']
                if gtype == 'Lab': valid = (self._dept_rooms_lab.get(sess['dept']) or self._valid_rooms_lab)
                elif gtype == 'Async': valid = (list(self.online_room_ids) or self._valid_rooms_lec)
                else: 
                    valid = (self._dept_rooms_lec_only.get(sess['dept']) or self._valid_rooms_lec_only)
                    valid = [r for r in valid if r not in self.online_room_ids]
                
                if gtype == 'Lab': valid = [r for r in valid if r not in self.online_room_ids]
                valid = [r for r in valid if r in occ_rooms]
                
                fitted = False
                for room_id in valid:
                    room_occ = occ_rooms[room_id]
                    for day in range(n_days):
                        if sec_day_slots is not None and sec_consec_cap is not None:
                            if sec_day_slots.get((sec_id, day), 0) + slots_needed > sec_consec_cap: continue
                        day_mask = room_occ[day]
                        for start in range(0, total_slots - slots_needed + 1, 2):
                            mask = ((1 << slots_needed) - 1) << start
                            if (day_mask & mask) == 0:
                                room_occ[day] |= mask
                                if sec_day_slots is not None: sec_day_slots[(sec_id, day)] = sec_day_slots.get((sec_id, day), 0) + slots_needed
                                placed.append(sess); fitted = True; break
                        if fitted: break
                    if fitted: break
                if not fitted: overflow.append(sess)
            return placed, overflow

        occ_l1 = _build_room_occ(1.0); p1, o1 = _greedy_place(occ_l1)
        occ_l2 = _build_room_occ(1.0); s_tracker = {}; p2, o2 = _greedy_place(occ_l2, s_tracker, 12)
        occ_l3 = _build_room_occ(0.60); p3, o3 = _greedy_place(occ_l3)

        n1, n2, n3 = len(o1), len(o2), len(o3)
        if n1 == 0 and n2 == 0 and n3 == 0:
            status, message = 'GREEN', 'All sessions fit comfortably. Sufficient capacity.'
        elif n1 == 0 and n2 == 0 and n3 > 0:
            status, message = 'YELLOW', 'Rooms are sufficient but running close to real-world limits.'
        elif n1 == 0 and n2 > 0:
            status, message = 'ORANGE', f'Mathematically enough but constraints cause {n2} overflow(s).'
        else:
            status, message = 'RED', f'Critically insufficient. {n1} sessions cannot fit even at full capacity.'

        return {'status': status, 'message': message}

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
        sorted_days = sorted(range(len(self.days)), key=lambda d: day_counts[d], reverse=True)
        return sorted_days

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

    # ---------------------------------------------------------
    # 3-PHASE OPTIMIZATION SUPPORT IN FITNESS
    # ---------------------------------------------------------
    def calculate_fitness(self, chromosome, hard_only=False, sc1_only=False):
        penalty = 0
        hard_conflicts = 0
        soft_score = 0
        conflicting_indices = set()
        genes = chromosome.genes
        
        # --- TRUE INTEGER BITMASK CACHING ---
        room_bits = defaultdict(int)
        faculty_bits = defaultdict(int)
        section_bits = defaultdict(int)
        
        for i, g in enumerate(genes):
            # Evaluate static rules
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
                
            # SC1: Evening Avoidance
            if not hard_only:
                if g.start_idx >= self.seven_pm_slot:
                    penalty += SC_PENALTY; soft_score += SC_PENALTY

            # Evaluate Overlaps via Bitwise AND
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

    def proportional_mutate(self, chromosome, rank):
        if rank < ELITISM_COUNT: return
        targets = list(set(chromosome.conflicting_indices))
        if not targets:
            if random.random() < 0.1:
                idx = random.randint(0, len(chromosome.genes) - 1)
                if not chromosome.genes[idx].is_fixed:
                    self.randomize_gene(chromosome.genes[idx], chromosome.genes)
            return

        random.shuffle(targets)
        count = max(1, int(len(targets) * 0.5))
        for _ in range(count):
            if not targets: break
            idx = targets.pop()
            if not chromosome.genes[idx].is_fixed:
                self.randomize_gene(chromosome.genes[idx], chromosome.genes)

    def randomize_gene(self, gene, genes):
        valid_rooms = self.get_valid_rooms(gene.gene_type)
        slots_needed = gene.duration_slots
        sorted_days = self._get_density_guided_days(gene.section_id, genes)
        gene.day_idx = sorted_days[0]
        gene.start_idx = random.randint(0, max(0, self.total_slots - slots_needed))
        gene.end_idx = gene.start_idx + slots_needed
        gene.bitmask = ((1 << slots_needed) - 1) << gene.start_idx
        if valid_rooms:
            gene.room_id = self._best_room(valid_rooms, gene.day_idx, genes)

    def select_parents(self, population):
        pop_size = len(population)
        weights = [pop_size - i for i in range(pop_size)]
        return random.choices(population, weights=weights, k=2)

    def crossover(self, p1, p2):
        child_genes = []
        for i in range(len(p1.genes)):
            if p1.genes[i].is_fixed:
                child_genes.append(p1.genes[i])
            else:
                child_genes.append(copy.deepcopy(p1.genes[i] if random.random() > 0.5 else p2.genes[i]))
        return Chromosome(child_genes)

    def run_algorithm(self, progress_callback=None):
        start_t0 = time.time()
        print("=== RUNNING ALPHA TEST CASE 4: 3-PHASE OPTIMIZATION ===")
        
        feasibility = self.check_room_feasibility()
        print(f"🔍 Pre-Feasibility Check: {feasibility['status']}")
        
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
                
            population.sort(key=lambda x: (x.hard_conflicts, x.soft_score))
            current_best = population[0]
            
            if best_schedule is None or current_best.fitness < best_schedule.fitness:
                best_schedule = copy.deepcopy(current_best)
                
            # Phase Switching Logic
            if current_best.hard_conflicts == 0 and current_phase == 'hard':
                current_phase = 'sc1'
                print(f"\n🔄 Phase Shift: Hard Conflicts resolved. Entering SC1 Phase.")
            elif current_best.hard_conflicts == 0 and current_best.soft_score == 0 and current_phase == 'sc1':
                current_phase = 'sc2'
                print(f"\n🔄 Phase Shift: SC1 resolved. Entering SC2 Phase.")
            
            if generation % 10 == 0:
                elapsed = time.time() - start_t0
                print(f"Gen {generation:04d} [{current_phase.upper()}] | Elapsed: {elapsed:.1f}s | Speed: {elapsed/generation:.4f}s/gen | HC: {current_best.hard_conflicts} | SS: {current_best.soft_score}")

            if current_best.hard_conflicts == 0 and current_best.soft_score == 0:
                print(f"\n✅ Perfect Schedule Found at Gen {generation}! Elapsed: {time.time() - start_t0:.1f}s")
                break

            new_population = [copy.deepcopy(population[i]) for i in range(ELITISM_COUNT)]
            while len(new_population) < POPULATION_SIZE:
                p1, p2 = self.select_parents(population)
                new_population.append(self.crossover(p1, p2))
            
            for rank, chrom in enumerate(new_population):
                self.proportional_mutate(chrom, rank)
            population = new_population

        return best_schedule

if __name__ == '__main__':
    print("================================================================")
    print("🧪 ALPHA TESTING: TEST CASE 4 (3-PHASE OPTIMIZATION)")
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
        pre_assignments = [SafePA(pa.course_id, pa.section_id, pa.faculty_id, pa.room_id, pa.day, pa.start_time, pa.end_time) for pa in raw_pre if pa.course_id in valid_course_ids]
        
        scheduler = GeneticSchedulerTC4(courses, sections, faculty, rooms, pre_assignments, {}, start_time=7, end_time=21, allowed_days=active_days)
        best = scheduler.run_algorithm()
