import os
import random
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

# --- CONFIGURATION ---
# POPULATION_SIZE is now computed dynamically inside run_algorithm() based on
# total gene count: max(40, min(150, n_genes × 0.35)).  A static fallback is
# kept here only for code paths that reference it before the scheduler runs.
POPULATION_SIZE   = 40       # fallback — overridden at runtime
OFFSPRING_COUNT   = 20       # Soft-phase offspring per gen
HARD_OFFSPRING    = 20       # Hard-phase CROSSOVER offspring (LNS adds on top)
LNS_OFFSPRING     = 15       # LNS offspring per hard-phase gen (copy-best + repair only HC genes)
MAX_GENERATIONS   = 2000     # Hard cap; early-exit logic fires well before this
SOFT_REFINE_GENS  = 800      # Soft refinement gens after SC-II phase starts

# Stagnation thresholds — two independent counters so STAG_SEVERE can actually fire
STAG_THRESHOLD    = 8        # Mild stagnation → 25% targeted repair (was 15)
STAG_SEVERE       = 20       # Severe stagnation → full diversification (was 40)
STAG_SC1_TIMEOUT  = 35       # SC-I phase: force-advance to SC-II after 35 stagnant gens (was 60)

# Diversity injection — fire when ≥85 % of population share identical (HC, SS)
DIV_THRESHOLD     = 0.85     # similarity ratio to trigger injection
DIV_COOLDOWN      = 20       # minimum gens between consecutive injections

# Penalty weights (for combined fitness display; NSGA-II uses HC + SS as separate objectives)
HC_PENALTY        = 1_000_000
SC1_BASE          = 100
SC2_BASE          = 10

# Thread pool size for parallel chromosome evaluation
# Uses min(8, cpu_count) workers — stays bounded so we don't oversubscribe the CPU.
_N_WORKERS = min(8, os.cpu_count() or 4)


class Gene:
    __slots__ = ('course_id', 'section_id', 'faculty_id', 'room_id',
                 'day_idx', 'start_idx', 'duration_slots', 'end_idx',
                 'gene_type', 'is_fixed', 'bitmask', 'locked_day')

    def __init__(self, course_id, section_id, faculty_id, room_id,
                 day_idx, start_idx, duration_slots, gene_type='Lec', is_fixed=False):
        self.course_id      = course_id
        self.section_id     = section_id
        self.faculty_id     = faculty_id
        self.room_id        = room_id
        self.day_idx        = day_idx
        self.start_idx      = start_idx
        self.duration_slots = duration_slots
        self.end_idx        = start_idx + duration_slots
        self.gene_type      = gene_type
        self.is_fixed       = is_fixed
        self.bitmask        = ((1 << duration_slots) - 1) << start_idx
        self.locked_day     = -1  # -1 = no day lock; >= 0 = must be placed on this day_idx


class Chromosome:
    __slots__ = ('genes', 'fitness', 'hard_conflicts', 'soft_score',
                 'conflicting_indices', 'rank', 'crowding_distance',
                 'sc1_violations', 'sc2_violations')

    def __init__(self, genes):
        self.genes               = genes
        self.fitness             = 0
        self.hard_conflicts      = 0
        self.soft_score          = 0
        self.conflicting_indices = []
        self.rank                = 0      # NSGA-II Pareto rank (1 = non-dominated front)
        self.crowding_distance   = 0.0   # NSGA-II crowding distance (higher = more diverse)
        self.sc1_violations      = 0     # Count of SC-I constraint violations
        self.sc2_violations      = 0     # Count of SC-II constraint violations


def _norm_dept(s):
    """Normalize department strings for comparison regardless of format.
    e.g. 'Department of Arts and Sciences' == 'Arts & Sciences' after normalization."""
    return (s or '').lower().replace('department of ', '').replace(' and ', ' & ').strip()


class GeneticScheduler:

    # ------------------------------------------------------------------ #
    # VISUALIZATION MATRIX (for Frontend Animation)                       #
    # ------------------------------------------------------------------ #
    def get_visualization_matrix(self, chromosome):
        """Return per-room block list with real course/faculty labels.

        Returns:
            {
              'rooms': N,          # number of room rows
              'cols':  M,          # total time slots
              'room_names': [...], # display name per row ("RM 1", room_name, …)
              'blocks': [          # one sub-list per room
                [{'start':s,'end':e,'status':1/2/3,'course':str,'faculty':str}, …],
                …
              ]
            }
        status codes: 1=normal (green), 2=conflict (red), 3=fixed/preassigned (blue)
        """
        total_slots  = self.total_slots
        room_list    = self.rooms          # ordered list of room dicts
        room_ids     = [r['id'] for r in room_list]
        room_idx_map = {rid: i for i, rid in enumerate(room_ids)}

        # Build conflict slot set (only non-fixed genes)
        conflict_set = set()
        for idx in chromosome.conflicting_indices:
            if idx < len(chromosome.genes):
                g = chromosome.genes[idx]
                if g.is_fixed or g.room_id not in room_idx_map:
                    continue
                ridx = room_idx_map[g.room_id]
                for s in range(max(0, g.start_idx), min(total_slots, g.end_idx)):
                    conflict_set.add((ridx, s))

        # Build blocks per room — show only day 0 (Monday) to avoid multi-day overlap on canvas
        # Using day 0; fall back to day 1 if day 0 has no genes at all
        def _pick_display_day(genes, room_idx_map):
            counts = {}
            for g in genes:
                if g.room_id in room_idx_map:
                    counts[g.day_idx] = counts.get(g.day_idx, 0) + 1
            if not counts:
                return 0
            return min(counts, key=lambda d: d)  # earliest day that has genes

        display_day = _pick_display_day(chromosome.genes, room_idx_map)

        blocks = [[] for _ in room_ids]
        for gene in chromosome.genes:
            if gene.room_id not in room_idx_map:
                continue
            if gene.day_idx != display_day:
                continue
            r_idx = room_idx_map[gene.room_id]
            course  = self.course_map.get(gene.course_id, {})
            faculty = self.faculty_map.get(gene.faculty_id, {})
            course_code = course.get('course_code', '?')
            # Use last name from full_name
            full_name = faculty.get('full_name', 'T.B.A.') if faculty else 'T.B.A.'
            fac_name  = full_name.split()[-1] if full_name and full_name != 'T.B.A.' else 'T.B.A.'

            if gene.is_fixed:
                status = 3
            elif any((r_idx, s) in conflict_set
                     for s in range(max(0, gene.start_idx), min(total_slots, gene.end_idx))):
                status = 2
            else:
                status = 1

            blocks[r_idx].append({
                'start':   gene.start_idx,
                'end':     gene.end_idx,
                'status':  status,
                'course':  course_code,
                'faculty': fac_name,
            })

        # Room display names — use actual room name if available
        room_names = [r.get('room_name', f'RM {i+1}') for i, r in enumerate(room_list)]

        return {
            'rooms':      len(room_ids),
            'cols':       total_slots,
            'room_names': room_names,
            'blocks':     blocks,
        }

    # ------------------------------------------------------------------ #
    # INITIALIZATION                                                       #
    # ------------------------------------------------------------------ #
    def __init__(self, courses, sections, faculty, rooms, pre_assignments,
                 constraints_config, start_time=7, end_time=20, allowed_days=None,
                 split_assignments=None, fa_map=None, blocked_slots=None):
        self.courses     = courses
        self.sections    = sections
        self.faculty     = faculty
        self.rooms       = rooms
        self.constraints = constraints_config

        # Adaptive SC-II weight (Step 5). Starts at SC2_BASE (10), climbs to 50
        # during Phase 3 to push the algorithm harder toward soft improvement.
        # Reset to SC2_BASE at the start of each run (see run_algorithm).
        self._sc2_base = SC2_BASE

        self.days      = allowed_days or ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        self.day_map   = {day: i for i, day in enumerate(self.days)}

        # Blocked time slots: {day_idx: combined_bitmask}. Never place any gene overlapping these.
        self._blocked_bitmasks = {}
        for _blk in (blocked_slots or []):
            _dname = _blk.get('day', '')
            if _dname not in self.day_map:
                continue
            _didx = self.day_map[_dname]
            try:
                _sh, _sm = map(int, _blk['start'].split(':'))
                _eh, _em = map(int, _blk['end'].split(':'))
                _s = max(0, (_sh - start_time) * 2 + (1 if _sm >= 30 else 0))
                _e = min((end_time - start_time) * 2, (_eh - start_time) * 2 + (1 if _em >= 30 else 0))
                if _e > _s:
                    _mask = ((1 << (_e - _s)) - 1) << _s
                    self._blocked_bitmasks[_didx] = self._blocked_bitmasks.get(_didx, 0) | _mask
            except Exception:
                pass

        # split_map: {(course_id, section_id, gtype): [(day_idx, slots, faculty_id), ...]}
        # gtype is 'Lab' or 'Lec' — splits apply only to the matching session type.
        # Built from split_assignments passed by the generate route.
        self.split_map = {}
        for sa in (split_assignments or []):
            pairs = []
            for sp in sa.get('splits', []):
                dname = sp.get('day', '')
                didx  = self.day_map.get(dname, -1)
                hours = sp.get('hours', 0) or 0
                slots = int(hours * 2)
                if didx >= 0 and slots > 0:
                    pairs.append((didx, slots, sa.get('faculty_id')))
            if pairs:
                gtype = sa.get('gtype', 'Lab')  # 'Lab' or 'Lec'
                self.split_map[(sa['course_id'], sa['section_id'], gtype)] = pairs
        # Preferred faculty per (course_id, section_id) from manual FacultyAssignment.
        # Used in create_genome() instead of random.choice() for initial assignment.
        self.fa_map = fa_map or {}
        self.start_hour = start_time
        self.end_hour   = end_time
        self.total_slots = (end_time - start_time) * 2

        # Quick-lookup maps
        self.room_map    = {r['id']: r for r in rooms}
        self.course_map  = {c['id']: c for c in courses}
        self.section_map = {s['id']: s for s in sections}
        self.faculty_map = {f['id']: f for f in faculty}
        self.faculty_ids = [f['id'] for f in faculty]
        # Department lookup per faculty — normalized for cross-format comparison
        self._fac_dept = {f['id']: _norm_dept(f.get('department', '')) for f in faculty}

        # Pre-cache faculty available day indices for HC-18 (FACULTY_AVAILABILITY)
        self._fac_avail_days = {}
        for f in faculty:
            avail_str = f.get('available_days', '')
            if avail_str:
                avail_set = set()
                for day in avail_str.split(','):
                    day = day.strip()
                    if day in self.day_map:
                        avail_set.add(self.day_map[day])
                if avail_set:
                    self._fac_avail_days[f['id']] = avail_set

        # Precompute time-boundary slots
        self.noon_slot          = (12 - start_time) * 2
        self.eve_slot           = (18 - start_time) * 2
        self._last_day          = len(self.days) - 1
        # HC-27: first class per room must start within 1 hour of system start
        # slot 0 = start_time, slot 1 = start+30min, slot 2 = start+1hr (VIOLATION)
        self._max_first_slot    = 1   # max allowed start slot for first class in a room
        # Lunch window: 10am–2pm — each section must have ≥1 free hour in this range
        self.lunch_window_start = (10 - start_time) * 2   # 10am
        self.lunch_window_end   = (14 - start_time) * 2   # 2pm

        # Pre-cache valid rooms by gene_type (computed once)
        available  = [r['id'] for r in rooms if r.get('status') == 'Available' and r.get('room_name', '') != 'T.B.A.']
        lab_rooms  = [r['id'] for r in rooms if r.get('status') == 'Available'
                      and 'Computer Lab' in r.get('capabilities', '') and r.get('room_name', '') != 'T.B.A.']
        all_rooms  = [r['id'] for r in rooms if r.get('room_name', '') != 'T.B.A.']
        self._valid_rooms_lec   = available if available else all_rooms
        self._valid_rooms_lab   = lab_rooms  if lab_rooms  else (available if available else all_rooms)
        self._valid_rooms_async = self._valid_rooms_lec
        self._valid_rooms_fixed = all_rooms

        # Identify rooms that allow multiple simultaneous assignments:
        # - University Field (outdoor/NSTP), T.B.A. (placeholder — admin resolves later)
        self.tba_room_ids = {r['id'] for r in rooms if r.get('room_name', '') == 'T.B.A.'}
        self.multi_assignment_rooms = (
            {r['id'] for r in rooms if 'FIELD' in r.get('room_name', '').upper()}
            | self.tba_room_ids
        )
        
        # Identify faculty that allow multiple simultaneous assignments (e.g., T.B.A.)
        self.multi_assignment_faculty = {f['id'] for f in faculty if 'T.B.A.' in f.get('full_name', '').upper()}

        # Lecture-only rooms (non-Computer-Lab) for packed lecture scheduling.
        # Lecture subjects fill these first (daytime), then evening slots, then lab rooms as last resort.
        # T.B.A. room has 'Lecture,Computer Lab' so it's excluded from lec_only by capability filter;
        # add it back explicitly since T.B.A. is a universal fallback for any gene type.
        lec_only = [r['id'] for r in rooms if r.get('status') == 'Available'
                    and 'Computer Lab' not in r.get('capabilities', '') and r.get('room_name', '') != 'T.B.A.']
        self._valid_rooms_lec_only = lec_only if lec_only else (available if available else all_rooms)
        self._lec_room_set = set(self._valid_rooms_lec_only)

        # 7 PM slot — boundary between daytime and evening for room priority and avoidance penalty.
        # Slots 0-23 = 7am-6:59pm (daytime), slots 24+ = 7pm-9pm (evening, last resort).
        self.seven_pm_slot = (19 - start_time) * 2

        # Special course → room mapping: if a course is assigned exclusively to a room,
        # the GA will force genes for that course to use only that room.
        self._special_room_for_course = {}
        for r in rooms:
            sids_str = r.get('special_course_ids', '') or ''
            for cid_str in sids_str.split(','):
                cid_str = cid_str.strip()
                if cid_str:
                    try:
                        cid = int(cid_str)
                        self._special_room_for_course[cid] = r['id']
                    except ValueError:
                        pass

        # Divisible-by-4 rule for lecture rooms: ensures classes start on clean 2-hour boundaries
        # (slot 0=7am, 4=9am, 8=11am, 12=1pm, 16=3pm, 20=5pm, 24=7pm, 28=9pm).
        # Dynamic threshold: count long-lec genes (sync_lec_hours > 2) that have a special room
        # assignment (e.g. NSTP → University Field). These are already exempt from div4 via
        # duration_slots < 6 and room checks, so they should not count against the threshold.
        # Threshold = special_long_lec_count + 5 to allow 5 additional non-special 3-hr courses.
        # Also include pre-assigned course IDs — fixed genes are already exempt from div4
        # via `not g.is_fixed`, so they should count as "special" for the threshold.
        _special_cids = set(self._special_room_for_course.keys())
        for _pa in pre_assignments:
            _special_cids.add(_pa.course_id)
        _long_lec_genes = sum(
            1 for sec in sections
            for cid in sec.get('course_ids', [])
            if (self.course_map.get(cid, {}).get('synchronous_lec_hours', 0) or 0) > 2
        )
        _special_long_lec = sum(
            1 for sec in sections
            for cid in sec.get('course_ids', [])
            if (self.course_map.get(cid, {}).get('synchronous_lec_hours', 0) or 0) > 2
            and cid in _special_cids
        )
        self._use_div4_for_lec = (_long_lec_genes <= _special_long_lec + 5)

        # Room departments: if a room has department restrictions, only matching-dept courses can use it.
        # Empty/blank room_departments = available to all departments.
        self._room_depts = {}  # room_id -> set of dept names (empty set = no restriction = all depts)
        for r in rooms:
            rd_str = r.get('room_departments', '') or ''
            self._room_depts[r['id']] = {d.strip() for d in rd_str.split(',') if d.strip()}

        # Pre-build per-dept room pools so _get_rooms_for_gene avoids re-computing each call.
        # A room is eligible for a dept if: room has no dept restriction OR dept is in room's restriction set.
        # Fallback priority: dept-eligible rooms → T.B.A. room (universal) → full pool (safety net).
        all_course_depts = {c.get('department', '') for c in courses if c.get('department', '')}
        self._dept_rooms_lec      = {}  # dept -> lec+lab available rooms
        self._dept_rooms_lab      = {}  # dept -> lab rooms
        self._dept_rooms_lec_only = {}  # dept -> lecture-only rooms
        _tba_list = list(self.tba_room_ids)
        for dept in all_course_depts:
            def _eligible(rid):
                rd = self._room_depts.get(rid)
                return not rd or dept in rd
            self._dept_rooms_lec[dept]      = [rid for rid in self._valid_rooms_lec      if _eligible(rid)] or self._valid_rooms_lec
            self._dept_rooms_lab[dept]      = [rid for rid in self._valid_rooms_lab      if _eligible(rid)] or self._valid_rooms_lab
            self._dept_rooms_lec_only[dept] = [rid for rid in self._valid_rooms_lec_only if _eligible(rid)] or self._valid_rooms_lec_only

        # Pre-cache PE / Async flags per course_id (avoid repeated string ops in fitness)
        self._is_pe = {}
        for c in courses:
            code_up = c.get('course_code', '').upper()
            self._is_pe[c['id']] = ('PE' in code_up or 'FITT' in code_up)

        # Pre-cache penalty values and types (constraints are static per run)
        self._pen      = {}
        self._pen_type = {}   # code → 'HC' | 'SC1' | 'SC2' | 'NC'
        for code in ('ROOM_AVAILABILITY', 'ROOM_SUITABILITY', 'ROOM_CAPACITY_PROPORTIONAL',
                     'OPERATING_HOURS', 'LUNCH_BREAK', 'EVENING_AVOIDANCE',
                     'PE_MORNING_PLACEMENT', 'PE_EARLY_WEEK', 'ASYNC_STRATEGIC_PLACEMENT',
                     'LEC_LAB_WEEKLY_DIST', 'LEC_LAB_PROXIMITY',
                     'MAX_CONSECUTIVE_STUDENT', 'MAX_CONSECUTIVE_FACULTY',
                     'LEC_LAB_SEQUENCE', 'NO_ISOLATED_LECTURES', 'NO_ISOLATED_LABS',
                     'MIN_DAILY_SECTION_LOAD',
                     'FACULTY_AVAILABILITY',
                     'GLOBAL_DAY_RESTRICTION', 'SECTION_DAY_RESTRICTIONS',
                     'HOURLY_ALIGNMENT', 'COMPLETE_COURSE_SCHEDULING',
                     'STRICT_LEC_DURATION', 'STRICT_LAB_DURATION',
                     'STRICT_ASYNC_LEC_DUR', 'STRICT_ASYNC_LAB_DUR',
                     'EARLY_START_ENFORCEMENT',
                     'LECTURE_SLOT_ALIGNMENT',
                     'FACULTY_DAY_SPLIT'):
            self._pen[code] = self._penalty(code)
            cfg = self.constraints.get(code, {})
            if isinstance(cfg, dict):
                self._pen_type[code] = cfg.get('type', 'HC')
            else:
                self._pen_type[code] = cfg or 'HC'

        # Pre-cache section student counts
        self._sec_students = {s['id']: s.get('number_of_students', 0) for s in sections}

        # Pre-cache required (section_id, course_id) pairs for HC-25
        # Only include courses that are actually in this run's course_map (i.e. current semester).
        # Sections carry course_ids across all semesters; filtering prevents false HC-25 penalties.
        self._required_sec_course = set()
        for _sec in sections:
            for _cid in _sec.get('course_ids', []):
                if _cid in self.course_map:
                    self._required_sec_course.add((_sec['id'], _cid))

        # Pre-cache expected duration (slots) per (course_id, gene_type) for HC-08/09/10/11
        self._expected_duration = {}
        for _c in courses:
            _cid = _c['id']
            _lec = (_c.get('synchronous_lec_hours', 0) or _c.get('lec_units', 0)) or 0
            _lab = (_c.get('synchronous_lab_hours', 0) or _c.get('lab_units', 0)) or 0
            _asy = (_c.get('asynchronous_lec_hours', 0) or 0) + (_c.get('asynchronous_lab_hours', 0) or 0)
            if _lec > 0: self._expected_duration[(_cid, 'Lec')]   = int(_lec * 2)
            if _lab > 0: self._expected_duration[(_cid, 'Lab')]   = int(_lab * 2)
            if _asy > 0: self._expected_duration[(_cid, 'Async')] = int(_asy * 2)

        # Lazily-populated sorted-room cache per (section_id, gene_type)
        self._sorted_rooms_cache = {}

        # Process pre-assignments (fixed genes)
        self.fixed_genes = []
        for pa in pre_assignments:
            if pa.day not in self.day_map:
                continue
            try:
                s_h, s_m = map(int, pa.start_time.split(':'))
                e_h, e_m = map(int, pa.end_time.split(':'))
                start_slot = ((s_h - self.start_hour) * 2) + (1 if s_m >= 30 else 0)
                end_slot   = ((e_h - self.start_hour) * 2) + (1 if e_m >= 30 else 0)
                duration   = end_slot - start_slot
                if start_slot >= 0 and duration > 0:
                    self.fixed_genes.append(Gene(
                        pa.course_id, pa.section_id, pa.faculty_id, pa.room_id,
                        self.day_map[pa.day], start_slot, duration, 'Fixed', True
                    ))
            except Exception:
                continue

    # ------------------------------------------------------------------ #
    # CONSTRAINT PENALTY HELPER                                           #
    # ------------------------------------------------------------------ #
    def _penalty(self, code):
        cfg = self.constraints.get(code, {})
        if isinstance(cfg, dict):
            ctype  = cfg.get('type', 'HC')
            weight = max(1, cfg.get('weight', 1))
        else:
            ctype  = cfg or 'HC'
            weight = 1
        if ctype == 'NC':  return 0
        if ctype == 'HC':  return HC_PENALTY
        if ctype == 'SC1': return SC1_BASE * weight
        if ctype == 'SC2': return self._sc2_base * weight
        return 0

    # ------------------------------------------------------------------ #
    # UTILITIES                                                            #
    # ------------------------------------------------------------------ #
    def slot_to_time(self, slot_idx):
        total_min = slot_idx * 30
        h = self.start_hour + (total_min // 60)
        m = total_min % 60
        return f"{h:02d}:{m:02d}"

    def get_valid_rooms(self, gene_type):
        if gene_type == 'Lab':   return self._valid_rooms_lab
        if gene_type == 'Fixed': return self._valid_rooms_fixed
        if gene_type == 'Lec':   return self._valid_rooms_lec_only
        return self._valid_rooms_lec  # Async

    def _get_rooms_for_gene(self, gene):
        """Return the correct room pool for a gene, accounting for 3-hour lecture override,
        special course-to-room assignments, and room department restrictions."""
        # Special assignment overrides everything (except Fixed genes)
        if gene.gene_type != 'Fixed' and gene.course_id in self._special_room_for_course:
            return [self._special_room_for_course[gene.course_id]]
        if gene.gene_type == 'Fixed':
            return self._valid_rooms_fixed
        # Get course department for dept-based room filtering
        dept = self.course_map.get(gene.course_id, {}).get('department', '')
        if gene.gene_type == 'Lab':
            return self._dept_rooms_lab.get(dept) or self._valid_rooms_lab
        if gene.gene_type == 'Lec' and gene.duration_slots >= 6:
            # 3-hour lectures → lab rooms (same as Lab genes)
            pool = self._dept_rooms_lab.get(dept) or self._valid_rooms_lab
            return pool if pool else (self._dept_rooms_lec_only.get(dept) or self._valid_rooms_lec_only)
        if gene.gene_type == 'Lec':
            return self._dept_rooms_lec_only.get(dept) or self._valid_rooms_lec_only
        return self._dept_rooms_lec.get(dept) or self._valid_rooms_lec  # Async

    def _smart_start(self, slots_needed, allow_evening=False, use_div4=False, even_only=True):
        """
        Return a smart start slot with optional slot alignment constraints.

        use_div4:     only divisible-by-4 slots (lecture rooms: 7am=0, 9am=4, 11am=8 …)
        even_only:    only even-numbered slots — eliminates 7:30/8:30/9:30 am starts
        allow_evening: if True, include slots from 7pm (seven_pm_slot) onwards

        Weights: morning 4×, lunch 2×, afternoon 4×, evening 3× (if allow_evening).
        Daytime band extends to 7pm (seven_pm_slot); evening = 7pm–close.
        """
        if use_div4:
            valid = lambda s: s % 4 == 0
        elif even_only:
            valid = lambda s: s % 2 == 0
        else:
            valid = lambda s: True

        max_start  = max(0, self.total_slots - slots_needed)
        lws        = self.lunch_window_start  # 10am
        lwe        = self.lunch_window_end    # 2pm
        day_upper  = self.seven_pm_slot       # 7pm = daytime/evening split

        # Morning: 7am up to 10am (slots before lunch window)
        morning_end = max(0, lws - slots_needed)
        morning = [s for s in range(0, morning_end + 1)
                   if s <= max_start and valid(s)]

        # Lunch zone: 10am–2pm — allowed but lower weight (need ≥1 free hour in window)
        upper_lz = max(lws, min(lwe, day_upper) - slots_needed)
        lunch_zone = ([s for s in range(lws, upper_lz + 1)
                       if s <= max_start and valid(s)]
                      if upper_lz >= lws else [])

        # Afternoon: 2pm–7pm
        upper_aft = day_upper - slots_needed
        afternoon = ([s for s in range(lwe, upper_aft + 1)
                      if s <= max_start and valid(s)]
                     if upper_aft >= lwe else [])

        evening = ([s for s in range(day_upper, max_start + 1) if valid(s)]
                   if allow_evening else [])

        # Morning 4×, lunch zone 2× (allow but discourage filling entire window),
        # afternoon 4×, evening 3×
        pool = morning * 4 + lunch_zone * 2 + afternoon * 4 + evening * 3
        if pool:
            return random.choice(pool)
        # Fallback: any valid slot in full range
        fallback = [s for s in range(0, max_start + 1) if valid(s)]
        if fallback:
            return random.choice(fallback)
        return random.randint(0, max_start)

    def _best_room(self, gene_type, section_id, occ_room=None, rooms_override=None):
        """Return capacity-matched room using utilization-squared weighting.

        Sorting: rooms sorted by waste ratio (cap - students) / cap — ascending.
        Ties between absolute-gap and ratio are identical for a fixed section size,
        but ratio is stored for clarity.

        Weighting: instead of linear rank weights, use (students/cap)^2 so that a
        tight-fit room (93% full) gets ~46% selection probability while an oversized
        room (30% full) gets ~5%.  This naturally reserves large rooms for large
        sections and lets small sections use appropriately-sized rooms.

        rooms_override: explicit room pool (bypasses cache), e.g. for phase priorities.
        """
        students = self._sec_students.get(section_id, 0)
        rm       = self.room_map

        def _waste(rid):
            c = rm.get(rid, {}).get('capacity', 0)
            return 999999.0 if c < students else (c - students) / max(c, 1)

        def _util_sq(rid):
            """Selection weight: utilization^2, clamped to [0.01, 1]."""
            c = rm.get(rid, {}).get('capacity', 1) or 1
            return max(min(students / c, 1.0) ** 2, 0.01)

        if rooms_override is not None:
            if students and rooms_override:
                valid_ids = sorted(rooms_override, key=_waste)
            else:
                valid_ids = list(rooms_override)
            if not valid_ids:
                return None
        else:
            cache_key = (section_id, gene_type)
            cached = self._sorted_rooms_cache.get(cache_key)
            if cached is None:
                valid_ids = self.get_valid_rooms(gene_type)
                if students and valid_ids:
                    self._sorted_rooms_cache[cache_key] = sorted(valid_ids, key=_waste)
                else:
                    self._sorted_rooms_cache[cache_key] = valid_ids
                cached = self._sorted_rooms_cache[cache_key]
            if not cached:
                return None
            valid_ids = cached

        top_k = min(5, len(valid_ids))
        if top_k == 0:
            return None
        if top_k == 1:
            return valid_ids[0]
        candidates = valid_ids[:top_k]

        # Utilization-squared weights: strongly prefer rooms the section nearly fills.
        # A 93%-full room gets weight 0.865; a 30%-full room gets weight 0.09.
        if students > 0:
            weights = [_util_sq(rid) for rid in candidates]
        else:
            weights = [top_k - i for i in range(top_k)]

        if occ_room is not None:
            # Warmth score: total occupied slots across all days for this room.
            # Higher warmth = room already in use = prefer it to concentrate usage.
            days_count = len(self.days)
            def warmth(rid):
                return sum(bin(occ_room.get((rid, d), 0)).count('1') for d in range(days_count))
            warm_scores = [warmth(rid) for rid in candidates]
            max_warm    = max(warm_scores) if any(warm_scores) else 1
            # Blend: 70% utilization-squared + 30% warmth bonus (normalised 0-1)
            combined = [w * (0.7 + 0.3 * (ws / max(max_warm, 1))) for w, ws in zip(weights, warm_scores)]
            return random.choices(candidates, weights=combined, k=1)[0]

        return random.choices(candidates, weights=weights, k=1)[0]

    def _find_soft_violation_indices(self, chromosome, sc1_only=False):
        violators_set = set()
        noon_slot     = self.noon_slot
        seven_pm_slot = self.seven_pm_slot
        lws           = self.lunch_window_start  # 10am
        lwe           = self.lunch_window_end    # 2pm
        last_day      = self._last_day
        is_pe         = self._is_pe
        sec_stu       = self._sec_students
        room_map      = self.room_map

        # Per-gene violations (per-gene soft constraints)
        for i, g in enumerate(chromosome.genes):
            if g.is_fixed:
                continue
            # SC-II-06: Evening Avoidance (SC2 — skip in sc1_only mode)
            if not sc1_only and g.start_idx >= seven_pm_slot:
                violators_set.add(i); continue
            if is_pe.get(g.course_id):
                if g.start_idx >= noon_slot or g.day_idx > 2:
                    violators_set.add(i); continue
            if g.gene_type == 'Async':
                if g.day_idx != 0 and g.day_idx != last_day:
                    violators_set.add(i); continue
            # SC-II-03: Room Capacity (SC2 — skip in sc1_only mode)
            if not sc1_only:
                r        = room_map.get(g.room_id, {})
                cap      = r.get('capacity', 0)
                students = sec_stu.get(g.section_id, 0)
                if cap > 0 and students > 0 and students / cap < 0.60:
                    violators_set.add(i)

        # Relational violations — require multi-gene context
        genes = chromosome.genes

        # Build per-(section, day) and per-(faculty, day) slot lists.
        # Occupancy maps include fixed genes so preassigned classes are counted.
        # Candidate lists (for flagging) exclude fixed genes (can't be moved).
        sec_day_genes = defaultdict(list)   # {(sec_id, day_idx): [non-fixed gene_idx, ...]}
        fac_day_genes = defaultdict(list)   # {(fac_id, day_idx): [non-fixed gene_idx, ...]}
        sec_day_occ   = defaultdict(set)    # {(sec_id, day_idx): lunch-window slots occupied}
        fac_day_occ   = defaultdict(set)    # {(fac_id, day_idx): lunch-window slots occupied}
        sec_course    = defaultdict(dict)   # {(sec_id, course_id): {type: gene_idx}}
        for i, g in enumerate(genes):
            # Always accumulate occupancy (fixed or not)
            for s in range(max(g.start_idx, lws), min(g.end_idx, lwe)):
                sec_day_occ[(g.section_id, g.day_idx)].add(s)
                if g.faculty_id:
                    fac_day_occ[(g.faculty_id, g.day_idx)].add(s)
            if g.is_fixed:
                continue
            sec_day_genes[(g.section_id, g.day_idx)].append(i)
            if g.faculty_id:
                fac_day_genes[(g.faculty_id, g.day_idx)].append(i)
            if g.gene_type in ('Lec', 'Lab'):
                sec_course[(g.section_id, g.course_id)][g.gene_type] = i

        if not sc1_only:
            # SC-II-04: Lunch Break — section must have ≥1 free hour in 10am–2pm window
            for (sec_id, day_idx), idxs in sec_day_genes.items():
                occ = sec_day_occ.get((sec_id, day_idx), set())
                if occ and not any(s not in occ and (s + 1) not in occ
                                   for s in range(lws, lwe - 1)):
                    for i in idxs:
                        g = genes[i]
                        if g.start_idx < lwe and g.end_idx > lws:
                            violators_set.add(i)

            # SC-II-04: Lunch Break — faculty must have ≥1 free hour in 10am–2pm window
            for (fac_id, day_idx), idxs in fac_day_genes.items():
                occ = fac_day_occ.get((fac_id, day_idx), set())
                if occ and not any(s not in occ and (s + 1) not in occ
                                   for s in range(lws, lwe - 1)):
                    for i in idxs:
                        g = genes[i]
                        if g.start_idx < lwe and g.end_idx > lws:
                            violators_set.add(i)

            # SC-II-01/02/05: NO_ISOLATED_LECTURES / NO_ISOLATED_LABS / MIN_DAILY_SECTION_LOAD
            for (sec_id, day_idx), idxs in sec_day_genes.items():
                if len(idxs) < 2:
                    violators_set.add(idxs[0])

        # SC-I-01: LEC_LAB_WEEKLY_DIST (Lab placed before Lec day)
        # SC-I-03: LEC_LAB_PROXIMITY (Lec and Lab more than 3 days apart)
        for type_map in sec_course.values():
            lec_i = type_map.get('Lec')
            lab_i = type_map.get('Lab')
            if lec_i is None or lab_i is None:
                continue
            lec_g = genes[lec_i]
            lab_g = genes[lab_i]
            if lab_g.day_idx < lec_g.day_idx:
                violators_set.add(lab_i)
            if abs(lec_g.day_idx - lab_g.day_idx) > 3:
                violators_set.add(lec_i)
                violators_set.add(lab_i)

        return list(violators_set)

    # ------------------------------------------------------------------ #
    # OCCUPATION SET HELPERS (for batch mutation)                        #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_occ_sets(genes):
        occ_room = defaultdict(int)
        occ_fac  = defaultdict(int)
        occ_sec  = defaultdict(int)
        for g in genes:
            mask = g.bitmask
            d    = g.day_idx
            occ_room[(g.room_id, d)] |= mask
            if g.faculty_id is not None:
                occ_fac[(g.faculty_id, d)] |= mask
            occ_sec[(g.section_id, d)] |= mask
        return occ_room, occ_fac, occ_sec

    @staticmethod
    def _remove_from_occ(gene, occ_room, occ_fac, occ_sec):
        mask = ~gene.bitmask
        d = gene.day_idx
        occ_room[(gene.room_id, d)] &= mask
        if gene.faculty_id is not None:
            occ_fac[(gene.faculty_id, d)] &= mask
        occ_sec[(gene.section_id, d)] &= mask

    @staticmethod
    def _add_to_occ(gene, occ_room, occ_fac, occ_sec):
        mask = gene.bitmask
        d = gene.day_idx
        occ_room[(gene.room_id, d)] |= mask
        if gene.faculty_id is not None:
            occ_fac[(gene.faculty_id, d)] |= mask
        occ_sec[(gene.section_id, d)] |= mask

    # ------------------------------------------------------------------ #
    # GREEDY CONFLICT-FREE GENOME CREATION                                #
    # ------------------------------------------------------------------ #
    def create_genome(self, skip_exhaustive=False):
        """
        Greedy constructor that GUARANTEES zero hard conflicts on every genome.
        Uses unified occ_room/fac/sec sets and falls back to exhaustive placement
        if the fast random search fails.
        skip_exhaustive=True: skip _exhaustive_place_gene during init for speed;
        any resulting conflicts are fixed by _hard_conflict_repair afterward.
        Lec genes are placed before Lab genes for each course so HC-04
        (LEC_LAB_SEQUENCE) is satisfied at construction time.
        """
        genes    = [self._copy_gene(g) for g in self.fixed_genes]
        occ_room, occ_fac, occ_sec = self._build_occ_sets(genes)

        faculty_ids = self.faculty_ids
        # Track placed Lec genes to enforce HC-04: Lab must not precede Lec
        lec_placed     = {}   # {(sec_id, course_id): placed_gene}
        lec_faculty_map = {}  # {(course_id, sec_id): faculty_id} — for Lab pairing

        for section in self.sections:
            sec_id = section['id']
            for course_id in section['course_ids']:
                # Skip if already pre-assigned
                skip = False
                for g in genes:
                    if g.course_id == course_id and g.section_id == sec_id and g.is_fixed:
                        skip = True; break
                if skip:
                    continue

                course = self.course_map.get(course_id)
                if not course:
                    continue

                loads = []
                lec     = course.get('synchronous_lec_hours', 0) or course.get('lec_units', 0)
                lab     = course.get('synchronous_lab_hours', 0) or course.get('lab_units', 0)
                async_h = course.get('asynchronous_lec_hours', 0) + course.get('asynchronous_lab_hours', 0)
                if lec     > 0: loads.append((lec,     'Lec'))
                if lab     > 0: loads.append((lab,     'Lab'))
                if async_h > 0: loads.append((async_h, 'Async'))

                for hours, gtype in loads:
                    slots = int(hours * 2)
                    # Lab genes reuse the same faculty as the sibling Lec gene (Option B pairing)
                    if gtype == 'Lab' and (course_id, sec_id) in lec_faculty_map:
                        fac = lec_faculty_map[(course_id, sec_id)]
                    else:
                        _fa_fac = self.fa_map.get((course_id, sec_id))
                        # Build dept-filtered pool: T.B.A. (multi-assignment) always eligible
                        _cdept = _norm_dept((course or {}).get('department', ''))
                        if _cdept:
                            _dept_pool = [fid for fid in faculty_ids
                                          if fid in self.multi_assignment_faculty
                                          or self._fac_dept.get(fid, '') == _cdept
                                          or self._fac_dept.get(fid, '') == '']
                            _dept_pool = _dept_pool or faculty_ids
                        else:
                            _dept_pool = faculty_ids
                        # Use FA-assigned faculty if still in the eligible pool; else dept-filtered random
                        fac = (_fa_fac if _fa_fac in faculty_ids else None) or (random.choice(_dept_pool) if _dept_pool else None)

                    # ── Faculty Day Split: expand one gene into N locked sub-genes ──
                    # Keyed by gtype so Lab splits only apply to Lab genes and Lec to Lec genes
                    _split_pairs = self.split_map.get((course_id, sec_id, gtype)) if gtype in ('Lab', 'Lec') else None
                    if _split_pairs:
                        # Use the split faculty_id if provided; otherwise keep fac
                        _split_fac = _split_pairs[0][2] or fac
                        _pref_fac = _split_fac if gtype == 'Lab' else _split_fac
                        _split_room = None  # room secured by first sub-gene; offered to siblings
                        for _didx, _dslots, _sfac in _split_pairs:
                            _sfac = _sfac or fac
                            vr = self.get_valid_rooms(gtype)
                            g  = Gene(course_id, sec_id, _sfac, vr[0] if vr else None,
                                      _didx, 0, _dslots, gtype, False)
                            g.locked_day = _didx
                            # HC-04 min_day: for Lab, must be >= Lec day
                            min_day_split = 0
                            min_start_sd_split = -1
                            if gtype == 'Lab':
                                lec_gene = lec_placed.get((sec_id, course_id))
                                if lec_gene and lec_gene.day_idx < len(self.days) - 1:
                                    min_day_split = lec_gene.day_idx
                                    min_start_sd_split = lec_gene.start_idx - 1
                            self.randomize_gene_fast(g, occ_room, occ_fac, occ_sec,
                                                     min_day_split, min_start_sd_split,
                                                     use_warmth=True, preferred_faculty=_pref_fac,
                                                     preferred_room=_split_room)
                            # Verify & fallback
                            mask = g.bitmask; d = g.day_idx
                            if ((occ_room.get((g.room_id, d), 0) & mask) != 0 or
                                (g.faculty_id is not None and (occ_fac.get((g.faculty_id, d), 0) & mask) != 0) or
                                (occ_sec.get((g.section_id, d), 0) & mask) != 0):
                                self._exhaustive_place_gene(g, occ_room, occ_fac, occ_sec,
                                                            min_day_split, min_start_sd_split)
                            if gtype == 'Lec':
                                lec_placed[(sec_id, course_id)] = g
                                lec_faculty_map[(course_id, sec_id)] = g.faculty_id
                            # Record first sibling's real room so subsequent siblings prefer it
                            if _split_room is None and g.room_id not in self.tba_room_ids:
                                _split_room = g.room_id
                            genes.append(g)
                            self._add_to_occ(g, occ_room, occ_fac, occ_sec)
                        continue  # skip normal single-gene path

                    # Build a scratch gene then find a conflict-free placement
                    vr  = self.get_valid_rooms(gtype)
                    g   = Gene(course_id, sec_id, fac, vr[0] if vr else None,
                               0, 0, slots, gtype, False)

                    # HC-04: Lab must be placed on day >= Lec day (and start >= Lec start on same day).
                    # Exception: if Lec is on the last available day, drop the min_day constraint
                    # so Lab isn't forced into an infeasible window (e.g. 3-hour Lab after a
                    # 2-hour Lec with only 2.5 hours left before operating-hours cutoff).
                    # The HC-04 fitness check will catch any remaining violation.
                    min_day = 0
                    min_start_sd = -1
                    if gtype == 'Lab':
                        lec_gene = lec_placed.get((sec_id, course_id))
                        if lec_gene and lec_gene.day_idx < len(self.days) - 1:
                            min_day = lec_gene.day_idx
                            min_start_sd = lec_gene.start_idx - 1  # Lab start must be >= Lec start

                    # Fast random search (60 attempts, includes faculty reassignment)
                    # use_warmth=True: prefer rooms already in use to concentrate utilisation
                    # Lab genes pass preferred_faculty to lock same faculty as sibling Lec
                    _pref_fac = lec_faculty_map.get((course_id, sec_id)) if gtype == 'Lab' else None
                    self.randomize_gene_fast(g, occ_room, occ_fac, occ_sec, min_day, min_start_sd,
                                             use_warmth=True, preferred_faculty=_pref_fac)

                    # Verify placement is actually conflict-free using bitwise ops
                    placed_ok = True
                    mask = g.bitmask
                    d = g.day_idx
                    if ((occ_room.get((g.room_id, d), 0) & mask) != 0 or
                        (g.faculty_id is not None and (occ_fac.get((g.faculty_id, d), 0) & mask) != 0) or
                        (occ_sec.get((g.section_id, d), 0) & mask) != 0):
                        placed_ok = False

                    if not placed_ok and not skip_exhaustive:
                        # Exhaustive fallback — guaranteed conflict-free if feasible
                        self._exhaustive_place_gene(g, occ_room, occ_fac, occ_sec, min_day, min_start_sd)

                    # Track Lec placement and faculty for sibling Lab genes
                    if gtype == 'Lec':
                        lec_placed[(sec_id, course_id)] = g
                        lec_faculty_map[(course_id, sec_id)] = g.faculty_id

                    genes.append(g)
                    self._add_to_occ(g, occ_room, occ_fac, occ_sec)

        return Chromosome(genes)

    # ------------------------------------------------------------------ #
    # FITNESS CALCULATION (Hard + Soft Constraints)                       #
    # ------------------------------------------------------------------ #
    def calculate_fitness(self, chromosome, hard_only=False, sc1_only=False):
        penalty        = 0
        hard_conflicts = 0
        soft_score     = 0
        sc1_violations = 0
        sc2_violations = 0
        conflicts      = set()
        # include_sc2: True only in full soft mode (Phase 3)
        include_sc2    = not hard_only and not sc1_only

        room_use  = defaultdict(list)
        fac_use   = defaultdict(list)
        sec_use   = defaultdict(list)
        # Bitmask dicts for O(1) inline overlap detection (replaces check_overlap sort+scan)
        room_bits = defaultdict(int)
        fac_bits  = defaultdict(int)
        sec_bits  = defaultdict(int)

        sec_course_genes = {}

        genes       = chromosome.genes
        pen      = self._pen
        pen_type = self._pen_type
        room_map    = self.room_map
        noon_slot   = self.noon_slot
        eve_slot    = self.eve_slot
        total_slots = self.total_slots
        is_pe       = self._is_pe
        sec_stu     = self._sec_students
        last_day    = self._last_day
        lws         = self.lunch_window_start  # 10am
        lwe         = self.lunch_window_end    # 2pm

        for i, g in enumerate(genes):

            # ── HC-22 / HC-21: Room Availability & Suitability ──────────────
            if not g.is_fixed:
                r = room_map.get(g.room_id)
                if r:
                    if r['status'] != 'Available':
                        p = pen['ROOM_AVAILABILITY']
                        if p:
                            penalty += p; hard_conflicts += 1; conflicts.add(i)

                    if g.gene_type == 'Lab' and 'Computer Lab' not in r.get('capabilities', ''):
                        p = pen['ROOM_SUITABILITY']
                        if p:
                            penalty += p; hard_conflicts += 1; conflicts.add(i)

                    if include_sc2:
                        students = sec_stu.get(g.section_id, 0)
                        cap      = r.get('capacity', 9999)
                        if cap < students:
                            p = pen['ROOM_CAPACITY_PROPORTIONAL']
                            if p:
                                penalty += p; soft_score += p
                                if pen_type.get('ROOM_CAPACITY_PROPORTIONAL', 'SC2') == 'SC1':
                                    sc1_violations += 1
                                else:
                                    sc2_violations += 1
                        # Room utilisation is tracked by ROOM_CAPACITY_PROPORTIONAL above;
                        # a separate hidden ROOM_UTIL penalty was removed because it was
                        # not a configurable constraint and inflated SC-II vs Constraint Checker.

            # ── HC-23: Operating Hours ────────────────────────────────────────
            if g.start_idx < 0 or g.end_idx > total_slots:
                p = pen['OPERATING_HOURS']
                if p:
                    penalty += p; hard_conflicts += 1; conflicts.add(i)

            # ── HC-17/18: Faculty Availability Days ───────────────────────────
            if g.faculty_id and g.faculty_id not in self.multi_assignment_faculty:
                avail = self._fac_avail_days.get(g.faculty_id)
                if avail and g.day_idx not in avail:
                    p = pen.get('FACULTY_AVAILABILITY', 0)
                    if p:
                        penalty += p; hard_conflicts += 1; conflicts.add(i)

            # ── HC-03 / HC-14: Global & Section Day Restriction ──────────────
            # GA only uses days in self.days (built from allowed_days), so this
            # is structurally guaranteed, but register any out-of-range day_idx.
            if not (0 <= g.day_idx < len(self.days)):
                p = pen.get('GLOBAL_DAY_RESTRICTION', 0) or pen.get('SECTION_DAY_RESTRICTIONS', 0)
                if p:
                    penalty += p; hard_conflicts += 1; conflicts.add(i)

            # ── Blocked Time Slots (always enforced) ─────────────────────────
            if self._blocked_bitmasks:
                _day_blocked = self._blocked_bitmasks.get(g.day_idx, 0)
                if _day_blocked and (g.bitmask & _day_blocked):
                    penalty += HC_PENALTY; hard_conflicts += 1; conflicts.add(i)

            # ── HC-08 / HC-09 / HC-10 / HC-11: Strict Duration ───────────────
            # Skip for split genes (locked_day >= 0): their duration is set by the admin's
            # Day Split configuration, not derived from course metadata. HC-29 already ensures
            # split genes stay on their designated day. Skipping here allows 3+3 splits of a
            # 6-hour lab to each have 3-hour genes without triggering a permanent HC violation.
            if not g.is_fixed and getattr(g, 'locked_day', -1) < 0:
                _exp_dur = self._expected_duration.get((g.course_id, g.gene_type))
                if _exp_dur and g.duration_slots != _exp_dur:
                    if g.gene_type == 'Lec':
                        _p_dur = pen.get('STRICT_LEC_DURATION', 0)
                    elif g.gene_type == 'Lab':
                        _p_dur = pen.get('STRICT_LAB_DURATION', 0)
                    else:  # Async covers HC-10 (async lec) + HC-11 (async lab) combined
                        _p_dur = pen.get('STRICT_ASYNC_LEC_DUR', 0) or pen.get('STRICT_ASYNC_LAB_DUR', 0)
                    if _p_dur:
                        penalty += _p_dur; hard_conflicts += 1; conflicts.add(i)

            # ── HC-24: Hourly Alignment ───────────────────────────────────────
            # Each slot = 30 min, so every start_idx is always on a half-hour
            # boundary; check is trivially satisfied but explicitly covered.
            # start_minutes = start_hour*60 + start_idx*30  → always % 30 == 0
            # Only trigger if a gene somehow has a fractional slot (should never occur).

            # ── HC-28: Lecture Slot Alignment (Div4) ─────────────────────────
            # When div4 is active (≤5 long-lec genes), Lec genes in lecture-only
            # rooms must start on div4 slots (7AM, 9AM, 11AM, 1PM, 3PM, 5PM).
            # 3-hour lectures (duration_slots >= 6) are exempt — they're routed
            # to lab rooms where even-only applies.
            if (self._use_div4_for_lec
                    and not g.is_fixed
                    and g.gene_type == 'Lec'
                    and g.duration_slots < 6
                    and g.room_id in self._lec_room_set
                    and g.start_idx % 4 != 0):
                p = pen.get('LECTURE_SLOT_ALIGNMENT', 0)
                if p:
                    penalty += p; hard_conflicts += 1; conflicts.add(i)

            # ── HC-29: Faculty Day Split ──────────────────────────────────────
            # If gene has a locked_day, it must be placed on that day.
            _ld = getattr(g, 'locked_day', -1)
            if _ld >= 0 and g.day_idx != _ld and not g.is_fixed:
                p = pen.get('FACULTY_DAY_SPLIT', 0)
                if p:
                    penalty += p; hard_conflicts += 1; conflicts.add(i)

            if not hard_only:
                # ── SC-II-06: Evening Avoidance (SC2 — skip in SC-I phase) ───
                if include_sc2 and g.start_idx >= self.seven_pm_slot:
                    p = pen['EVENING_AVOIDANCE']
                    if p:
                        penalty += p; soft_score += p
                        if pen_type.get('EVENING_AVOIDANCE', 'SC2') == 'SC1':
                            sc1_violations += 1
                        else:
                            sc2_violations += 1

                # ── PE / Async soft constraints (SC1 — always in soft phases) ─
                if is_pe.get(g.course_id):
                    if g.start_idx >= noon_slot:
                        p = pen['PE_MORNING_PLACEMENT']
                        if p:
                            penalty += p; soft_score += p
                            if pen_type.get('PE_MORNING_PLACEMENT', 'SC1') == 'SC1':
                                sc1_violations += 1
                            else:
                                sc2_violations += 1
                    if g.day_idx > 2:
                        p = pen['PE_EARLY_WEEK']
                        if p:
                            penalty += p; soft_score += p
                            if pen_type.get('PE_EARLY_WEEK', 'SC1') == 'SC1':
                                sc1_violations += 1
                            else:
                                sc2_violations += 1
                elif g.gene_type == 'Async':
                    if g.day_idx != 0 and g.day_idx != last_day:
                        p = pen['ASYNC_STRATEGIC_PLACEMENT']
                        if p:
                            penalty += p; soft_score += p
                            if pen_type.get('ASYNC_STRATEGIC_PLACEMENT', 'SC1') == 'SC1':
                                sc1_violations += 1
                            else:
                                sc2_violations += 1

            # Track Lec/Lab for sequence (HC-04) and proximity (SC-I-01/03) checks
            if g.gene_type in ('Lec', 'Lab'):
                lc_key = (g.section_id, g.course_id)
                if lc_key not in sec_course_genes:
                    sec_course_genes[lc_key] = {}
                sec_course_genes[lc_key][g.gene_type] = (g, i)

            # ── Inline bitmask overlap detection (HC-12/13/16) + build usage maps ──
            # Bitmask approach: O(1) check via bitwise AND instead of sort+scan.
            # Lists are still maintained for HC-15/19/27 and lunch break checks.
            _mask = g.bitmask
            _d    = g.day_idx

            # Room overlap (HC-12 / HC-16)
            if g.room_id not in self.multi_assignment_rooms:
                _rkey = (g.room_id, _d)
                if (room_bits[_rkey] & _mask) != 0:
                    penalty += HC_PENALTY; hard_conflicts += 1
                    if not g.is_fixed:
                        conflicts.add(i)
                    for _ps, _pe, _pi in room_use[_rkey]:
                        if _ps < g.end_idx and _pe > g.start_idx:
                            if not genes[_pi].is_fixed:
                                conflicts.add(_pi)
                room_bits[_rkey] |= _mask

            # Faculty overlap (HC-13)
            if g.faculty_id and g.faculty_id not in self.multi_assignment_faculty:
                _fkey = (g.faculty_id, _d)
                if (fac_bits[_fkey] & _mask) != 0:
                    penalty += HC_PENALTY; hard_conflicts += 1
                    if not g.is_fixed:
                        conflicts.add(i)
                    for _ps, _pe, _pi in fac_use[_fkey]:
                        if _ps < g.end_idx and _pe > g.start_idx:
                            if not genes[_pi].is_fixed:
                                conflicts.add(_pi)
                fac_bits[_fkey] |= _mask

            # Section overlap (HC-16)
            _skey = (g.section_id, _d)
            if (sec_bits[_skey] & _mask) != 0:
                penalty += HC_PENALTY; hard_conflicts += 1
                if not g.is_fixed:
                    conflicts.add(i)
                for _ps, _pe, _pi in sec_use[_skey]:
                    if _ps < g.end_idx and _pe > g.start_idx:
                        if not genes[_pi].is_fixed:
                            conflicts.add(_pi)
            sec_bits[_skey] |= _mask

            # Append to lists for HC-15/19/27 and lunch break
            room_use[(g.room_id,    _d)].append((g.start_idx, g.end_idx, i))
            if g.faculty_id:
                fac_use[(g.faculty_id, _d)].append((g.start_idx, g.end_idx, i))
            sec_use[(g.section_id,  _d)].append((g.start_idx, g.end_idx, i))

        if include_sc2:
            # ── SC-II-04: Lunch Break (SC2 — skip in SC-I phase) ─────────────
            # Each section AND faculty must have ≥1 free hour (2 consecutive
            # slots) in the 10am–2pm window on each day they have classes.
            p_lb = pen.get('LUNCH_BREAK', 0)
            if p_lb:
                lb_type_is_sc1 = pen_type.get('LUNCH_BREAK', 'SC2') == 'SC1'
                for (_, day_idx), slots in sec_use.items():
                    occ = set()
                    for start, end, _i in slots:
                        for s in range(max(start, lws), min(end, lwe)):
                            occ.add(s)
                    if occ and not any(s not in occ and (s + 1) not in occ
                                       for s in range(lws, lwe - 1)):
                        penalty += p_lb; soft_score += p_lb
                        if lb_type_is_sc1:
                            sc1_violations += 1
                        else:
                            sc2_violations += 1
                for (_, day_idx), slots in fac_use.items():
                    occ = set()
                    for start, end, _i in slots:
                        for s in range(max(start, lws), min(end, lwe)):
                            occ.add(s)
                    if occ and not any(s not in occ and (s + 1) not in occ
                                       for s in range(lws, lwe - 1)):
                        penalty += p_lb; soft_score += p_lb
                        if lb_type_is_sc1:
                            sc1_violations += 1
                        else:
                            sc2_violations += 1

        if not hard_only:
            # ── SC-I-01 & SC-I-03: Lec-Lab weekly distribution & proximity ───
            for type_genes in sec_course_genes.values():
                lec_entry = type_genes.get('Lec')
                lab_entry = type_genes.get('Lab')
                if not (lec_entry and lab_entry):
                    continue
                lec_g, _ = lec_entry
                lab_g, _ = lab_entry
                if lab_g.day_idx < lec_g.day_idx:
                    p = pen['LEC_LAB_WEEKLY_DIST']
                    if p:
                        penalty += p; soft_score += p
                        if pen_type.get('LEC_LAB_WEEKLY_DIST', 'SC1') == 'SC1':
                            sc1_violations += 1
                        else:
                            sc2_violations += 1
                if abs(lec_g.day_idx - lab_g.day_idx) > 3:
                    p = pen['LEC_LAB_PROXIMITY']
                    if p:
                        penalty += p; soft_score += p
                        if pen_type.get('LEC_LAB_PROXIMITY', 'SC1') == 'SC1':
                            sc1_violations += 1
                        else:
                            sc2_violations += 1

        # ── Overlap checks (HC-12/13/16) are done inline via bitmasks above ───
        # (check_overlap removed — replaced by inline bitmask detection in gene loop)

        # ── HC-27: Early Start Enforcement ───────────────────────────────────
        # First class in each room on each day must start within 1 hr of system start.
        p_ese = pen.get('EARLY_START_ENFORCEMENT', 0)
        if p_ese:
            mfs = self._max_first_slot   # slot 1 = start+30min; slot 2+ = violation
            for (room_id, day_idx), slots in room_use.items():
                first_start, _, first_idx = min(slots, key=lambda x: x[0])
                if first_start > mfs and not genes[first_idx].is_fixed:
                    penalty += p_ese; hard_conflicts += 1; conflicts.add(first_idx)

        # ── HC-25: Complete Course Scheduling ────────────────────────────────
        # NOTE: Excluded from GA fitness — missing pairs have no gene index to add
        # to conflicting_indices, so violations are irresolvable by _hard_conflict_repair.
        # HC-25 is still fully checked by the post-generation constraint checker.

        # ── HC-04: Lec-Lab Sequence ──────────────────────────────────────────
        p_lls = pen.get('LEC_LAB_SEQUENCE', 0)
        if p_lls:
            for type_genes in sec_course_genes.values():
                lec_entry = type_genes.get('Lec')
                lab_entry = type_genes.get('Lab')
                if not (lec_entry and lab_entry):
                    continue
                lec_g, lec_i = lec_entry
                lab_g, lab_i = lab_entry
                if (lab_g.day_idx < lec_g.day_idx or
                        (lab_g.day_idx == lec_g.day_idx and
                         lab_g.start_idx < lec_g.start_idx)):
                    penalty += p_lls; hard_conflicts += 1
                    if not lab_g.is_fixed: conflicts.add(lab_i)

        # ── HC-15: Max Consecutive Student Load ──────────────────────────────
        p_mcs = pen.get('MAX_CONSECUTIVE_STUDENT', 0)
        if p_mcs:
            for key, slots in sec_use.items():
                sorted_slots = sorted(slots, key=lambda x: x[0])
                streak = 0; last_end = -1
                for start, end, idx in sorted_slots:
                    dur = end - start
                    if last_end < 0:
                        streak = dur
                    elif start <= last_end:
                        streak += dur
                    else:
                        streak = dur
                    last_end = max(last_end, end)
                    if streak > 12:  # 6 hours = 12 slots (30 min/slot)
                        penalty += p_mcs; hard_conflicts += 1
                        if not genes[idx].is_fixed: conflicts.add(idx)
                        break

        # ── HC-19: Max Consecutive Faculty Load ──────────────────────────────
        p_mcf = pen.get('MAX_CONSECUTIVE_FACULTY', 0)
        if p_mcf:
            for key, slots in fac_use.items():
                if key[0] in self.multi_assignment_faculty:
                    continue
                sorted_slots = sorted(slots, key=lambda x: x[0])
                streak = 0; last_end = -1
                for start, end, idx in sorted_slots:
                    dur = end - start
                    if last_end < 0:
                        streak = dur
                    elif start <= last_end:
                        streak += dur
                    else:
                        streak = dur
                    last_end = max(last_end, end)
                    if streak > 12:
                        penalty += p_mcf; hard_conflicts += 1
                        if not genes[idx].is_fixed: conflicts.add(idx)
                        break

        if include_sc2:
            # ── SC-II-01 / SC-II-02 / SC-II-05: Isolation & min daily load ──
            p_nil = pen.get('NO_ISOLATED_LECTURES', 0)
            p_nib = pen.get('NO_ISOLATED_LABS', 0)
            p_mdl = pen.get('MIN_DAILY_SECTION_LOAD', 0)
            if p_nil or p_nib or p_mdl:
                for (sec_id, day_idx), slots in sec_use.items():
                    n = len(slots)
                    if n < 2 and p_mdl:
                        penalty += p_mdl; soft_score += p_mdl
                        if pen_type.get('MIN_DAILY_SECTION_LOAD', 'SC2') == 'SC1':
                            sc1_violations += 1
                        else:
                            sc2_violations += 1
                    if n == 1:
                        _, _, idx = slots[0]
                        gt = genes[idx].gene_type
                        if gt == 'Lec' and p_nil:
                            penalty += p_nil; soft_score += p_nil
                            if pen_type.get('NO_ISOLATED_LECTURES', 'SC2') == 'SC1':
                                sc1_violations += 1
                            else:
                                sc2_violations += 1
                        elif gt == 'Lab' and p_nib:
                            penalty += p_nib; soft_score += p_nib
                            if pen_type.get('NO_ISOLATED_LABS', 'SC2') == 'SC1':
                                sc1_violations += 1
                            else:
                                sc2_violations += 1

        chromosome.fitness             = penalty
        chromosome.hard_conflicts      = hard_conflicts
        chromosome.soft_score          = soft_score
        chromosome.sc1_violations      = sc1_violations
        chromosome.sc2_violations      = sc2_violations
        chromosome.conflicting_indices = list(conflicts)
        return penalty

    # ------------------------------------------------------------------ #
    # MUTATION                                                             #
    # ------------------------------------------------------------------ #
    def proportional_mutate(self, chromosome):
        """Mutate all hard-conflicting genes; otherwise randomly improve soft violations."""
        targets = list(set(chromosome.conflicting_indices))

        if not targets:
            soft_targets = self._find_soft_violation_indices(chromosome)
            _occ_r, _occ_f, _occ_s = self._build_occ_sets(chromosome.genes)
            _lec_fac = {(g.section_id, g.course_id): g.faculty_id
                        for g in chromosome.genes if g.gene_type == 'Lec' and g.faculty_id is not None}
            if soft_targets and random.random() < 0.40:
                idx = random.choice(soft_targets)
                gene = chromosome.genes[idx]
                if not gene.is_fixed:
                    self._remove_from_occ(gene, _occ_r, _occ_f, _occ_s)
                    _pref = _lec_fac.get((gene.section_id, gene.course_id)) if gene.gene_type == 'Lab' else None
                    self.randomize_gene_fast(gene, _occ_r, _occ_f, _occ_s, preferred_faculty=_pref)
                    self._add_to_occ(gene, _occ_r, _occ_f, _occ_s)
            elif random.random() < 0.15:
                idx = random.randint(0, len(chromosome.genes) - 1)
                gene = chromosome.genes[idx]
                if not gene.is_fixed:
                    self._remove_from_occ(gene, _occ_r, _occ_f, _occ_s)
                    _pref = _lec_fac.get((gene.section_id, gene.course_id)) if gene.gene_type == 'Lab' else None
                    self.randomize_gene_fast(gene, _occ_r, _occ_f, _occ_s, preferred_faculty=_pref)
                    self._add_to_occ(gene, _occ_r, _occ_f, _occ_s)
            return

        random.shuffle(targets)
        count = len(targets)  # Mutate ALL hard-conflicting genes every time

        # Build occ sets ONCE for all batch mutations
        occ_room, occ_fac, occ_sec = self._build_occ_sets(chromosome.genes)

        # Build Lec day lookup for HC-04: Lab must not precede its sibling Lec
        lec_lookup = {}  # {(section_id, course_id): (day_idx, start_idx)}
        lec_fac_lookup = {}  # {(section_id, course_id): faculty_id} — for Lab pairing
        for g in chromosome.genes:
            if g.gene_type == 'Lec':
                lec_lookup[(g.section_id, g.course_id)] = (g.day_idx, g.start_idx)
                if g.faculty_id is not None:
                    lec_fac_lookup[(g.section_id, g.course_id)] = g.faculty_id

        for _ in range(count):
            if not targets:
                break
            idx  = targets.pop()
            gene = chromosome.genes[idx]
            if gene.is_fixed:
                continue
            self._remove_from_occ(gene, occ_room, occ_fac, occ_sec)

            min_day = 0
            min_start_sd = -1
            pref_fac = None
            if gene.gene_type == 'Lab':
                lec_info = lec_lookup.get((gene.section_id, gene.course_id))
                if lec_info:
                    min_day, lec_start = lec_info
                    min_start_sd = lec_start - 1
                pref_fac = lec_fac_lookup.get((gene.section_id, gene.course_id))

            self.randomize_gene_fast(gene, occ_room, occ_fac, occ_sec, min_day, min_start_sd,
                                     preferred_faculty=pref_fac)
            self._add_to_occ(gene, occ_room, occ_fac, occ_sec)

            # Update lookup if we just relocated a Lec gene
            if gene.gene_type == 'Lec':
                lec_lookup[(gene.section_id, gene.course_id)] = (gene.day_idx, gene.start_idx)
                if gene.faculty_id is not None:
                    lec_fac_lookup[(gene.section_id, gene.course_id)] = gene.faculty_id

    def _guided_soft_mutate(self, chromosome):
        """
        Phase 3 (SC-II) targeted mutation: find soft-violating genes and mutate
        a batch of them, keeping HC=0.

        Unlike proportional_mutate (which targets 1 gene at ~40% chance),
        this mutates 30–60% of all soft violators (2–8 genes) per call.
        This creates stronger pressure on soft constraints without introducing
        hard conflicts (occ-set-aware placement).

        Safe to call only when chromosome.hard_conflicts == 0.
        """
        if chromosome.hard_conflicts > 0:
            return

        targets = self._find_soft_violation_indices(chromosome)
        if not targets:
            return

        # Mutate 40-70% of soft violators, capped at 12 genes per call (was 30-60%, cap 8)
        n_mutate = max(1, min(12, int(len(targets) * random.uniform(0.40, 0.70))))
        selected = random.sample(targets, min(n_mutate, len(targets)))

        # Build occ sets once for the batch
        occ_room, occ_fac, occ_sec = self._build_occ_sets(chromosome.genes)
        lec_lookup     = {}
        lec_fac_lookup = {}
        for g in chromosome.genes:
            if g.gene_type == 'Lec':
                lec_lookup[(g.section_id, g.course_id)] = (g.day_idx, g.start_idx)
                if g.faculty_id is not None:
                    lec_fac_lookup[(g.section_id, g.course_id)] = g.faculty_id

        for idx in selected:
            gene = chromosome.genes[idx]
            if gene.is_fixed:
                continue

            self._remove_from_occ(gene, occ_room, occ_fac, occ_sec)

            min_day = 0; min_start_sd = -1; pref_fac = None
            if gene.gene_type == 'Lab':
                lec_info = lec_lookup.get((gene.section_id, gene.course_id))
                if lec_info:
                    min_day, lec_start = lec_info
                    min_start_sd = lec_start - 1
                pref_fac = lec_fac_lookup.get((gene.section_id, gene.course_id))

            self.randomize_gene_fast(gene, occ_room, occ_fac, occ_sec,
                                     min_day, min_start_sd, preferred_faculty=pref_fac)
            self._add_to_occ(gene, occ_room, occ_fac, occ_sec)

            if gene.gene_type == 'Lec':
                lec_lookup[(gene.section_id, gene.course_id)] = (gene.day_idx, gene.start_idx)
                if gene.faculty_id is not None:
                    lec_fac_lookup[(gene.section_id, gene.course_id)] = gene.faculty_id

    # ------------------------------------------------------------------ #
    # PARALLEL CHROMOSOME EVALUATION                                      #
    # ------------------------------------------------------------------ #
    def _eval_batch(self, chromosomes, hard_only=False, sc1_only=False):
        """
        Evaluate a list of chromosomes using a ThreadPoolExecutor.

        Thread-safety: calculate_fitness() reads only from self.* caches
        (all read-only after __init__) and writes only to individual chromosome
        attributes — no shared mutable state between threads.

        Small batches (<= 6) are evaluated sequentially to avoid thread
        overhead exceeding the compute cost.

        Note: Python's GIL limits pure-Python parallelism, but the thread
        pool still benefits from GIL-yield interleaving during the tight inner
        loops of calculate_fitness(), giving a practical 15-35% wall-clock
        improvement on typical population sizes (40–150 chromosomes).
        """
        n = len(chromosomes)
        if n == 0:
            return
        if n <= 6:
            for c in chromosomes:
                self.calculate_fitness(c, hard_only=hard_only, sc1_only=sc1_only)
            return

        def _eval(c):
            self.calculate_fitness(c, hard_only=hard_only, sc1_only=sc1_only)

        with ThreadPoolExecutor(max_workers=min(_N_WORKERS, n)) as executor:
            list(executor.map(_eval, chromosomes))

    def randomize_gene_fast(self, gene, occ_room, occ_fac, occ_sec,
                            min_day=0, min_start_same_day=-1, use_warmth=False,
                            preferred_faculty=None, preferred_room=None):
        """Place gene using pre-built occ sets (caller must remove gene first).
        Every 3rd attempt also tries a different faculty to escape faculty conflicts.
        min_day: gene must be placed on day >= min_day (HC-04: Lab after Lec day).
        min_start_same_day: if placed on exactly min_day, start must be > this value
                            (HC-04: Lab start >= Lec start when on the same day).
        use_warmth: if True, passes occ_room to _best_room() for warmth-aware selection.
        preferred_faculty: if provided (for Lab genes), use this faculty_id instead of
                           random — ensures Lab uses same faculty as sibling Lec gene.

        Room & slot priority for Lecture genes:
          Phase 1 (0-34):  lecture-only rooms, daytime (7am-7pm), div4 or even slots
          Phase 2 (35-44): lecture-only rooms, evening (7pm-9pm) — last resort in lec rooms
          Phase 3 (45-54): lab rooms (fallback when lecture rooms full)
          Phase 4 (55-60): fully random fallback
        3-hour Lec and Lab genes go directly to lab rooms across all phases."""
        slots_needed = gene.duration_slots
        _fa_pref = self.fa_map.get((gene.course_id, gene.section_id))
        _fa_pref = _fa_pref if (_fa_pref is not None and _fa_pref in self.faculty_ids) else None
        if preferred_faculty is None and _fa_pref is not None:
            preferred_faculty = _fa_pref        # treat fa_map assignment like Lab pairing
        orig_fac     = preferred_faculty if preferred_faculty is not None else gene.faculty_id
        # Restrict day selection to faculty's available days (HC-18 prevention at placement time)
        _pref_avail_days = None
        if preferred_faculty is not None and preferred_faculty not in self.multi_assignment_faculty:
            _pref_avail_days = self._fac_avail_days.get(preferred_faculty)
        sec_id       = gene.section_id
        days_count   = len(self.days)
        total_slots  = self.total_slots
        faculty_ids  = self.faculty_ids
        gtype        = gene.gene_type
        # Dept-filtered faculty pool: T.B.A./multi-assignment always eligible
        _cdept_rf = _norm_dept(self.course_map.get(gene.course_id, {}).get('department', ''))
        if _cdept_rf and preferred_faculty is None:
            _dept_fac_ids = [fid for fid in faculty_ids
                             if fid in self.multi_assignment_faculty
                             or self._fac_dept.get(fid, '') == _cdept_rf
                             or self._fac_dept.get(fid, '') == '']
            _dept_fac_ids = _dept_fac_ids or faculty_ids
        else:
            _dept_fac_ids = faculty_ids

        # ── Determine room pools and slot constraints ──────────────────────────
        is_three_hr_lec = (gtype == 'Lec' and slots_needed >= 6)
        dept = self.course_map.get(gene.course_id, {}).get('department', '')

        if gtype == 'Lab' or is_three_hr_lec:
            primary_rooms  = self._dept_rooms_lab.get(dept) or self._valid_rooms_lab
            fallback_rooms = self._dept_rooms_lec_only.get(dept) or self._valid_rooms_lec_only
            use_div4_pri   = False  # even slots only for lab rooms
        elif gtype == 'Lec':
            primary_rooms  = self._dept_rooms_lec_only.get(dept) or self._valid_rooms_lec_only
            fallback_rooms = self._valid_rooms_lab
            use_div4_pri   = self._use_div4_for_lec
        else:  # Async
            primary_rooms  = self._dept_rooms_lec.get(dept) or self._valid_rooms_lec
            fallback_rooms = primary_rooms
            use_div4_pri   = False

        if not primary_rooms:
            primary_rooms = self._valid_rooms_lec
        if not fallback_rooms:
            fallback_rooms = primary_rooms

        # Precompute valid starts for fallback line (even slots, full range)
        _even_starts = [s for s in range(0, max(1, total_slots - slots_needed + 1)) if s % 2 == 0] or \
                       list(range(0, max(1, total_slots - slots_needed + 1)))

        _locked_day = getattr(gene, 'locked_day', -1)
        # _use_preferred_room: True when a real dept room is provided by a split sibling
        _use_preferred_room = (preferred_room is not None
                               and preferred_room not in self.tba_room_ids
                               and preferred_room in primary_rooms)

        for attempt in range(60):
            if _locked_day >= 0:
                day = _locked_day
            elif _pref_avail_days:
                _valid_days = [d for d in _pref_avail_days if d >= min_day]
                day = random.choice(_valid_days) if _valid_days else random.randint(min_day, days_count - 1)
            else:
                day = random.randint(min_day, days_count - 1)

            # Phase 1 (0-34): primary rooms, daytime (7am–7pm)
            if attempt < 35:
                start = self._smart_start(slots_needed, allow_evening=False,
                                          use_div4=use_div4_pri, even_only=True)
                _occ  = occ_room if use_warmth else None
                # Prefer sibling's room (split gene pairing) for all Phase 1 attempts
                if _use_preferred_room:
                    room = preferred_room
                else:
                    _b = self._best_room(gtype, sec_id, _occ, rooms_override=primary_rooms)
                    if _b:
                        room = _b
                    elif primary_rooms:
                        # Room Compaction: First-Fit instead of random
                        mask = ((1 << slots_needed) - 1) << start
                        room = primary_rooms[0]
                        for r in primary_rooms:
                            if (occ_room.get((r, day), 0) & mask) == 0:
                                room = r
                                break
                    else:
                        room = gene.room_id

            # Phase 2 (35-44): primary rooms, allow evening (7pm-9pm last resort)
            elif attempt < 45:
                start = self._smart_start(slots_needed, allow_evening=True,
                                          use_div4=use_div4_pri, even_only=True)
                _occ  = occ_room if use_warmth else None
                if _use_preferred_room:
                    room = preferred_room
                else:
                    _b = self._best_room(gtype, sec_id, _occ, rooms_override=primary_rooms)
                    if _b:
                        room = _b
                    elif primary_rooms:
                        mask = ((1 << slots_needed) - 1) << start
                        room = primary_rooms[0]
                        for r in primary_rooms:
                            if (occ_room.get((r, day), 0) & mask) == 0:
                                room = r
                                break
                    else:
                        room = gene.room_id

            # Phase 3 (45-54): fallback rooms (lec rooms for Lec, lec rooms for Lab)
            elif attempt < 55:
                start = self._smart_start(slots_needed, allow_evening=False,
                                          use_div4=False, even_only=True)
                if fallback_rooms:
                    mask = ((1 << slots_needed) - 1) << start
                    room = fallback_rooms[0]
                    for r in fallback_rooms:
                        if (occ_room.get((r, day), 0) & mask) == 0:
                            room = r
                            break
                else:
                    room = gene.room_id

            # Phase 4 (55-60): purely random physical fallback (no TBA)
            else:
                start = random.choice(_even_starts)
                valid_rooms = list(self._get_rooms_for_gene(gene))
                phys = [r for r in valid_rooms if r not in self.tba_room_ids]
                if phys:
                    mask = ((1 << slots_needed) - 1) << start
                    room = phys[0]
                    for r in phys:
                        if (occ_room.get((r, day), 0) & mask) == 0:
                            room = r
                            break
                else:
                    room = gene.room_id

            end = start + slots_needed

            # HC-04: if same day as Lec, Lab must not start before Lec
            if day == min_day and min_start_same_day >= 0 and start <= min_start_same_day:
                continue

            # Every 3 attempts try a different faculty — faster escape from faculty conflicts.
            # If preferred_faculty is set (Lab pairing), keep it locked; only try random after many fails.
            if preferred_faculty is not None:
                fac_id = preferred_faculty if (attempt < 45 or not _dept_fac_ids) else random.choice(_dept_fac_ids)
            else:
                fac_id = orig_fac if (attempt % 3 != 2 or not _dept_fac_ids) else random.choice(_dept_fac_ids)

            mask = ((1 << slots_needed) - 1) << start
            conflict = False

            # Check room, faculty, and section occupancy. Skip checks for multi-assignment rooms/faculty.
            if ((room not in self.multi_assignment_rooms and (occ_room.get((room, day), 0) & mask) != 0) or
                (fac_id is not None and fac_id not in self.multi_assignment_faculty and (occ_fac.get((fac_id, day), 0) & mask) != 0) or
                (occ_sec.get((sec_id, day), 0) & mask) != 0):
                conflict = True

            if not conflict:
                gene.day_idx    = day
                gene.start_idx  = start
                gene.end_idx    = end
                gene.room_id    = room
                gene.faculty_id = fac_id   # persist faculty change
                gene.bitmask    = mask
                return True

        # Fallback: all 60 attempts failed — place randomly and let repair handle it.
        # Ignore min_day here so infeasible last-day situations don't create guaranteed conflicts.
        valid_rooms_fb = list(self._get_rooms_for_gene(gene))
        phys_fb = [r for r in valid_rooms_fb if r not in self.tba_room_ids]
        tbas_fb = [r for r in valid_rooms_fb if r in self.tba_room_ids]
        for _t_rid in self.tba_room_ids:
            if _t_rid not in tbas_fb:
                tbas_fb.append(_t_rid)
        
        _ld_fb = getattr(gene, 'locked_day', -1)
        if _ld_fb >= 0:
            gene.day_idx = _ld_fb
        elif _pref_avail_days:
            gene.day_idx = random.choice(sorted(_pref_avail_days))
        else:
            gene.day_idx = random.randint(0, days_count - 1)
        gene.start_idx = random.choice(_even_starts)
        gene.end_idx   = gene.start_idx + slots_needed
        
        mask = ((1 << slots_needed) - 1) << gene.start_idx
        picked_room = None
        if phys_fb:
            picked_room = phys_fb[0]
            for r in phys_fb:
                if (occ_room.get((r, gene.day_idx), 0) & mask) == 0:
                    picked_room = r
                    break
        gene.room_id = picked_room if picked_room else (random.choice(tbas_fb) if tbas_fb else gene.room_id)
        
        if preferred_faculty is not None:
            gene.faculty_id = preferred_faculty  # keep Lab paired with Lec faculty
        elif _dept_fac_ids and random.random() < 0.5:
            gene.faculty_id = random.choice(_dept_fac_ids)
        gene.bitmask = mask
        return False

    def randomize_gene(self, gene, all_genes):
        others = [other for other in all_genes if other is not gene]
        occ_room, occ_fac, occ_sec = self._build_occ_sets(others)
        pref_fac = None
        if gene.gene_type == 'Lab':
            for g in others:
                if (g.gene_type == 'Lec' and g.section_id == gene.section_id
                        and g.course_id == gene.course_id and g.faculty_id is not None):
                    pref_fac = g.faculty_id
                    break
        self.randomize_gene_fast(gene, occ_room, occ_fac, occ_sec, preferred_faculty=pref_fac)

    # ------------------------------------------------------------------ #
    # SEED CHROMOSOME — build from saved DB records                      #
    # ------------------------------------------------------------------ #
    def _build_seed_chromosome(self, records):
        """
        Convert saved ScheduledClass DB records (dicts with day/start_time/end_time/…)
        into a Chromosome.  Records for unknown courses / out-of-range times are
        skipped; any missing loads (new courses, extra components) are filled in
        using the same greedy logic as create_genome().
        """
        genes    = [self._copy_gene(g) for g in self.fixed_genes]
        occ_room, occ_fac, occ_sec = self._build_occ_sets(genes)
        for g in genes:
            self._add_to_occ(g, occ_room, occ_fac, occ_sec)

        seed_count = defaultdict(int)   # (sec_id, course_id) → genes loaded from seed

        # Pre-compute max genes per (section_id, course_id) so we never create
        # more genes than the current curriculum requires (prevents length mismatch
        # with create_genome() chromosomes which would crash crossover).
        _expected_loads = {}
        for _sec in self.sections:
            _sid = _sec['id']
            for _cid in _sec['course_ids']:
                _c = self.course_map.get(_cid)
                if not _c:
                    continue
                _lec = _c.get('synchronous_lec_hours', 0) or _c.get('lec_units', 0)
                _lab = _c.get('synchronous_lab_hours', 0) or _c.get('lab_units', 0)
                _asy = (_c.get('asynchronous_lec_hours', 0) +
                        _c.get('asynchronous_lab_hours', 0))
                _n = (1 if _lec > 0 else 0) + (1 if _lab > 0 else 0) + (1 if _asy > 0 else 0)
                if _n > 0:
                    _expected_loads[(_sid, _cid)] = _n

        for rec in records:
            day = rec.get('day', '')
            if day not in self.day_map:
                continue
            try:
                s_h, s_m = map(int, str(rec['start_time']).split(':'))
                e_h, e_m = map(int, str(rec['end_time']).split(':'))
                start_slot = (s_h - self.start_hour) * 2 + (1 if s_m >= 30 else 0)
                end_slot   = (e_h - self.start_hour) * 2 + (1 if e_m >= 30 else 0)
                duration   = end_slot - start_slot
            except Exception:
                continue

            if duration <= 0 or start_slot < 0 or end_slot > self.total_slots:
                continue

            course_id  = rec.get('course_id')
            section_id = rec.get('section_id')
            room_id    = rec.get('room_id')
            faculty_id = rec.get('faculty_id')

            if course_id not in self.course_map:
                continue
            if section_id not in self.section_map:
                continue

            # Skip genes for (section, course) combos not in current curriculum,
            # or that already hit the expected gene count for that combo.
            _combo = (section_id, course_id)
            if _combo not in _expected_loads:
                continue
            if seed_count[_combo] >= _expected_loads[_combo]:
                continue

            # Infer gene_type: Computer Lab room → Lab, otherwise Lec
            # (Async uses same rooms as Lec; mis-labelling only skips one soft check)
            room = self.room_map.get(room_id)
            caps = room.get('capabilities', '') if room else ''
            gene_type = 'Lab' if 'Computer Lab' in caps else 'Lec'

            g = Gene(course_id, section_id, faculty_id, room_id,
                     self.day_map[day], start_slot, duration, gene_type, False)
            genes.append(g)
            self._add_to_occ(g, occ_room, occ_fac, occ_sec)
            seed_count[(section_id, course_id)] += 1

        # Build Lec-faculty map from already-seeded genes for Lab pairing in fill-in step
        _seed_lec_fac = {(g.section_id, g.course_id): g.faculty_id
                         for g in genes if g.gene_type == 'Lec' and g.faculty_id is not None}

        # Fill any missing loads (new courses / extra components not in saved schedule)
        for section in self.sections:
            sec_id = section['id']
            for course_id in section['course_ids']:
                # Skip pre-assigned genes
                if any(g.course_id == course_id and g.section_id == sec_id and g.is_fixed
                       for g in self.fixed_genes):
                    continue
                course = self.course_map.get(course_id)
                if not course:
                    continue

                lec     = course.get('synchronous_lec_hours', 0) or course.get('lec_units', 0)
                lab     = course.get('synchronous_lab_hours', 0) or course.get('lab_units', 0)
                async_h = (course.get('asynchronous_lec_hours', 0) +
                           course.get('asynchronous_lab_hours', 0))
                loads = []
                if lec     > 0: loads.append((lec,     'Lec'))
                if lab     > 0: loads.append((lab,     'Lab'))
                if async_h > 0: loads.append((async_h, 'Async'))

                missing_n = max(0, len(loads) - seed_count[(sec_id, course_id)])
                if missing_n == 0:
                    continue

                # Fill from the tail of the loads list
                for hours, gtype in loads[-missing_n:]:
                    slots = int(hours * 2)
                    fac   = random.choice(self.faculty_ids) if self.faculty_ids else None
                    vr    = self.get_valid_rooms(gtype)
                    g     = Gene(course_id, sec_id, fac, vr[0] if vr else None,
                                 0, 0, slots, gtype, False)
                    _pref_fac_fill = _seed_lec_fac.get((sec_id, course_id)) if gtype == 'Lab' else None
                    self.randomize_gene_fast(g, occ_room, occ_fac, occ_sec, preferred_faculty=_pref_fac_fill)
                    _mask = g.bitmask
                    placed_ok = not (
                        (occ_room.get((g.room_id, g.day_idx), 0) & _mask) or
                        (g.faculty_id is not None and occ_fac.get((g.faculty_id, g.day_idx), 0) & _mask) or
                        (occ_sec.get((g.section_id, g.day_idx), 0) & _mask)
                    )
                    if not placed_ok:
                        self._exhaustive_place_gene(g, occ_room, occ_fac, occ_sec)
                    if gtype == 'Lec' and g.faculty_id is not None:
                        _seed_lec_fac[(sec_id, course_id)] = g.faculty_id
                    genes.append(g)
                    self._add_to_occ(g, occ_room, occ_fac, occ_sec)

        return Chromosome(genes)

    def _perturb_chromosome(self, base_chrom, fraction=0.15):
        """
        Lighter variant of _repair_chromosome: perturb only `fraction` of genes.
        Used to build diverse population variants around a seed chromosome.
        """
        nc = self._copy_chromosome(base_chrom)
        non_fixed = [i for i, g in enumerate(nc.genes) if not g.is_fixed]
        if not non_fixed:
            return nc
        perturb_count = max(1, int(len(non_fixed) * fraction))
        indices = random.sample(non_fixed, min(perturb_count, len(non_fixed)))
        occ_room, occ_fac, occ_sec = self._build_occ_sets(nc.genes)
        lec_lookup = {(g.section_id, g.course_id): (g.day_idx, g.start_idx)
                      for g in nc.genes if g.gene_type == 'Lec'}
        lec_fac_lookup = {(g.section_id, g.course_id): g.faculty_id
                          for g in nc.genes if g.gene_type == 'Lec' and g.faculty_id is not None}
        for idx in indices:
            gene = nc.genes[idx]
            self._remove_from_occ(gene, occ_room, occ_fac, occ_sec)
            min_day = 0; min_start_sd = -1; pref_fac = None
            if gene.gene_type == 'Lab':
                lec_info = lec_lookup.get((gene.section_id, gene.course_id))
                if lec_info:
                    min_day, lec_start = lec_info
                    min_start_sd = lec_start - 1
                pref_fac = lec_fac_lookup.get((gene.section_id, gene.course_id))
            self.randomize_gene_fast(gene, occ_room, occ_fac, occ_sec, min_day, min_start_sd,
                                     preferred_faculty=pref_fac)
            self._add_to_occ(gene, occ_room, occ_fac, occ_sec)
            if gene.gene_type == 'Lec':
                lec_lookup[(gene.section_id, gene.course_id)] = (gene.day_idx, gene.start_idx)
                if gene.faculty_id is not None:
                    lec_fac_lookup[(gene.section_id, gene.course_id)] = gene.faculty_id
        return nc

    # ------------------------------------------------------------------ #
    # REPAIR CHROMOSOME (fast stagnation recovery)                        #
    # ------------------------------------------------------------------ #
    def _repair_chromosome(self, base_chrom):
        """Perturb 1/3 of non-fixed genes — 3-5× faster than create_genome."""
        nc = self._copy_chromosome(base_chrom)
        non_fixed = [i for i, g in enumerate(nc.genes) if not g.is_fixed]
        if not non_fixed:
            return nc

        perturb_count = max(1, len(non_fixed) // 3)
        indices = random.sample(non_fixed, min(perturb_count, len(non_fixed)))

        occ_room, occ_fac, occ_sec = self._build_occ_sets(nc.genes)
        lec_lookup = {(g.section_id, g.course_id): (g.day_idx, g.start_idx)
                      for g in nc.genes if g.gene_type == 'Lec'}
        lec_fac_lookup = {(g.section_id, g.course_id): g.faculty_id
                          for g in nc.genes if g.gene_type == 'Lec' and g.faculty_id is not None}
        for idx in indices:
            gene = nc.genes[idx]
            self._remove_from_occ(gene, occ_room, occ_fac, occ_sec)
            min_day = 0; min_start_sd = -1; pref_fac = None
            if gene.gene_type == 'Lab':
                lec_info = lec_lookup.get((gene.section_id, gene.course_id))
                if lec_info:
                    min_day, lec_start = lec_info
                    min_start_sd = lec_start - 1
                pref_fac = lec_fac_lookup.get((gene.section_id, gene.course_id))
            self.randomize_gene_fast(gene, occ_room, occ_fac, occ_sec, min_day, min_start_sd,
                                     preferred_faculty=pref_fac)
            self._add_to_occ(gene, occ_room, occ_fac, occ_sec)
            if gene.gene_type == 'Lec':
                lec_lookup[(gene.section_id, gene.course_id)] = (gene.day_idx, gene.start_idx)
                if gene.faculty_id is not None:
                    lec_fac_lookup[(gene.section_id, gene.course_id)] = gene.faculty_id

        return nc

    # ------------------------------------------------------------------ #
    # LOCAL SEARCH REFINEMENT (Soft-Constraint Polishing)                #
    # ------------------------------------------------------------------ #
    def _local_search_refinement(self, chromosome, max_attempts=150):
        """
        Hill-climbing local search to polish soft constraints without breaking hard constraints.
        Searches same-day time shifts, room swaps, and full-day relocations to fix
        both per-gene and relational soft violations (isolation, proximity, daily load).
        """
        if chromosome.hard_conflicts > 0 or chromosome.soft_score == 0:
            return chromosome

        refined = self._copy_chromosome(chromosome)
        occ_room, occ_fac, occ_sec = self._build_occ_sets(refined.genes)

        # Get indices of genes causing soft penalties (now includes relational violations)
        violators = self._find_soft_violation_indices(refined)
        if not violators:
            return refined

        days_count  = len(self.days)
        total_slots = self.total_slots
        improved    = False
        attempts    = 0

        while violators and attempts < max_attempts:
            idx  = random.choice(violators)
            gene = refined.genes[idx]

            # Remove gene from occ so we can test new placements cleanly
            self._remove_from_occ(gene, occ_room, occ_fac, occ_sec)

            orig_day   = gene.day_idx
            orig_start = gene.start_idx
            orig_room  = gene.room_id
            duration   = gene.duration_slots
            _gene_locked_day = getattr(gene, 'locked_day', -1)

            best_gene_state  = (orig_day, orig_start, orig_room)
            best_local_score = self.calculate_fitness(refined, hard_only=False)

            # ── Build candidate search space ──────────────────────────────
            search_space = []
            valid_rooms = self.get_valid_rooms(gene.gene_type)

            # 1. Slide ±2 slots on the same day (same room)
            for shift in [-2, -1, 1, 2]:
                ns = orig_start + shift
                if 0 <= ns <= total_slots - duration:
                    search_space.append((orig_day, ns, orig_room))

            # 2. Alternative room, same time (fixes room utilisation violations)
            for new_room in random.sample(valid_rooms, min(3, len(valid_rooms))):
                if new_room != orig_room:
                    search_space.append((orig_day, orig_start, new_room))

            # 3. Relocate to a different day entirely (fixes isolation / proximity)
            #    Skip for split genes (locked_day must be respected — HC-29).
            if _gene_locked_day < 0:
                other_days = [d for d in range(days_count) if d != orig_day]
                for alt_day in random.sample(other_days, min(3, len(other_days))):
                    alt_start = self._smart_start(duration, allow_evening=False)
                    if 0 <= alt_start <= total_slots - duration:
                        search_space.append((alt_day, alt_start, orig_room))

            # ── Evaluate candidates with CORRECT bitmask-based conflict check ──
            found_better = False
            for (test_day, test_start, test_room) in search_space:
                test_end = test_start + duration
                mask = ((1 << duration) - 1) << test_start

                # P2-fix: use bitmask lookup (occ_room keys are (room_id, day_idx))
                conflict = (
                    (test_room not in self.multi_assignment_rooms and
                     (occ_room.get((test_room, test_day), 0) & mask) != 0) or
                    (gene.faculty_id is not None and
                     gene.faculty_id not in self.multi_assignment_faculty and
                     (occ_fac.get((gene.faculty_id, test_day), 0) & mask) != 0) or
                    (occ_sec.get((gene.section_id, test_day), 0) & mask) != 0
                )

                if not conflict:
                    gene.day_idx   = test_day
                    gene.start_idx = test_start
                    gene.end_idx   = test_end
                    gene.room_id   = test_room
                    gene.bitmask   = mask

                    self._add_to_occ(gene, occ_room, occ_fac, occ_sec)
                    new_score = self.calculate_fitness(refined, hard_only=False)
                    self._remove_from_occ(gene, occ_room, occ_fac, occ_sec)

                    if new_score < best_local_score:
                        best_local_score = new_score
                        best_gene_state  = (test_day, test_start, test_room)
                        found_better     = True

            # Apply best found state
            test_day, test_start, test_room = best_gene_state
            gene.day_idx   = test_day
            gene.start_idx = test_start
            gene.end_idx   = test_start + duration
            gene.room_id   = test_room
            gene.bitmask   = ((1 << duration) - 1) << test_start
            self._add_to_occ(gene, occ_room, occ_fac, occ_sec)

            if found_better:
                improved = True
                violators = self._find_soft_violation_indices(refined)

            attempts += 1

        if improved:
            self.calculate_fitness(refined, hard_only=False)
            return refined
        return chromosome

    # ------------------------------------------------------------------ #
    # FAST COPY HELPERS (avoid expensive copy.deepcopy)                   #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _copy_gene(g):
        ng = Gene.__new__(Gene)
        ng.course_id      = g.course_id
        ng.section_id     = g.section_id
        ng.faculty_id     = g.faculty_id
        ng.room_id        = g.room_id
        ng.day_idx        = g.day_idx
        ng.start_idx      = g.start_idx
        ng.duration_slots = g.duration_slots
        ng.end_idx        = g.end_idx
        ng.gene_type      = g.gene_type
        ng.is_fixed       = g.is_fixed
        ng.bitmask        = getattr(g, 'bitmask', ((1 << g.duration_slots) - 1) << g.start_idx)
        ng.locked_day     = getattr(g, 'locked_day', -1)
        return ng

    @staticmethod
    def _copy_chromosome(chrom):
        nc = Chromosome([GeneticScheduler._copy_gene(g) for g in chrom.genes])
        nc.fitness             = chrom.fitness
        nc.hard_conflicts      = chrom.hard_conflicts
        nc.soft_score          = chrom.soft_score
        nc.conflicting_indices = list(chrom.conflicting_indices)
        nc.rank                = chrom.rank
        nc.crowding_distance   = chrom.crowding_distance
        nc.sc1_violations      = chrom.sc1_violations
        nc.sc2_violations      = chrom.sc2_violations
        return nc

    # ------------------------------------------------------------------ #
    # CROSSOVER — greedy conflict-aware                                   #
    # ------------------------------------------------------------------ #
    def crossover(self, p1, p2):
        """
        Greedy conflict-aware crossover: genes are placed in random order;
        for each gene we try the p1 version first — if it conflicts with
        already-placed genes we try the p2 version; if both conflict we
        pick randomly (rare case, repair handles it).

        With both parents at HC=0 this almost always produces a 0-HC child:
        - At least one parent's version of each gene was placed in a slot
          that doesn't clash with the OTHER genes already committed.
        - No repair needed in the common case → dramatically faster per gen.
        Block crossover was worse because entire sections from different
        parents could compete for the same rooms at the same times,
        creating O(sections^2) cross-section conflicts.
        """
        child_genes = [None] * len(p1.genes)
        occ_room    = defaultdict(int)
        occ_fac     = defaultdict(int)
        occ_sec     = defaultdict(int)

        # Track Lec faculty so Lab siblings can be paired — same pattern as proportional_mutate
        lec_fac_lookup = {}  # {(section_id, course_id): faculty_id}

        # Fixed genes first
        for i, g in enumerate(p1.genes):
            if g.is_fixed:
                child_genes[i] = g
                self._add_to_occ(g, occ_room, occ_fac, occ_sec)
                if g.gene_type == 'Lec' and g.faculty_id is not None:
                    lec_fac_lookup[(g.section_id, g.course_id)] = g.faculty_id

        # Non-fixed genes in random order (prevents systematic bias)
        non_fixed = [i for i in range(len(p1.genes)) if not p1.genes[i].is_fixed]
        random.shuffle(non_fixed)

        p2g = p2.genes
        p2_len = len(p2g)
        for i in non_fixed:
            g1 = p1.genes[i]
            # Safety: p2 may have fewer genes than p1 (warm-start length mismatch)
            g2 = p2g[i] if i < p2_len else g1

            # Check if g1 is conflict-free with already-placed genes
            d1    = g1.day_idx
            mask1 = getattr(g1, 'bitmask', ((1 << g1.duration_slots) - 1) << g1.start_idx)
            g1_ok = not ((occ_room.get((g1.room_id, d1), 0) & mask1) or
                         (g1.faculty_id is not None and (occ_fac.get((g1.faculty_id, d1), 0) & mask1)) or
                         (occ_sec.get((g1.section_id, d1), 0) & mask1))

            if g1_ok:
                chosen = self._copy_gene(g1)
            else:
                # g1 conflicts — try g2
                d2    = g2.day_idx
                mask2 = getattr(g2, 'bitmask', ((1 << g2.duration_slots) - 1) << g2.start_idx)
                g2_ok = not ((occ_room.get((g2.room_id, d2), 0) & mask2) or
                             (g2.faculty_id is not None and (occ_fac.get((g2.faculty_id, d2), 0) & mask2)) or
                             (occ_sec.get((g2.section_id, d2), 0) & mask2))
                if g2_ok:
                    chosen = self._copy_gene(g2)
                else:
                    # Both parents conflict — find a brand-new conflict-free slot.
                    # This guarantees HC=0 offspring when exhaustive succeeds (~99.9%),
                    # eliminating almost all repair calls and their ~86M-iteration cost.
                    chosen = self._copy_gene(g1)
                    if not self._exhaustive_place_gene(chosen, occ_room, occ_fac, occ_sec):
                        # Truly no slot found (schedule extremely dense) — fall back
                        chosen = self._copy_gene(g1 if random.random() < 0.5 else g2)

            # Enforce Lab/Lec faculty pairing before committing to occ tables
            if chosen.gene_type == 'Lab':
                _pf = lec_fac_lookup.get((chosen.section_id, chosen.course_id))
                if _pf is not None:
                    chosen.faculty_id = _pf
            elif chosen.gene_type == 'Lec' and chosen.faculty_id is not None:
                lec_fac_lookup[(chosen.section_id, chosen.course_id)] = chosen.faculty_id

            child_genes[i] = chosen
            self._add_to_occ(chosen, occ_room, occ_fac, occ_sec)

        # Second pass: fix any Lab placed before its Lec sibling (Lab-first random order case)
        for i, g in enumerate(child_genes):
            if g and g.gene_type == 'Lab' and not g.is_fixed:
                _pf = lec_fac_lookup.get((g.section_id, g.course_id))
                if _pf is not None and g.faculty_id != _pf:
                    self._remove_from_occ(g, occ_room, occ_fac, occ_sec)
                    g.faculty_id = _pf
                    self._add_to_occ(g, occ_room, occ_fac, occ_sec)

        return Chromosome(child_genes)

    # ------------------------------------------------------------------ #
    # CONFLICT-GRAPH HELPERS                                              #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _genes_overlap(g1, g2):
        """True if g1 and g2 have a direct hard-constraint conflict."""
        if g1.day_idx != g2.day_idx:
            return False
        if g1.end_idx <= g2.start_idx or g2.end_idx <= g1.start_idx:
            return False
        return (g1.room_id == g2.room_id or
                (g1.faculty_id is not None and g1.faculty_id == g2.faculty_id) or
                g1.section_id == g2.section_id)

    def _exhaustive_place_gene(self, gene, occ_room, occ_fac, occ_sec,
                               min_day=0, min_start_same_day=-1):
        """
        Two-phase placement:
        Phase 1 — full exhaustive scan with the gene's current faculty (orig logic).
          Exits on first valid (day, start, room). Fast when faculty isn't fully
          booked; only slow when every slot for that faculty is occupied.
        Phase 2 — if Phase 1 fails (faculty fully booked), try up to 3 alternative
          faculty with 40 random attempts each.  This is the KEY fix for HC getting
          stuck: genes whose assigned faculty is 100% occupied were previously
          guaranteed to fail; now they can switch faculty and escape the conflict.
        min_day / min_start_same_day: HC-04 Lab-after-Lec enforcement (same semantics
          as randomize_gene_fast).
        """
        valid_rooms  = list(self._get_rooms_for_gene(gene))
        for _t_rid in self.tba_room_ids:
            if _t_rid not in valid_rooms:
                valid_rooms.append(_t_rid)
        slots_needed = gene.duration_slots
        sec_id       = gene.section_id
        orig_fac     = gene.faculty_id
        total_slots  = self.total_slots

        # Compute aligned start slots: div4 for standard Lec rooms, even for Lab/3hr-Lec/Async
        is_three_hr_lec = (gene.gene_type == 'Lec' and slots_needed >= 6)
        if gene.gene_type == 'Lec' and not is_three_hr_lec and self._use_div4_for_lec:
            _starts = [s for s in range(0, max(1, total_slots - slots_needed + 1)) if s % 4 == 0]
        else:
            _starts = [s for s in range(0, max(1, total_slots - slots_needed + 1)) if s % 2 == 0]
        if not _starts:  # safety fallback
            _starts = list(range(0, max(1, total_slots - slots_needed + 1)))

        _locked_day = getattr(gene, 'locked_day', -1)
        if _locked_day >= 0:
            days = [_locked_day]
        else:
            _fa_avail = (self._fac_avail_days.get(orig_fac)
                         if orig_fac and orig_fac not in self.multi_assignment_faculty else None)
            if _fa_avail:
                days = [d for d in range(min_day, len(self.days)) if d in _fa_avail]
                if not days:    # safety: overloaded faculty — let HC flag it
                    days = list(range(min_day, len(self.days)))
            else:
                days = list(range(min_day, len(self.days)))
        starts = list(_starts)
        
        phys_rooms = [r for r in valid_rooms if r not in self.tba_room_ids]
        tba_rooms = [r for r in valid_rooms if r in self.tba_room_ids]
        random.shuffle(phys_rooms)
        random.shuffle(tba_rooms)
        rooms = phys_rooms + tba_rooms
        
        random.shuffle(days); random.shuffle(starts)

        # ── Phase 1: exhaustive with original faculty ──────────────────────
        for day in days:
            for start in starts:
                # HC-04: if same day as Lec, Lab must not start before Lec
                if day == min_day and min_start_same_day >= 0 and start <= min_start_same_day:
                    continue
                end = start + slots_needed
                mask = ((1 << slots_needed) - 1) << start

                # Fast check section and faculty (these don't vary by room)
                if (occ_sec.get((sec_id, day), 0) & mask) != 0:
                    continue
                if orig_fac is not None and orig_fac not in self.multi_assignment_faculty and (occ_fac.get((orig_fac, day), 0) & mask) != 0:
                    continue

                for room in rooms:
                    # Skip occupancy check if it's a Multi-Assignment Room
                    if room in self.multi_assignment_rooms or (occ_room.get((room, day), 0) & mask) == 0:
                        gene.day_idx = day
                        gene.start_idx = start
                        gene.end_idx = end
                        gene.room_id = room
                        gene.bitmask = mask
                        return True

        # ── Phase 2: original faculty is fully booked — try alternatives ──
        # Skip Phase 2 if this gene has a manual fa_map assignment — preserve it even if fully booked
        if self.fa_map.get((gene.course_id, gene.section_id)) is not None:
            return False
        faculty_ids = self.faculty_ids
        if not faculty_ids:
            return False
        alts = [f for f in faculty_ids if f != orig_fac]
        random.shuffle(alts)
        n_days = len(self.days)
        for alt_fac in alts[:3]:      # try up to 3 alternative faculty
            _alt_avail = (self._fac_avail_days.get(alt_fac)
                          if alt_fac not in self.multi_assignment_faculty else None)
            for _ in range(40):       # 40 random attempts per alt (fast, probabilistic)
                day   = random.randint(min_day, n_days - 1)
                if _alt_avail and day not in _alt_avail:
                    continue
                start = random.choice(_starts)
                # HC-04: same-day start constraint
                if day == min_day and min_start_same_day >= 0 and start <= min_start_same_day:
                    continue
                end   = start + slots_needed
                mask  = ((1 << slots_needed) - 1) << start
                
                if (occ_sec.get((sec_id, day), 0) & mask) != 0:
                    continue
                if (occ_fac.get((alt_fac, day), 0) & mask) != 0:
                    continue
                    
                for room in rooms:
                    if (occ_room.get((room, day), 0) & mask) == 0:
                        gene.day_idx    = day
                        gene.start_idx  = start
                        gene.end_idx    = end
                        gene.room_id    = room
                        gene.faculty_id = alt_fac  # reassign faculty
                        gene.bitmask    = mask
                        return True
        return False

    # ------------------------------------------------------------------ #
    # LAST-SEAT BACKTRACKING  (1-level, for HC=1-5 stagnation)           #
    # ------------------------------------------------------------------ #
    def _exhaustive_resolve_last_conflicts(self, chromosome):
        """
        1-level backtracking for the "Last Seat Problem".

        When HC is stuck at 1-5, normal repair fails because every valid slot
        for the conflicting gene is already occupied by non-conflicting genes
        (the blocker genes have 'stolen' all available space).

        Strategy per stuck gene:
          1. Try direct placement (maybe repair already freed a slot).
          2. If that fails: find non-conflicting genes (blockers) that share a
             resource (room / faculty / section) on the same day/time window.
          3. Temporarily remove the blocker from occ.
          4. Try placing the stuck gene in the freed space.
          5. If stuck placed: try re-placing the blocker anywhere else.
          6. If blocker also re-placed → commit swap (both fit, conflict resolved).
          7. Otherwise → rollback both to original positions and try the next blocker.

        Precondition: chromosome.conflicting_indices must be fresh
                      (call calculate_fitness before calling this function).
        Returns True if at least one conflict was resolved.
        """
        genes = chromosome.genes
        conflict_set = set(
            i for i in chromosome.conflicting_indices if not genes[i].is_fixed
        )
        if not conflict_set:
            return False

        # Build occ from all NON-conflicting genes
        occ_room = defaultdict(int)
        occ_fac  = defaultdict(int)
        occ_sec  = defaultdict(int)
        for i, g in enumerate(genes):
            if i not in conflict_set:
                self._add_to_occ(g, occ_room, occ_fac, occ_sec)

        # Lec-day and faculty-pairing lookups (HC-04 + pairing invariant)
        lec_lookup     = {}  # {(section_id, course_id): (day_idx, start_idx)}
        lec_fac_lookup = {}  # {(section_id, course_id): faculty_id}
        for i, g in enumerate(genes):
            if g.gene_type == 'Lec' and i not in conflict_set:
                lec_lookup[(g.section_id, g.course_id)] = (g.day_idx, g.start_idx)
                if g.faculty_id is not None:
                    lec_fac_lookup[(g.section_id, g.course_id)] = g.faculty_id
        # Also seed faculty pairing from conflicting Lec genes so Lab can still pair
        # even when both Lec and Lab are in conflict_set simultaneously.
        for i, g in enumerate(genes):
            if g.gene_type == 'Lec' and i in conflict_set:
                key = (g.section_id, g.course_id)
                if g.faculty_id is not None and key not in lec_fac_lookup:
                    lec_fac_lookup[key] = g.faculty_id

        resolved_any = False

        for stuck_idx in list(conflict_set):
            stuck = genes[stuck_idx]
            if stuck.is_fixed:
                continue

            # HC-04 constraints for this gene
            min_day      = 0
            min_start_sd = -1
            pref_fac     = None
            if stuck.gene_type == 'Lab':
                lec_info = lec_lookup.get((stuck.section_id, stuck.course_id))
                if lec_info:
                    min_day, lec_start = lec_info
                    min_start_sd = lec_start - 1
                pref_fac = lec_fac_lookup.get((stuck.section_id, stuck.course_id))

            # ── Pass 1: direct placement (no backtracking) ──────────────
            placed = self.randomize_gene_fast(
                stuck, occ_room, occ_fac, occ_sec, min_day, min_start_sd,
                preferred_faculty=pref_fac
            )
            if not placed:
                placed = self._exhaustive_place_gene(
                    stuck, occ_room, occ_fac, occ_sec, min_day, min_start_sd
                )
            if placed:
                self._add_to_occ(stuck, occ_room, occ_fac, occ_sec)
                if stuck.gene_type == 'Lec':
                    lec_lookup[(stuck.section_id, stuck.course_id)] = (stuck.day_idx, stuck.start_idx)
                    if stuck.faculty_id is not None:
                        lec_fac_lookup[(stuck.section_id, stuck.course_id)] = stuck.faculty_id
                conflict_set.discard(stuck_idx)
                resolved_any = True
                continue

            # ── C-2: HC-18 bypass — faculty unavailability ──────────────
            # If stuck gene's faculty has restricted days AND no valid day is
            # free, moving to a different time won't help.  Reassign to T.B.A.
            # so the schedule can complete; admin resolves manually afterward.
            fac_avail = self._fac_avail_days.get(stuck.faculty_id) if stuck.faculty_id else None
            if fac_avail is not None and self.fa_map.get((stuck.course_id, stuck.section_id)) is None:
                _tba_ids = list(self.multi_assignment_faculty)
                if _tba_ids:
                    _orig_fac = stuck.faculty_id
                    _bypassed = False
                    for _tba_id in _tba_ids:
                        stuck.faculty_id = _tba_id
                        _bp = self.randomize_gene_fast(
                            stuck, occ_room, occ_fac, occ_sec, min_day, min_start_sd
                        )
                        if not _bp:
                            _bp = self._exhaustive_place_gene(
                                stuck, occ_room, occ_fac, occ_sec, min_day, min_start_sd
                            )
                        if _bp:
                            self._add_to_occ(stuck, occ_room, occ_fac, occ_sec)
                            if stuck.gene_type == 'Lec':
                                lec_lookup[(stuck.section_id, stuck.course_id)] = (stuck.day_idx, stuck.start_idx)
                                lec_fac_lookup[(stuck.section_id, stuck.course_id)] = stuck.faculty_id
                            conflict_set.discard(stuck_idx)
                            resolved_any = True
                            _bypassed = True
                            print(f"⚠️  HC-18 bypass: gene (course={stuck.course_id}, sec={stuck.section_id}) "
                                  f"reassigned to T.B.A. (orig faculty_id={_orig_fac}) — faculty had no free available days")
                            break
                    if not _bypassed:
                        stuck.faculty_id = _orig_fac  # restore if bypass failed
                    if _bypassed:
                        continue

            # ── Pass 2: find blocker genes (share resource, same day) ───
            stuck_mask = stuck.bitmask
            stuck_day  = stuck.day_idx
            blockers   = []
            for i, g in enumerate(genes):
                if i in conflict_set or g.is_fixed:
                    continue
                if g.day_idx != stuck_day:
                    continue
                if (g.bitmask & stuck_mask) == 0:   # no time overlap
                    continue
                if (g.room_id == stuck.room_id or
                        (g.faculty_id is not None and
                         g.faculty_id == stuck.faculty_id) or
                        g.section_id == stuck.section_id):
                    blockers.append(i)

            # ── C-1: Broaden blocker search — same room, any section/faculty ─
            # The primary search may miss genes that share only the room
            # (different section AND different faculty). Second pass finds them.
            if not blockers:
                for i, g in enumerate(genes):
                    if i in conflict_set or g.is_fixed:
                        continue
                    if g.day_idx != stuck_day:
                        continue
                    if (g.bitmask & stuck_mask) == 0:
                        continue
                    if g.room_id == stuck.room_id:
                        blockers.append(i)

            # ── Pass 3: try displacing each blocker (up to 10 candidates) ─
            swap_done = False
            for blocker_idx in blockers[:10]:
                blocker = genes[blocker_idx]

                # Save blocker's full placement state for rollback
                b_day   = blocker.day_idx
                b_start = blocker.start_idx
                b_end   = blocker.end_idx
                b_room  = blocker.room_id
                b_fac   = blocker.faculty_id
                b_mask  = blocker.bitmask

                # Temporarily remove blocker → try to place stuck gene
                self._remove_from_occ(blocker, occ_room, occ_fac, occ_sec)

                stuck_placed = self.randomize_gene_fast(
                    stuck, occ_room, occ_fac, occ_sec, min_day, min_start_sd,
                    preferred_faculty=pref_fac
                )
                if not stuck_placed:
                    stuck_placed = self._exhaustive_place_gene(
                        stuck, occ_room, occ_fac, occ_sec, min_day, min_start_sd
                    )

                if stuck_placed:
                    self._add_to_occ(stuck, occ_room, occ_fac, occ_sec)

                    # Try re-placing the displaced blocker
                    b_min_day = 0; b_min_sd = -1; b_pref_fac = None
                    if blocker.gene_type == 'Lab':
                        b_lec = lec_lookup.get((blocker.section_id, blocker.course_id))
                        if b_lec:
                            b_min_day, b_ls = b_lec
                            b_min_sd = b_ls - 1
                        b_pref_fac = lec_fac_lookup.get(
                            (blocker.section_id, blocker.course_id))

                    blocker_placed = self.randomize_gene_fast(
                        blocker, occ_room, occ_fac, occ_sec, b_min_day, b_min_sd,
                        preferred_faculty=b_pref_fac
                    )
                    if not blocker_placed:
                        blocker_placed = self._exhaustive_place_gene(
                            blocker, occ_room, occ_fac, occ_sec, b_min_day, b_min_sd
                        )

                    if blocker_placed:
                        # ✓ Both placed — commit swap
                        self._add_to_occ(blocker, occ_room, occ_fac, occ_sec)
                        if stuck.gene_type == 'Lec':
                            lec_lookup[(stuck.section_id, stuck.course_id)] = \
                                (stuck.day_idx, stuck.start_idx)
                            if stuck.faculty_id is not None:
                                lec_fac_lookup[(stuck.section_id, stuck.course_id)] = \
                                    stuck.faculty_id
                        if blocker.gene_type == 'Lec':
                            lec_lookup[(blocker.section_id, blocker.course_id)] = \
                                (blocker.day_idx, blocker.start_idx)
                            if blocker.faculty_id is not None:
                                lec_fac_lookup[(blocker.section_id, blocker.course_id)] = \
                                    blocker.faculty_id
                        conflict_set.discard(stuck_idx)
                        resolved_any = True
                        swap_done = True
                        break
                    else:
                        # ✗ Blocker can't be re-placed → rollback both
                        self._remove_from_occ(stuck, occ_room, occ_fac, occ_sec)
                        blocker.day_idx    = b_day
                        blocker.start_idx  = b_start
                        blocker.end_idx    = b_end
                        blocker.room_id    = b_room
                        blocker.faculty_id = b_fac
                        blocker.bitmask    = b_mask
                        self._add_to_occ(blocker, occ_room, occ_fac, occ_sec)
                else:
                    # ✗ Stuck gene still can't be placed → restore blocker, try next
                    blocker.day_idx    = b_day
                    blocker.start_idx  = b_start
                    blocker.end_idx    = b_end
                    blocker.room_id    = b_room
                    blocker.faculty_id = b_fac
                    blocker.bitmask    = b_mask
                    self._add_to_occ(blocker, occ_room, occ_fac, occ_sec)

            if not swap_done:
                # Gene remains stuck — add at current position to keep occ consistent
                self._add_to_occ(stuck, occ_room, occ_fac, occ_sec)

        return resolved_any

    # ------------------------------------------------------------------ #
    # ISOLATED HARD CONFLICT REPAIR  (DSatur-ordered)                    #
    # ------------------------------------------------------------------ #
    def _hard_conflict_repair(self, chromosome):
        """
        Graph-coloring-inspired repair:
        1. Build conflict graph among the conflicting genes
        2. Sort by degree (most mutually-conflicted gene first — DSatur heuristic)
        3. Place each gene into CLEAN space (occ from non-conflicting genes only)
        4. Use exhaustive scan as fallback
        """
        if not chromosome.conflicting_indices:
            return

        genes        = chromosome.genes
        conflict_idxs = [i for i in chromosome.conflicting_indices if not genes[i].is_fixed]
        if not conflict_idxs:
            return

        conflict_set = set(conflict_idxs)

        # Build conflict graph: count how many other conflicting genes each gene overlaps
        degree = {idx: 0 for idx in conflict_idxs}
        for a in range(len(conflict_idxs)):
            for b in range(a + 1, len(conflict_idxs)):
                ia, ib = conflict_idxs[a], conflict_idxs[b]
                if self._genes_overlap(genes[ia], genes[ib]):
                    degree[ia] += 1
                    degree[ib] += 1

        # DSatur: process most-constrained (highest degree) genes first
        ordered = sorted(conflict_idxs, key=lambda i: -degree[i])

        # Build occ sets from ONLY the clean (non-conflicting) genes
        occ_room = defaultdict(int); occ_fac = defaultdict(int); occ_sec = defaultdict(int)
        for i, g in enumerate(genes):
            if i not in conflict_set:
                self._add_to_occ(g, occ_room, occ_fac, occ_sec)

        # Build Lec day lookup from clean genes for HC-04 enforcement
        lec_lookup = {}  # {(section_id, course_id): (day_idx, start_idx)}
        lec_fac_lookup = {}  # {(section_id, course_id): faculty_id} — for Lab pairing
        for i, g in enumerate(genes):
            if g.gene_type == 'Lec' and i not in conflict_set:
                lec_lookup[(g.section_id, g.course_id)] = (g.day_idx, g.start_idx)
                if g.faculty_id is not None:
                    lec_fac_lookup[(g.section_id, g.course_id)] = g.faculty_id

        # Place each gene cleanly
        for idx in ordered:
            gene = genes[idx]

            min_day = 0
            min_start_sd = -1
            pref_fac = None
            if gene.gene_type == 'Lab':
                lec_info = lec_lookup.get((gene.section_id, gene.course_id))
                if lec_info:
                    min_day, lec_start = lec_info
                    min_start_sd = lec_start - 1
                pref_fac = lec_fac_lookup.get((gene.section_id, gene.course_id))

            self.randomize_gene_fast(gene, occ_room, occ_fac, occ_sec, min_day, min_start_sd,
                                     preferred_faculty=pref_fac)

            placed_ok = True
            mask = gene.bitmask
            d = gene.day_idx
            if ((occ_room.get((gene.room_id, d), 0) & mask) != 0 or
                (gene.faculty_id is not None and (occ_fac.get((gene.faculty_id, d), 0) & mask) != 0) or
                (occ_sec.get((gene.section_id, d), 0) & mask) != 0):
                placed_ok = False

            if not placed_ok:
                self._exhaustive_place_gene(gene, occ_room, occ_fac, occ_sec, min_day, min_start_sd)

            self._add_to_occ(gene, occ_room, occ_fac, occ_sec)

            # Update lookup if we just placed a Lec gene
            if gene.gene_type == 'Lec':
                lec_lookup[(gene.section_id, gene.course_id)] = (gene.day_idx, gene.start_idx)
                if gene.faculty_id is not None:
                    lec_fac_lookup[(gene.section_id, gene.course_id)] = gene.faculty_id

    # ------------------------------------------------------------------ #
    # NSGA-II: NON-DOMINATED SORTING  (feasibility-first dominance)       #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _constrained_dominates(a, b):
        """
        Feasibility-first dominance for constrained NSGA-II (Deb et al., 2002).

        Rules:
          1. A feasible solution (HC=0) always dominates an infeasible one (HC>0).
          2. Among two feasible solutions, the one with lower soft_score dominates.
          3. Among two infeasible solutions, fewer hard_conflicts dominates;
             ties broken by soft_score.

        This guarantees HC=0 solutions always rank before HC>0 solutions,
        so the algorithm cannot 'trade' a hard conflict for a soft improvement.
        """
        a_ok = a.hard_conflicts == 0
        b_ok = b.hard_conflicts == 0

        if a_ok and not b_ok:
            return True   # feasible beats infeasible unconditionally
        if not a_ok and b_ok:
            return False  # infeasible never beats feasible

        if a_ok:
            # Both feasible → single objective: soft_score
            return a.soft_score < b.soft_score
        else:
            # Both infeasible → lexicographic (HC first, SS second)
            if a.hard_conflicts != b.hard_conflicts:
                return a.hard_conflicts < b.hard_conflicts
            return a.soft_score < b.soft_score

    def fast_non_dominated_sort(self, population):
        """
        NSGA-II fast non-dominated sort using feasibility-first dominance.
        Returns a list of Pareto fronts (each front is a list of chromosomes).
        Complexity: O(N^2) for N chromosomes.
        """
        n = len(population)
        dominated_by   = [[] for _ in range(n)]
        domination_cnt = [0] * n
        dom = GeneticScheduler._constrained_dominates

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

    # ------------------------------------------------------------------ #
    # NSGA-II: CROWDING DISTANCE ASSIGNMENT                               #
    # ------------------------------------------------------------------ #
    def crowding_distance_assignment(self, front):
        """
        Assign crowding distance to each chromosome in a Pareto front.
        Boundary solutions (min/max of each objective) get infinite distance.
        Interior solutions get the sum of normalized objective differences.
        Higher crowding distance = more isolated = preferred for diversity.
        """
        l = len(front)
        if l == 0:
            return
        if l == 1:
            front[0].crowding_distance = float('inf')
            return

        for c in front:
            c.crowding_distance = 0.0

        # Process each objective independently
        for get_obj in (lambda c: c.hard_conflicts, lambda c: c.soft_score):
            front_sorted = sorted(front, key=get_obj)
            min_val = get_obj(front_sorted[0])
            max_val = get_obj(front_sorted[-1])
            # Boundary solutions always get infinite distance
            front_sorted[0].crowding_distance  = float('inf')
            front_sorted[-1].crowding_distance = float('inf')
            rng = max_val - min_val
            if rng == 0:
                continue
            for i in range(1, l - 1):
                front_sorted[i].crowding_distance += (
                    get_obj(front_sorted[i + 1]) - get_obj(front_sorted[i - 1])
                ) / rng

    # ------------------------------------------------------------------ #
    # NSGA-II: BINARY TOURNAMENT SELECTION                                #
    # ------------------------------------------------------------------ #
    def nsga2_tournament_select(self, population):
        """
        Binary tournament using NSGA-II crowded comparison operator (<n):
          a <n b  iff  (a.rank < b.rank) OR
                       (a.rank == b.rank AND a.crowding_distance > b.crowding_distance)
        Prefers non-dominated solutions; among equals prefers the less crowded one.
        """
        a = random.choice(population)
        b = random.choice(population)
        if (a.rank < b.rank or
                (a.rank == b.rank and a.crowding_distance > b.crowding_distance)):
            return a
        return b

    def _hard_phase_select(self, population):
        """
        Binary tournament for hard phase: minimise hard_conflicts, then soft_score.
        Avoids NSGA-II rank/crowding overhead when all solutions are infeasible.
        """
        a = random.choice(population)
        b = random.choice(population)
        if (a.hard_conflicts < b.hard_conflicts or
                (a.hard_conflicts == b.hard_conflicts and a.soft_score < b.soft_score)):
            return a
        return b

    # ------------------------------------------------------------------ #
    # BEST CHROMOSOME HELPER                                               #
    # ------------------------------------------------------------------ #
    def _find_best(self, population):
        """
        Best = chromosome with 0 HC and minimum soft_score.
        If no 0-HC solution exists, best = minimum (HC, soft_score) lexicographically.
        """
        zero_hc = [c for c in population if c.hard_conflicts == 0]
        if zero_hc:
            return min(zero_hc, key=lambda c: c.soft_score)
        return min(population, key=lambda c: (c.hard_conflicts, c.soft_score))

    def _is_better(self, a, b):
        """True if a strictly improves over b (fewer HC, or same HC with fewer soft)."""
        if a.hard_conflicts < b.hard_conflicts:
            return True
        if a.hard_conflicts == b.hard_conflicts and a.soft_score < b.soft_score:
            return True
        return False

    # ------------------------------------------------------------------ #
    # MAIN LOOP — NSGA-II (Multi-Objective Genetic Algorithm II)          #
    # ------------------------------------------------------------------ #
    def run_algorithm(self, progress_callback=None, seed_records=None):
        """
        NSGA-II main loop with warm-start and two-phase fitness.

        Warm start (seed_records provided):
          - Converts saved DB schedule to a seed Chromosome
          - Population seeded as: 1 exact seed + 50% mild variants + 50% fresh genomes
          - Algorithm continues improving the existing schedule instead of starting cold

        Hard phase (HC > 0):
          - Simple O(N log N) sort replaces O(N²) NSGA-II sort — no Pareto overhead
          - 100 offspring per generation (2× wider exploration)
          - hard_only=True fitness (~40% faster per evaluation)

        Soft phase (HC = 0 in best):
          - Full NSGA-II Pareto sort + crowding distance for multi-objective diversity
          - SOFT_REFINE_GENS more generations to minimise soft violations
        """
        print("=== FAST INIT V5 === (seed_repair=1pass, pop_size=reduced)")

        # ── Dynamic population size ────────────────────────────────────────
        # Estimate number of genes per chromosome from sections × courses, then
        # scale population: max(40, min(150, n_genes × 0.35)).
        # Larger schedules benefit from higher diversity; smaller ones stay fast.
        n_genes_estimate = sum(
            (1 if (cm.get('synchronous_lec_hours', 0) or cm.get('lec_units', 0)) > 0 else 0) +
            (1 if (cm.get('synchronous_lab_hours', 0) or cm.get('lab_units', 0)) > 0 else 0) +
            (1 if ((cm.get('asynchronous_lec_hours', 0) or 0) +
                   (cm.get('asynchronous_lab_hours', 0) or 0)) > 0 else 0)
            for sec in self.sections for cid in sec['course_ids']
            for cm in [self.course_map.get(cid, {})]
        )
        if seed_records:
            # Warm start: seed provides quality; small pop is sufficient, keep init fast
            pop_size = max(12, min(20, int(n_genes_estimate * 0.05)))
        else:
            # Cold start: slightly more diversity, still keep init fast
            pop_size = max(15, min(30, int(n_genes_estimate * 0.08)))

        print(f"GA Initializing: pop={pop_size} (genes≈{n_genes_estimate}, "
              f"{'warm' if seed_records else 'cold'}-start), lns/gen={LNS_OFFSPRING}, "
              f"cross/gen={HARD_OFFSPRING}, max_gen={MAX_GENERATIONS}")

        # Track start time to enforce 5-minute strict timeout
        start_time_limit = time.time()

        # Signal UI: init phase starting with actual pop_size
        if progress_callback:
            progress_callback({
                'generation': 0,
                'hard_conflicts': 0,
                'sc1_violations': 0,
                'sc2_violations': 0,
                'soft_score': 0,
                'pop_size': pop_size,
            })

        # ── Initialise population ──────────────────────────────────────────
        population = []

        if seed_records:
            # Warm start: build seed chromosome from saved schedule
            _t0 = time.time()
            print("🌱 Building seed chromosome from saved schedule...")
            seed_chrom = self._build_seed_chromosome(seed_records)
            self.calculate_fitness(seed_chrom, hard_only=True)
            print(f"   Seed build: {time.time()-_t0:.1f}s  HC={seed_chrom.hard_conflicts}")

            # No repair at init — GA Phase 1 (20-min budget) handles HC from gen 1
            # _hard_conflict_repair calls _exhaustive_place_gene per stuck gene → 1-3 min
            population.append(seed_chrom)

            # 60% mild variants (5-20% perturbation) — exploit seed diversity
            # 40% fresh genomes — explore new territory
            _t2 = time.time()
            n_variants = int(pop_size * 0.60)
            variant_chroms = []
            for i in range(n_variants):
                frac = 0.05 + 0.15 * (i / max(n_variants - 1, 1))  # 5% → 20%
                variant_chroms.append(self._perturb_chromosome(seed_chrom, fraction=frac))
            print(f"   Variants ({n_variants}): {time.time()-_t2:.1f}s")

            fresh_count = (pop_size - 1) - n_variants
            if fresh_count > 0:
                _t3 = time.time()
                with ThreadPoolExecutor(max_workers=min(_N_WORKERS, fresh_count)) as _exe:
                    fresh_chroms = list(_exe.map(lambda _: self.create_genome(skip_exhaustive=True), range(fresh_count)))
                print(f"   Fresh genomes ({fresh_count}): {time.time()-_t3:.1f}s")
            else:
                fresh_chroms = []

            pending = variant_chroms + fresh_chroms

            _t4 = time.time()
            self._eval_batch(pending, hard_only=True)
            print(f"   Eval batch ({len(pending)}): {time.time()-_t4:.1f}s")
            # No repair pass — GA Phase 1 handles HC reduction from gen 1 onward
            population.extend(pending)
            print(f"   Init pool: {len(population)} chromosomes, "
                  f"best HC={min(c.hard_conflicts for c in population)}, "
                  f"total init={time.time()-_t0:.1f}s")
        else:
            # Cold start: create all in parallel (skip exhaustive for speed; repair handles HC>0)
            _t0 = time.time()
            with ThreadPoolExecutor(max_workers=min(_N_WORKERS, pop_size)) as _exe:
                population = list(_exe.map(lambda _: self.create_genome(skip_exhaustive=True), range(pop_size)))
            print(f"   Cold genomes ({pop_size}): {time.time()-_t0:.1f}s")
            _t1 = time.time()
            self._eval_batch(population, hard_only=True)
            print(f"   Cold eval: {time.time()-_t1:.1f}s  total={time.time()-_t0:.1f}s")

        # No NSGA-II rank/crowding needed at init — simple sort is enough
        population.sort(key=lambda c: (c.hard_conflicts, c.soft_score))

        best_schedule        = self._copy_chromosome(self._find_best(population))
        stagnation_counter   = 0   # mild counter — resets on improvement OR mild trigger
        severe_counter       = 0   # severe counter — resets on improvement OR severe trigger only
        last_best_hc         = best_schedule.hard_conflicts
        last_best_sc1        = best_schedule.sc1_violations
        last_best_ss         = best_schedule.soft_score
        # 3-phase tracking
        current_phase        = 'hard'   # 'hard' | 'sc1' | 'sc2'
        sc1_start_time       = None
        sc2_start_time       = None
        sc1_start_gen        = None
        sc2_start_gen        = None
        sc1_stag_counter     = 0   # stagnation within SC-I phase → force-advance to SC-II
        last_diversity_inject = -DIV_COOLDOWN  # allow injection from gen 0

        print(f"Init done. Best HC={best_schedule.hard_conflicts}, SS={best_schedule.soft_score}")

        for generation in range(MAX_GENERATIONS):
            # ── Three-phase time limits ────────────────────────────────────
            if current_phase == 'hard':
                if time.time() - start_time_limit > 1200:
                    print(f"⏳ Hard phase time limit (20 min) reached at Gen {generation}.")
                    break
            elif current_phase == 'sc1':
                if time.time() - sc1_start_time > 600:
                    print(f"⏳ SC-I phase time limit (10 min) reached at Gen {generation} — advancing to SC-II phase.")
                    current_phase    = 'sc2'
                    sc2_start_time   = time.time()
                    sc2_start_gen    = generation
                    self._eval_batch(population)
                    stagnation_counter = 0; severe_counter = 0
                    last_best_ss = self._find_best(population).soft_score
            elif current_phase == 'sc2':
                if time.time() - sc2_start_time > 600:
                    print(f"⏳ SC-II phase time limit (10 min) reached at Gen {generation}.")
                    break

            # Yield GIL every 6 gens for UI polling
            if generation % 6 == 0:
                time.sleep(0.005)

            # ── Phase flags ───────────────────────────────────────────────
            hard_phase = (current_phase == 'hard')
            sc1_phase  = (current_phase == 'sc1')

            # ── Adaptive SC-II weight (Step 5) ─────────────────────────────
            # In Phase 3: ramp self._sc2_base from SC2_BASE (10) → 50 linearly
            # over the first SOFT_REFINE_GENS/2 gens of Phase 3. After midpoint
            # it stays at 50. This creates increasing pressure on SC-II rules
            # as the run progresses, forcing the GA to care more about "nice to
            # have" constraints (lunch break, isolation avoidance, etc.).
            if current_phase == 'sc2':
                _sc2_elapsed = generation - sc2_start_gen
                _ramp_end    = max(1, SOFT_REFINE_GENS // 2)
                _sc2_t       = min(1.0, _sc2_elapsed / _ramp_end)
                self._sc2_base = int(SC2_BASE + (50 - SC2_BASE) * _sc2_t)
            else:
                self._sc2_base = SC2_BASE

            # Hard phase: more offspring for wider exploration; soft phases: standard
            n_off = HARD_OFFSPRING if hard_phase else OFFSPRING_COUNT

            # ── Generate offspring ─────────────────────────────────────────
            offspring = []

            # ── LNS offspring (hard phase only) ───────────────────────────
            if hard_phase and best_schedule.hard_conflicts > 0:
                _lns_low_hc = (best_schedule.hard_conflicts <= 5)
                for _ in range(LNS_OFFSPRING):
                    nc = self._copy_chromosome(best_schedule)
                    self._hard_conflict_repair(nc)
                    # Backtracking pass for "Last Seat Problem" (HC=1–5 only)
                    if _lns_low_hc:
                        self.calculate_fitness(nc, hard_only=True)
                        if nc.hard_conflicts > 0:
                            self._exhaustive_resolve_last_conflicts(nc)
                    self.calculate_fitness(nc, hard_only=True)
                    offspring.append(nc)

            # ── Crossover offspring ───────────────────────────────────────
            # Adaptive Mutation Rate:
            #   hard phase  → base 0.2 (explore HC landscape)
            #   sc1/sc2     → base 0.5 (aggressive soft targeting)
            #   All phases  → scale up to 0.8 with stagnation pressure
            mutation_base = 0.2 if hard_phase else 0.5
            mutation_max  = 0.8
            stag_ratio    = min(1.0, stagnation_counter / max(1, STAG_THRESHOLD))
            adaptive_mutation_rate = mutation_base + (mutation_max - mutation_base) * stag_ratio

            sc2_phase = (not hard_phase and not sc1_phase)
            while len(offspring) < n_off:
                p1 = self._hard_phase_select(population)
                p2 = self._hard_phase_select(population)
                child = self.crossover(p1, p2)
                if random.random() < adaptive_mutation_rate:
                    if sc2_phase:
                        # Phase 3: guided mutation — target soft-violating genes only
                        self._guided_soft_mutate(child)
                    else:
                        self.proportional_mutate(child)
                if hard_phase:
                    # Hard phase: inline eval + repair (repair needs fitness first)
                    self.calculate_fitness(child, hard_only=True)
                    if child.hard_conflicts > 0:
                        self._hard_conflict_repair(child)
                        self.calculate_fitness(child, hard_only=True)
                offspring.append(child)

            # Soft phases: batch-evaluate all offspring in parallel (no repair dependency)
            if sc1_phase:
                self._eval_batch(offspring, sc1_only=True)
            elif sc2_phase:
                self._eval_batch(offspring)

            # ── Phase transitions ──────────────────────────────────────────
            # Hard → SC-I: first generation where HC = 0
            if current_phase == 'hard' and best_schedule.hard_conflicts == 0:
                current_phase  = 'sc1'
                sc1_start_time = time.time()
                sc1_start_gen  = generation
                sc1_stag_counter = 0
                last_best_sc1  = best_schedule.sc1_violations
                self._eval_batch(population, sc1_only=True)
                self._eval_batch(offspring,  sc1_only=True)
                stagnation_counter = 0; severe_counter = 0
                print(f"🔀 SC-I phase begins at Gen {generation} "
                      f"(HC=0, SC-I={best_schedule.sc1_violations})")

            # SC-I → SC-II: SC-I=0  OR  stagnant for STAG_SC1_TIMEOUT gens
            if current_phase == 'sc1' and (
                    best_schedule.sc1_violations == 0 or
                    sc1_stag_counter >= STAG_SC1_TIMEOUT):
                reason = ("SC-I=0" if best_schedule.sc1_violations == 0
                          else f"SC-I stagnant ({sc1_stag_counter} gens)")
                current_phase  = 'sc2'
                sc2_start_time = time.time()
                sc2_start_gen  = generation
                self._eval_batch(population)
                self._eval_batch(offspring)
                stagnation_counter = 0; severe_counter = 0
                last_best_ss = self._find_best(population).soft_score
                print(f"🔀 SC-II phase begins at Gen {generation}: {reason} "
                      f"(SC-I={best_schedule.sc1_violations}, SC-II={best_schedule.sc2_violations})")

            # ── Survivor selection ─────────────────────────────────────────
            # Both phases: O(N log N) sort — (HC, SS) lexicographic.
            # NSGA-II O(N²) dominance sort is removed entirely; the simple sort
            # keeps the best solutions and is ~100× faster per generation.
            combined = population + offspring
            combined.sort(key=lambda c: (c.hard_conflicts, c.soft_score))
            population = combined[:pop_size]

            # ── Track best-ever ────────────────────────────────────────────
            current_best = self._find_best(population)
            if self._is_better(current_best, best_schedule):
                best_schedule = self._copy_chromosome(current_best)

            # ── Stagnation detection (per-phase metric) ────────────────────
            if hard_phase:
                improved = current_best.hard_conflicts < last_best_hc
            elif sc1_phase:
                improved = current_best.sc1_violations < last_best_sc1
            else:
                improved = current_best.soft_score < last_best_ss

            if improved:
                if hard_phase:   last_best_hc  = current_best.hard_conflicts
                elif sc1_phase:  last_best_sc1 = current_best.sc1_violations
                else:            last_best_ss  = current_best.soft_score
                stagnation_counter = 0
                severe_counter     = 0
                sc1_stag_counter   = 0
            else:
                stagnation_counter += 1
                severe_counter     += 1
                if sc1_phase:
                    sc1_stag_counter += 1

            # ── Stagnation recovery ────────────────────────────────────────
            def _get_elites():
                zero = [c for c in population if c.hard_conflicts == 0]
                pool = zero if zero else population
                return sorted(pool, key=lambda c: (c.hard_conflicts, c.soft_score))[:10]

            def _fit(c):
                if hard_phase:  self.calculate_fitness(c, hard_only=True)
                elif sc1_phase: self.calculate_fitness(c, sc1_only=True)
                else:           self.calculate_fitness(c, hard_only=False)

            if severe_counter >= STAG_SEVERE:
                elites  = _get_elites()
                n_keep  = min(len(elites), 3)
                new_pop = list(elites[:n_keep])
                for elite in elites[:5]:
                    nc = self._copy_chromosome(elite)
                    self._hard_conflict_repair(nc)
                    _fit(nc)
                    # Backtracking for stubborn last-seat conflicts (HC=1–5)
                    if hard_phase and 0 < nc.hard_conflicts <= 5:
                        self._exhaustive_resolve_last_conflicts(nc)
                        _fit(nc)
                    new_pop.append(nc)
                while len(new_pop) < pop_size:
                    nc = self.create_genome()
                    _fit(nc)
                    new_pop.append(nc)
                population = new_pop[:pop_size]
                stagnation_counter = 0
                severe_counter     = 0
                print(f"🔄 Severe stagnation Gen {generation}: targeted repair + reset "
                      f"(HC={current_best.hard_conflicts}, phase={current_phase})")

            elif stagnation_counter >= STAG_THRESHOLD:
                elites    = _get_elites()
                n_replace = max(1, int(pop_size * 0.25))
                new_tail  = []
                for _ in range(n_replace):
                    if random.random() < 0.7 and elites:
                        nc = self._copy_chromosome(random.choice(elites))
                        self._hard_conflict_repair(nc)
                        _fit(nc)
                    else:
                        nc = self.create_genome()
                        _fit(nc)
                    new_tail.append(nc)
                population[-n_replace:] = new_tail
                stagnation_counter = 0
                print(f"🔄 Stagnation Gen {generation}: 25% targeted repair "
                      f"(HC={current_best.hard_conflicts}, phase={current_phase}, severe={severe_counter})")

            # ── Diversity injection (hard phase only) ──────────────────────
            if (hard_phase
                    and generation % 10 == 0
                    and generation - last_diversity_inject >= DIV_COOLDOWN):
                fingerprints = [(c.hard_conflicts, c.soft_score) for c in population]
                most_common  = max(set(fingerprints), key=fingerprints.count)
                similarity   = fingerprints.count(most_common) / len(population)
                if similarity >= DIV_THRESHOLD:
                    elites     = _get_elites()
                    n_keep     = max(1, int(pop_size * 0.30))
                    n_perturb  = int(pop_size * 0.30)
                    n_fresh    = pop_size - n_keep - n_perturb
                    new_pop    = list(elites[:n_keep])
                    for _ in range(n_perturb):
                        base = random.choice(elites) if elites else population[0]
                        nc   = self._perturb_chromosome(base, fraction=0.40)
                        self._hard_conflict_repair(nc)
                        self.calculate_fitness(nc, hard_only=True)
                        new_pop.append(nc)
                    for _ in range(n_fresh):
                        nc = self.create_genome()
                        self.calculate_fitness(nc, hard_only=True)
                        new_pop.append(nc)
                    population = new_pop[:pop_size]
                    last_diversity_inject = generation
                    print(f"🧬 Diversity inject Gen {generation}: "
                          f"similarity={similarity:.0%} → 30% keep / 30% perturb / 40% fresh "
                          f"(HC={current_best.hard_conflicts})")

            # ── Progress callback ──────────────────────────────────────────
            if progress_callback:
                progress_callback({
                    'generation':      generation + 1,
                    'hard_conflicts':  current_best.hard_conflicts,
                    'sc1_violations':  current_best.sc1_violations,
                    'sc2_violations':  current_best.sc2_violations,
                    'soft_score':      current_best.soft_score,
                    'best_fitness':    current_best.fitness,
                    'best_chromosome': current_best,
                    'phase':           current_phase,
                    'pop_size':        pop_size,
                })

            # ── Termination ────────────────────────────────────────────────
            if current_phase == 'sc2' and current_best.hard_conflicts == 0:
                # Perfect: all three layers resolved
                if current_best.fitness == 0 and (generation - sc2_start_gen) >= 20:
                    print(f"🏆 Perfect schedule at Gen {generation}!")
                    break
                # Gen cap for SC-II phase
                if (generation - sc2_start_gen) >= SOFT_REFINE_GENS:
                    print(f"✅ SC-II optimisation complete at Gen {generation}.")
                    break
            elif current_phase == 'sc1' and current_best.hard_conflicts == 0:
                # Early-perfect: SC-I already 0 (will transition to SC-II next iter)
                pass

        # ── Final Local Search Refinement ───────────────────────────────
        if best_schedule.hard_conflicts == 0 and best_schedule.soft_score > 0:
            print(f"🔍 Running Local Search refinement on best schedule (Soft Score: {best_schedule.soft_score})...")
            best_schedule = self._local_search_refinement(best_schedule, max_attempts=200)
            print(f"✨ Refinement complete. Final Soft Score: {best_schedule.soft_score}")

        return best_schedule
