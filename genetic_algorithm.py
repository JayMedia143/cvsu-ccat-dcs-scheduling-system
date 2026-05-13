import os
import random
import time
import psutil
import eventlet
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

class AlgorithmStopException(Exception):
    """Custom exception to interrupt the GA loop immediately."""
    pass

def get_hardware_profile():
    """
    Hardware-Aware Adaptive Scaling Engine (CPU Only).
    Profiles CPU to determine optimal optimization depth (Generations/Population).
    """
    cpu_count = os.cpu_count() or 4
    cpu_freq  = psutil.cpu_freq().max if hasattr(psutil.cpu_freq(), 'max') else 3000
    
    print(f"\n--- HARDWARE DIAGNOSTIC (CPU ONLY) ---")
    print(f"Detected CPU: {cpu_count} Cores @ {cpu_freq}MHz")

    profile = None

    # ── PERFORMANCE MODE (8+ Cores) ──────────────────────────────────────
    if cpu_count >= 8:
        profile = {
            'label'           : f"High-End CPU ({cpu_count} Cores)",
            'mode'            : 'Performance',
            'score'           : cpu_count,

            # Population & Offspring — Fix 8: Increased for wider search space
            'pop_size'        : 120,      
            'hard_offspring'  : 60,
            'lns_offspring'   : 35,
            'offspring_count' : 50,

            # Stagnation Thresholds
            'stag_threshold'  : 10,
            'stag_severe'     : 25,
            'stag_sc1_timeout': 40,

            # Placement Attempts
            'randomize_attempts': 60,
            'phase1_end'        : 35,
            'phase2_end'        : 45,
            'phase3_end'        : 55,

            # Local Search
            'ls_max_attempts' : 250,      
            'ls_max_violators': 25,

            # Threading
            'max_workers'     : min(cpu_count, 8),

            # GA Generations
            'target_gens'     : 6000,     # Fast High-End
            'soft_gens'       : 1500,
            'pop_boost'       : 1.5,
        }

    # ── BALANCED MODE (4-7 Cores) ────────────────────────────────────────
    elif cpu_count >= 4:
        profile = {
            'label'           : f"Mid-Range CPU ({cpu_count} Cores)",
            'mode'            : 'Balanced',
            'score'           : cpu_count,

            # Population & Offspring — Fix 8: Increased for wider search space
            'pop_size'        : 85,       
            'hard_offspring'  : 40,
            'lns_offspring'   : 25,
            'offspring_count' : 32,

            # Stagnation Thresholds
            'stag_threshold'  : 12,
            'stag_severe'     : 28,
            'stag_sc1_timeout': 45,

            # Placement Attempts
            'randomize_attempts': 50,
            'phase1_end'        : 28,
            'phase2_end'        : 38,
            'phase3_end'        : 48,

            # Local Search
            'ls_max_attempts' : 150,
            'ls_max_violators': 18,

            # Threading
            'max_workers'     : min(cpu_count, 4),

            # GA Generations
            'target_gens'     : 4500,    
            'soft_gens'       : 1000,
            'pop_boost'       : 1.3,
        }

    # ── EFFICIENCY MODE (< 4 Cores) ──────────────────────────────────────
    else:
        profile = {
            'label'           : f"Low-End CPU ({cpu_count} Cores)",
            'mode'            : 'Efficiency',
            'score'           : cpu_count,

            # Population & Offspring — Fix 8: Increased 40→65 for wider search space
            'pop_size'        : 65,
            'hard_offspring'  : 28,
            'lns_offspring'   : 16,
            'offspring_count' : 20,

            # Stagnation Thresholds
            'stag_threshold'  : 15,
            'stag_severe'     : 35,
            'stag_sc1_timeout': 60,

            # Placement Attempts
            'randomize_attempts': 60,
            'phase1_end'        : 25,
            'phase2_end'        : 40,
            'phase3_end'        : 55,

            # Local Search
            'ls_max_attempts' : 100,
            'ls_max_violators': 12,

            # Threading
            'max_workers'     : min(cpu_count, 2),

            # GA Generations
            'target_gens'     : 3000,    
            'soft_gens'       : 800,
            'pop_boost'       : 1.2,
        }
    
    print(f"Selected Mode: {profile['mode']} ({profile['label']})")
    print(f"---------------------------\n")
    return profile

# --- CONFIGURATION ---
# POPULATION_SIZE is now computed dynamically inside run_algorithm() based on
# total gene count: max(40, min(150, n_genes × 0.35)).  A static fallback is
# kept here only for code paths that reference it before the scheduler runs.
POPULATION_SIZE   = 40       
OFFSPRING_COUNT   = 15       
HARD_OFFSPRING    = 20       
LNS_OFFSPRING     = 12        
MAX_GENERATIONS   = 3000     
SOFT_REFINE_GENS  = 800      

# Stagnation thresholds
STAG_THRESHOLD    = 15        
STAG_SEVERE       = 35        
STAG_SC1_TIMEOUT  = 60        

# Diversity injection — fire when ≥65% of population share identical (HC, SS)
# Lowered from 0.85 → 0.65: inject BEFORE population fully converges (not after)
DIV_THRESHOLD     = 0.65     # similarity ratio to trigger injection
DIV_COOLDOWN      = 8        # minimum gens between consecutive injections (was 20)

# Penalty weights (for combined fitness display; NSGA-II uses HC + SS as separate objectives)
HC_PENALTY        = 1_000_000
SC1_BASE          = 100
SC2_BASE          = 1

# Thread pool size for parallel chromosome evaluation
# Explicitly limited to 2 workers for 2-core CPU to avoid overhead.
_N_WORKERS = 2


# ─────────────────────────────────────────────────────────────────────────────
# Helper (standalone, no self needed) — Mathematical Break Enforcer
# Checks if the provided daily bitmask violates the 6-Hour Max Consecutive 
# limit OR the 1-Hour Minimum Gap rule.
# ─────────────────────────────────────────────────────────────────────────────
def _is_valid_break_mask(mask):
    """
    Returns False if the daily schedule mask contains:
    1. A streak of 13 consecutive slots (>6 hours) -> '1111111111111'
    2. An isolated 1-slot gap (30 minutes) -> '101'
    """
    b = bin(mask)[2:]
    if '1111111111111' in b: return False
    if '101' in b: return False
    return True

# ─────────────────────────────────────────────────────────────────────────────
# Helper (standalone, no self needed) — finds first free window of `slots`
# slots inside a room-day given a combined occupancy bitmask.
# Returns start slot or -1.  Steps by 2 (hourly alignment).
# ─────────────────────────────────────────────────────────────────────────────
def _compact_gap_scan(combined_mask, slots, total_slots, start_from=0):
    """
    Bitwise scan for the first `slots`-wide clear window inside `combined_mask`.

    combined_mask : room | fac | sec | blocked bits OR'd together
    slots         : number of 30-min slots needed
    total_slots   : upper bound of the day
    start_from    : skip positions below this (for Lab-after-Lec enforcement)

    Returns first clear start (even), or -1 if none.
    """
    mask_needed = (1 << slots) - 1
    # Align start_from to next even slot
    s = start_from if start_from % 2 == 0 else start_from + 1
    while s + slots <= total_slots:
        window = mask_needed << s
        if (combined_mask & window) == 0:
            return s
        # Jump past the blocking bit for speed
        # Find the highest set bit inside the window that conflicts
        conflict = combined_mask & window
        # bit_length() - 1 gives the position of the highest set bit
        highest_conflict = conflict.bit_length() - 1
        # Next candidate must start AFTER highest_conflict and be at least s + 2, aligned to even
        next_s = max(s + 2, highest_conflict + 1)
        s = next_s if next_s % 2 == 0 else next_s + 1
    return -1


class Gene:
    __slots__ = ('course_id', 'section_id', 'faculty_id', 'room_id',
                 'day_idx', 'start_idx', 'duration_slots', 'end_idx',
                 'gene_type', 'is_fixed', 'bitmask', 'locked_day',
                 'allowed_mask')

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
        self.allowed_mask   = None # [day0_mask, day1_mask, ...] for static constraint bitmasking


class Chromosome:
    __slots__ = ('genes', 'fitness', 'hard_conflicts', 'soft_score',
                 'conflicting_indices', 'rank', 'crowding_distance',
                 'sc1_violations', 'sc2_violations', 'violation_codes',
                 '_violated_indices', '_occ_room', '_occ_fac', '_occ_sec',
                 '_soft_violators_cache', '_soft_cache_gen', '_eval_gen')

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
        self.violation_codes     = set() # Specific codes like HC-01, SC-02 currently active
        self._violated_indices   = []
        self._occ_room           = None  # Memory for Delta Fitness (Phase 4)
        self._occ_fac            = None
        self._occ_sec            = None
        self._soft_violators_cache = None
        self._soft_cache_gen       = -1
        self._eval_gen             = -1


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
    # PRE-FEASIBILITY CHECK (Greedy FFD Room Assessment)                 #
    # ------------------------------------------------------------------ #
    # ------------------------------------------------------------------ #
    # 3-LEVEL PRE-FEASIBILITY CHECK (Greedy FFD)                         #
    # ------------------------------------------------------------------ #
    def check_room_feasibility(self):
        """
        3-Level Pre-Feasibility Check (Greedy FFD).
        Level 1 - Raw:          Pure capacity math, no constraints
        Level 2 - Realistic:    With section day-spread + consecutive limits
        Level 3 - Conservative: 60% room utilization cap (real-world buffer)
        """
        from collections import defaultdict
        n_days      = len(self.days)
        total_slots = self.total_slots

        # ── Step 1: Build all sessions ──────────────────────────────────────
        sessions = []
        for section in self.sections:
            sec_id   = section['id']
            sec_name = section.get('section_name', '?')
            for course_id in section.get('course_ids', []):
                course = self.course_map.get(course_id)
                if not course: continue
                dept = course.get('department', '')
                ccode = course.get('course_code', '?')
                lec = (course.get('synchronous_lec_hours', 0) or course.get('lec_units', 0)) or 0
                lab = (course.get('synchronous_lab_hours', 0) or course.get('lab_units', 0)) or 0
                asy = (course.get('asynchronous_lec_hours', 0) or 0) + (course.get('asynchronous_lab_hours', 0) or 0)

                if lec > 0:
                    sessions.append({'course_id': course_id, 'section_id': sec_id, 'course_code': ccode, 'sec_name': sec_name, 'type': 'Lec', 'slots': int(lec * 2), 'dept': dept})
                if lab > 0:
                    sessions.append({'course_id': course_id, 'section_id': sec_id, 'course_code': ccode, 'sec_name': sec_name, 'type': 'Lab', 'slots': int(lab * 2), 'dept': dept})
                # Note: Async removed from physical feasibility check per user request (online rooms can overlap)

        # Sort longest first (FFD principle)
        sessions.sort(key=lambda s: -s['slots'])
        total_sessions = len(sessions)

        # ── Step 2: Helper Functions ────────────────────────────────────────
        def _build_room_occ(cap_ratio=1.0):
            occ = {}
            for r in self.rooms:
                if (r.get('status') != 'Available' or r['id'] in self.tba_room_ids):
                    continue
                
                # Initialize with blocked slots from Admin Settings
                day_masks = [self._blocked_bitmasks.get(d, 0) for d in range(n_days)]
                
                if cap_ratio < 1.0:
                    usable = int(total_slots * cap_ratio)
                    if usable < total_slots:
                        # Add buffer mask to the top slots
                        block_mask = ((1 << (total_slots - usable)) - 1) << usable
                        for d in range(n_days):
                            day_masks[d] |= block_mask
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
                    # Sync Lec
                    valid = (self._dept_rooms_lec_only.get(sess['dept']) or self._valid_rooms_lec_only)
                    # Exclude Online Room for Sync Lec
                    valid = [r for r in valid if r not in self.online_room_ids]
                
                # Double check for Lab as well (should already be physical but let's be sure)
                if gtype == 'Lab':
                    valid = [r for r in valid if r not in self.online_room_ids]
                
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
                                if sec_day_slots is not None:
                                    sec_day_slots[(sec_id, day)] = sec_day_slots.get((sec_id, day), 0) + slots_needed
                                placed.append(sess); fitted = True; break
                        if fitted: break
                    if fitted: break
                if not fitted: overflow.append(sess)
            return placed, overflow

        def _room_util_stats(occ_rooms, cap_ratio=1.0):
            stats = {}
            usable_per_room = int(total_slots * cap_ratio) * n_days
            for rid, day_masks in occ_rooms.items():
                used = sum(bin(m).count('1') for m in day_masks)
                pre_blocked = (total_slots - int(total_slots * cap_ratio)) * n_days
                actual_used = max(0, used - pre_blocked)
                pct = round(actual_used / max(usable_per_room, 1) * 100, 1)
                rname = self.room_map.get(rid, {}).get('room_name', rid)
                stats[rid] = {'name': rname, 'utilization': pct}
            return stats

        def _overflow_details(overflow_list):
            details = defaultdict(list)
            for s in overflow_list: details[f"{s['course_code']} ({s['type']})"].append(s['sec_name'])
            return dict(details)

        def _rooms_needed(overflow_list, gtype_filter):
            filtered = [s for s in overflow_list if s['type'] == gtype_filter]
            total_sl = sum(s['slots'] for s in filtered)
            slots_avail = int(total_slots * 0.75) * n_days # 75% estimate
            return max(0, -(-total_sl // max(slots_avail, 1)))

        # ── Step 3: Run 3 Levels ───────────────────────────────────────────
        # L1: Raw
        occ_l1 = _build_room_occ(1.0); p1, o1 = _greedy_place(occ_l1)
        # L2: Realistic (Max 12 slots/day per section = 6hrs)
        occ_l2 = _build_room_occ(1.0); s_tracker = {}; p2, o2 = _greedy_place(occ_l2, s_tracker, 12)
        # L3: Conservative (60% utilization)
        occ_l3 = _build_room_occ(0.60); p3, o3 = _greedy_place(occ_l3)

        # ── Step 4: Build Report ───────────────────────────────────────────
        def _pct(n): return round(n / max(total_sessions, 1) * 100, 1)

        extra_lec = _rooms_needed(o2, 'Lec'); extra_lab = _rooms_needed(o2, 'Lab')
        
        # Build Summary
        n1, n2, n3 = len(o1), len(o2), len(o3)
        if n1 == 0 and n2 == 0 and n3 == 0:
            status, message = 'GREEN', 'All sessions fit comfortably. Sufficient capacity.'
        elif n1 == 0 and n2 == 0 and n3 > 0:
            status, message = 'YELLOW', 'Rooms are sufficient but running close to real-world limits.'
        elif n1 == 0 and n2 > 0:
            status, message = 'ORANGE', f'Mathematically enough but constraints cause {n2} overflow(s). Suggest adding {extra_lec} Lec / {extra_lab} Lab rooms.'
        else:
            status, message = 'RED', f'Critically insufficient. {n1} sessions cannot fit even at full capacity.'

        return {
            'total_sessions': total_sessions,
            'summary': {'status': status, 'message': message, 'tba_expected': n2 > 0},
            'levels': {
                'l1': {'label': 'Raw Capacity', 'feasible': n1 == 0, 'overflow': n1, 'details': _overflow_details(o1), 'utilization': _room_util_stats(occ_l1, 1.0)},
                'l2': {'label': 'Realistic', 'feasible': n2 == 0, 'overflow': n2, 'details': _overflow_details(o2), 'utilization': _room_util_stats(occ_l2, 1.0), 'needed': {'lec': extra_lec, 'lab': extra_lab}},
                'l3': {'label': 'Conservative', 'feasible': n3 == 0, 'overflow': n3, 'details': _overflow_details(o3), 'utilization': _room_util_stats(occ_l3, 0.60)}
            }
        }

    def _suggest_rooms(self, n_overflow):
        """Estimate additional rooms needed based on overflow count."""
        slots_per_room = self.total_slots * len(self.days)
        # Assume average session is 2 hours (4 slots)
        needed_slots = n_overflow * 4
        return max(1, round(needed_slots / slots_per_room) + 1)

    # ------------------------------------------------------------------ #
    # INITIALIZATION                                                       #
    # ------------------------------------------------------------------ #
    def __init__(self, courses, sections, faculty, rooms, pre_assignments,
                 constraints_config, start_time=7, end_time=20, allowed_days=None,
                 split_assignments=None, fa_map=None, blocked_slots=None, evening_start_hour=19):
        self.hardware_profile = get_hardware_profile()
        hw = self.hardware_profile  # shortcut

        self.max_workers = hw['max_workers']

        # I-assign globally para ma-access ng ibang methods
        self._hw_pop_size         = hw['pop_size']
        self._hw_hard_offspring   = hw['hard_offspring']
        self._hw_lns_offspring    = hw['lns_offspring']
        self._hw_offspring_count  = hw['offspring_count']
        self._hw_stag_threshold   = hw['stag_threshold']
        self._hw_stag_severe      = hw['stag_severe']
        self._hw_stag_sc1_timeout = hw['stag_sc1_timeout']
        self._hw_rand_attempts    = hw['randomize_attempts']
        self._hw_phase1_end       = hw['phase1_end']
        self._hw_phase2_end       = hw['phase2_end']
        self._hw_phase3_end       = hw['phase3_end']
        self._hw_ls_max_attempts  = hw['ls_max_attempts']
        self._hw_ls_max_violators = hw['ls_max_violators']
        self.courses     = courses
        self.sections    = sections
        self.faculty     = faculty
        self.rooms       = rooms
        self.constraints = constraints_config

        # Adaptive SC-II weight (Step 5). Starts at SC2_BASE (100), climbs to 500
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
        self.evening_start_hour = evening_start_hour
        self.total_slots = (evening_start_hour - start_time) * 2
        
        # Pre-calculate signal file path for high-frequency stop checks
        self.sig_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ga_stop.signal")

        # Quick-lookup maps
        self.room_map    = {r['id']: r for r in rooms}
        self.course_map  = {c['id']: c for c in courses}
        self.section_map = {s['id']: s for s in sections}
        self.faculty_map = {f['id']: f for f in faculty}
        self.faculty_ids = [f['id'] for f in faculty]
        # Department lookup per faculty — normalized for cross-format comparison
        self._fac_dept = {f['id']: _norm_dept(f.get('department', '')) for f in faculty}

        # Pre-cache metadata for TBA Hybrid system
        self._room_types = {r['id']: r.get('room_type', 'Sync') for r in rooms}
        self._fac_status = {f['id']: f.get('assignment_status', 'Announced') for f in faculty}
        self._is_fac_tba = {f['id']: (f.get('assignment_status', 'Announced') == 'TBA') for f in faculty}

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

        # Pre-cache section available day indices
        self._sec_avail_days = {}
        for s in sections:
            avail_str = s.get('available_days', '')
            if avail_str:
                avail_set = set()
                for day in avail_str.split(','):
                    day = day.strip()
                    if day in self.day_map:
                        avail_set.add(self.day_map[day])
                if avail_set:
                    self._sec_avail_days[s['id']] = avail_set

        # Precompute time-boundary slots
        self.noon_slot          = (12 - start_time) * 2
        self.eve_slot           = (18 - start_time) * 2
        self._last_day          = len(self.days) - 1
        # SC-I-09: first class per room must start within 1 hour of system start
        # slot 0 = start_time, slot 1 = start+30min, slot 2 = start+1hr (VIOLATION)
        self._max_first_slot    = 1   # max allowed start slot for first class in a room
        # Lunch window: 10am–2pm — each section must have ≥1 free hour in this range
        self.lunch_window_start = (10 - start_time) * 2   # 10am
        self.lunch_window_end   = (14 - start_time) * 2   # 2pm

        self.tba_room_ids = {r['id'] for r in rooms if r.get('room_name', '') == 'T.B.A.'}
        self.online_room_ids = {r['id'] for r in rooms if r.get('room_name', '') == 'Online Room'}
        self.online_room_id = next(iter(self.online_room_ids), None)

        # Pre-cache valid rooms by gene_type (computed once)
        available  = [r['id'] for r in rooms if r.get('status') == 'Available' and r['id'] not in self.tba_room_ids and r['id'] not in self.online_room_ids]
        lab_rooms  = [r['id'] for r in rooms if r.get('status') == 'Available'
                      and 'Computer Lab' in r.get('capabilities', '') and r['id'] not in self.tba_room_ids and r['id'] not in self.online_room_ids]
        all_rooms  = [r['id'] for r in rooms if r['id'] not in self.tba_room_ids and r['id'] not in self.online_room_ids]
        self.async_room_ids = {r['id'] for r in rooms if r.get('room_type') == 'Async' and r['id'] not in self.tba_room_ids and r['id'] not in self.online_room_ids}
        self._valid_rooms_lec   = available if available else all_rooms
        self._valid_rooms_lab   = lab_rooms  if lab_rooms  else (available if available else all_rooms)
        self._valid_rooms_async = list(self.async_room_ids) if self.async_room_ids else (list(self.online_room_ids) if self.online_room_ids else self._valid_rooms_lec)
        self._valid_rooms_fixed = all_rooms

        # Sequential Priority Lists for greedy packing
        self._seq_lab_rooms = sorted(lab_rooms)
        self._seq_lec_rooms = sorted([rid for rid in available if rid not in lab_rooms])

        # Identify rooms that allow multiple simultaneous assignments:
        # - University Field/Court/Gym/Playground (outdoor/NSTP/PE), T.B.A. (placeholder — admin resolves later)
        self.multi_assignment_rooms = (
            {r['id'] for r in rooms if any(word in r.get('room_name', '').upper() for word in ['FIELD', 'COURT', 'GYM', 'PLAYGROUND'])}
            | self.tba_room_ids
            | self.online_room_ids
        )
        
        # Identify faculty that allow multiple simultaneous assignments (e.g., T.B.A.)
        self.multi_assignment_faculty = {f['id'] for f in faculty if 'T.B.A.' in f.get('full_name', '').upper() or f.get('assignment_status') == 'TBA'}

        # Lecture-only rooms (non-Computer-Lab) for packed lecture scheduling.
        # Lecture subjects fill these first (daytime), then evening slots, then lab rooms as last resort.
        # T.B.A. room has 'Lecture,Computer Lab' so it's excluded from lec_only by capability filter;
        # add it back explicitly since T.B.A. is a universal fallback for any gene type.
        lec_only = [r['id'] for r in rooms if r.get('status') == 'Available'
                    and 'Computer Lab' not in r.get('capabilities', '') and r.get('room_name', '') != 'T.B.A.']
        self._valid_rooms_lec_only = lec_only if lec_only else (available if available else all_rooms)
        self._lec_room_set = set(self._valid_rooms_lec_only)

        # evening start slot — boundary between daytime and evening for room priority and avoidance penalty.
        # Defaults to 19 (7:00 PM) but can be adjusted dynamically by the admin settings.
        self.seven_pm_slot = (evening_start_hour - start_time) * 2

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

        # Hourly Alignment Rule: ensures classes start on clean 1-hour boundaries
        # (slot 0=7am, 2=8am, 4=9am, 6=10am, 8=11am, 10=12pm, 12=1pm, 14=2pm, ...).
        # This is now enforced for ALL synchronous classes to prevent 30-min gaps.
        self._use_hourly_alignment = True

        # Room departments: if a room has department restrictions, only matching-dept courses can use it.
        # Empty/blank room_departments = available to all departments.
        self._room_depts = {}  # room_id -> set of dept names (empty set = no restriction = all depts)
        for r in rooms:
            rd_str = r.get('room_departments', '') or ''
            self._room_depts[r['id']] = {_norm_dept(d) for d in rd_str.split(',') if d.strip()}

        # ── DYNAMIC ROOM IDLE GAP THRESHOLD ──────────────────────────────────
        # Short-circuit scan for 1-hour subjects. If found, any 1-hour gap is useful.
        # Only 30-min gaps become 'idle'. Otherwise, gaps up to 1.5h are penalized.
        min_h = 2.0
        for c in courses:
            if c.get('synchronous_lec_hours', 0) == 1.0 or c.get('synchronous_lab_hours', 0) == 1.0:
                min_h = 1.0
                break
        self._idle_gap_threshold_slots = 3 if min_h >= 2.0 else 1

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
                return not rd or _norm_dept(dept) in rd
            # Strict Exclusivity: Remove fallback to all_rooms if no dept rooms found.
            # This ensures department rooms remain private.
            self._dept_rooms_lec[dept]      = [rid for rid in self._valid_rooms_lec      if _eligible(rid)]
            self._dept_rooms_lab[dept]      = [rid for rid in self._valid_rooms_lab      if _eligible(rid)]
            self._dept_rooms_lec_only[dept] = [rid for rid in self._valid_rooms_lec_only if _eligible(rid)]

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
                     'LEC_LAB_WEEKLY_DIST',
                     'MAX_CONSECUTIVE_STUDENT', 'MAX_CONSECUTIVE_FACULTY',
                     'LEC_LAB_SEQUENCE',
                     'MIN_DAILY_SECTION_LOAD',
                     'FACULTY_AVAILABILITY',
                     'GLOBAL_DAY_RESTRICTION',
                     'HOURLY_ALIGNMENT', 'COMPLETE_COURSE_SCHEDULING',
                     'STRICT_LEC_DURATION', 'STRICT_LAB_DURATION',
                     'STRICT_ASYNC_LEC_DUR', 'STRICT_ASYNC_LAB_DUR',
                     'FACULTY_DAY_SPLIT',
                     'VIRTUAL_ROOM_USAGE', 'ROOM_IDLE_GAP',
                     'STRICT_ALLOC_ASYNC', 'STRICT_ALLOC_LEC', 'STRICT_ALLOC_LAB', 'LEC_IN_LAB_FALLBACK'):
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

        # ── HC-24 IMPOSSIBILITY FILTER ────────────────────────────────────────
        # Pre-compute the total weekly scheduled hours for each section.
        # Sections with total weekly hours < 6 (< 12 slots) can NEVER satisfy
        # HC-24 (min 3 hrs/active day) — no matter where their genes are placed.
        # These are marked as exempt to prevent the GA from looping forever on
        # a mathematically unsolvable constraint. This is computed ONCE at init.
        _sec_total_slots = defaultdict(int)
        for _sec in sections:
            _sid = _sec['id']
            for _cid in _sec.get('course_ids', []):
                _dur_lec = self._expected_duration.get((_cid, 'Lec'), 0)
                _dur_lab = self._expected_duration.get((_cid, 'Lab'), 0)
                _sec_total_slots[_sid] += _dur_lec + _dur_lab
        # Sections with < 6 slots total (< 3 hours) are impossibly exempt.
        self._hc24_exempt_sections = frozenset(
            _sid for _sid, _slots in _sec_total_slots.items() if _slots < 6
        )


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

        self._sc2_base = 10 
        self.seven_pm_slot = (self.evening_start_hour - self.start_hour) * 2
        self.five_pm_slot  = (17 - self.start_hour) * 2  # 5:00 PM
        self._virtual_room_set = set(self.tba_room_ids) | self.online_room_ids
        for r in rooms:
            if 'TBA' in (r.get('room_name', '') or '').upper() or 'VIRTUAL' in (r.get('room_name', '') or '').upper():
                self._virtual_room_set.add(r['id'])

        # --- CONTINUOUS ENGINE VARIABLES ---
        self.background_mode    = False     # False = Active (Full Speed), True = Background (Throttled)
        self.pending_injections = []        # Queue for dynamic data (Courses/Sections)
        self.is_running         = False     # Flag for the background loop
        self.is_paused          = False     # Internal lock during injection
        self.force_stop         = False     # [NEW] Absolute Memory Kill-Switch

        # --- PHASE 3: Lec-Lab Pairing Lookup ---
        # Maps (section_id, course_id) -> {'Lec': gene_idx, 'Lab': gene_idx}
        # Built once at the start of evolution.
        self._lec_lab_pair_map = {}

        # --- PERFORMANCE BITMASKS ---
        # LWS (Lunch Window Start) is slot 6 (10 AM), LWE (End) is slot 14 (2 PM)
        # We find if there is at least a 1-hour (2-slot) gap in this window using bitwise logic.
        self._lunch_window_mask = ((1 << (self.lunch_window_end - self.lunch_window_start)) - 1) << self.lunch_window_start

        # ------------------------------------------------------------------ #
        # CONSTRAINT MAPPING (Internal Key -> Display Code)                  #
        # ------------------------------------------------------------------ #
        self.CONSTRAINT_MAP = {
            # --- HARD CONSTRAINTS (HC-01 to HC-28) ---
            # A1: Built-In / Structural Hard Constraints (HC-01 to HC-20)
            'LOCKED_SCHEDULES':           'HC-01',
            'GLOBAL_DAY_RESTRICTION':     'HC-02',
            'STRICT_LEC_DURATION':        'HC-03',
            'STRICT_LAB_DURATION':        'HC-04',
            'STRICT_ASYNC_LEC_DUR':       'HC-05',
            'STRICT_ASYNC_LAB_DUR':       'HC-06',
            'SECTION_OVERLAP':            'HC-07',
            'FACULTY_OVERLAP':            'HC-08',
            'ROOM_OVERLAP':               'HC-09',
            'SINGLE_FACULTY_PER_TIMESLOT':'HC-10',
            'FACULTY_AVAILABILITY':       'HC-11',
            'SINGLE_ROOM_PER_SESSION':    'HC-12',
            'ROOM_AVAILABILITY':          'HC-13',
            'OPERATING_HOURS':            'HC-14',
            'HOURLY_ALIGNMENT':           'HC-15',
            'COMPLETE_COURSE_SCHEDULING': 'HC-16',
            'PREASSIGNMENT_EXCLUSIVITY':  'HC-17',
            'FACULTY_DAY_SPLIT':          'HC-18',
            'LUNCH_BREAK':                'HC-19',

            # A2: Evaluated Hard Constraints (HC-20 to HC-25)
            'MAX_CONSECUTIVE_STUDENT':    'HC-20',
            'MAX_CONSECUTIVE_FACULTY':    'HC-21',
            'MIN_DAILY_SECTION_LOAD':     'HC-22',
            'LEC_IN_LAB_FALLBACK':        'HC-23',
            'LEC_LAB_SEQUENCE':           'HC-24',
            'ROOM_SUITABILITY':           'HC-25',

            # --- SOFT CONSTRAINTS I (SC-I-01 to SC-I-05) ---
            'VIRTUAL_ROOM_USAGE':         'SC-I-01',
            'EVENING_AVOIDANCE':          'SC-I-02',
            'ROOM_IDLE_GAP':              'SC-I-03',
            'LEC_LAB_WEEKLY_DIST':        'SC-I-04',

            # --- SOFT CONSTRAINTS II (SC-II-01 to SC-II-02) ---
            'ROOM_CAPACITY_PROPORTIONAL': 'SC-II-01'
        }

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

    def _adaptive_relax_constraints(self, severe_counter):
        """
        Temporarily relax soft penalties of highly-blocking constraints during
        severe stagnation (e.g. severe_counter >= 15) to expand search space
        and help the crossovers/local-search escape local minima.
        """
        if severe_counter >= 15:
            # Relax room suitability, proportional capacity, and max consecutive loads
            for code in ('ROOM_SUITABILITY', 'ROOM_CAPACITY_PROPORTIONAL', 
                         'MAX_CONSECUTIVE_STUDENT', 'MAX_CONSECUTIVE_FACULTY',
                         'LEC_LAB_SEQUENCE'):
                if code in self._pen:
                    self._pen[code] = max(1, self._penalty(code) // 4)
            print(f"⚠️ Stagnation counter={severe_counter}. Adaptive Constraint Relaxation active.")

    def _rebuild_penalties(self):
        """
        Restore original full penalties to self._pen.
        """
        for code in list(self._pen.keys()):
            self._pen[code] = self._penalty(code)

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
        return self._valid_rooms_async  # Async

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
            # 3-hour lectures → lab rooms
            return self._dept_rooms_lab.get(dept) or self._valid_rooms_lab
        if gene.gene_type == 'Lec':
            return self._dept_rooms_lec_only.get(dept) or self._valid_rooms_lec_only
        return self._valid_rooms_async  # Async

    def _smart_start(self, slots_needed, allow_evening=None, even_only=True):
        """
        Return a smart start slot with optional slot alignment constraints.

        even_only:    only even-numbered slots — eliminates 7:30/8:30/9:30 am starts
        allow_evening: if True, include slots from 7pm (seven_pm_slot) onwards

        Weights: morning 4×, lunch 2×, afternoon 4×, evening 3× (if allow_evening).
        Daytime band extends to 7pm (seven_pm_slot); evening = 7pm–close.
        """
        if allow_evening is None:
            allow_evening = (self._pen_type.get('EVENING_AVOIDANCE', 'SC1') == 'NC')
        if even_only:
            valid = lambda s: s % 2 == 0
        else:
            valid = lambda s: True

        # Cache attributes for speed (LOAD_FAST vs LOAD_ATTR)
        total_slots = self.total_slots
        lws         = self.lunch_window_start  # 10am
        lwe         = self.lunch_window_end    # 2pm
        day_upper   = self.seven_pm_slot       # 7pm = daytime/evening split
        
        max_start  = max(0, total_slots - slots_needed)

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
        # SPECIAL: For 3-hour lectures (>= 6 slots), give 7 AM (0) and 1 PM (12) a massive 100x bonus.
        if slots_needed >= 6:
            m_pool = [s for s in morning if s == 0] * 100 + [s for s in morning if s != 0] * 4
            a_pool = [s for s in afternoon if s == 12] * 100 + [s for s in afternoon if s != 12] * 4
            pool = m_pool + lunch_zone * 2 + a_pool + evening * 3
        else:
            pool = morning * 4 + lunch_zone * 2 + afternoon * 4 + evening * 3

        if pool:
            return random.choice(pool)
        # Fallback: any valid slot in full range
        fallback = [s for s in range(0, max_start + 1) if valid(s)]
        _eve_mode = self._pen_type.get('EVENING_AVOIDANCE', 'NC')
        if _eve_mode == 'HC':
            fallback = [s for s in fallback if s < self.seven_pm_slot]
        if fallback:
            return random.choice(fallback)
        return random.randint(0, max(0, min(max_start, self.seven_pm_slot - 1 if _eve_mode == 'HC' else max_start)))

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
        # Cache attributes for speed
        sec_stu  = self._sec_students
        rm       = self.room_map
        students = sec_stu.get(section_id, 0)

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

        top_k = min(2, len(valid_ids)) # Reduced from 5 to be greedier (Bin Packing)
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
                total = 0
                for d in range(days_count):
                    total += occ_room.get((rid, d), 0).bit_count()
                return total
            warm_scores = [warmth(rid) for rid in candidates]
            max_warm    = max(warm_scores) if any(warm_scores) else 1
            # Blend: 5% utilization-squared + 95% warmth bonus (STRICTLY Prioritize occupied rooms for clustering)
            combined = [w * (0.05 + 0.95 * (ws / max(max_warm, 1))) for w, ws in zip(weights, warm_scores)]
            return random.choices(candidates, weights=combined, k=1)[0]

    def _get_soft_violators(self, chromosome, generation):
        """Cache-backed retrieval of soft violators for a chromosome.
        Invalidates and recalculates when the generation ID mismatch is detected.
        """
        if (chromosome._soft_violators_cache is None or 
                chromosome._soft_cache_gen != generation):
            chromosome._soft_violators_cache = self._find_soft_violation_indices(chromosome)
            chromosome._soft_cache_gen = generation
        return chromosome._soft_violators_cache

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
            # EVENING_AVOIDANCE: check if active as soft constraint (SC1 or SC2)
            _eve_mode = self._pen_type.get('EVENING_AVOIDANCE', 'NC')
            if _eve_mode in ('SC1', 'SC2') and g.start_idx >= seven_pm_slot and g.room_id not in self._virtual_room_set:
                violators_set.add(i)
                continue

            if g.gene_type == 'Async':
                if g.day_idx != 0 and g.day_idx != last_day:
                    violators_set.add(i); continue
            # SC-II-03: Room Capacity (SC2 — skip in sc1_only mode)
            if not sc1_only:
                r        = room_map.get(g.room_id)
                if r:
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
        sec_day_occ   = defaultdict(int)    # {(sec_id, day_idx): bitmask of occupied slots}
        fac_day_occ   = defaultdict(int)    # {(fac_id, day_idx): bitmask of occupied slots}
        sec_course    = defaultdict(dict)   # {(sec_id, course_id): {type: gene_idx}}
        for i, g in enumerate(genes):
            # Always accumulate occupancy (fixed or not)
            # Intersection of gene bits and lunch window
            bits_in_lunch = g.bitmask & self._lunch_window_mask
            if bits_in_lunch:
                sec_day_occ[(g.section_id, g.day_idx)] |= bits_in_lunch
                if g.faculty_id:
                    fac_day_occ[(g.faculty_id, g.day_idx)] |= bits_in_lunch
            if g.is_fixed:
                continue
            sec_day_genes[(g.section_id, g.day_idx)].append(i)
            if g.faculty_id:
                fac_day_genes[(g.faculty_id, g.day_idx)].append(i)
            if g.gene_type in ('Lec', 'Lab'):
                sec_course[(g.section_id, g.course_id)][g.gene_type] = i

        if not sc1_only:
            # SC-II-04: Lunch Break — check using bitmask for high speed
            # Find if there is at least a 1-hour (2-slot) free gap in the window.
            # "free" bits in window: (~occ & self._lunch_window_mask)
            for (sec_id, day_idx), idxs in sec_day_genes.items():
                occ = sec_day_occ.get((sec_id, day_idx), 0)
                free_in_window = (~occ) & self._lunch_window_mask
                # Check for 2 consecutive bits: (free & (free >> 1))
                if not (free_in_window & (free_in_window >> 1)):
                    for i in idxs:
                        g = genes[i]
                        if g.start_idx < lwe and g.end_idx > lws:
                            violators_set.add(i)

            for (fac_id, day_idx), idxs in fac_day_genes.items():
                occ = fac_day_occ.get((fac_id, day_idx), 0)
                free_in_window = (~occ) & self._lunch_window_mask
                if not (free_in_window & (free_in_window >> 1)):
                    for i in idxs:
                        g = genes[i]
                        if g.start_idx < lwe and g.end_idx > lws:
                            violators_set.add(i)

            # MIN_DAILY_SECTION_LOAD: find soft violators where total hours < 3.0
            p_mdl = self._pen.get('MIN_DAILY_SECTION_LOAD', 0)
            if p_mdl:
                for (sec_id, day_idx), idxs in sec_day_genes.items():
                    # EXEMPTION: If any class in this section-day is Async, it is exempted
                    if any(self._room_types.get(genes[_i].room_id) == 'Async' for _i in idxs):
                        continue
                    total_hrs = sum(genes[_i].duration_slots / 2 for _i in idxs)
                    if total_hrs < 3.0:
                        for _i in idxs:
                            violators_set.add(_i)

        # SC-I-01: LEC_LAB_WEEKLY_DIST (Lab placed before Lec day)
        # LEC_LAB_SEQUENCE: Lecture must be scheduled before Laboratory
        for type_map in sec_course.values():
            lec_i = type_map.get('Lec')
            lab_i = type_map.get('Lab')
            if lec_i is None or lab_i is None:
                continue
            lec_g = genes[lec_i]
            lab_g = genes[lab_i]
            if lab_g.day_idx < lec_g.day_idx:
                violators_set.add(lab_i)
            if (lab_g.day_idx < lec_g.day_idx or 
                (lab_g.day_idx == lec_g.day_idx and lab_g.start_idx < lec_g.start_idx)):
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
    def _add_to_occ(gene, occ_room, occ_fac, occ_sec):
        mask = gene.bitmask
        d = gene.day_idx
        occ_room[(gene.room_id, d)] |= mask
        if gene.faculty_id is not None:
            occ_fac[(gene.faculty_id, d)] |= mask
        occ_sec[(gene.section_id, d)] |= mask

    @staticmethod
    def _remove_from_occ(gene, occ_room, occ_fac, occ_sec):
        mask = ~gene.bitmask
        d = gene.day_idx
        occ_room[(gene.room_id, d)] &= mask
        if gene.faculty_id is not None:
            occ_fac[(gene.faculty_id, d)] &= mask
        occ_sec[(gene.section_id, d)] &= mask

    def _calculate_delta_hc(self, chromosome, gene_idx, old_day, old_room, old_mask, 
                             new_day, new_room, new_mask):
        """
        Phase 4: O(1) Hard Conflict Delta.
        Returns: (change_in_hc_count, set_of_newly_conflicting_indices)
        """
        if chromosome._occ_room is None: return 0, set() # Fallback if no state
        
        occ_r, occ_f, occ_s = chromosome._occ_room, chromosome._occ_fac, chromosome._occ_sec
        gene = chromosome.genes[gene_idx]
        fid, sid = gene.faculty_id, gene.section_id
        
        # 1. Remove old conflicts (XOR out old gene bits)
        # 2. Check for new conflicts at target position
        new_hc = 0
        if (occ_r.get((new_room, new_day), 0) & new_mask) != 0: new_hc += 1
        if fid and (occ_f.get((fid, new_day), 0) & new_mask) != 0: new_hc += 1
        if (occ_s.get((sid, new_day), 0) & new_mask) != 0: new_hc += 1
        
        # Simple delta for now: if new position is busy, it's a conflict.
        # (This is a heuristic delta for high-speed mutation)
        return new_hc

    def _get_density_guided_days(self, sec_id, occ_sec, min_day=0, priority_day=-1):
        """
        Returns days sorted by section activity density to cluster classes.
        - Priority 1: Active days with remaining space (0 < load < 12 slots/6 hours), sorted descending to pack them first.
        - Priority 2: Saturated days (load >= 12 slots) placed second to prevent consecutive hour violations.
        - Priority 3: Completely empty days (load == 0) sorted last to keep them free and prevent isolated slots.
        Optimized to be memory-free by doing on-the-fly bit_count lookups.
        HC-24 GUARD: priority_day is injected at position 0 so it is always
        tried first — keeps genes on their source day when removing would
        drop section hours below the 3hr (6 slot) HC-24 minimum.
        """
        days_count = len(self.days)

        def _density_key(d):
            load = occ_sec.get((sec_id, d), 0).bit_count()
            if load == 0:
                return (2, 0)
            elif load >= 12:
                return (1, -load)
            else:
                return (0, -load)

        sorted_days = sorted(range(days_count), key=_density_key)

        # ── HC-24 SOURCE DAY GUARD: try priority_day first ─────────────────────
        if priority_day >= 0 and priority_day in sorted_days:
            sorted_days.remove(priority_day)
            sorted_days.insert(0, priority_day)

        # Apply min_day constraints if passed
        if min_day > 0:
            sorted_days = [d for d in sorted_days if d >= min_day]
            if not sorted_days:
                sorted_days = list(range(min_day, days_count))

        return sorted_days

    def create_genome(self, skip_exhaustive=False):
        """
        Tiered FFD Greedy Packer with gap-filling and multi-pass reclaim.

        Sort order (most-constrained first):
          1. Labs before Lecs
          2. Longest first within type
          3. MRV tie-break: fewest eligible rooms → scheduled first

        Room tiers:
          Lab  → lab rooms → lec rooms (penultimate) → online (last)
          Lec  → lec rooms → lab rooms (penultimate) → online (last)
          Both: async-designated physical rooms are EXCLUDED
        """
        genes = [self._copy_gene(g) for g in self.fixed_genes]
        occ_room, occ_fac, occ_sec = self._build_occ_sets(genes)

        # ── Step 1: Collect sessions ───────────────────────────────────────
        assignments = []
        fixed_set = {(g.course_id, g.section_id) for g in genes if g.is_fixed}

        for section in self.sections:
            sec_id = section['id']
            for course_id in section['course_ids']:
                if (course_id, sec_id) in fixed_set:
                    continue
                course = self.course_map.get(course_id)
                if not course:
                    continue
                lec = (course.get('synchronous_lec_hours', 0)
                       or course.get('lec_units', 0)) or 0
                lab = (course.get('synchronous_lab_hours', 0)
                       or course.get('lab_units', 0)) or 0
                dept = course.get('department', '')
                # Lecture splits
                lec_splits = self.split_map.get((course_id, sec_id, 'Lec'))
                if lec_splits:
                    for didx, slots, faculty_id in lec_splits:
                        assignments.append({
                            'cid': course_id, 'sid': sec_id,
                            'slots': slots, 'type': 'Lec', 'dept': dept,
                            'locked_day': didx, 'faculty_id': faculty_id
                        })
                elif lec > 0:
                    assignments.append({
                        'cid': course_id, 'sid': sec_id,
                        'slots': int(lec * 2), 'type': 'Lec', 'dept': dept
                    })

                # Lab splits
                lab_splits = self.split_map.get((course_id, sec_id, 'Lab'))
                if lab_splits:
                    for didx, slots, faculty_id in lab_splits:
                        assignments.append({
                            'cid': course_id, 'sid': sec_id,
                            'slots': slots, 'type': 'Lab', 'dept': dept,
                            'locked_day': didx, 'faculty_id': faculty_id
                        })
                elif lab > 0:
                    assignments.append({
                        'cid': course_id, 'sid': sec_id,
                        'slots': int(lab * 2), 'type': 'Lab', 'dept': dept
                    })

        # ── Step 2: MRV-aware sort ─────────────────────────────────────────
        # Labs first, then by (fewest_eligible_rooms, longest_duration).
        # This ensures the most room-constrained sessions are packed first,
        # which is the core of the First-Fit Decreasing heuristic.
        def _mrv_key(a):
            type_pri = 0 if a['type'] == 'Lab' else 1
            dept = a['dept']
            if a['type'] == 'Lab':
                eligible = len(self._dept_rooms_lab.get(dept) or self._valid_rooms_lab)
            else:
                eligible = len(self._dept_rooms_lec_only.get(dept)
                               or self._valid_rooms_lec_only)
            # (type, scarcity ascending, duration descending)
            return (type_pri, eligible, -a['slots'])

        assignments.sort(key=_mrv_key)

        # ── Step 3: State for compact packing ─────────────────────────────
        lec_fac_map = {}   # {(cid, sid): faculty_id} for Lab reuse

        n_days      = len(self.days)
        total_slots = self.total_slots
        online_id   = self.online_room_id
        # Physical async rooms — excluded from Lec/Lab placement
        async_phys  = self.async_room_ids  # set

        # ── Step 4: Faculty picker ─────────────────────────────────────────
        def _pick_faculty(cid, sid, gtype):
            if gtype == 'Lab':
                paired = lec_fac_map.get((cid, sid))
                if paired:
                    return paired
            fa_fac = self.fa_map.get((cid, sid))
            if fa_fac and fa_fac in self.faculty_ids:
                return fa_fac
            cdept = _norm_dept(self.course_map.get(cid, {}).get('department', ''))
            pool = [f for f in self.faculty_ids
                    if self._fac_dept.get(f) == cdept
                    or f in self.multi_assignment_faculty]
            if not pool:
                pool = self.faculty_ids
            fac_load = {f: sum(1 for g in genes
                               if g.faculty_id == f and not g.is_fixed)
                        for f in pool}
            return min(pool, key=lambda f: (
                fac_load.get(f, 0),
                -len(self._fac_avail_days.get(f, range(7)))
            ))

        # ── Step 5: Dept room filter (excludes online + async phys) ───────
        def _dept_filter(room_list, dept):
            out = []
            for rid in room_list:
                if rid in self.online_room_ids:
                    continue
                if rid in async_phys:       # async-designated physical room
                    continue
                rd_set = self._room_depts.get(rid)
                if rd_set:
                    norm = _norm_dept(dept)
                    if not any(_norm_dept(d) == norm for d in rd_set):
                        continue
                out.append(rid)
            return out

        # ── Step 6: Try to place one session ──────────────────────────────
        def _place_session(a, enforce_seq=True):
            cid, sid, slots, gtype = a['cid'], a['sid'], a['slots'], a['type']
            dept = a['dept']
            mask_full = (1 << slots) - 1
            fac_id = _pick_faculty(cid, sid, gtype)
            is_big_lec = (gtype == 'Lec' and slots >= 6)

            # Check for paired gene if sequence enforcement is on
            paired_gene = None
            if enforce_seq:
                for g in genes:
                    if g.course_id == cid and g.section_id == sid and g.gene_type != gtype:
                        paired_gene = g
                        break

            # ── FIX 4: Dynamic warmth sort before room scan ────────────────────
            # Instead of static alphabetical order, sort by current occupancy.
            # Most-occupied rooms come first → bin packing / gravity effect.
            def _sort_by_warmth(room_list):
                return sorted(
                    room_list,
                    key=lambda rid: -sum(
                        occ_room.get((rid, d), 0).bit_count()
                        for d in range(n_days)
                    )
                )

            if gtype == 'Lab':
                tier1_raw = _dept_filter(self._seq_lab_rooms, dept)
                tier2_raw = _dept_filter(self._seq_lec_rooms, dept)
            elif is_big_lec:
                tier1_raw = _dept_filter(self._seq_lec_rooms, dept)
                tier2_raw = _dept_filter(self._seq_lab_rooms, dept)
            else:
                tier1_raw = _dept_filter(self._seq_lec_rooms, dept)
                tier2_raw = []

            # Apply warmth sort to both tiers
            tier1 = _sort_by_warmth(tier1_raw)
            tier2 = _sort_by_warmth(tier2_raw) if tier2_raw else []

            for room_list in (tier1, tier2):
                for rid in room_list:
                    # Spread section across days — sort by density-guided preference
                    _days_spread = [a['locked_day']] if 'locked_day' in a and a['locked_day'] >= 0 else self._get_density_guided_days(sid, occ_sec)
                    for d in _days_spread:
                        sec_avail_set = self._sec_avail_days.get(sid)
                        if sec_avail_set and d not in sec_avail_set:
                            continue
                        if paired_gene:
                            if gtype == 'Lec' and d > paired_gene.day_idx:
                                continue
                            if gtype == 'Lab' and d < paired_gene.day_idx:
                                continue

                        start = self._try_pack(
                            rid, d, fac_id, sid, slots, mask_full,
                            occ_room, occ_fac, occ_sec
                        )
                        if start >= 0:
                            if paired_gene and d == paired_gene.day_idx:
                                if gtype == 'Lec' and start >= paired_gene.start_idx:
                                    continue
                                if gtype == 'Lab' and start < paired_gene.end_idx:
                                    continue

                            m = mask_full << start
                            g = Gene(cid, sid, fac_id, rid, d,
                                     start, slots, gtype, False)
                            g.locked_day = a.get('locked_day', -1)
                            g.end_idx = start + slots
                            g.bitmask = m
                            genes.append(g)
                            self._add_to_occ(g, occ_room, occ_fac, occ_sec)
                            if gtype == 'Lec':
                                lec_fac_map[(cid, sid)] = fac_id
                            return True

            # Tier 3 — online room (faculty + section still enforced)
            if online_id:
                fa_avail = (self._fac_avail_days.get(fac_id)
                            if fac_id and fac_id not in self.multi_assignment_faculty
                            else None)
                days_to_try = [a['locked_day']] if 'locked_day' in a and a['locked_day'] >= 0 else range(n_days)
                for d in days_to_try:
                    sec_avail_set = self._sec_avail_days.get(sid)
                    if sec_avail_set and d not in sec_avail_set:
                        continue
                    if fa_avail and d not in fa_avail:
                        continue
                    if paired_gene:
                        if gtype == 'Lec' and d > paired_gene.day_idx:
                            continue
                        if gtype == 'Lab' and d < paired_gene.day_idx:
                            continue
                    combined = (occ_sec.get((sid, d), 0)
                                | (occ_fac.get((fac_id, d), 0)
                                   if fac_id and fac_id not in self.multi_assignment_faculty
                                   else 0)
                                | self._blocked_bitmasks.get(d, 0))
                    start = _compact_gap_scan(combined, slots, total_slots)
                    while start >= 0:
                        if paired_gene and d == paired_gene.day_idx:
                            if gtype == 'Lec' and start >= paired_gene.start_idx:
                                start = _compact_gap_scan(combined, slots, total_slots, start + 2)
                                continue
                            if gtype == 'Lab' and start < paired_gene.end_idx:
                                start = _compact_gap_scan(combined, slots, total_slots, start + 2)
                                continue

                        m = mask_full << start
                        new_sec = occ_sec.get((sid, d), 0) | m
                        new_fac = (occ_fac.get((fac_id, d), 0) if fac_id is not None else 0) | m
                        if _is_valid_break_mask(new_sec) and _is_valid_break_mask(new_fac):
                            break
                        start = _compact_gap_scan(combined, slots, total_slots, start + 2)
                    if start >= 0:
                        m = mask_full << start
                        g = Gene(cid, sid, fac_id, online_id, d,
                                 start, slots, gtype, False)
                        g.locked_day = a.get('locked_day', -1)
                        g.end_idx = start + slots
                        g.bitmask = m
                        genes.append(g)
                        self._add_to_occ(g, occ_room, occ_fac, occ_sec)
                        if gtype == 'Lec':
                            lec_fac_map[(cid, sid)] = fac_id
                        return True
            return False

        # ── Step 7: Pack all sessions ──────────────────────────────────────
        for a in assignments:
            success = _place_session(a, enforce_seq=True)
            if not success:
                _place_session(a, enforce_seq=False)

        # ── Step 8: Multi-pass reclaim — pull online genes into physical gaps
        self._reclaim_online_genes(genes, occ_room, occ_fac, occ_sec)

        # ── Step 9: Pre-calculate allowed_mask for GA fitness checks ──────
        self._precalc_gene_masks(genes)

        return Chromosome(genes)

    # ------------------------------------------------------------------ #
    # GAP-FILLING PACK (replaces append-only version)                     #
    # ------------------------------------------------------------------ #
    def _try_pack(self, rid, d, fac_id, sec_id, slots, mask_full,
                  occ_room, occ_fac, occ_sec):
        """
        Find the first clear `slots`-wide window in room `rid` on day `d`.

        Unlike the old append-only logic, this scans ALL positions from 0
        (not just from bit_length), so it fills mid-room gaps created by
        blocked slots or faculty unavailability.

        Returns start slot (even-aligned) or -1.
        """
        fa_avail = (self._fac_avail_days.get(fac_id)
                    if fac_id and fac_id not in self.multi_assignment_faculty
                    else None)
        if fa_avail and d not in fa_avail:
            return -1

        # Build combined mask once — single OR operation
        combined = (occ_room.get((rid, d), 0)
                    | occ_sec.get((sec_id, d), 0)
                    | (occ_fac.get((fac_id, d), 0)
                       if fac_id and fac_id not in self.multi_assignment_faculty
                       else 0)
                    | self._blocked_bitmasks.get(d, 0))

        start = _compact_gap_scan(combined, slots, self.total_slots)
        while start >= 0:
            m = mask_full << start
            new_sec = occ_sec.get((sec_id, d), 0) | m
            new_fac = (occ_fac.get((fac_id, d), 0) if fac_id is not None else 0) | m
            if _is_valid_break_mask(new_sec) and _is_valid_break_mask(new_fac):
                return start
            start = _compact_gap_scan(combined, slots, self.total_slots, start + 2)
        return -1

    # ------------------------------------------------------------------ #
    # MULTI-PASS RECLAIM                                                   #
    # ------------------------------------------------------------------ #
    def _reclaim_online_genes(self, genes, occ_room, occ_fac, occ_sec):
        """
        Move genes sitting in the online room into physical gaps.

        Runs multiple passes until no more genes can be moved (stable).
        This handles the case where reclaiming gene A frees a slot that
        allows gene B to also be reclaimed.

        Exclusions:
          - Async-designated physical rooms are excluded (genes would just
            get an SC-I-01 penalty for being in virtual room — let GA fix).
          - TBA rooms are excluded (kept clean as admin placeholder).

        Labs are scanned against lab rooms first, then lec rooms.
        Lecs are scanned against lec rooms only (no lab room spill here —
        the GA's soft constraints already penalise lec-in-lab fallback).
        """
        online_ids = self.online_room_ids
        if not online_ids:
            return

        async_phys = self.async_room_ids   # physical rooms designated async
        n_days      = len(self.days)
        total_slots = self.total_slots

        max_passes = 5   # safety ceiling; usually stable in 2–3 passes
        for _pass in range(max_passes):
            moved_this_pass = 0

            online_indices = [
                i for i, g in enumerate(genes)
                if g.room_id in online_ids and not g.is_fixed
            ]
            if not online_indices:
                break

            # Sort: Labs and largest classes first to maximize reclamation efficiency
            online_indices.sort(key=lambda i: (
                0 if genes[i].gene_type == 'Lab' else 1,
                -genes[i].duration_slots
            ))

            for idx in online_indices:
                g     = genes[idx]
                slots = g.duration_slots
                dept  = self.course_map.get(g.course_id, {}).get('department', '')

                # Build candidate physical room list
                if g.gene_type == 'Lab':
                    lab_pool = self._dept_rooms_lab.get(dept) or self._valid_rooms_lab
                    lec_pool = self._dept_rooms_lec_only.get(dept) or self._valid_rooms_lec_only
                    phys = (
                        [r for r in lab_pool
                         if r not in online_ids and r not in self.tba_room_ids
                         and r not in async_phys]
                        + [r for r in lec_pool
                           if r not in online_ids and r not in self.tba_room_ids
                           and r not in async_phys]
                    )
                else:
                    lec_pool = self._dept_rooms_lec_only.get(dept) or self._valid_rooms_lec_only
                    phys = [r for r in lec_pool
                            if r not in online_ids and r not in self.tba_room_ids
                            and r not in async_phys]

                fa_avail = (self._fac_avail_days.get(g.faculty_id)
                            if g.faculty_id and g.faculty_id not in self.multi_assignment_faculty
                            else None)

                placed = False
                for rid in phys:
                    if placed:
                        break
                    # Spread: prefer days with less section load
                    _days_reclaim = sorted(
                        range(n_days),
                        key=lambda d: occ_sec.get((g.section_id, d), 0).bit_count()
                    )
                    for d in _days_reclaim:
                        if fa_avail and d not in fa_avail:
                            continue
                        combined = (occ_room.get((rid, d), 0)
                                    | occ_sec.get((g.section_id, d), 0)
                                    | (occ_fac.get((g.faculty_id, d), 0)
                                       if g.faculty_id and g.faculty_id
                                       not in self.multi_assignment_faculty
                                       else 0)
                                    | self._blocked_bitmasks.get(d, 0))

                        start = _compact_gap_scan(combined, slots, total_slots)
                        if start < 0:
                            continue

                        # Move gene
                        self._remove_from_occ(g, occ_room, occ_fac, occ_sec)
                        m         = ((1 << slots) - 1) << start
                        g.day_idx   = d
                        g.start_idx = start
                        g.end_idx   = start + slots
                        g.room_id   = rid
                        g.bitmask   = m
                        self._add_to_occ(g, occ_room, occ_fac, occ_sec)
                        moved_this_pass += 1
                        placed = True
                        break

            if moved_this_pass == 0:
                break   # stable — no more reclaims possible

    def _try_compact_place(self, gene, occ_room, occ_fac, occ_sec,
                            min_day=0, min_start_sd=-1, pref_fac=None, hc24_src_day=-1):
        """
        Compact placement: tries to append immediately after the last session
        in the gene's current room-day, then tries same room other days,
        then tries other rooms in order (gravity logic, A1→A6/B1→B6).
        Much faster than exhaustive scan and keeps rooms packed.
        """
        slots = gene.duration_slots
        mask_full = (1 << slots) - 1
        dept = self.course_map.get(gene.course_id, {}).get('department', '')
        
        if gene.gene_type == 'Lab':
            room_order = self._seq_lab_rooms + self._seq_lec_rooms
        else:
            room_order = self._seq_lec_rooms + self._seq_lab_rooms

        # Filter by dept exclusivity
        valid_rooms = []
        for rid in room_order:
            rd_set = self._room_depts.get(rid)
            if rd_set:
                norm_dept = _norm_dept(dept)
                if not any(_norm_dept(d_name) == norm_dept for d_name in rd_set):
                    continue
            valid_rooms.append(rid)
        room_order = valid_rooms

        fac_id = pref_fac or gene.faculty_id
        fa_avail_set = (self._fac_avail_days.get(fac_id)
                        if fac_id and fac_id not in self.multi_assignment_faculty else None)

        for rid in room_order:
            if rid in self.online_room_ids: continue
            day_order = self._get_density_guided_days(gene.section_id, occ_sec, min_day, priority_day=hc24_src_day)
            for d in day_order:
                sec_avail_set = self._sec_avail_days.get(gene.section_id)
                if sec_avail_set and d not in sec_avail_set: continue
                if fa_avail_set and d not in fa_avail_set: continue
                blocked = self._blocked_bitmasks.get(d, 0)
                # Compact: start right after what's already in this room-day
                existing_bits = occ_room.get((rid, d), 0)
                if existing_bits == 0:
                    last_end = 0   # Empty room: start from slot 0
                else:
                    last_end = existing_bits.bit_length()
                    if last_end % 2 != 0: last_end += 1

                while last_end + slots <= self.total_slots:
                    m = mask_full << last_end
                    if (blocked & m) != 0: last_end += 2; continue
                    if d == min_day and min_start_sd >= 0 and last_end <= min_start_sd:
                        last_end += 2; continue
                    if rid not in self.multi_assignment_rooms:
                        if (occ_room.get((rid, d), 0) & m) != 0: last_end += 2; continue
                    if fac_id and fac_id not in self.multi_assignment_faculty:
                        if (occ_fac.get((fac_id, d), 0) & m) != 0: last_end += 2; continue
                    if (occ_sec.get((gene.section_id, d), 0) & m) != 0: last_end += 2; continue

                    # Place it
                    gene.day_idx = d
                    gene.start_idx = last_end
                    gene.end_idx = last_end + slots
                    gene.room_id = rid
                    gene.faculty_id = fac_id
                    gene.bitmask = m
                    return True
        return False

    # ------------------------------------------------------------------ #
    # FITNESS CALCULATION (Hard + Soft Constraints)                       #
    # ------------------------------------------------------------------ #
    def calculate_fitness(self, chromosome, hard_only=False, sc1_only=False, stop_event=None):
        if not hard_only and not sc1_only and getattr(chromosome, '_eval_gen', -1) == getattr(self, 'current_generation', -2):
            return chromosome.fitness
        self._check_stop(stop_event, raise_exception=True)
        penalty        = 0
        hard_conflicts = 0
        soft_score     = 0
        sc1_violations = 0
        sc2_violations = 0
        conflicts      = set()
        violation_codes = set()
        violation_indices = set() # To count "clean" genes for progress bar
        cmap = self.CONSTRAINT_MAP
        # include_sc2: True only in full soft mode (Phase 3)
        include_sc2    = not hard_only and not sc1_only

        room_use  = defaultdict(list)
        fac_use   = defaultdict(list)
        sec_use   = defaultdict(list)
        # Bitmask dicts for O(1) inline overlap detection (replaces check_overlap sort+scan)
        room_bits = defaultdict(int)
        fac_bits  = defaultdict(int)
        sec_bits  = defaultdict(int)

        # ── HC-24 PIGGYBACK ACCUMULATORS ─────────────────────────────────────
        # Populated for free during the main gene scan below.
        # sec_day_slots : (sec_id, day_idx) -> total duration_slots (int)
        # sec_day_async : set of (sec_id, day_idx) that have ≥1 Async gene
        # This eliminates any() + sum() generators in the HC-24 eval block.
        sec_day_slots = defaultdict(int)
        sec_day_async = set()
        _room_types   = self._room_types  # local alias — avoids attr lookup in tight loop

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
        seven_pm    = self.seven_pm_slot
        five_pm     = self.five_pm_slot
        v_room_set  = self._virtual_room_set
        lec_rooms   = self._lec_room_set
        multi_fac   = self.multi_assignment_faculty
        avail_days  = self._fac_avail_days
        blocked     = self._blocked_bitmasks
        exp_dur     = self._expected_duration
        multi_room  = self.multi_assignment_rooms

        def _apply_violation(code, p_val, idxs, is_fixed_list=None):
            nonlocal penalty, hard_conflicts, soft_score, sc1_violations, sc2_violations
            ctype = pen_type.get(code, 'HC')
            if ctype == 'NC': return
            
            penalty += p_val
            if code in cmap:
                violation_codes.add(cmap[code])
                
            for k, idx in enumerate(idxs):
                violation_indices.add(idx)
                if ctype == 'HC':
                    if is_fixed_list is None or not is_fixed_list[k]:
                        conflicts.add(idx)
            
            if ctype == 'HC':
                hard_conflicts += 1
            else:
                soft_score += p_val
                if ctype == 'SC1': sc1_violations += 1
                else: sc2_violations += 1

        for i, g in enumerate(genes):
            # Absolute Stop Check (Every 10 genes for near-instant response)
            if i % 10 == 0:
                self._check_stop(stop_event, raise_exception=True)

            # ── HC-22 / HC-21: Room Availability & Suitability ──────────────
            if not g.is_fixed:
                r = room_map.get(g.room_id)
                if r:
                    if r.get('status') != 'Available':
                        p = pen.get('ROOM_AVAILABILITY')
                        if p:
                            penalty += p; hard_conflicts += 1; conflicts.add(i); violation_codes.add(cmap['ROOM_AVAILABILITY']); violation_indices.add(i)

                    # Department Exclusivity Rule: If room has assigned depts, gene must match
                    r_depts_set = self._room_depts.get(g.room_id)
                    if r_depts_set:
                        _c_info = self.course_map.get(g.course_id, {})
                        gene_dept = _norm_dept(_c_info.get('department', ''))
                        if gene_dept not in r_depts_set:
                            p = pen.get('ROOM_SUITABILITY')
                            if p:
                                _apply_violation('ROOM_SUITABILITY', p, [i], [g.is_fixed])
                                continue

                    # ── VIRTUAL_ROOM_USAGE ──
                    if g.gene_type in ['Lec', 'Lab'] and g.room_id in self.online_room_ids:
                        p = pen.get('VIRTUAL_ROOM_USAGE', 100)
                        if p:
                            _apply_violation('VIRTUAL_ROOM_USAGE', p, [i], [g.is_fixed])

                    # ── ROOM_SUITABILITY (HC) ──
                    else:
                        if g.gene_type == 'Lab' and 'Computer Lab' not in r.get('capabilities', ''):
                            p = pen.get('ROOM_SUITABILITY', HC_PENALTY)
                            if p:
                                _apply_violation('ROOM_SUITABILITY', p, [i], [g.is_fixed])
                        elif g.gene_type == 'Lec' and 'Lecture' not in r.get('capabilities', ''):
                            p = pen.get('ROOM_SUITABILITY', HC_PENALTY)
                            if p:
                                _apply_violation('ROOM_SUITABILITY', p, [i], [g.is_fixed])

                    # ── SC-I-10: Lecture in Lab Fallback ──
                    if g.gene_type == 'Lec' and 'Computer Lab' in r.get('capabilities', ''):
                        p = pen.get('LEC_IN_LAB_FALLBACK', 50)
                        if p:
                            _apply_violation('LEC_IN_LAB_FALLBACK', p, [i], [g.is_fixed])


                    _cap_hc = pen_type.get('ROOM_CAPACITY_PROPORTIONAL', 'SC2') == 'HC'
                    if include_sc2 or _cap_hc:
                        # SC-II-05: Room Capacity Allocation (Absolute Fit)
                        r_name = r.get('room_name', '').upper()
                        # Exemptions: Courts, Gymnasium, TBA, Online Room
                        if not any(ex in r_name for ex in ['COURT', 'GYM', 'T.B.A.', 'ONLINE', 'VIRTUAL']):
                            students = sec_stu.get(g.section_id, 0)
                            cap      = r.get('capacity', 0)
                            # Penalty is the absolute difference to prioritize 'Closest Fit'
                            diff = abs(cap - students)
                            p = pen.get('ROOM_CAPACITY_PROPORTIONAL', 0)
                            if p and diff > 0:
                                # Scale penalty by distance (higher diff = higher penalty)
                                # but keep it within reasonable soft bounds.
                                actual_p = p * (diff / 10.0) 
                                _apply_violation('ROOM_CAPACITY_PROPORTIONAL', actual_p, [i], [g.is_fixed])

                    # ── SC-I-01: Virtual Room (TBA) Penalty ──────────────────
                    if not g.is_fixed and g.room_id in v_room_set and g.gene_type != 'Async':
                        p = pen.get('VIRTUAL_ROOM_USAGE', 0)
                        if p:
                            _apply_violation('VIRTUAL_ROOM_USAGE', p, [i], [g.is_fixed])

            # ── STATIC CONSTRAINTS: Operating Hours, Faculty Avail, Blocked Slots ──
            # Combined into a single bitwise check via Gene.allowed_mask
            if g.allowed_mask:
                _day_allowed = g.allowed_mask[g.day_idx]
                if (g.bitmask & _day_allowed) != g.bitmask:
                    # One or more slots are outside operating hours or in a blocked time
                    p = pen.get('OPERATING_HOURS', HC_PENALTY)
                    if p:
                        penalty += p; hard_conflicts += 1; conflicts.add(i); violation_indices.add(i)
                        violation_codes.add(cmap.get('OPERATING_HOURS', 'HC-23'))

            # ── HC-08 / HC-09 / HC-10 / HC-11: Strict Duration ───────────────
            if not g.is_fixed and getattr(g, 'locked_day', -1) < 0:
                _exp_dur = exp_dur.get((g.course_id, g.gene_type))
                if _exp_dur and g.duration_slots != _exp_dur:
                    if g.gene_type == 'Lec':
                        _p_dur = pen.get('STRICT_LEC_DURATION', 0)
                        _code = cmap['STRICT_LEC_DURATION']
                    elif g.gene_type == 'Lab':
                        _p_dur = pen.get('STRICT_LAB_DURATION', 0)
                        _code = cmap['STRICT_LAB_DURATION']
                    else:
                        _p_dur = pen.get('STRICT_ASYNC_LEC_DUR', 0) or pen.get('STRICT_ASYNC_LAB_DUR', 0)
                        _code = cmap['STRICT_ASYNC_LEC_DUR']
                    if _p_dur:
                        penalty += _p_dur; hard_conflicts += 1; conflicts.add(i); violation_codes.add(_code); violation_indices.add(i)

            # ── HC-24: Hourly Slot Alignment (Whole-Hour Only) ───────────
            if (not g.is_fixed and g.start_idx % 2 != 0):
                p = pen.get('HOURLY_ALIGNMENT', 0)
                if p:
                    penalty += p; hard_conflicts += 1; conflicts.add(i); violation_codes.add(cmap['HOURLY_ALIGNMENT']); violation_indices.add(i)

            # ── HC-27: Faculty Day Split ──────────────────────────────────────
            _ld = getattr(g, 'locked_day', -1)
            if _ld >= 0 and g.day_idx != _ld and not g.is_fixed:
                p = pen.get('FACULTY_DAY_SPLIT', 0)
                if p:
                    penalty += p; hard_conflicts += 1; conflicts.add(i); violation_codes.add(cmap['FACULTY_DAY_SPLIT']); violation_indices.add(i)

            _eve_hc = pen_type.get('EVENING_AVOIDANCE', 'SC1') == 'HC'
            if not hard_only or _eve_hc:
                # ── SC-I-03: Evening Avoidance (Physical Room Only) ──────────
                if g.room_id not in self._virtual_room_set:
                    p = pen.get('EVENING_AVOIDANCE', 0)
                    if p and g.start_idx >= seven_pm:
                        _apply_violation('EVENING_AVOIDANCE', p, [i], [g.is_fixed])

            if include_sc2:
                if g.gene_type == 'Async':
                    # SC-II-03: Strategic Async Placement (Disabled as per user request — online rooms available)
                    pass

            # Track Lec/Lab for sequence (HC-04) and proximity (SC-I-01/03) checks
            if g.gene_type in ('Lec', 'Lab'):
                lc_key = (g.section_id, g.course_id)
                if lc_key not in sec_course_genes:
                    sec_course_genes[lc_key] = {}
                sec_course_genes[lc_key][g.gene_type] = (g, i)

            # ── Inline bitmask overlap detection (HC-12/13/16) + build usage maps ──
            _mask = g.bitmask
            _d    = g.day_idx

            # Room overlap (HC-16)
            if g.room_id not in self.online_room_ids and g.room_id not in self.multi_assignment_rooms:
                _rkey = (g.room_id, _d)
                if (room_bits[_rkey] & _mask) != 0:
                    penalty += HC_PENALTY; hard_conflicts += 1; violation_codes.add(cmap['ROOM_OVERLAP'])
                    if not g.is_fixed:
                        conflicts.add(i); violation_indices.add(i)
                    for _ps, _pe, _pi in room_use[_rkey]:
                        if _ps < g.end_idx and _pe > g.start_idx:
                            if not genes[_pi].is_fixed:
                                conflicts.add(_pi); violation_indices.add(_pi)
                room_bits[_rkey] |= _mask

            # Faculty overlap (HC-13)
            if g.faculty_id and g.faculty_id not in self.multi_assignment_faculty:
                _fkey = (g.faculty_id, _d)
                if (fac_bits[_fkey] & _mask) != 0:
                    penalty += HC_PENALTY; hard_conflicts += 1; violation_codes.add(cmap['FACULTY_OVERLAP'])
                    if not g.is_fixed:
                        conflicts.add(i); violation_indices.add(i)
                    for _ps, _pe, _pi in fac_use[_fkey]:
                        if _ps < g.end_idx and _pe > g.start_idx:
                            if not genes[_pi].is_fixed:
                                conflicts.add(_pi); violation_indices.add(_pi)
                fac_bits[_fkey] |= _mask

            # Section overlap (HC-12)
            _skey = (g.section_id, _d)
            if (sec_bits[_skey] & _mask) != 0:
                penalty += HC_PENALTY; hard_conflicts += 1; violation_codes.add(cmap['SECTION_OVERLAP'])
                if not g.is_fixed:
                    conflicts.add(i); violation_indices.add(i)
                for _ps, _pe, _pi in sec_use[_skey]:
                    if _ps < g.end_idx and _pe > g.start_idx:
                        if not genes[_pi].is_fixed:
                            conflicts.add(_pi); violation_indices.add(_pi)
            sec_bits[_skey] |= _mask

            # Append to lists for HC-15/19/27 and lunch break
            room_use[(g.room_id,    _d)].append((g.start_idx, g.end_idx, i))
            if g.faculty_id:
                fac_use[(g.faculty_id, _d)].append((g.start_idx, g.end_idx, i))
            _sday = (g.section_id, _d)
            sec_use[_sday].append((g.start_idx, g.end_idx, i))
            # ── HC-24 PIGGYBACK: accumulate while we're already here ──
            sec_day_slots[_sday] += g.duration_slots
            if _room_types.get(g.room_id) == 'Async':
                sec_day_async.add(_sday)

            # EARLY EXIT for hard_only mode
            _hc_cutoff = getattr(self, '_hc_eval_cutoff', 9999)
            if hard_only and hard_conflicts > _hc_cutoff:
                chromosome.fitness = hard_conflicts * HC_PENALTY
                chromosome.hard_conflicts = hard_conflicts
                chromosome.soft_score = 0
                chromosome.conflicting_indices = list(conflicts)
                return chromosome.fitness

        if include_sc2:
            # ── SC-II-04: Lunch Break (SC2 — skip in SC-I phase) ─────────────
            p_lb = pen.get('LUNCH_BREAK', 0)
            if p_lb:
                lw_mask = self._lunch_window_mask
                
                # Check section lunch breaks
                for (sec_id, day_idx), slots in sec_use.items():
                    # Periodic stop check for large schedules
                    if day_idx % 3 == 0: self._check_stop(stop_event, raise_exception=True)
                    occ_bits = sec_bits.get((sec_id, day_idx), 0) & lw_mask
                    if occ_bits:
                        free_in_window = (~occ_bits) & lw_mask
                        # Check if there are 2 consecutive free slots in the window
                        if not (free_in_window & (free_in_window >> 1)):
                            idxs = [_i for _, _, _i in slots]
                            fixed_list = [genes[_i].is_fixed for _i in idxs]
                            _apply_violation('LUNCH_BREAK', p_lb, idxs, fixed_list)
                            
                # Check faculty lunch breaks
                for (fac_id, day_idx), slots in fac_use.items():
                    if day_idx % 3 == 0: self._check_stop(stop_event, raise_exception=True)
                    occ_bits = fac_bits.get((fac_id, day_idx), 0) & lw_mask
                    if occ_bits:
                        free_in_window = (~occ_bits) & lw_mask
                        # Check if there are 2 consecutive free slots in the window
                        if not (free_in_window & (free_in_window >> 1)):
                            idxs = [_i for _, _, _i in slots]
                            fixed_list = [genes[_i].is_fixed for _i in idxs]
                            _apply_violation('LUNCH_BREAK', p_lb, idxs, fixed_list)

        if not hard_only:
            # ── SC-I-01 & SC-I-03: Lec-Lab weekly distribution & proximity ───
            for type_genes in sec_course_genes.values():
                lec_entry = type_genes.get('Lec')
                lab_entry = type_genes.get('Lab')
                if not (lec_entry and lab_entry):
                    continue
                lec_g, lec_i = lec_entry
                lab_g, lab_i = lab_entry
                if lab_g.day_idx == lec_g.day_idx:
                    p = pen['LEC_LAB_WEEKLY_DIST']
                    if p:
                        _apply_violation('LEC_LAB_WEEKLY_DIST', p, [lec_i, lab_i], [lec_g.is_fixed, lab_g.is_fixed])


        # ── SC-I-04: Room Idle Gap Penalty ───────────────────────────────────
        p_rig = pen.get('ROOM_IDLE_GAP', 0)
        if p_rig:
            for (room_id, day_idx), slots in room_use.items():
                if room_id in self._virtual_room_set: continue
                sorted_slots = sorted(slots, key=lambda x: x[0])
                for j in range(len(sorted_slots) - 1):
                    gap = sorted_slots[j+1][0] - sorted_slots[j][1]
                    # DYNAMIC penalty for idle gaps (30m up to the curriculum's minimum subject duration)
                    if 0 < gap <= self._idle_gap_threshold_slots and sorted_slots[j][1] < self.seven_pm_slot:
                        # Triple penalty for gaps to force classes to stick together
                        idx1 = sorted_slots[j][2]
                        idx2 = sorted_slots[j+1][2]
                        _apply_violation('ROOM_IDLE_GAP', p_rig * 3, [idx1, idx2], [genes[idx1].is_fixed, genes[idx2].is_fixed])

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
                    _apply_violation('LEC_LAB_SEQUENCE', p_lls, [lab_i], [lab_g.is_fixed])

        # ── Built-in: Max Consecutive Student Load (Enforced via Bitmask) ──
        for (sec_id, d), mask in sec_bits.items():
            if not _is_valid_break_mask(mask):
                penalty += HC_PENALTY; hard_conflicts += 1; violation_codes.add(cmap['MAX_CONSECUTIVE_STUDENT'])
                for _start, _end, idx in sec_use.get((sec_id, d), []):
                    if not genes[idx].is_fixed:
                        conflicts.add(idx); violation_indices.add(idx)

        # ── Built-in: Max Consecutive Faculty Load (Enforced via Bitmask) ──
        for (fac_id, d), mask in fac_bits.items():
            if fac_id in self.multi_assignment_faculty:
                continue
            if not _is_valid_break_mask(mask):
                penalty += HC_PENALTY; hard_conflicts += 1; violation_codes.add(cmap['MAX_CONSECUTIVE_FACULTY'])
                for _start, _end, idx in fac_use.get((fac_id, d), []):
                    if not genes[idx].is_fixed:
                        conflicts.add(idx); violation_indices.add(idx)

        # ── DYNAMIC EVALUATION: Minimum Daily Section Load (HC-24) ───────────
        # PIGGYBACK OPTIMIZED: sec_day_slots and sec_day_async were pre-populated
        # during the main gene scan above — no secondary iteration needed here.
        # Cost per entry: 2× O(1) dict/set lookups + 1 integer compare.
        p_mdl = pen.get('MIN_DAILY_SECTION_LOAD', 0)
        if p_mdl:
            type_mdl = pen_type.get('MIN_DAILY_SECTION_LOAD', 'SC1')
            # Evaluate dynamically based on type and current phase:
            # - Always run if it is a Hard Constraint (HC) to enforce it strictly.
            # - Run if it is SC1 and we are not in hard_only mode.
            # - Run if it is SC2 and include_sc2 is True.
            if (type_mdl == 'HC') or (type_mdl == 'SC1' and not hard_only) or (type_mdl == 'SC2' and include_sc2):
                _hc24_exempt = self._hc24_exempt_sections
                for _sday, _total_slots in sec_day_slots.items():
                    _sec_id, _day_idx = _sday
                    # IMPOSSIBILITY FILTER: O(1) frozenset lookup
                    if _sec_id in _hc24_exempt:
                        continue
                    # ASYNC EXEMPTION: O(1) set lookup (pre-built during main scan)
                    if _sday in sec_day_async:
                        continue
                    # MAIN CHECK: integer compare — no sum() needed
                    if _total_slots < 6:  # 6 slots == 3.0 hours
                        _slots = sec_use[_sday]
                        idxs = [_i for _, _, _i in _slots]
                        fixed_list = [genes[_i].is_fixed for _i in idxs]
                        _apply_violation('MIN_DAILY_SECTION_LOAD', p_mdl, idxs, fixed_list)


        # ── SC-II-05: Room Fragmentation Penalty (Clustering) ────────────────
        # Penalize each physical room that is 'Active' but sparsely populated (< 4 hrs/day).
        # Optimization: Only run this if we are already HC-free (SC-polishing phase).
        if include_sc2 and hard_conflicts == 0:
            p_frag = pen.get('ROOM_CAPACITY_PROPORTIONAL', 0)
            if p_frag:
                for bits in room_bits.values():
                    used_slots = bits.bit_count()
                    if 0 < used_slots < 8: # Less than 4 hours active in a day
                        penalty += p_frag; soft_score += p_frag; sc2_violations += 1

        chromosome.fitness             = penalty
        chromosome.hard_conflicts      = hard_conflicts
        chromosome.soft_score          = soft_score
        chromosome.sc1_violations      = sc1_violations
        chromosome.sc2_violations      = sc2_violations
        chromosome.conflicting_indices = list(conflicts)
        chromosome.violation_codes     = sorted(list(violation_codes))
        # Unique indices of genes that have at least one violation (Hard or Soft)
        chromosome._violated_indices    = list(violation_indices)

        if not hard_only and not sc1_only:
            chromosome._eval_gen = getattr(self, 'current_generation', -1)

        # Phase 4: Save state for Delta Fitness
        chromosome._occ_room = room_bits
        chromosome._occ_fac  = fac_bits
        chromosome._occ_sec  = sec_bits

        return penalty

    # ------------------------------------------------------------------ #
    # MUTATION                                                             #
    # ------------------------------------------------------------------ #
    def proportional_mutate(self, chromosome, stop_event=None):
        """Mutate all hard-conflicting genes; otherwise randomly improve soft violations."""
        self._check_stop(stop_event, raise_exception=True)
        targets = list(set(chromosome.conflicting_indices))

        def _recalc_mask(g):
            if g.allowed_mask is not None:
                fac_avail = self._fac_avail_days.get(g.faculty_id) \
                            if g.faculty_id and g.faculty_id not in self.multi_assignment_faculty \
                            else None
                op_mask = (1 << self.total_slots) - 1
                g.allowed_mask = []
                for d_idx in range(len(self.days)):
                    m_val = op_mask
                    if fac_avail and d_idx not in fac_avail:
                        m_val = 0
                    day_blocked = self._blocked_bitmasks.get(d_idx, 0)
                    if day_blocked:
                        m_val &= ~day_blocked
                    g.allowed_mask.append(m_val)

        if targets:
            # Hard conflict phase: ONLY move conflicting genes, preserve the rest
            occ_room, occ_fac, occ_sec = (
                chromosome._occ_room, chromosome._occ_fac, chromosome._occ_sec
            ) if chromosome._occ_room is not None else self._build_occ_sets(chromosome.genes)
            chromosome._occ_room = occ_room
            chromosome._occ_fac = occ_fac
            chromosome._occ_sec = occ_sec

            # Room-only swap first (cheap, fixes 'right time wrong room')
            if random.random() < 0.40:
                self._room_only_swap(chromosome)

            lec_lookup = {}
            lec_fac_lookup = {}
            for g in chromosome.genes:
                if g.gene_type == 'Lec':
                    lec_lookup[(g.section_id, g.course_id)] = (g.day_idx, g.start_idx)
                    if g.faculty_id:
                        lec_fac_lookup[(g.section_id, g.course_id)] = g.faculty_id

            random.shuffle(targets)
            _hc24_active = bool(self._pen.get('MIN_DAILY_SECTION_LOAD', 0))
            _hc24_exempt = self._hc24_exempt_sections
            for idx in targets:
                gene = chromosome.genes[idx]
                if gene.is_fixed: continue
                _src_day = gene.day_idx
                self._remove_from_occ(gene, occ_room, occ_fac, occ_sec)

                # After removal, check if remaining load on source day is below 6 slots
                _hc24_src = -1
                if _hc24_active and gene.section_id not in _hc24_exempt:
                    remaining_load = occ_sec.get((gene.section_id, _src_day), 0).bit_count()
                    if 0 < remaining_load < 6:
                        _hc24_src = _src_day

                min_day, min_start_sd, pref_fac = 0, -1, None
                if gene.gene_type == 'Lab':
                    lec_info = lec_lookup.get((gene.section_id, gene.course_id))
                    if lec_info:
                        min_day, lec_start = lec_info
                        min_start_sd = lec_start - 1
                    pref_fac = lec_fac_lookup.get((gene.section_id, gene.course_id))

                # Try compact placement first (append after existing sessions in room)
                placed = self._try_compact_place(gene, occ_room, occ_fac, occ_sec,
                                                  min_day, min_start_sd, pref_fac,
                                                  hc24_src_day=_hc24_src)
                if not placed:
                    self.randomize_gene_fast(gene, occ_room, occ_fac, occ_sec,
                                              min_day, min_start_sd,
                                              preferred_faculty=pref_fac,
                                              hc24_src_day=_hc24_src)

                self._add_to_occ(gene, occ_room, occ_fac, occ_sec)
                _recalc_mask(gene)
                if gene.gene_type == 'Lec':
                    lec_lookup[(gene.section_id, gene.course_id)] = (gene.day_idx, gene.start_idx)
                    if gene.faculty_id:
                        lec_fac_lookup[(gene.section_id, gene.course_id)] = gene.faculty_id

            chromosome._dirty = True
            return  # EXIT EARLY — don't do soft mutation when HC > 0

        # Soft mutation only when HC == 0 (existing logic below unchanged)
        soft_targets = self._find_soft_violation_indices(chromosome)
        
        # Phase 4: Use stored occupancy maps instead of building from scratch
        if chromosome._occ_room is None:
            _occ_r, _occ_f, _occ_s = self._build_occ_sets(chromosome.genes)
            chromosome._occ_room = _occ_r
            chromosome._occ_fac  = _occ_f
            chromosome._occ_sec  = _occ_s
        else:
            _occ_r, _occ_f, _occ_s = chromosome._occ_room, chromosome._occ_fac, chromosome._occ_sec
            
        _lec_fac = {(g.section_id, g.course_id): g.faculty_id
                    for g in chromosome.genes if g.gene_type == 'Lec' and g.faculty_id is not None}
        mutated = False
        if soft_targets and random.random() < 0.40:
            idx = random.choice(soft_targets)
            gene = chromosome.genes[idx]
            if not gene.is_fixed:
                self._remove_from_occ(gene, _occ_r, _occ_f, _occ_s)
                _pref = _lec_fac.get((gene.section_id, gene.course_id)) if gene.gene_type == 'Lab' else None
                self.randomize_gene_fast(gene, _occ_r, _occ_f, _occ_s, preferred_faculty=_pref)
                self._add_to_occ(gene, _occ_r, _occ_f, _occ_s)
                _recalc_mask(gene)
                mutated = True
        elif random.random() < 0.15:
            # GUIDED INTELLIGENCE: Instead of purely random, prefer soft violators if they exist
            if soft_targets and random.random() < 0.85:
                idx = random.choice(soft_targets)
            else:
                idx = random.randint(0, len(chromosome.genes) - 1)
            
            gene = chromosome.genes[idx]
            if not gene.is_fixed:
                # Phase 3: Route Lec/Lab to SuperGene mutation
                if gene.gene_type in ('Lec', 'Lab'):
                    self._mutate_lec_lab_pair(chromosome, idx, _occ_r, _occ_f, _occ_s)
                else:
                    self._remove_from_occ(gene, _occ_r, _occ_f, _occ_s)
                    _pref = _lec_fac.get((gene.section_id, gene.course_id)) if gene.gene_type == 'Lab' else None
                    self.randomize_gene_fast(gene, _occ_r, _occ_f, _occ_s, preferred_faculty=_pref)
                    self._add_to_occ(gene, _occ_r, _occ_f, _occ_s)
                    _recalc_mask(gene)
                mutated = True

    def _mutate_lec_lab_pair(self, chromosome, idx, occ_room, occ_fac, occ_sec):
        """
        Phase 3: SuperGene Mutation (Atomic Lec-Lab Move).
        Moves both Lec and Lab together to ensure proximity (SC-I-09).
        Respects faculty available days dynamically.
        """
        genes = chromosome.genes
        g1 = genes[idx]
        pair_info = self._lec_lab_pair_map.get((g1.section_id, g1.course_id))
        if not pair_info or 'Lec' not in pair_info or 'Lab' not in pair_info:
            # Not a paired course — fallback to normal randomization
            self.randomize_gene_fast(g1, occ_room, occ_fac, occ_sec)
            return

        lec_idx = pair_info['Lec']
        lab_idx = pair_info['Lab']
        g_lec = genes[lec_idx]
        g_lab = genes[lab_idx]

        if g_lec.is_fixed or g_lab.is_fixed:
            return

        # Remove BOTH from occupancy
        self._remove_from_occ(g_lec, occ_room, occ_fac, occ_sec)
        self._remove_from_occ(g_lab, occ_room, occ_fac, occ_sec)

        # --- FIX 1: Pick Lec day from faculty's actual available days ---
        lec_fac_id = g_lec.faculty_id
        _lec_avail = None
        if lec_fac_id and lec_fac_id not in self.multi_assignment_faculty:
            _lec_avail = self._fac_avail_days.get(lec_fac_id)

        n_days = len(self.days)
        if _lec_avail:
            # Only pick from days the faculty is actually available
            # Reserve at least 1 day gap for Lab (so don't pick last day)
            valid_lec_days = sorted([d for d in _lec_avail if d < n_days - 1])
            if not valid_lec_days:
                valid_lec_days = list(_lec_avail)
            lec_day = random.choice(valid_lec_days)
        else:
            # No restriction — pick any day except the last (need room for Lab)
            lec_day = random.randint(0, max(0, n_days - 2))

        # Place Lec first
        self.randomize_gene_fast(g_lec, occ_room, occ_fac, occ_sec, min_day=lec_day)

        # --- FIX 2: Lab uses same faculty as Lec (preferred_faculty) ---
        # Lab goes Day+1 or Day+2 after Lec (SC-I-09 proximity)
        gap = random.choice([1, 2])
        lab_day = min(n_days - 1, g_lec.day_idx + gap)

        self.randomize_gene_fast(
            g_lab, occ_room, occ_fac, occ_sec,
            min_day=lab_day,
            preferred_faculty=g_lec.faculty_id  # ← KEY FIX: Same faculty as Lec
        )

        # Re-add BOTH
        self._add_to_occ(g_lec, occ_room, occ_fac, occ_sec)
        self._add_to_occ(g_lab, occ_room, occ_fac, occ_sec)

        # Recalculate masks immediately for both mutated genes
        for g in [g_lec, g_lab]:
            if g.allowed_mask is not None:
                fac_avail = self._fac_avail_days.get(g.faculty_id) \
                            if g.faculty_id and g.faculty_id not in self.multi_assignment_faculty \
                            else None
                op_mask = (1 << self.total_slots) - 1
                g.allowed_mask = []
                for d_idx in range(len(self.days)):
                    m_val = op_mask
                    if fac_avail and d_idx not in fac_avail:
                        m_val = 0
                    day_blocked = self._blocked_bitmasks.get(d_idx, 0)
                    if day_blocked:
                        m_val &= ~day_blocked
                    g.allowed_mask.append(m_val)

    def _rebuild_lec_lab_pair_map(self, reference_chromosome):
        """
        Rebuild the Lec-Lab pair index map from a reference chromosome.
        Must be called after:
          - Initial population creation
          - Severe stagnation reset (new create_genome() calls)
          - CEE data injection
        Uses gene indices which are consistent across all chromosomes
        since create_genome() produces deterministic gene ordering.
        """
        self._lec_lab_pair_map = {}
        for i, g in enumerate(reference_chromosome.genes):
            if g.gene_type not in ('Lec', 'Lab'):
                continue
            key = (g.section_id, g.course_id)
            if key not in self._lec_lab_pair_map:
                self._lec_lab_pair_map[key] = {}
            self._lec_lab_pair_map[key][g.gene_type] = i

        # Stats
        paired = sum(1 for v in self._lec_lab_pair_map.values()
                     if 'Lec' in v and 'Lab' in v)
        print(f"🧬 [SuperGene] Pair map rebuilt: {paired} Lec-Lab pairs tracked "
              f"({len(self._lec_lab_pair_map)} total course-section combos)")

    def _room_only_swap(self, chromosome):
        """
        Room-Only Swap Operator (Fix 2: Direct Room Conflict Resolution).

        Finds two genes in conflicting rooms and swaps ONLY their room_ids.
        - Does NOT touch day_idx or start_idx (timing is preserved).
        - Resolves "right time, wrong room" scenarios directly.
        - Much cheaper than full re-randomization.
        - Returns True if a beneficial swap was found, False otherwise.
        """
        genes = chromosome.genes
        non_fixed = [g for g in genes if not g.is_fixed and g.gene_type in ('Lec', 'Lab')]
        if len(non_fixed) < 2:
            return False

        # Find pairs of conflicting genes that share the same room/day/time
        # These are prime candidates for a room swap
        room_day_map = {}  # (room_id, day_idx) -> list of genes
        for g in non_fixed:
            key = (g.room_id, g.day_idx)
            if key not in room_day_map:
                room_day_map[key] = []
            room_day_map[key].append(g)

        # Collect conflicting pairs (same room, same day, overlapping time)
        conflict_candidates = []
        for key, grp in room_day_map.items():
            if len(grp) < 2:
                continue
            for i in range(len(grp)):
                for j in range(i + 1, len(grp)):
                    g1, g2 = grp[i], grp[j]
                    # Check actual time overlap
                    if g1.start_idx < g2.end_idx and g2.start_idx < g1.end_idx:
                        conflict_candidates.append((g1, g2))

        if not conflict_candidates:
            # No direct conflicts found — try a random room exploration swap
            # Pick two genes with compatible times (non-overlapping) and swap rooms
            sample = random.sample(non_fixed, min(10, len(non_fixed)))
            for i in range(len(sample)):
                for j in range(i + 1, len(sample)):
                    g1, g2 = sample[i], sample[j]
                    # Only swap if they are on the same day and don't overlap
                    if (g1.day_idx == g2.day_idx and
                            not (g1.start_idx < g2.end_idx and g2.start_idx < g1.end_idx) and
                            g1.room_id != g2.room_id):
                        # Check room type compatibility (Lab<->Lab, Lec<->Lec)
                        r1 = self.room_map.get(g1.room_id, {})
                        r2 = self.room_map.get(g2.room_id, {})
                        if (g1.gene_type == g2.gene_type and
                                r1.get('capabilities') == r2.get('capabilities')):
                            g1.room_id, g2.room_id = g2.room_id, g1.room_id
                            return True
            return False

        # Pick a random conflicting pair and swap their rooms
        g1, g2 = random.choice(conflict_candidates)
        r1 = self.room_map.get(g1.room_id, {})
        r2 = self.room_map.get(g2.room_id, {})

        # Only swap if rooms are type-compatible
        if (r1.get('capabilities') == r2.get('capabilities') and
                g1.gene_type == g2.gene_type):
            g1.room_id, g2.room_id = g2.room_id, g1.room_id
            return True

        # Fallback: swap regardless (algorithm will flag if wrong type, repair handles it)
        g1.room_id, g2.room_id = g2.room_id, g1.room_id
        return True

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
    def _eval_batch(self, chromosomes, hard_only=False, sc1_only=False, stop_event=None):
        """
        Evaluate a list of chromosomes.
        LOW-END: sequential (thread overhead > benefit on 2-core machines)
        MID/HIGH: parallel via ThreadPoolExecutor
        """
        n = len(chromosomes)
        if n == 0:
            return
        
        self._check_stop(stop_event, raise_exception=True)
        
        # Efficiency Mode: Skip thread overhead for <= 2 workers OR small batches
        if self.max_workers <= 2 or n <= (self.max_workers * 2):
            for c in chromosomes:
                self.calculate_fitness(c, hard_only=hard_only, sc1_only=sc1_only, stop_event=stop_event)
            return

        def _eval(c):
            self.calculate_fitness(c, hard_only=hard_only, sc1_only=sc1_only, stop_event=stop_event)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(_eval, c) for c in chromosomes]
            for f in as_completed(futures):
                # Absolute check during parallel eval
                if getattr(self, 'force_stop', False):
                    raise AlgorithmStopException("Stop signal detected during batch evaluation.")
                f.result()

    def randomize_gene_fast(self, gene, occ_room, occ_fac, occ_sec,
                            min_day=0, min_start_same_day=-1, use_warmth=True,
                            preferred_faculty=None, preferred_room=None, stop_event=None,
                            hc24_src_day=-1):
        """Place gene using pre-built occ sets (caller must remove gene first).
        FIX 2: Added warmth-based room sorting + section-active-day preference.
        """
        slots_needed = gene.duration_slots
        _fa_pref = self.fa_map.get((gene.course_id, gene.section_id))
        _fa_pref = _fa_pref if (_fa_pref is not None and _fa_pref in self.faculty_ids) else None
        if preferred_faculty is None and _fa_pref is not None:
            preferred_faculty = _fa_pref
        orig_fac     = preferred_faculty if preferred_faculty is not None else gene.faculty_id
        _pref_avail_days = None
        if preferred_faculty is not None and preferred_faculty not in self.multi_assignment_faculty:
            _pref_avail_days = self._fac_avail_days.get(preferred_faculty)
        sec_id       = gene.section_id
        days_count   = len(self.days)
        total_slots  = self.total_slots
        faculty_ids  = self.faculty_ids
        gtype        = gene.gene_type
        _cdept_rf = _norm_dept(self.course_map.get(gene.course_id, {}).get('department', ''))
        if _cdept_rf and preferred_faculty is None:
            _dept_fac_ids = [fid for fid in faculty_ids
                             if fid in self.multi_assignment_faculty
                             or self._fac_dept.get(fid, '') == _cdept_rf
                             or self._fac_dept.get(fid, '') == '']
            _dept_fac_ids = _dept_fac_ids or faculty_ids
        else:
            _dept_fac_ids = faculty_ids

        dept = self.course_map.get(gene.course_id, {}).get('department', '')

        if gtype == 'Lab':
            primary_rooms  = self._dept_rooms_lab.get(dept)
            fallback_rooms = self._dept_rooms_lec_only.get(dept)
        else:
            primary_rooms  = self._dept_rooms_lec_only.get(dept)
            fallback_rooms = []

        if not primary_rooms:
            primary_rooms = self._valid_rooms_lec
        if not fallback_rooms and gtype == 'Lab':
            fallback_rooms = primary_rooms

        starts = [s for s in range(0, self.total_slots - slots_needed + 1) if s % 2 == 0]
        _eve_mode = self._pen_type.get('EVENING_AVOIDANCE', 'NC')
        if _eve_mode in ('SC1', 'SC2'):
            day_starts = [s for s in starts if s < self.seven_pm_slot]
            eve_starts = [s for s in starts if s >= self.seven_pm_slot]
            starts = day_starts + eve_starts

        _locked_day = getattr(gene, 'locked_day', -1)
        _use_preferred_room = (preferred_room is not None
                               and preferred_room not in self.tba_room_ids
                               and preferred_room in primary_rooms)

        # ── FIX 2A: Warmth-based room sorting ─────────────────────────────────
        # Sort rooms by total occupied slots (descending) — most occupied first.
        # This creates a gravity effect: new genes pack into already-warm rooms.
        def _room_warmth(rid):
            return sum(
                occ_room.get((rid, d), 0).bit_count()
                for d in range(days_count)
            )

        def _warm_sort(room_list):
            """Sort room list by warmth descending, excluding online rooms."""
            phys = [r for r in room_list if r not in self.online_room_ids]
            if not phys:
                return room_list
            return sorted(phys, key=_room_warmth, reverse=True)

        # Apply warmth sort to room pools
        warm_primary  = _warm_sort(primary_rooms)
        warm_fallback = _warm_sort(fallback_rooms) if fallback_rooms else []

        room_pools = [warm_primary]
        if warm_fallback:
            room_pools.append(warm_fallback)

        # ── FIX 2B REPLACEMENT: Spread sections across days ───────────────────
        # Sort days ASCENDING by section's current slot usage on that day.
        # Least-loaded day comes first → sections spread across available days
        # instead of concentrating on one day → prevents HC-09 Section Overlap.
        #
        # Example with 4 days:
        #   Monday:    BSCS201A = 8 slots used  → priority 3 (most loaded)
        #   Tuesday:   BSCS201A = 4 slots used  → priority 2
        #   Wednesday: BSCS201A = 0 slots used  → priority 1 (least loaded)
        #   Thursday:  BSCS201A = 0 slots used  → priority 1 (tie → sorted by index)
        # ── Density-Guided Day sorting to cluster classes ─────────────────────
        # ── HC-24 SOURCE DAY PRIORITY (Layer 1+3) ────────────────────────────
        # If the source day would drop below 3hrs (6 slots) when this gene
        # leaves, inject source day at position 0 — gene stays there if a
        # valid slot exists, preventing HC-24 regression. O(1) cost.
        _hc24_priority = -1
        if (hc24_src_day >= 0
                and self._pen.get('MIN_DAILY_SECTION_LOAD', 0)
                and sec_id not in self._hc24_exempt_sections
                and occ_sec.get((sec_id, hc24_src_day), 0).bit_count() < 6):
            _hc24_priority = hc24_src_day
        _preferred_day_order = self._get_density_guided_days(sec_id, occ_sec, min_day,
                                                             priority_day=_hc24_priority)

        fac_candidates = [orig_fac]
        if preferred_faculty is None and _dept_fac_ids:
            fac_candidates.extend([f for f in _dept_fac_ids if f != orig_fac])
        elif preferred_faculty is not None and preferred_faculty != orig_fac:
            fac_candidates.insert(0, preferred_faculty)

        # ── Step 3: Guided Scan Loop ───────────────────────────────────────────
        for pool in room_pools:
            sorted_pool = pool if pool else []
            for fac_id in fac_candidates:
                # Use preferred day order (active days first) instead of plain range
                _days_iter = _preferred_day_order if _preferred_day_order else list(range(days_count))

                for d in _days_iter:
                    if _locked_day >= 0 and d != _locked_day: continue
                    if min_day >= 0 and d < min_day: continue
                    sec_avail_set = self._sec_avail_days.get(sec_id)
                    if sec_avail_set and d not in sec_avail_set: continue
                    if _pref_avail_days and d not in _pref_avail_days: continue

                    f_mask = (occ_fac.get((fac_id, d), 0) if fac_id is not None else 0)
                    f_mask |= occ_sec.get((sec_id, d), 0)
                    f_mask |= self._blocked_bitmasks.get(d, 0)

                    for rid in sorted_pool:
                        if rid in self.multi_assignment_rooms: continue
                        total_mask = f_mask | occ_room.get((rid, d), 0)

                        for start in starts:
                            if d == min_day and min_start_same_day >= 0 and start <= min_start_same_day:
                                continue
                            
                            # If EVENING_AVOIDANCE is a Hard Constraint, avoid evening starts (7pm onwards) for physical rooms
                            if (self._pen_type.get('EVENING_AVOIDANCE', 'SC1') == 'HC' 
                                    and rid not in self.online_room_ids 
                                    and start >= self.seven_pm_slot):
                                continue

                            mask = ((1 << slots_needed) - 1) << start
                            if (total_mask & mask) == 0:
                                new_sec_mask = occ_sec.get((sec_id, d), 0) | mask
                                new_fac_mask = (occ_fac.get((fac_id, d), 0) if fac_id is not None else 0) | mask
                                if not _is_valid_break_mask(new_sec_mask) or not _is_valid_break_mask(new_fac_mask):
                                    continue
                                # Found the first surgical hole!
                                gene.day_idx = d
                                gene.start_idx = start
                                gene.end_idx = start + slots_needed
                                gene.room_id = rid
                                gene.faculty_id = fac_id
                                gene.bitmask = mask
                                return True

        # 4. Final Desperation Pass: Online Room (Overflow Tank)
        # T.B.A. is strictly excluded from AI selection pool.
        v_pool = list(self.online_room_ids)
        if v_pool:
            rid = v_pool[0]
            # Online Room always succeeds because it's in multi_assignment_rooms
            # (No room conflict). We just need to avoid Faculty and Section overlaps.
            for fac_id in fac_candidates:
                for d in range(days_count):
                    if _locked_day >= 0 and d != _locked_day: continue
                    fa_mask  = (occ_fac.get((fac_id, d), 0) if fac_id is not None else 0)
                    sec_mask = occ_sec.get((sec_id, d), 0)
                    combined = fa_mask | sec_mask
                    for start in starts:
                        mask = ((1 << slots_needed) - 1) << start
                        if (combined & mask) == 0:
                            new_sec_mask = occ_sec.get((sec_id, d), 0) | mask
                            new_fac_mask = (occ_fac.get((fac_id, d), 0) if fac_id is not None else 0) | mask
                            if not _is_valid_break_mask(new_sec_mask) or not _is_valid_break_mask(new_fac_mask):
                                continue
                            gene.day_idx, gene.start_idx, gene.room_id = d, start, rid
                            gene.faculty_id, gene.bitmask = fac_id, mask
                            gene.end_idx = start + slots_needed
                            return True

        # Fallback: Absolute failure (should be rare with TBA)
        gene.end_idx = gene.start_idx + gene.duration_slots
        gene.bitmask = ((1 << gene.duration_slots) - 1) << gene.start_idx
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
                start_slot = (s_h - self.start_hour) * 2 # Forced even slot for Hourly Alignment
                end_slot   = (e_h - self.start_hour) * 2
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

            # Use session_type or gene_type if provided directly in record, fallback to room capability
            gene_type = rec.get('session_type') or rec.get('gene_type')
            if not gene_type:
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
        _hc24_active_rc          = bool(self._pen.get('MIN_DAILY_SECTION_LOAD', 0))
        _hc24_exempt_sections_rc = self._hc24_exempt_sections

        perturb_count = max(1, len(non_fixed) // 3)
        indices = random.sample(non_fixed, min(perturb_count, len(non_fixed)))

        occ_room, occ_fac, occ_sec = self._build_occ_sets(nc.genes)
        lec_lookup = {(g.section_id, g.course_id): (g.day_idx, g.start_idx)
                      for g in nc.genes if g.gene_type == 'Lec'}
        lec_fac_lookup = {(g.section_id, g.course_id): g.faculty_id
                          for g in nc.genes if g.gene_type == 'Lec' and g.faculty_id is not None}
        for idx in indices:
            gene = nc.genes[idx]
            _src_day = gene.day_idx
            self._remove_from_occ(gene, occ_room, occ_fac, occ_sec)
            # After removal occ_sec shows what OTHER genes contribute on src day
            _hc24_src = -1
            if (_hc24_active_rc
                    and gene.section_id not in _hc24_exempt_sections_rc):
                remaining_load = occ_sec.get((gene.section_id, _src_day), 0).bit_count()
                if 0 < remaining_load < 6:
                    _hc24_src = _src_day
            min_day = 0; min_start_sd = -1; pref_fac = None
            if gene.gene_type == 'Lab':
                lec_info = lec_lookup.get((gene.section_id, gene.course_id))
                if lec_info:
                    min_day, lec_start = lec_info
                    min_start_sd = lec_start - 1
                pref_fac = lec_fac_lookup.get((gene.section_id, gene.course_id))
            self.randomize_gene_fast(gene, occ_room, occ_fac, occ_sec, min_day, min_start_sd,
                                     preferred_faculty=pref_fac, hc24_src_day=_hc24_src)
            self._add_to_occ(gene, occ_room, occ_fac, occ_sec)
            if gene.gene_type == 'Lec':
                lec_lookup[(gene.section_id, gene.course_id)] = (gene.day_idx, gene.start_idx)
                if gene.faculty_id is not None:
                    lec_fac_lookup[(gene.section_id, gene.course_id)] = gene.faculty_id

        return nc

    # ------------------------------------------------------------------ #
    # LOCAL SEARCH REFINEMENT (Soft-Constraint Polishing)                #
    # ------------------------------------------------------------------ #
    def _local_search_refinement(self, chromosome, max_attempts=None):
        """
        Hill-climbing local search to polish soft constraints without breaking hard constraints.
        Searches same-day time shifts, room swaps, and full-day relocations to fix
        both per-gene and relational soft violations.
        Uses Tabu memory list to avoid repeating recent moves, and fast violator list
        spot-checking to avoid expensive O(N) full fitness recalculation in evaluation loops.
        """
        if chromosome.hard_conflicts > 0 or chromosome.soft_score == 0:
            return chromosome

        refined = self._copy_chromosome(chromosome)
        occ_room, occ_fac, occ_sec = self._build_occ_sets(refined.genes)

        # Get indices of genes causing soft penalties
        violators = self._find_soft_violation_indices(refined)
        if not violators:
            return refined

        # Use hardware-aware default if no override provided
        if max_attempts is None:
            max_attempts = self._hw_ls_max_attempts

        _max_violators = self._hw_ls_max_violators

        # Limit violators batch size to prevent slowdown
        if len(violators) > _max_violators:
            violators = random.sample(violators, _max_violators)

        days_count  = len(self.days)
        total_slots = self.total_slots
        improved    = False
        attempts    = 0

        # Tabu List for local search: format (idx, test_day, test_start, test_room)
        tabu_list = []

        while violators and attempts < max_attempts:
            # --- STOP SIGNAL CHECK ---
            self._check_stop(None, raise_exception=True)
            
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
            best_local_score = len(violators)

            # ── Build candidate search space ──────────────────────────────
            search_space = []
            valid_rooms = self.get_valid_rooms(gene.gene_type)

            # 1. Slide ±2 slots on the same day (same room)
            for shift in [-2, -1, 1, 2]:
                ns = orig_start + shift
                if 0 <= ns <= total_slots - duration:
                    search_space.append((orig_day, ns, orig_room))

            # 2. Alternative room, same time
            phys_valid = [r for r in valid_rooms if r not in self.tba_room_ids and r not in self.online_room_ids]
            tba_valid = [r for r in valid_rooms if r in self.tba_room_ids or r in self.online_room_ids]
            
            room_candidates = random.sample(phys_valid, min(3, len(phys_valid))) if phys_valid else []
            if len(room_candidates) < 3 and tba_valid:
                 room_candidates += random.sample(tba_valid, min(3 - len(room_candidates), len(tba_valid)))

            for new_room in room_candidates:
                if new_room != orig_room:
                    search_space.append((orig_day, orig_start, new_room))

            # 3. Relocate to a different day entirely (respected split gene locks)
            if _gene_locked_day < 0:
                other_days = [d for d in range(days_count) if d != orig_day]
                for alt_day in random.sample(other_days, min(3, len(other_days))):
                    alt_start = self._smart_start(duration)
                    if 0 <= alt_start <= total_slots - duration:
                        search_space.append((alt_day, alt_start, orig_room))

            # ── Evaluate candidates with CORRECT bitmask-based conflict check ──
            found_better = False
            for (test_day, test_start, test_room) in search_space:
                # Tabu Check
                if (idx, test_day, test_start, test_room) in tabu_list:
                    continue
                # Cache-like skip
                if test_day == orig_day and test_room == orig_room:
                    continue
                
                test_end = test_start + duration
                mask = ((1 << duration) - 1) << test_start

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
                    new_score = len(self._find_soft_violation_indices(refined))
                    self._remove_from_occ(gene, occ_room, occ_fac, occ_sec)

                    if new_score < best_local_score:
                        best_local_score = new_score
                        best_gene_state  = (test_day, test_start, test_room)
                        found_better     = True

            # Apply best found state (or original state if no improvement)
            test_day, test_start, test_room = best_gene_state
            gene.day_idx   = test_day
            gene.start_idx = test_start
            gene.end_idx   = test_start + duration
            gene.room_id   = test_room
            gene.bitmask   = ((1 << duration) - 1) << test_start
            self._add_to_occ(gene, occ_room, occ_fac, occ_sec)

            if found_better:
                improved = True
                tabu_list.append((idx, test_day, test_start, test_room))
                if len(tabu_list) > 30:
                    tabu_list.pop(0)
                violators = self._find_soft_violation_indices(refined)
                if len(violators) > _max_violators:
                    violators = random.sample(violators, _max_violators)

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
        ng.allowed_mask   = getattr(g, 'allowed_mask', None)
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
        nc.sc2_violations      = chrom.sc2_violations
        nc._soft_violators_cache = chrom._soft_violators_cache
        nc._soft_cache_gen     = chrom._soft_cache_gen
        
        # Phase 4: Copy occupancy maps for delta fitness
        if chrom._occ_room is not None:
            nc._occ_room = chrom._occ_room.copy()
            nc._occ_fac  = chrom._occ_fac.copy()
            nc._occ_sec  = chrom._occ_sec.copy()
            
        return nc

    # ------------------------------------------------------------------ #
    # CROSSOVER — greedy conflict-aware                                   #
    # ------------------------------------------------------------------ #
    def crossover(self, p1, p2, stop_event=None):
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
        for j, i in enumerate(non_fixed):
            if j % 30 == 0:
                self._check_stop(stop_event, raise_exception=True)
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
                    self._guaranteed_place(chosen, occ_room, occ_fac, occ_sec)
                    # chosen is NOW guaranteed collision-free regardless of outcome

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

    def _guaranteed_place(self, gene, occ_room, occ_fac, occ_sec):
        """
        Guaranteed collision-free placement. Never returns a conflicting gene.
        Priority: physical rooms → online room (section+faculty checked) → absolute last slot.
        Called only when both parents conflict — this is the safety net.
        """
        # Try physical rooms first
        if self._exhaustive_place_gene(gene, occ_room, occ_fac, occ_sec):
            return True

        # Online room fallback — strict section+faculty check
        if self.online_room_ids:
            rid = list(self.online_room_ids)[0]
            gene.room_id = rid
            slots = gene.duration_slots
            fa = gene.faculty_id
            fa_avail = (self._fac_avail_days.get(fa)
                        if fa and fa not in self.multi_assignment_faculty else None)

            for d in range(len(self.days)):
                if fa_avail and d not in fa_avail:
                    continue
                fa_mask  = (occ_fac.get((fa, d), 0)
                            if fa and fa not in self.multi_assignment_faculty else 0)
                sec_mask = occ_sec.get((gene.section_id, d), 0)
                combined = fa_mask | sec_mask

                start = _compact_gap_scan(combined, slots, self.total_slots)
                if start >= 0:
                    mask = ((1 << slots) - 1) << start
                    gene.day_idx   = d
                    gene.start_idx = start
                    gene.end_idx   = start + slots
                    gene.bitmask   = mask
                    return True

        # Absolute last resort: spread across any day with section check only
        slots = gene.duration_slots
        rid = list(self.online_room_ids)[0] if self.online_room_ids else gene.room_id
        for d in range(len(self.days)):
            sec_mask = occ_sec.get((gene.section_id, d), 0)
            start = _compact_gap_scan(sec_mask, slots, self.total_slots)
            if start >= 0:
                mask = ((1 << slots) - 1) << start
                gene.day_idx, gene.start_idx = d, start
                gene.end_idx, gene.bitmask   = start + slots, mask
                gene.room_id = rid
                return True

        return False

    def _exhaustive_place_gene(self, gene, occ_room, occ_fac, occ_sec,
                               min_day=0, min_start_same_day=-1, stop_event=None, room_strict=True):
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
        # T.B.A. room addition REMOVED as per user request to keep TBA clean.
        slots_needed = gene.duration_slots
        # Filter candidates by suitability and department exclusivity
        _c_info = self.course_map.get(gene.course_id, {})
        gene_dept = _norm_dept(_c_info.get('department', ''))
        if gene.gene_type == 'Lab':
            lab_rooms_e = [r for r in valid_rooms 
                           if 'Computer Lab' in self.room_map.get(r, {}).get('capabilities', "")]
            lec_rooms_e = [r for r in valid_rooms 
                           if 'Lecture' in self.room_map.get(r, {}).get('capabilities', "")
                           and 'Computer Lab' not in self.room_map.get(r, {}).get('capabilities', "")]
            valid_rooms = lab_rooms_e + lec_rooms_e  # Lab rooms muna, lec rooms bilang fallback
        elif gene.gene_type == 'Lec':
            valid_rooms = [r for r in valid_rooms if 'Lecture' in self.room_map.get(r, {}).get('capabilities', "")]
            
        # Dept Exclusivity: Only rooms with no dept OR matching dept
        valid_rooms = [r for r in valid_rooms if not self.room_map.get(r, {}).get('room_departments', '') or 
                      gene_dept in self.room_map.get(r, {}).get('room_departments', '')]

        # Sync-Only Rule: Lec/Lab (Sync) strictly forbidden in Online Rooms
        if gene.gene_type in ['Lec', 'Lab']:
            valid_rooms = [r for r in valid_rooms if r not in self.online_room_ids]
            
        sec_id       = gene.section_id
        orig_fac     = gene.faculty_id
        total_slots  = self.total_slots

        # Hourly Alignment: Force even slots (0, 2, 4...)
        _starts = [s for s in range(0, max(1, total_slots - slots_needed + 1)) if s % 2 == 0]
        if not _starts:  # safety fallback
            _starts = list(range(0, max(1, total_slots - slots_needed + 1)))
            
        # Allow scanning all starts chronologically


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
        
        phys_rooms = sorted([r for r in valid_rooms if r not in self.tba_room_ids and r not in self.online_room_ids])
        tba_rooms = sorted([r for r in valid_rooms if r in self.tba_room_ids or r in self.online_room_ids])
        # Filter room pools for Sync genes (Physical classes prefer physical rooms, but we keep the Online Room in tba_rooms as a last-resort fallback)
        if gene.gene_type in ['Lec', 'Lab']:
            phys_rooms = [r for r in phys_rooms if r not in self.online_room_ids]
            # Keep Online Room in tba_rooms so Phase 2 can use it as a last-resort safety fallback!
            tba_rooms  = [r for r in tba_rooms]
            for or_id in self.online_room_ids:
                if or_id not in tba_rooms:
                    tba_rooms.append(or_id)

        # Gravity Logic: Remove shuffles for days and starts to prioritize early slots
        # days and starts are already in chronological order [0, 1, 2...]
        
        # ── Phase 0: Quick Probes (Random Sampling) for High Speed ─────────
        # Try 20 random (day, slot, physical room) combos first.
        # This restores the "Seeder 8" speed for most placements.
        if phys_rooms:
            for _ in range(20):
                d = random.choice(days)
                s = random.choice(starts)
                r = random.choice(phys_rooms)
                
                # No evening limitation during random probes

                
                # Fast validation
                end = s + slots_needed
                mask = ((1 << slots_needed) - 1) << s
                if (occ_sec.get((sec_id, d), 0) & mask) == 0:
                    if orig_fac is None or orig_fac in self.multi_assignment_faculty or (occ_fac.get((orig_fac, d), 0) & mask) == 0:
                        new_sec_mask = occ_sec.get((sec_id, d), 0) | mask
                        new_fac_mask = (occ_fac.get((orig_fac, d), 0) if orig_fac is not None else 0) | mask
                        if not _is_valid_break_mask(new_sec_mask) or not _is_valid_break_mask(new_fac_mask):
                            continue
                        if (room_strict == False) or r in self.multi_assignment_rooms or (occ_room.get((r, d), 0) & mask) == 0:
                            if not (d == min_day and min_start_same_day >= 0 and s <= min_start_same_day):
                                gene.day_idx = d; gene.start_idx = s; gene.end_idx = end
                                gene.room_id = r; gene.bitmask = mask
                                return True

        # ── Phase 1: Physical Rooms across ALL days/slots (Exhaustive) ─────
        if phys_rooms:
            for day in days:
                if getattr(self, 'force_stop', False):
                    raise AlgorithmStopException("Stop in exhaustive place.")
                self._check_stop(stop_event, raise_exception=True)
                for s_idx, start in enumerate(starts):
                    if s_idx % 5 == 0 and self.force_stop:
                        raise AlgorithmStopException("Stop in exhaustive physical inner.")
                    if day == min_day and min_start_same_day >= 0 and start <= min_start_same_day:
                        continue
                    
                    # No evening limitation during exhaustive place

                        
                    end = start + slots_needed
                    mask = ((1 << slots_needed) - 1) << start

                    if (occ_sec.get((sec_id, day), 0) & mask) != 0:
                        continue
                    if orig_fac is not None and orig_fac not in self.multi_assignment_faculty and (occ_fac.get((orig_fac, day), 0) & mask) != 0:
                        continue
                    
                    new_sec_mask = occ_sec.get((sec_id, day), 0) | mask
                    new_fac_mask = (occ_fac.get((orig_fac, day), 0) if orig_fac is not None else 0) | mask
                    if not _is_valid_break_mask(new_sec_mask) or not _is_valid_break_mask(new_fac_mask):
                        continue

                    for room in phys_rooms:
                        if (room_strict == False) or room in self.multi_assignment_rooms or (occ_room.get((room, day), 0) & mask) == 0:
                            gene.day_idx = day
                            gene.start_idx = start
                            gene.end_idx = end
                            gene.room_id = room
                            gene.bitmask = mask
                            return True

        # ── Phase 2: Virtual Rooms (TBA/Online) ONLY if Physical fails ──────
        if tba_rooms:
            for day in days:
                if getattr(self, 'force_stop', False):
                    raise AlgorithmStopException("Stop in exhaustive place.")
                self._check_stop(stop_event, raise_exception=True)
                for s_idx, start in enumerate(starts):
                    if s_idx % 5 == 0 and self.force_stop:
                        raise AlgorithmStopException("Stop in exhaustive virtual inner.")
                    if day == min_day and min_start_same_day >= 0 and start <= min_start_same_day:
                        continue
                    end = start + slots_needed
                    mask = ((1 << slots_needed) - 1) << start

                    if (occ_sec.get((sec_id, day), 0) & mask) != 0:
                        continue
                    if orig_fac is not None and orig_fac not in self.multi_assignment_faculty and (occ_fac.get((orig_fac, day), 0) & mask) != 0:
                        continue

                    new_sec_mask = occ_sec.get((sec_id, day), 0) | mask
                    new_fac_mask = (occ_fac.get((orig_fac, day), 0) if orig_fac is not None else 0) | mask
                    if not _is_valid_break_mask(new_sec_mask) or not _is_valid_break_mask(new_fac_mask):
                        continue

                    for room in tba_rooms:
                        if room in self.multi_assignment_rooms or (occ_room.get((room, day), 0) & mask) == 0:
                            gene.day_idx = day
                            gene.start_idx = start
                            gene.end_idx = end
                            gene.room_id = room
                            gene.bitmask = mask
                            return True

        # ── Phase 3: alternative faculty — try alternatives ──
        # Skip Phase 3 if this gene has a manual fa_map assignment
        if self.fa_map.get((gene.course_id, gene.section_id)) is not None:
            return False
        faculty_ids = self.faculty_ids
        if not faculty_ids:
            return False
        alts = [f for f in faculty_ids if f != orig_fac]
        random.shuffle(alts)
        
        n_days = len(self.days)
        # Use the same prioritized rooms: physical first
        rooms_alt = phys_rooms + tba_rooms
        _starts = [s for s in range(0, total_slots - slots_needed + 1)]
        
        for alt_fac in alts[:2]:      # try up to 2 alternative faculty
            self._check_stop(stop_event, raise_exception=True)
            _alt_avail = (self._fac_avail_days.get(alt_fac) 
                          if alt_fac not in self.multi_assignment_faculty else None)
            
            # Probabilistic search for speed (40 random attempts per faculty)
            for attempt_alt in range(40):
                if attempt_alt % 10 == 9:
                    self._check_stop(stop_event, raise_exception=True)
                
                day = random.randint(min_day, n_days - 1)
                if _alt_avail is not None and day not in _alt_avail:
                    continue
                
                start = random.choice(_starts)
                if day == min_day and min_start_same_day >= 0 and start <= min_start_same_day:
                    continue
                
                end = start + slots_needed
                mask = ((1 << slots_needed) - 1) << start

                if (occ_sec.get((sec_id, day), 0) & mask) != 0:
                    continue
                if alt_fac not in self.multi_assignment_faculty and (occ_fac.get((alt_fac, day), 0) & mask) != 0:
                    continue

                new_sec_mask = occ_sec.get((sec_id, day), 0) | mask
                new_fac_mask = (occ_fac.get((alt_fac, day), 0) if alt_fac is not None else 0) | mask
                if not _is_valid_break_mask(new_sec_mask) or not _is_valid_break_mask(new_fac_mask):
                    continue

                # Instead of looping ALL rooms, pick a few candidates
                for room in rooms_alt[:10]: # Check top 10 prioritized rooms
                    # No evening filtering in prioritized rooms

                    if room in self.multi_assignment_rooms or (occ_room.get((room, day), 0) & mask) == 0:
                        gene.day_idx    = day
                        gene.start_idx  = start
                        gene.end_idx    = end
                        gene.room_id    = room
                        gene.faculty_id = alt_fac
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
            self._check_stop(None, raise_exception=True)
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
                self._check_stop(None, raise_exception=True)
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

    def _classify_conflicts(self, chromosome):
        """Group conflicting genes by HC type for targeted repair."""
        genes = chromosome.genes
        overlap_idxs = []
        duration_idxs = []
        alignment_idxs = []
        availability_idxs = []
        
        for i in chromosome.conflicting_indices:
            g = genes[i]
            if g.is_fixed: continue
            
            # Duration mismatch
            exp = self._expected_duration.get((g.course_id, g.gene_type))
            if exp and g.duration_slots != exp:
                duration_idxs.append(i); continue
                
            # Hourly alignment
            if g.start_idx % 2 != 0:
                alignment_idxs.append(i); continue
                
            # Faculty availability
            fa_avail = self._fac_avail_days.get(g.faculty_id) if g.faculty_id else None
            if fa_avail and g.day_idx not in fa_avail:
                availability_idxs.append(i); continue
                
            overlap_idxs.append(i)
            
        return {
            'overlap': overlap_idxs,
            'duration': duration_idxs,
            'alignment': alignment_idxs,
            'availability': availability_idxs
        }

    # ------------------------------------------------------------------ #
    # ISOLATED HARD CONFLICT REPAIR  (DSatur-ordered)                    #
    # ------------------------------------------------------------------ #
    def _hard_conflict_repair(self, chromosome, stop_event=None, allow_backtrack=True):
        """
        Graph-coloring-inspired repair:
        """
        self._check_stop(stop_event, raise_exception=True)
        if not chromosome.conflicting_indices:
            return

        genes        = chromosome.genes
        conflict_idxs = [i for i in chromosome.conflicting_indices if not genes[i].is_fixed]
        if not conflict_idxs:
            return

        # NEW: Route based on count for ultra-low HC
        if allow_backtrack and len(conflict_idxs) <= 10:
            self._exhaustive_resolve_last_conflicts(chromosome)
            return

        # NEW: Classify before repair
        classified = self._classify_conflicts(chromosome)
        
        # Fix alignment first (cheapest fix)
        for idx in classified['alignment']:
            genes[idx].start_idx = (genes[idx].start_idx // 2) * 2
            genes[idx].bitmask = ((1 << genes[idx].duration_slots) - 1) << genes[idx].start_idx
            
        # Fix duration
        for idx in classified['duration']:
            exp = self._expected_duration.get((genes[idx].course_id, genes[idx].gene_type))
            if exp:
                genes[idx].duration_slots = exp
                genes[idx].end_idx = genes[idx].start_idx + exp
                genes[idx].bitmask = ((1 << exp) - 1) << genes[idx].start_idx

        # NEW: Build "hot zone" set
        _conflict_rooms = defaultdict(int)
        for idx in conflict_idxs:
            g = genes[idx]
            _conflict_rooms[(g.room_id, g.day_idx)] += 1
        _hot_zones = {k for k, v in _conflict_rooms.items() if v >= 2}

        conflict_set = set(conflict_idxs)
        # ── Fix 7 (CORRECTED): Reciprocal Two-Gene Swap with Validation ──────
        # Build a temp occ set to validate swaps before committing.
        if len(conflict_idxs) >= 2:
            if getattr(chromosome, '_occ_room', None) is not None:
                _tmp_occ_r = chromosome._occ_room.copy()
                _tmp_occ_f = chromosome._occ_fac.copy()
                _tmp_occ_s = chromosome._occ_sec.copy()
                for idx in conflict_idxs:
                    g = genes[idx]
                    self._remove_from_occ(g, _tmp_occ_r, _tmp_occ_f, _tmp_occ_s)
            else:
                _tmp_occ_r = defaultdict(int)
                _tmp_occ_f = defaultdict(int)
                _tmp_occ_s = defaultdict(int)
                for i, g in enumerate(genes):
                    if i not in conflict_set:
                        self._add_to_occ(g, _tmp_occ_r, _tmp_occ_f, _tmp_occ_s)
            _swap_tried = 0
            for _a in range(min(len(conflict_idxs), 8)):
                for _b in range(_a + 1, min(len(conflict_idxs), 8)):
                    ga, gb = genes[conflict_idxs[_a]], genes[conflict_idxs[_b]]
                    if ga.is_fixed or gb.is_fixed: continue
                    if ga.duration_slots != gb.duration_slots: continue
                    # Validate: would ga fit in gb's slot (and vice versa)?
                    ma = ga.bitmask; mb = gb.bitmask
                    da, db = ga.day_idx, gb.day_idx
                    ra, rb = ga.room_id, gb.room_id
                    fa, fb = ga.faculty_id, gb.faculty_id
                    ga_fits = (
                        (_tmp_occ_r.get((rb, da), 0) & ma) == 0 and
                        (fa is None or (_tmp_occ_f.get((fa, da), 0) & ma) == 0) and
                        (_tmp_occ_s.get((ga.section_id, da), 0) & ma) == 0
                    )
                    gb_fits = (
                        (_tmp_occ_r.get((ra, db), 0) & mb) == 0 and
                        (fb is None or (_tmp_occ_f.get((fb, db), 0) & mb) == 0) and
                        (_tmp_occ_s.get((gb.section_id, db), 0) & mb) == 0
                    )
                    if ga_fits and gb_fits:
                        ga.room_id, gb.room_id = gb.room_id, ga.room_id
                        ga.day_idx, gb.day_idx = gb.day_idx, ga.day_idx
                        ga.start_idx, gb.start_idx = gb.start_idx, ga.start_idx
                        ga.end_idx, gb.end_idx = gb.end_idx, ga.end_idx
                        ga.bitmask, gb.bitmask = gb.bitmask, ga.bitmask
                        _swap_tried += 1
                    if _swap_tried >= 3:
                        break
                if _swap_tried >= 3:
                    break

        # ── SPEED FIX 1: Dynamic DSatur Threshold ──────────────────────────
        ordered = sorted(conflict_idxs, key=lambda i: (
            0 if genes[i].gene_type == 'Lec' else 1,
            -genes[i].duration_slots
        ))

        if getattr(chromosome, '_occ_room', None) is not None:
            occ_room = chromosome._occ_room.copy()
            occ_fac = chromosome._occ_fac.copy()
            occ_sec = chromosome._occ_sec.copy()
            for idx in conflict_set:
                g = genes[idx]
                self._remove_from_occ(g, occ_room, occ_fac, occ_sec)
        else:
            occ_room = defaultdict(int)
            occ_fac = defaultdict(int)
            occ_sec = defaultdict(int)
            for i, g in enumerate(genes):
                if i not in conflict_set:
                    self._add_to_occ(g, occ_room, occ_fac, occ_sec)

        lec_lookup = {}
        lec_fac_lookup = {}
        for i, g in enumerate(genes):
            if g.gene_type == 'Lec' and i not in conflict_set:
                lec_lookup[(g.section_id, g.course_id)] = (g.day_idx, g.start_idx)
                if g.faculty_id is not None:
                    lec_fac_lookup[(g.section_id, g.course_id)] = g.faculty_id

        _hc24_active = bool(self._pen.get('MIN_DAILY_SECTION_LOAD', 0))
        _hc24_exempt_sections = self._hc24_exempt_sections

        for idx in ordered:
            if getattr(self, 'force_stop', False):
                raise AlgorithmStopException("Stop in hard conflict repair.")
            self._check_stop(stop_event, raise_exception=True)
            gene = genes[idx]
            _src_day = gene.day_idx
            _hc24_src = -1
            if (_hc24_active
                    and gene.section_id not in _hc24_exempt_sections):
                remaining_load = occ_sec.get((gene.section_id, _src_day), 0).bit_count()
                if 0 < remaining_load < 6:
                    _hc24_src = _src_day

            min_day = 0
            min_start_sd = -1
            pref_fac = None
            if gene.gene_type == 'Lab':
                lec_info = lec_lookup.get((gene.section_id, gene.course_id))
                if lec_info:
                    min_day, lec_start = lec_info
                    min_start_sd = lec_start - 1
                pref_fac = lec_fac_lookup.get((gene.section_id, gene.course_id))

            self.randomize_gene_fast(gene, occ_room, occ_fac, occ_sec,
                                     min_day, min_start_sd, preferred_faculty=pref_fac,
                                     hc24_src_day=_hc24_src)
            placed_ok = True
            mask = gene.bitmask
            d = gene.day_idx
            if ((occ_room.get((gene.room_id, d), 0) & mask) != 0 or
                (gene.faculty_id is not None and
                 (occ_fac.get((gene.faculty_id, d), 0) & mask) != 0) or
                (occ_sec.get((gene.section_id, d), 0) & mask) != 0):
                placed_ok = False

            # Check hot zones
            if placed_ok and getattr(self, '_hot_zones', None) and (gene.room_id, d) in self._hot_zones:
                placed_ok = False

            if not placed_ok:
                self._guaranteed_place(gene, occ_room, occ_fac, occ_sec)

            self._add_to_occ(gene, occ_room, occ_fac, occ_sec)

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
    def _precalc_gene_masks(self, genes):
        """Pre-calculate static allowed_mask (operating hours + faculty avail + section blocked)."""
        total_slots = self.total_slots
        days_count  = len(self.days)
        op_mask_full = (1 << total_slots) - 1
        
        # Evening Avoidance logic: Avoid evening starts (7pm onwards) if EVENING_AVOIDANCE is HC.
        # This keeps the search space aligned and prevents infinite hard conflict loops.
        avoid_evening = (self._pen_type.get('EVENING_AVOIDANCE', 'SC1') == 'HC')
        op_mask_daytime = (1 << self.seven_pm_slot) - 1 if avoid_evening else op_mask_full
        
        multi_fac = self.multi_assignment_faculty
        fac_avail = self._fac_avail_days
        blocked   = self._blocked_bitmasks

        for g in genes:
            g.allowed_mask = []
            f_avail = fac_avail.get(g.faculty_id) if g.faculty_id and g.faculty_id not in multi_fac else None
            
            # Non-fixed genes are restricted to daytime if avoid_evening is True.
            # Pre-assignments (fixed genes) bypass evening restrictions.
            base_mask = op_mask_full if g.is_fixed else op_mask_daytime
            
            for d in range(days_count):
                mask = base_mask
                # HC-17/18: Faculty Availability
                if f_avail is not None and d not in f_avail:
                    mask = 0 
                # Blocked Time Slots
                day_blocked = blocked.get(d, 0)
                if day_blocked:
                    mask &= ~day_blocked
                g.allowed_mask.append(mask)

    def stop_engine(self):
        """Absolute Kill-Switch: Signals the engine to stop immediately via memory."""
        self.force_stop = True
        print("🛑 Engine Stop Requested (Memory Signal)")

    def _check_stop(self, stop_event=None, raise_exception=False):
        """
        Unified stop check.
        FIX: force_stop and event checks are NEVER throttled.
        File-system check remains throttled (expensive I/O).
        """
        # 0. Yield control to Eventlet on EVERY call to avoid CPU starvation and let Flask receive stop request!
        eventlet.sleep(0)

        # 1. Memory Check — ALWAYS checked, zero overhead (O(1) attribute read)
        if getattr(self, 'force_stop', False):
            if raise_exception:
                raise AlgorithmStopException("Force stop signal.")
            return True

        # 2. Eventlet / Thread Event — ALWAYS checked when provided
        if stop_event:
            if hasattr(stop_event, 'ready') and stop_event.ready():
                if raise_exception:
                    raise AlgorithmStopException("Eventlet stop event.")
                return True
            elif hasattr(stop_event, 'is_set') and stop_event.is_set():
                if raise_exception:
                    raise AlgorithmStopException("Thread stop event.")
                return True

        # 3. File-System Signal — throttled (disk I/O is expensive)
        hw_mode = self.hardware_profile.get('mode', 'Efficiency')
        if hw_mode == 'Efficiency':   _fs_freq = 50   # was 200 — reduced for faster response
        elif hw_mode == 'Balanced':   _fs_freq = 25   # was 50
        else:                         _fs_freq = 10   # was 1 (already fast for Performance)

        self._stop_check_count = getattr(self, '_stop_check_count', 0) + 1
        if self._stop_check_count % _fs_freq == 0:
            if os.path.exists(self.sig_path):
                if raise_exception:
                    raise AlgorithmStopException("Signal file stop.")
                return True

        return False

    def _greedy_seed_repair(self, chromosome, stop_event=None):
        """Quick heuristic pass to reduce seed conflicts before variant creation."""
        occ_room, occ_fac, occ_sec = self._build_occ_sets(chromosome.genes)
        targets = list(chromosome.conflicting_indices)
        random.shuffle(targets)
        
        for idx in targets:
            self._check_stop(stop_event, raise_exception=True)
            gene = chromosome.genes[idx]
            if gene.is_fixed: continue
            
            self._remove_from_occ(gene, occ_room, occ_fac, occ_sec)
            self.randomize_gene_fast(gene, occ_room, occ_fac, occ_sec, use_warmth=True)
            self._add_to_occ(gene, occ_room, occ_fac, occ_sec)

    def inject_new_data(self, new_course=None, new_section=None):
        """
        Public API for dynamic data injection. Call this when Admin adds a new record.
        Safely appends to the queue for processing in the next GA generation.
        """
        if new_course:
            self.courses.append(new_course)
            self.course_map[new_course['id']] = new_course
            # Update expected duration cache
            _lec = (new_course.get('synchronous_lec_hours', 0) or new_course.get('lec_units', 0)) or 0
            _lab = (new_course.get('synchronous_lab_hours', 0) or new_course.get('lab_units', 0)) or 0
            if _lec > 0: self._expected_duration[(new_course['id'], 'Lec')] = int(_lec * 2)
            if _lab > 0: self._expected_duration[(new_course['id'], 'Lab')] = int(_lab * 2)

        if new_section:
            self.sections.append(new_section)
            self.section_map[new_section['id']] = new_section
            self._sec_students[new_section['id']] = new_section.get('number_of_students', 0)

        self.pending_injections.append({'course': new_course, 'section': new_section})
        print(f"💉 Injection Queued: {new_course['course_code'] if new_course else 'Section Update'}")

    def _process_injections(self, population):
        """
        Internal handler to absorb new data into the current population.
        1. Identifies the current best chromosome.
        2. Appends new genes for the injected data.
        3. Performs greedy 'Least-Conflict' placement for the new genes.
        4. Re-populates the rest of the members to match the new chromosome length.
        """
        if not self.pending_injections:
            return population

        self.is_paused = True
        print(f"🔄 CEE: Processing {len(self.pending_injections)} injections...")
        
        # Start with the best one
        best_chrom = self._copy_chromosome(self._find_best(population))
        occ_room, occ_fac, occ_sec = self._build_occ_sets(best_chrom.genes)
        
        while self.pending_injections:
            data = self.pending_injections.pop(0)
            sec  = data['section']
            # Only handle section-based course expansion for now
            if sec:
                for cid in sec.get('course_ids', []):
                    # Check if already exists in genes to prevent duplicates
                    if any(g.course_id == cid and g.section_id == sec['id'] for g in best_chrom.genes):
                        continue
                        
                    course = self.course_map.get(cid)
                    if not course: continue
                    
                    # Create Lec/Lab genes (Simplified initial placement)
                    lec_dur = self._expected_duration.get((cid, 'Lec'))
                    if lec_dur:
                        new_g = Gene(cid, sec['id'], None, None, 0, 0, lec_dur, 'Lec', False)
                        self.randomize_gene_fast(new_g, occ_room, occ_fac, occ_sec, use_warmth=True)
                        best_chrom.genes.append(new_g)
                        self._add_to_occ(new_g, occ_room, occ_fac, occ_sec)

                    lab_dur = self._expected_duration.get((cid, 'Lab'))
                    if lab_dur:
                        new_g = Gene(cid, sec['id'], None, None, 0, 0, lab_dur, 'Lab', False)
                        self.randomize_gene_fast(new_g, occ_room, occ_fac, occ_sec, use_warmth=True)
                        best_chrom.genes.append(new_g)
                        self._add_to_occ(new_g, occ_room, occ_fac, occ_sec)

        # Full re-eval of the updated elite
        self.calculate_fitness(best_chrom)
        self._rebuild_lec_lab_pair_map(best_chrom)
        
        # Rebuild population with the new gene count
        new_population = [best_chrom]
        while len(new_population) < len(population):
            variant = self._perturb_chromosome(best_chrom, fraction=0.15)
            self.calculate_fitness(variant)
            new_population.append(variant)
            
        print(f"✅ CEE: Population synchronized to new gene count ({len(best_chrom.genes)})")
        self.is_paused = False
        return new_population

    def run_algorithm(self, progress_callback=None, seed_records=None, stop_event=None):
        """
        NSGA-II main loop with CEE (Continuous Evolutionary Engine) support.
        Supports background throttling and dynamic gene injection.
        """
        print("=== CEE CORE V1 === (continuous=on, dynamic_injection=ready)")
        self.is_running = True

        # ── Dynamic population size ────────────────────────────────────────
        n_genes_estimate = sum(
            (1 if (cm.get('synchronous_lec_hours', 0) or cm.get('lec_units', 0)) > 0 else 0) +
            (1 if (cm.get('synchronous_lab_hours', 0) or cm.get('lab_units', 0)) > 0 else 0) +
            (1 if ((cm.get('asynchronous_lec_hours', 0) or 0) +
                   (cm.get('asynchronous_lab_hours', 0) or 0)) > 0 else 0)
            for sec in self.sections for cid in sec['course_ids']
            for cm in [self.course_map.get(cid, {})]
        )
        
        _base_pop = self._hw_pop_size
        pop_size = max(_base_pop, min(120, int(n_genes_estimate * 0.4)))
        
        _scale_factor = pop_size / _base_pop
        n_hard_off     = int(self._hw_hard_offspring * _scale_factor)
        n_lns_off      = int(self._hw_lns_offspring * _scale_factor)
        n_soft_off     = int(self._hw_offspring_count * _scale_factor)
        
        stag_thresh    = self._hw_stag_threshold
        stag_severe    = self._hw_stag_severe
        stag_sc1_time  = self._hw_stag_sc1_timeout
        _target_gens   = self.hardware_profile['target_gens']
        _soft_max      = self.hardware_profile['soft_gens']

        # ── Initialise population ──────────────────────────────────────────
        population = []

        if seed_records:
            print("🌱 CEE: Initializing from seed records...")
            seed_chrom = self._build_seed_chromosome(seed_records)
            self._precalc_gene_masks(seed_chrom.genes)
            self.calculate_fitness(seed_chrom, hard_only=True)
            if seed_chrom.hard_conflicts > 0:
                self._greedy_seed_repair(seed_chrom, stop_event=stop_event)
                self.calculate_fitness(seed_chrom, hard_only=True)
            population.append(seed_chrom)

            n_variants = int(pop_size * 0.60)
            def _create_variant(i):
                frac = 0.05 + 0.15 * (i / max(n_variants - 1, 1))
                v = self._perturb_chromosome(seed_chrom, fraction=frac)
                self.calculate_fitness(v, hard_only=True)
                return v

            with ThreadPoolExecutor(max_workers=min(self.max_workers, n_variants)) as _exe:
                variant_chroms = list(_exe.map(_create_variant, range(n_variants)))
            
            fresh_count = (pop_size - 1) - n_variants
            if fresh_count > 0:
                with ThreadPoolExecutor(max_workers=min(self.max_workers, fresh_count)) as _exe:
                    fresh_chroms = list(_exe.map(lambda _: self.create_genome(skip_exhaustive=True), range(fresh_count)))
            else:
                fresh_chroms = []

            pending = variant_chroms + fresh_chroms
            self._eval_batch(pending, hard_only=True)
            population.extend(pending)
        else:
            # Cold start
            with ThreadPoolExecutor(max_workers=min(self.max_workers, pop_size)) as _exe:
                population = list(_exe.map(lambda _: self.create_genome(skip_exhaustive=True), range(pop_size)))
            for chrom in population:
                self._precalc_gene_masks(chrom.genes)
            self._eval_batch(population, hard_only=True, stop_event=stop_event)

        population.sort(key=lambda c: (c.hard_conflicts, c.soft_score))
        best_schedule        = self._copy_chromosome(self._find_best(population))
        
        stagnation_counter   = 0
        severe_counter       = 0
        last_best_hc         = best_schedule.hard_conflicts
        last_best_sc1        = best_schedule.sc1_violations
        last_best_ss         = best_schedule.soft_score

        # --- PHASE 3: Populate Lec-Lab Map ---
        self._rebuild_lec_lab_pair_map(best_schedule)
        current_phase        = 'hard'
        sc1_start_time       = None
        sc2_start_time       = None
        sc2_start_gen        = 0
        sc1_stag_counter     = 0
        last_diversity_inject = 0
        hc_stuck_counter = 0          # FIX 3: tracks gens with no HC improvement
        last_hc_for_stuck = best_schedule.hard_conflicts  # FIX 3: reference value
        
        def _get_elites():
            zero = [c for c in population if c.hard_conflicts == 0]
            pool = zero if zero else population
            return sorted(pool, key=lambda c: (c.hard_conflicts, c.soft_score))[:10]

        def _fit(c):
            if hard_phase:  self.calculate_fitness(c, hard_only=True)
            elif sc1_phase: self.calculate_fitness(c, sc1_only=True)
            else:           self.calculate_fitness(c, hard_only=False)

        _algo_t0 = time.time()
        generation = 1
        
        try:
            while self.is_running:
                # --- ABSOLUTE UNTHROTTLED STOP SIGNAL CHECK ---
                if self.force_stop:
                    raise AlgorithmStopException("Force stop.")
                if stop_event and (
                    (hasattr(stop_event, 'ready') and stop_event.ready()) or
                    (hasattr(stop_event, 'is_set') and stop_event.is_set())
                ):
                    raise AlgorithmStopException("Event stop.")
                if os.path.exists(self.sig_path):
                    self.force_stop = True
                    raise AlgorithmStopException("Signal file stop.")

                # --- CEE: Dynamic Data Injection ---
                if self.pending_injections:
                    population = self._process_injections(population)
                    best_schedule = self._copy_chromosome(self._find_best(population))
                    # Reset counters when data changes
                    stagnation_counter = 0; severe_counter = 0
                    if current_phase != 'hard':
                        current_phase = 'hard' # Force return to hard phase for new genes
                        print("🔀 CEE: Data injected. Returning to Hard Phase.")

                # ── Phase flags (Fixed order) ──────────────────────────────────
                hard_phase = (current_phase == 'hard')
                sc1_phase  = (current_phase == 'sc1')

                # Natural completion: exit when target generations reached
                if generation > _target_gens:
                    print(f"⏰ Target generations ({_target_gens}) reached at Gen {generation}. Best HC: {best_schedule.hard_conflicts}")
                    break

                # Hard phase safety timeout: if HC never reaches 0 by target_gens,
                # stop gracefully instead of running forever.
                if hard_phase and best_schedule.hard_conflicts > 0 and generation > _target_gens:
                    print(f"⏰ Hard phase timeout at Gen {generation}. Best HC: {best_schedule.hard_conflicts}")
                    break

                # --- CEE: Throttling / Resource Management ---
                if self.background_mode:
                    # 500ms sleep = near 0% CPU impact, but still evolves 2x per sec
                    eventlet.sleep(0.5) 
                else:
                    # Active mode: yield control to Eventlet on EVERY single generation
                    # to keep Flask/Socket.IO completely responsive (sub-100ms stop latency)!
                    eventlet.sleep(0)
                    
                    hw_mode = self.hardware_profile.get('mode', 'Efficiency')
                    _ts_freq = 20 if hw_mode == 'Efficiency' else 10
                    if generation % _ts_freq == 0:
                        time.sleep(0.005)


                if current_phase == 'sc2':
                    _sc2_elapsed = generation - sc2_start_gen
                    _ramp_end    = max(1, SOFT_REFINE_GENS // 2)
                    _sc2_t       = min(1.0, _sc2_elapsed / _ramp_end)
                    self._sc2_base = int(SC2_BASE + (500 - SC2_BASE) * _sc2_t)
                else:
                    self._sc2_base = SC2_BASE

                n_off = n_hard_off if hard_phase else n_soft_off

                # ── Generate offspring ─────────────────────────────────────────
                offspring = []
                if hard_phase and best_schedule.hard_conflicts > 0:
                    _cur_hc = best_schedule.hard_conflicts
                    
                    _adaptive_lns = (
                        n_lns_off                  if _cur_hc > 100 else
                        max(6, n_lns_off * 3 // 4) if _cur_hc > 50  else
                        max(4, n_lns_off // 2)     if _cur_hc > 15  else
                        max(3, n_lns_off // 3)     if _cur_hc > 5   else
                        max(2, n_lns_off // 4)
                    )
                    
                    # Optimize backtracking: only run heavy backtracking every 10 generations, or on interval stagnation steps (every 5th stagnation generation)
                    _allow_bt = (generation % 10 == 0 or (stagnation_counter > 0 and stagnation_counter % 5 == 0))
                    if _cur_hc <= 10 and _allow_bt:
                        nc = self._copy_chromosome(best_schedule)
                        self._exhaustive_resolve_last_conflicts(nc)
                        self.calculate_fitness(nc, hard_only=True)
                        if nc.hard_conflicts < _cur_hc:
                            offspring.append(nc)
                            # Walang continue para makabuo pa ng offspring
                    
                    for _ in range(_adaptive_lns):
                        nc = self._copy_chromosome(best_schedule)
                        self._hard_conflict_repair(nc, allow_backtrack=_allow_bt, stop_event=stop_event)
                        self.calculate_fitness(nc, hard_only=True)
                        offspring.append(nc)

                mutation_base = 0.2 if hard_phase else 0.5
                mutation_max  = 0.8
                stag_ratio    = min(1.0, stagnation_counter / max(1, stag_thresh))
                adaptive_mutation_rate = mutation_base + (mutation_max - mutation_base) * stag_ratio

                # SPEED FIX 4: Elite pool parent selection (top 40% only)
                _elite_pool = population[:max(4, len(population) * 4 // 10)]
                sc2_phase = (not hard_phase and not sc1_phase)
                
                # Adaptive offspring count
                if hard_phase:
                    _hc_drop_rate = getattr(self, '_last_gen_best_hc', best_schedule.hard_conflicts) - best_schedule.hard_conflicts
                    if _hc_drop_rate > 3:
                        n_off_actual = max(n_hard_off // 2, 4)
                    elif stagnation_counter > stag_thresh // 2:
                        n_off_actual = min(n_hard_off * 2, n_hard_off + 20)
                    else:
                        n_off_actual = n_off
                    self._last_gen_best_hc = best_schedule.hard_conflicts
                else:
                    n_off_actual = n_off
                    
                while len(offspring) < n_off_actual:
                    # Yield to Eventlet on each child cycle to handle stop signals instantly!
                    eventlet.sleep(0)
                    p1 = self._hard_phase_select(_elite_pool)
                    p2 = self._hard_phase_select(_elite_pool)
                    child = self.crossover(p1, p2, stop_event=stop_event)
                    if random.random() < adaptive_mutation_rate:
                        if sc2_phase:
                            self._guided_soft_mutate(child)
                        else:
                            self.proportional_mutate(child, stop_event=stop_event)
                    if hard_phase:
                        self.calculate_fitness(child, hard_only=True)
                        if child.hard_conflicts > 0:
                            _best_hc = best_schedule.hard_conflicts
                            # SPEED FIX 3: Skip repair when HC is high.
                            # At HC>50, let selection pressure work instead of
                            # calling expensive repair on every child.
                            _should_repair = (
                                _best_hc <= 50 or
                                child.hard_conflicts <= max(5, _best_hc // 3)
                            )
                            if _should_repair:
                                self._hard_conflict_repair(child, stop_event=stop_event, allow_backtrack=False)
                                self.calculate_fitness(child, hard_only=True)
                    offspring.append(child)

                if sc1_phase:
                    self._eval_batch(offspring, sc1_only=True, stop_event=stop_event)
                elif sc2_phase:
                    self._eval_batch(offspring, stop_event=stop_event)

                # ── Phase transitions ──────────────────────────────────────────
                if current_phase == 'hard' and best_schedule.hard_conflicts == 0:
                    current_phase  = 'sc1'
                    sc1_start_time = time.time()
                    sc1_stag_counter = 0
                    last_best_sc1  = best_schedule.sc1_violations
                    self._eval_batch(population, sc1_only=True, stop_event=stop_event)
                    self._eval_batch(offspring,  sc1_only=True, stop_event=stop_event)
                    stagnation_counter = 0; severe_counter = 0
                    print(f"🔀 SC-I phase begins at Gen {generation} (HC=0)")

                if current_phase == 'sc1' and (
                        best_schedule.sc1_violations == 0 or
                        sc1_stag_counter >= stag_sc1_time):
                    current_phase  = 'sc2'
                    sc2_start_time = time.time()
                    sc2_start_gen  = generation
                    self._eval_batch(population, stop_event=stop_event)
                    self._eval_batch(offspring, stop_event=stop_event)
                    stagnation_counter = 0; severe_counter = 0
                    last_best_ss = self._find_best(population).soft_score
                    print(f"🔀 SC-II phase begins at Gen {generation}")

                combined = population + offspring
                combined.sort(key=lambda c: (c.hard_conflicts, c.soft_score))
                population = combined[:pop_size]

                current_best = self._find_best(population)
                if self._is_better(current_best, best_schedule):
                    best_schedule = self._copy_chromosome(current_best)

                # ── Stagnation detection ───────────────────────────────────────
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
                    stagnation_counter = 0; severe_counter = 0; sc1_stag_counter = 0
                    self._rebuild_penalties()
                    # FIX 3: Reset stuck counter on any improvement
                    if hard_phase:
                        self._hc_eval_cutoff = max(5, current_best.hard_conflicts * 5)
                        if current_best.hard_conflicts < last_hc_for_stuck:
                            hc_stuck_counter = 0
                            last_hc_for_stuck = current_best.hard_conflicts
                else:
                    stagnation_counter += 1; severe_counter += 1
                    if sc1_phase: sc1_stag_counter += 1
                    self._adaptive_relax_constraints(severe_counter)
                    # FIX 3: Track HC stagnation separately
                    if hard_phase:
                        if current_best.hard_conflicts == last_hc_for_stuck:
                            hc_stuck_counter += 1
                        else:
                            hc_stuck_counter = 0
                            last_hc_for_stuck = current_best.hard_conflicts

                # ── FIX 3: Adaptive Nuclear Escape ─────────────────────────────
                _nuclear_threshold = (
                    50  if current_best.hard_conflicts == 1 else
                    75  if current_best.hard_conflicts <= 3 else
                    100 if current_best.hard_conflicts <= 5 else
                    150 if current_best.hard_conflicts <= 10 else
                    200
                )
                
                if (hard_phase and
                        hc_stuck_counter >= _nuclear_threshold and
                        current_best.hard_conflicts <= 10 and
                        current_best.hard_conflicts > 0):

                    print(f"☢️  NUCLEAR RESET at Gen {generation}: "
                          f"HC={current_best.hard_conflicts} stuck for "
                          f"{hc_stuck_counter} gens — rebuilding population")

                    # Keep the single best chromosome as seed
                    elite = self._copy_chromosome(best_schedule)

                    # Rebuild entire population fresh
                    population = [elite]
                    with ThreadPoolExecutor(max_workers=min(self.max_workers, pop_size - 1)) as _nuke_exe:
                        fresh_chroms = list(_nuke_exe.map(
                            lambda _: self.create_genome(skip_exhaustive=True),
                            range(pop_size - 1)
                        ))
                    for nc in fresh_chroms:
                        self._precalc_gene_masks(nc.genes)
                        self.calculate_fitness(nc, hard_only=True)
                    population.extend(fresh_chroms)

                    # Reset all counters
                    hc_stuck_counter   = 0
                    stagnation_counter = 0
                    severe_counter     = 0
                    last_hc_for_stuck  = self._find_best(population).hard_conflicts

                    # Rebuild pair map with new chromosomes
                    self._rebuild_lec_lab_pair_map(self._find_best(population))
                    self._rebuild_penalties()

                    print(f"☢️  Nuclear reset complete. New best HC: "
                          f"{self._find_best(population).hard_conflicts}")

                # ── Stagnation recovery ────────────────────────────────────────
                if severe_counter >= stag_severe:
                    elites  = _get_elites()
                    n_keep  = min(len(elites), 3)
                    new_pop = list(elites[:n_keep])
                    for elite in elites[:5]:
                        self._check_stop(stop_event, raise_exception=True)
                        nc = self._copy_chromosome(elite)
                        self._hard_conflict_repair(nc, stop_event=stop_event)
                        _fit(nc)
                        if hard_phase and 0 < nc.hard_conflicts <= 10:
                            self._exhaustive_resolve_last_conflicts(nc)
                            _fit(nc)
                        new_pop.append(nc)
                    
                    pop_size = self._hw_pop_size
                    while len(new_pop) < pop_size:
                        self._check_stop(stop_event, raise_exception=True)
                        nc = self.create_genome(skip_exhaustive=True)
                        _fit(nc)
                        new_pop.append(nc)
                    population = new_pop[:pop_size]
                    stagnation_counter = 0; severe_counter = 0
                    self._rebuild_penalties()
                    
                    # Rebuild pair map since new genomes were created
                    _new_best = self._find_best(population)
                    self._rebuild_lec_lab_pair_map(_new_best)

                elif stagnation_counter >= stag_thresh:
                    if len(population) < 80:
                        new_blood = []
                        for _ in range(10):
                            self._check_stop(stop_event, raise_exception=True)
                            new_blood.append(self.create_genome(skip_exhaustive=True))
                        for nc in new_blood: _fit(nc)
                        population.extend(new_blood)
                        pop_size = len(population)
                        stagnation_counter = 0

                # ── Diversity injection ────────────────────────────────────────
                # ── Diversity Injection (Fix 4: All Phases) ───────────────────
                # Extended from hard-phase-only to all phases, with scaled aggressiveness.
                _div_check_freq = 10 if hard_phase else 15
                if (generation % _div_check_freq == 0 and generation - last_diversity_inject >= DIV_COOLDOWN):
                    fingerprints = [(c.hard_conflicts, c.soft_score) for c in population]
                    most_common  = max(set(fingerprints), key=fingerprints.count)
                    similarity   = fingerprints.count(most_common) / len(population)
                    if similarity >= DIV_THRESHOLD:
                        elites     = _get_elites()
                        n_keep     = max(1, int(pop_size * 0.30))
                        n_perturb  = int(pop_size * 0.30)
                        n_fresh    = pop_size - n_keep - n_perturb

                        # Fix 5: Phase-aware perturb fraction
                        if hard_phase:
                            _perturb_frac = 0.58  # Aggressive in hard phase (was 0.40)
                        elif sc1_phase:
                            _perturb_frac = 0.30  # Medium in SC1 phase
                        else:
                            _perturb_frac = 0.15  # Gentle in SC2 — don't ruin good solutions

                        new_pop    = list(elites[:n_keep])
                        for _ in range(n_perturb):
                            base = random.choice(elites) if elites else population[0]
                            nc   = self._perturb_chromosome(base, fraction=_perturb_frac)
                            self._hard_conflict_repair(nc, stop_event=stop_event)
                            self.calculate_fitness(nc, hard_only=True)
                            new_pop.append(nc)
                        for _ in range(n_fresh):
                            self._check_stop(stop_event, raise_exception=True)
                            nc = self.create_genome(skip_exhaustive=True)
                            self.calculate_fitness(nc, hard_only=True)
                            new_pop.append(nc)
                        population = new_pop[:pop_size]
                        last_diversity_inject = generation

                # ── Telemetry Update ───────────────────────────────────────────
                if progress_callback:
                    prog_now = time.time()
                    prog_elapsed = prog_now - _algo_t0
                    gps = round(generation / prog_elapsed, 1) if prog_elapsed > 0 else 0
                    progress_callback({
                        'generation': generation,
                        'hard_conflicts': current_best.hard_conflicts,
                        'soft_score': current_best.soft_score,
                        'sc1_violations': current_best.sc1_violations,
                        'sc2_violations': current_best.sc2_violations,
                        'best_chromosome': current_best,
                        'gen_per_sec': gps,
                        'hardware': {'label': self.hardware_profile['label'], 'mode': self.hardware_profile['mode'], 'target_gens': _target_gens}
                    })

                # ── Termination ────────────────────────────────────────────────
                # PERFECT SCHEDULE AUTO-STOP: If all conflicts and violations (HC, SC-I, and SC-II) are exactly 0,
                # stop immediately to secure this flawless schedule.
                if (current_best.hard_conflicts == 0 and 
                        getattr(current_best, 'sc1_violations', -1) == 0 and 
                        getattr(current_best, 'sc2_violations', -1) == 0):
                    print(f"🎉 PERFECT SCHEDULE FOUND at Gen {generation}! (HC=0, SC-I=0, SC-II=0). Auto-stopping...")
                    best_schedule = self._copy_chromosome(current_best)
                    break

                if current_phase == 'sc2' and current_best.hard_conflicts == 0:
                    if current_best.fitness == 0 and (generation - sc2_start_gen) >= 20:
                        break
                    if (generation - sc2_start_gen) >= _soft_max:
                        break
                
                generation += 1

        except AlgorithmStopException:
            print(f"🛑 Generation {generation}: Global stop signal detected. Terminating...")
        finally:
            print(f"🏁 Generation {generation}: Loop terminated. Cleaning up...")
            self.is_running = False
            # Ensure sig file is cleared
            try:
                if os.path.exists(self.sig_path):
                    os.remove(self.sig_path)
            except: pass

        # ── Final Local Search Refinement ───────────────────────────────
        # Skip refinement if stop was forced
        if not self.force_stop and best_schedule.hard_conflicts == 0 and best_schedule.soft_score > 0:
            print(f"🔍 Running Local Search refinement on best schedule (Soft Score: {best_schedule.soft_score})...")
            best_schedule = self._local_search_refinement(best_schedule, max_attempts=200)
            print(f"✨ Refinement complete. Final Soft Score: {best_schedule.soft_score}")

        return best_schedule
