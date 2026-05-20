import os
import sys
sys.path.append(os.getcwd())
import random
import time
import copy
from collections import defaultdict

# --- CONFIGURATION ---
POPULATION_SIZE = 100
MAX_GENERATIONS = 9999999  # Walang limit, titigil lang kapag 0 conflict na
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

class Chromosome:
    def __init__(self, genes):
        self.genes = genes
        self.fitness = 0
        self.hard_conflicts = 0
        self.soft_score = 0
        self.conflicting_indices = []

class GeneticSchedulerTC2:
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
        
        self.room_map = {r['id']: r for r in rooms}
        self.faculty_ids = [f['id'] for f in faculty]
        self.fixed_genes = []
        
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
        # Count slots per day for this section
        day_counts = defaultdict(int)
        for g in genes:
            if g.section_id == section_id:
                day_counts[g.day_idx] += g.duration_slots
        
        # Sort days: active days first (highest count), then empty days
        sorted_days = sorted(range(len(self.days)), key=lambda d: day_counts[d], reverse=True)
        return sorted_days

    def _best_room(self, valid_rooms, day_idx, genes):
        # Count slots per room on this day (Warmth Score)
        room_counts = defaultdict(int)
        for g in genes:
            if g.day_idx == day_idx:
                room_counts[g.room_id] += g.duration_slots
        
        if not valid_rooms:
            return None
            
        # Sort rooms by warmth (highest count first)
        sorted_rooms = sorted(valid_rooms, key=lambda r: room_counts[r], reverse=True)
        
        # Pick the warmest room if available, else random
        if room_counts[sorted_rooms[0]] > 0:
            return sorted_rooms[0]
        return random.choice(valid_rooms)

    def create_genome(self):
        genes = copy.deepcopy(self.fixed_genes)
        
        for section in self.sections:
            for course_id in section.get('course_ids', []):
                if any(g.course_id == course_id and g.section_id == section['id'] and g.is_fixed for g in genes):
                    continue

                course = next((c for c in self.courses if c['id'] == course_id), None)
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
                    
                    # Smart placement (Density-Guided Days and Warmth Score)
                    sorted_days = self._get_density_guided_days(section['id'], genes)
                    day = sorted_days[0] # Pick the densest day
                    max_start = max(0, self.total_slots - slots_needed)
                    start = random.randint(0, max_start)
                    room = self._best_room(valid_rooms, day, genes)
                    
                    genes.append(Gene(course_id, section['id'], faculty, room, day, start, slots_needed, gtype))

        return Chromosome(genes)

    def calculate_fitness(self, chromosome):
        penalty = 0
        hard_conflicts = 0
        conflicting_indices = set()
        genes = chromosome.genes
        
        # --- O(1) IN-MEMORY OCCUPANCY BITMASK CACHING ---
        # Instead of scanning O(N^2) nested loops, we populate hash maps instantly.
        room_occupancy = defaultdict(lambda: defaultdict(list))
        faculty_occupancy = defaultdict(lambda: defaultdict(list))
        section_occupancy = defaultdict(lambda: defaultdict(list))
        
        for i, g in enumerate(genes):
            if not g.is_fixed:
                room_info = self.room_map.get(g.room_id)
                if room_info and room_info.get('status') != 'Available':
                    penalty += HC_PENALTY; hard_conflicts += 1; conflicting_indices.add(i)
                if g.gene_type == 'Lab' and room_info and 'Computer Lab' not in room_info.get('capabilities', ''):
                    penalty += HC_PENALTY; hard_conflicts += 1; conflicting_indices.add(i)

            # HC-12: Faculty Day Off / Availability
            if g.faculty_id:
                fac = next((f for f in self.faculty if f['id'] == g.faculty_id), None)
                if fac:
                    fac_avail = fac.get('available_days', '')
                    current_day = self.days[g.day_idx] if hasattr(self, 'days') else str(g.day_idx)
                    if fac_avail and current_day not in fac_avail:
                        penalty += HC_PENALTY; hard_conflicts += 1; conflicting_indices.add(i)

            # HC-20: Lunch Break Allocation (Avoid 12:00 PM - 1:00 PM, slots 10-12)
            if g.start_idx < 12 and g.end_idx > 10:
                penalty += HC_PENALTY; hard_conflicts += 1; conflicting_indices.add(i)

            # HC-03: Strict Async Allocation (Online classes in Virtual rooms)
            room_info = self.room_map.get(g.room_id)
            if g.gene_type == 'Async' and room_info and 'Virtual' not in room_info.get('capabilities', ''):
                penalty += HC_PENALTY; hard_conflicts += 1; conflicting_indices.add(i)

            # HC-19: Faculty Day Split Rule
            if g.locked_day >= 0 and g.day_idx != g.locked_day and not g.is_fixed:
                penalty += HC_PENALTY; hard_conflicts += 1; conflicting_indices.add(i)

            # Record occupancy across all active time slots
            for slot in range(g.start_idx, g.end_idx):
                time_key = (g.day_idx, slot)
                
                # Check Room Collision in O(1)
                if g.room_id:
                    if time_key in room_occupancy[g.room_id]:
                        penalty += HC_PENALTY; hard_conflicts += 1
                        conflicting_indices.add(i)
                        for prev_i in room_occupancy[g.room_id][time_key]:
                            if not genes[prev_i].is_fixed: conflicting_indices.add(prev_i)
                    room_occupancy[g.room_id][time_key].append(i)
                
                # Check Faculty Collision in O(1)
                if g.faculty_id:
                    if time_key in faculty_occupancy[g.faculty_id]:
                        penalty += HC_PENALTY; hard_conflicts += 1
                        conflicting_indices.add(i)
                        for prev_i in faculty_occupancy[g.faculty_id][time_key]:
                            if not genes[prev_i].is_fixed: conflicting_indices.add(prev_i)
                    faculty_occupancy[g.faculty_id][time_key].append(i)
                
                # Check Section Collision in O(1)
                if time_key in section_occupancy[g.section_id]:
                    penalty += HC_PENALTY; hard_conflicts += 1
                    conflicting_indices.add(i)
                    for prev_i in section_occupancy[g.section_id][time_key]:
                        if not genes[prev_i].is_fixed: conflicting_indices.add(prev_i)
                section_occupancy[g.section_id][time_key].append(i)

        chromosome.fitness = penalty
        chromosome.hard_conflicts = hard_conflicts
        chromosome.soft_score = 0
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
        
        # Smart placement (Density-Guided Days and Warmth Score)
        sorted_days = self._get_density_guided_days(gene.section_id, genes)
        gene.day_idx = sorted_days[0]
        gene.start_idx = random.randint(0, max(0, self.total_slots - slots_needed))
        gene.end_idx = gene.start_idx + slots_needed
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
        print("=== RUNNING ALPHA TEST CASE 2: O(1) IN-MEMORY BITMASK CACHING ===")
        print("Telemetry: O(1) Hash Map scanning active, unguided mutation.")
        
        population = [self.create_genome() for _ in range(POPULATION_SIZE)]
        best_schedule = None
        
        for generation in range(1, MAX_GENERATIONS + 1):
            gen_start_t = time.time()
            for chrom in population:
                self.calculate_fitness(chrom)
            
            population.sort(key=lambda x: x.fitness)
            current_best = population[0]
            
            if best_schedule is None or current_best.fitness < best_schedule.fitness:
                best_schedule = copy.deepcopy(current_best)
            
            if generation % 10 == 0:
                elapsed = time.time() - start_t0
                print(f"Gen {generation:04d} | Elapsed: {elapsed:.1f}s | Speed: {elapsed/generation:.4f}s/gen | HC: {current_best.hard_conflicts} | Fitness: {current_best.fitness}")
                
            if progress_callback:
                progress_callback({
                    'generation': generation,
                    'hard_conflicts': current_best.hard_conflicts,
                    'soft_score': current_best.soft_score,
                    'best_fitness': current_best.fitness
                })

            if current_best.hard_conflicts == 0:
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
    print("🧪 ALPHA TESTING: TEST CASE 2 (O(1) BITMASK OCCUPANCY CACHING)")
    print("Connecting to live SQLite database records (instance/scheduling.db)...")
    print("================================================================")
    
    print("Importing app and database models...")
    from app import app, db, Course, Section, Room, Faculty, PreAssignment, Constraint, get_settings
    print("Import successful. Starting app context...")
    
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
        courses = [{
            'id': c.id, 'course_code': c.course_code, 'department': c.department or '',
            'lec_units': c.lec_units or 0, 'lab_units': c.lab_units or 0,
            'synchronous_lec_hours': c.synchronous_lec_hours or 0,
            'synchronous_lab_hours': c.synchronous_lab_hours or 0,
            'asynchronous_lec_hours': c.asynchronous_lec_hours or 0,
            'asynchronous_lab_hours': c.asynchronous_lab_hours or 0,
        } for c in raw_courses]
        
        raw_rooms = Room.query.filter_by(is_archived=False).all()
        rooms = [{'id': r.id, 'room_name': r.room_name, 'capabilities': r.capabilities, 'status': r.status, 'capacity': r.capacity} for r in raw_rooms]
        
        raw_faculty = Faculty.query.filter_by(is_archived=False).all()
        faculty = [{'id': f.id, 'full_name': f.full_name, 'available_days': f.available_days or '', 'max_weekly_hours': f.max_weekly_hours if f.max_weekly_hours is not None else 35} for f in raw_faculty]
        
        raw_sections = Section.query.filter_by(is_archived=False).all()
        sections = [{'id': s.id, 'course_ids': [c.id for c in s.courses], 'number_of_students': s.number_of_students, 'available_days': s.available_days} for s in raw_sections]
        
        valid_course_ids = {c['id'] for c in courses}
        raw_pre = PreAssignment.query.filter_by(is_archived=False).all()
        pre_assignments = [SafePA(pa.course_id, pa.section_id, pa.faculty_id, pa.room_id, pa.day, pa.start_time, pa.end_time) for pa in raw_pre if pa.course_id in valid_course_ids]
        
        db_constraints = Constraint.query.all()
        constraints_config = {c.logic_code: {'type': c.constraint_type, 'weight': c.weight} for c in db_constraints}
        
        print(f"Loaded live data: {len(courses)} courses, {len(sections)} sections, {len(faculty)} faculty, {len(rooms)} rooms.")
        print(f"Active Campus Days: {active_days}")
        
        scheduler = GeneticSchedulerTC2(courses, sections, faculty, rooms, pre_assignments, constraints_config, start_time=7, end_time=21, allowed_days=active_days)
        best = scheduler.run_algorithm()
        print(f"\n🏁 TC2 Benchmark Finished. Best Fitness: {best.fitness}, Conflicts: {best.hard_conflicts}")
