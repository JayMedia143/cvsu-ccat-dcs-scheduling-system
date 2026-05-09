import sys
import os
import argparse
import json
from collections import defaultdict
import re

try:
    import eventlet
    eventlet.monkey_patch()
except ImportError:
    pass

from sqlalchemy import or_
try:
    from app import (app, db, ScheduledClass, Course, Section, Faculty, Room,
                     Constraint, SystemSettings, PreAssignment, FacultyAssignment)
    from genetic_algorithm import GeneticScheduler, Gene, Chromosome
except ImportError as e:
    print(f"\033[91mError: Could not import required modules.\033[0m\n{e}")
    sys.exit(1)


class SafeObject:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class Colors:
    HEADER = '\033[95m'
    BLUE   = '\033[94m'
    CYAN   = '\033[96m'
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    RED    = '\033[91m'
    BOLD   = '\033[1m'
    RESET  = '\033[0m'


# ─────────────────────────────────────────────────────────────────────────────
# BANNER
# ─────────────────────────────────────────────────────────────────────────────
def print_banner():
    print(f"""
{Colors.HEADER}{Colors.BOLD}========================================================================
🧬  CVSU DCS SCHEDULER — ACCURATE CONSTRAINT DEBUGGER  🧬
        Powered by GA's own calculate_fitness() engine
========================================================================{Colors.RESET}
Exact same logic as the Genetic Algorithm.
HC count here == HC count in the running system.
""")


# ─────────────────────────────────────────────────────────────────────────────
# BUILD GENETIC SCHEDULER (mirrors app.py's generate route setup)
# ─────────────────────────────────────────────────────────────────────────────
def build_scheduler(selected_semester, start_hour, end_hour, allowed_days, selected_depts=None):
    """Instantiate GeneticScheduler with the same data the GA uses."""

    if selected_depts:
        raw_courses = Course.query.filter(
            Course.is_archived == False,
            Course.semester_offered == selected_semester,
            Course.department.in_(selected_depts)
        ).all()
    else:
        raw_courses = Course.query.filter_by(
            is_archived=False, semester_offered=selected_semester).all()
    courses_data = [{
        'id': c.id, 'course_code': c.course_code,
        'department': c.department or '',
        'lec_units': c.lec_units or 0, 'lab_units': c.lab_units or 0,
        'synchronous_lec_hours':  c.synchronous_lec_hours  or 0,
        'synchronous_lab_hours':  c.synchronous_lab_hours  or 0,
        'asynchronous_lec_hours': c.asynchronous_lec_hours or 0,
        'asynchronous_lab_hours': c.asynchronous_lab_hours or 0,
    } for c in raw_courses]

    raw_rooms = Room.query.filter_by(is_archived=False).all()
    rooms_data = [{
        'id': r.id, 'room_name': r.room_name,
        'capabilities': r.capabilities or '',
        'status': r.status, 'capacity': r.capacity or 0,
        'special_course_ids': r.special_course_ids or '',
        'room_departments': r.room_departments or '',
    } for r in raw_rooms]

    valid_course_ids = {c['id'] for c in courses_data}

    _fa_fac_ids = [
        r[0] for r in db.session.query(FacultyAssignment.faculty_id)
        .join(Course, FacultyAssignment.course_id == Course.id)
        .filter(Course.semester_offered == selected_semester)
        .distinct().all() if r[0]
    ]
    raw_faculty = Faculty.query.filter(
        Faculty.is_archived == False,
        Faculty.max_weekly_hours > 0,
        or_(Faculty.full_name == 'T.B.A.', Faculty.id.in_(_fa_fac_ids))
    ).all()
    faculty_data = [{
        'id': f.id, 'full_name': f.full_name,
        'available_days': f.available_days or '',
        'max_weekly_hours': f.max_weekly_hours or 35,
        'department': f.department or '',
    } for f in raw_faculty]

    raw_sections = Section.query.filter_by(is_archived=False).all()
    sections_data = [{
        'id': s.id,
        'course_ids': [c.id for c in s.courses if c.id in valid_course_ids],
        'number_of_students': s.number_of_students or 0,
        'section_name': s.section_name,
    } for s in raw_sections]

    raw_pre = PreAssignment.query.filter_by(is_archived=False).all()
    pre_assignments = [
        SafeObject(
            course_id=pa.course_id, section_id=pa.section_id,
            faculty_id=pa.faculty_id, room_id=pa.room_id,
            day=pa.day, start_time=pa.start_time, end_time=pa.end_time
        )
        for pa in raw_pre if pa.course_id in valid_course_ids
    ]

    constraints_config = {
        c.logic_code: {'type': c.constraint_type, 'weight': c.weight}
        for c in Constraint.query.all()
    }

    raw_splits = (FacultyAssignment.query
                  .join(Course, FacultyAssignment.course_id == Course.id)
                  .filter(Course.semester_offered == selected_semester)
                  .all())
    split_assignments = []
    for fa in raw_splits:
        if fa.course_id not in valid_course_ids:
            continue
        for gtype, d1f, h1f, d2f, h2f in [
            ('Lab', 'split_day_1', 'split_hours_1', 'split_day_2', 'split_hours_2'),
            ('Lec', 'split_lec_day_1', 'split_lec_hours_1', 'split_lec_day_2', 'split_lec_hours_2'),
        ]:
            splits = []
            d1, h1 = getattr(fa, d1f, None), getattr(fa, h1f, None)
            d2, h2 = getattr(fa, d2f, None), getattr(fa, h2f, None)
            if d1 and h1: splits.append({'day': d1, 'hours': h1})
            if d2 and h2: splits.append({'day': d2, 'hours': h2})
            if splits:
                split_assignments.append({
                    'faculty_id': fa.faculty_id,
                    'course_id':  fa.course_id,
                    'section_id': fa.section_id,
                    'gtype': gtype, 'splits': splits,
                })

    fa_map = {
        (fa.course_id, fa.section_id): fa.faculty_id
        for fa in raw_splits if fa.course_id in valid_course_ids
    }

    # Blocked slots from SystemSettings
    settings = SystemSettings.query.first()
    blocked_slots = []
    if settings and getattr(settings, 'blocked_slots_json', None):
        try:
            blocked_slots = json.loads(settings.blocked_slots_json)
        except Exception:
            pass

    scheduler = GeneticScheduler(
        courses_data, sections_data, faculty_data, rooms_data,
        pre_assignments, constraints_config,
        start_time=start_hour, end_time=end_hour,
        allowed_days=allowed_days,
        split_assignments=split_assignments,
        fa_map=fa_map,
        blocked_slots=blocked_slots,
    )
    return scheduler


# ─────────────────────────────────────────────────────────────────────────────
# BUILD CHROMOSOME FROM RECORDS (list of dicts with course/section/room/day/time)
# ─────────────────────────────────────────────────────────────────────────────
def records_to_chromosome(scheduler, records):
    """Use scheduler's own _build_seed_chromosome so logic is identical."""
    chrom = scheduler._build_seed_chromosome(records)
    scheduler._precalc_gene_masks(chrom.genes)
    return chrom


# ─────────────────────────────────────────────────────────────────────────────
# HUMAN-READABLE REPORT from a fully-evaluated Chromosome
# ─────────────────────────────────────────────────────────────────────────────
def print_accurate_report(scheduler, chromosome, mode_title, semester):
    genes     = chromosome.genes
    cmap_inv  = {v: k for k, v in scheduler.CONSTRAINT_MAP.items()}

    # Quick lookup helpers
    course_map  = scheduler.course_map
    section_map = scheduler.section_map
    faculty_map = scheduler.faculty_map
    room_map    = scheduler.room_map

    def gene_label(g):
        c   = course_map.get(g.course_id,  {})
        sec = section_map.get(g.section_id, {})
        fac = faculty_map.get(g.faculty_id, {})
        r   = room_map.get(g.room_id,       {})
        day = scheduler.days[g.day_idx] if 0 <= g.day_idx < len(scheduler.days) else '?'
        st  = scheduler.slot_to_time(g.start_idx)
        en  = scheduler.slot_to_time(g.end_idx)
        ccode   = c.get('course_code', f'CID={g.course_id}') if isinstance(c, dict) else getattr(c, 'course_code', f'CID={g.course_id}')
        secname = sec.get('section_name', f'SID={g.section_id}') if isinstance(sec, dict) else getattr(sec, 'section_name', f'SID={g.section_id}')
        facname = (fac.get('full_name', 'T.B.A.') if isinstance(fac, dict) else getattr(fac, 'full_name', 'T.B.A.')) or 'T.B.A.'
        roomname = (r.get('room_name', '?') if isinstance(r, dict) else getattr(r, 'room_name', '?')) or '?'
        return f"{ccode} ({secname}) [{g.gene_type}] | {day} {st}-{en} | {roomname} | {facname}"

    # ── Header ────────────────────────────────────────────────────────────────
    print(f"\n{Colors.GREEN}{Colors.BOLD}{'='*72}{Colors.RESET}")
    print(f"📊 {Colors.BOLD}ACCURATE GA DIAGNOSTIC — {mode_title} ({semester.upper()}){Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}{'='*72}{Colors.RESET}")
    print(f"   Total genes (classes)  : {len(genes)}")
    print(f"   Hard Conflicts (HC)    : {Colors.RED}{Colors.BOLD}{chromosome.hard_conflicts}{Colors.RESET}  ← exact same as GA display")
    print(f"   SC-I Violations        : {Colors.YELLOW}{chromosome.sc1_violations}{Colors.RESET}")
    print(f"   SC-II Violations       : {Colors.YELLOW}{chromosome.sc2_violations}{Colors.RESET}")
    print(f"   Soft Score             : {chromosome.soft_score}")
    print(f"   Active violation codes : {', '.join(chromosome.violation_codes) or 'none'}")

    # ── Per-constraint detailed breakdown ────────────────────────────────────
    # Re-run a targeted scan so we can print PER-GENE details
    # This mirrors calculate_fitness() logic exactly.

    # Build occ bitmasks (same as GA)
    from collections import defaultdict as dd
    room_bits = dd(int); fac_bits = dd(int); sec_bits = dd(int)
    room_use  = dd(list); fac_use  = dd(list); sec_use  = dd(list)

    HC_DETAILS  = dd(list)   # code → [human-readable strings]
    SC1_DETAILS = dd(list)
    SC2_DETAILS = dd(list)

    multi_fac  = scheduler.multi_assignment_faculty
    multi_room = scheduler.multi_assignment_rooms
    exp_dur    = scheduler._expected_duration
    online_ids = scheduler.online_room_ids
    v_room_set = scheduler._virtual_room_set
    is_pe      = scheduler._is_pe
    sec_stu    = scheduler._sec_students
    seven_pm   = scheduler.seven_pm_slot
    five_pm    = scheduler.five_pm_slot
    blocked    = scheduler._blocked_bitmasks
    pen        = scheduler._pen

    sec_course_genes = {}   # (sec_id, course_id) → {'Lec': (g,i), 'Lab': (g,i)}

    for i, g in enumerate(genes):
        gl = gene_label(g)

        # HC-04: TBA Faculty in Sync Room
        if not g.is_fixed:
            r_info = room_map.get(g.room_id, {})
            r_type = (r_info.get('room_type') if isinstance(r_info, dict) else getattr(r_info, 'room_type', 'Sync')) or 'Sync'
            is_tba = scheduler._is_fac_tba.get(g.faculty_id, False)
            if is_tba and r_type == 'Sync' and pen.get('STRICT_ALLOC_ASYNC', 0):
                HC_DETAILS['HC-04 (TBA Faculty in Sync Room)'].append(gl)

        # HC-19/Operating Hours via allowed_mask
        if g.allowed_mask:
            am = g.allowed_mask[g.day_idx]
            if (g.bitmask & am) != g.bitmask:
                HC_DETAILS['HC-19/HC-15 (Outside allowed hours or unavailable day)'].append(gl)

        # HC-05/06: Strict Duration
        if not g.is_fixed and getattr(g, 'locked_day', -1) < 0:
            ed = exp_dur.get((g.course_id, g.gene_type))
            if ed and g.duration_slots != ed:
                tag = 'HC-05 (Wrong Lec Duration)' if g.gene_type == 'Lec' else 'HC-06 (Wrong Lab Duration)'
                HC_DETAILS[tag].append(
                    f"{gl}  [expected {ed//2}h, got {g.duration_slots//2}h]"
                )

        # HC-20: Hourly Alignment
        if not g.is_fixed and g.start_idx % 2 != 0:
            HC_DETAILS['HC-20 (Half-hour start)'].append(gl)

        # HC-23: Faculty Day Split
        ld = getattr(g, 'locked_day', -1)
        if ld >= 0 and g.day_idx != ld and not g.is_fixed:
            HC_DETAILS['HC-23 (Faculty Day Split)'].append(gl)

        # SC-I-01: Virtual Room
        if not g.is_fixed and g.room_id in v_room_set and g.gene_type != 'Async':
            SC1_DETAILS['SC-I-01 (Virtual/Online Room)'].append(gl)

        # SC-I-03: Evening Avoidance
        if not g.is_fixed and g.room_id not in v_room_set:
            if g.start_idx >= seven_pm:
                SC1_DETAILS['SC-I-03 (Evening — after 7PM)'].append(gl)
            elif g.start_idx >= five_pm:
                SC1_DETAILS['SC-I-03 (Evening — 5–7PM)'].append(gl)

        # SC-I-14: Room Suitability (Lab not in lab room, Lec not in lec room)
        if not g.is_fixed:
            r_info = room_map.get(g.room_id, {})
            caps = (r_info.get('capabilities', '') if isinstance(r_info, dict) else getattr(r_info, 'capabilities', '')) or ''
            if g.gene_type == 'Lab' and 'Computer Lab' not in caps and g.room_id not in online_ids:
                SC1_DETAILS['SC-I-14 (Lab not in Lab room)'].append(gl)
            elif g.gene_type == 'Lec' and 'Computer Lab' in caps:
                SC1_DETAILS['SC-I-10 (Lec in Lab fallback)'].append(gl)

        # Bitmask overlap tracking
        _mask = g.bitmask
        _d    = g.day_idx

        # Room Overlap (HC-13)
        if g.room_id not in online_ids and g.room_id not in multi_room:
            rkey = (g.room_id, _d)
            if (room_bits[rkey] & _mask) != 0:
                r_info = room_map.get(g.room_id, {})
                rn = (r_info.get('room_name', '?') if isinstance(r_info, dict) else getattr(r_info, 'room_name', '?'))
                day = scheduler.days[_d] if 0 <= _d < len(scheduler.days) else '?'
                for ps, pe, pi in room_use[rkey]:
                    if ps < g.end_idx and pe > g.start_idx and not genes[pi].is_fixed:
                        HC_DETAILS['HC-13 (Room Overlap)'].append(
                            f"Room {rn} on {day}:\n"
                            f"       {gene_label(genes[pi])}\n"
                            f"     ↔ {gl}"
                        )
            room_bits[rkey] |= _mask

        # Faculty Overlap (HC-10)
        if g.faculty_id and g.faculty_id not in multi_fac:
            fkey = (g.faculty_id, _d)
            if (fac_bits[fkey] & _mask) != 0:
                fac_info = faculty_map.get(g.faculty_id, {})
                fn = (fac_info.get('full_name', '?') if isinstance(fac_info, dict) else getattr(fac_info, 'full_name', '?'))
                day = scheduler.days[_d] if 0 <= _d < len(scheduler.days) else '?'
                for ps, pe, pi in fac_use[fkey]:
                    if ps < g.end_idx and pe > g.start_idx and not genes[pi].is_fixed:
                        HC_DETAILS['HC-10 (Faculty Overlap)'].append(
                            f"{fn} on {day}:\n"
                            f"       {gene_label(genes[pi])}\n"
                            f"     ↔ {gl}"
                        )
            fac_bits[fkey] |= _mask

        # Section Overlap (HC-09)
        skey = (g.section_id, _d)
        if (sec_bits[skey] & _mask) != 0:
            sec_info = section_map.get(g.section_id, {})
            sn = (sec_info.get('section_name', '?') if isinstance(sec_info, dict) else getattr(sec_info, 'section_name', '?'))
            day = scheduler.days[_d] if 0 <= _d < len(scheduler.days) else '?'
            for ps, pe, pi in sec_use[skey]:
                if ps < g.end_idx and pe > g.start_idx and not genes[pi].is_fixed:
                    HC_DETAILS['HC-09 (Section Overlap)'].append(
                        f"{sn} on {day}:\n"
                        f"       {gene_label(genes[pi])}\n"
                        f"     ↔ {gl}"
                    )
        sec_bits[skey] |= _mask

        room_use[(g.room_id, _d)].append((g.start_idx, g.end_idx, i))
        if g.faculty_id:
            fac_use[(g.faculty_id, _d)].append((g.start_idx, g.end_idx, i))
        sec_use[(g.section_id, _d)].append((g.start_idx, g.end_idx, i))

        if g.gene_type in ('Lec', 'Lab'):
            key = (g.section_id, g.course_id)
            if key not in sec_course_genes:
                sec_course_genes[key] = {}
            sec_course_genes[key][g.gene_type] = (g, i)

    # HC-12: Max Consecutive Student Load (> 12 slots = 6h, same as GA)
    for (sec_id, day_idx), slots in sec_use.items():
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
                sec_info = section_map.get(sec_id, {})
                sn  = (sec_info.get('section_name', f'SID={sec_id}') if isinstance(sec_info, dict)
                        else getattr(sec_info, 'section_name', f'SID={sec_id}'))
                day = scheduler.days[day_idx] if 0 <= day_idx < len(scheduler.days) else '?'
                HC_DETAILS['HC-12 (Max 6h Consecutive Student Load)'].append(
                    f"Section {sn} on {day}: {streak/2:.1f}h consecutive"
                )
                break

    # HC-16: Max Consecutive Faculty Load (> 12 slots = 6h, same as GA)
    for (fac_id, day_idx), slots in fac_use.items():
        if fac_id in multi_fac:
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
                fac_info = faculty_map.get(fac_id, {})
                fn  = (fac_info.get('full_name', f'FID={fac_id}') if isinstance(fac_info, dict)
                       else getattr(fac_info, 'full_name', f'FID={fac_id}'))
                day = scheduler.days[day_idx] if 0 <= day_idx < len(scheduler.days) else '?'
                HC_DETAILS['HC-16 (Max 6h Consecutive Faculty Load)'].append(
                    f"{fn} on {day}: {streak/2:.1f}h consecutive"
                )
                break

    # SC-I-08/09/11: Lec-Lab sequence & proximity
    for type_genes in sec_course_genes.values():
        lec_entry = type_genes.get('Lec')
        lab_entry = type_genes.get('Lab')
        if not (lec_entry and lab_entry):
            continue
        lg, li = lec_entry
        bg, bi = lab_entry

        lec_day = scheduler.days[lg.day_idx] if 0 <= lg.day_idx < len(scheduler.days) else '?'
        lab_day = scheduler.days[bg.day_idx] if 0 <= bg.day_idx < len(scheduler.days) else '?'

        c_info = course_map.get(lg.course_id, {})
        ccode  = (c_info.get('course_code', '?') if isinstance(c_info, dict) else getattr(c_info, 'course_code', '?'))
        s_info = section_map.get(lg.section_id, {})
        sname  = (s_info.get('section_name', '?') if isinstance(s_info, dict) else getattr(s_info, 'section_name', '?'))

        # HC-11 / SC-I-11: Lab before Lec (GA counts this as hard_conflicts += 1)
        if (bg.day_idx < lg.day_idx or
                (bg.day_idx == lg.day_idx and bg.start_idx < lg.start_idx)):
            HC_DETAILS['SC-I-11/LEC_LAB_SEQUENCE (Lab placed before Lec — counted as HC by GA)'].append(
                f"{ccode} ({sname}): Lec on {lec_day} {scheduler.slot_to_time(lg.start_idx)}"
                f" | Lab on {lab_day} {scheduler.slot_to_time(bg.start_idx)}"
            )

        # SC-I-08: Lab day before Lec day (soft only)
        elif bg.day_idx < lg.day_idx:
            SC1_DETAILS['SC-I-08 (Lab day before Lec day)'].append(
                f"{ccode} ({sname}): Lec={lec_day}, Lab={lab_day}"
            )

        # SC-I-09: Lec-Lab more than 2 days apart
        if abs(lg.day_idx - bg.day_idx) > 2:
            SC1_DETAILS['SC-I-09 (Lec-Lab more than 2 days apart)'].append(
                f"{ccode} ({sname}): Lec={lec_day}, Lab={lab_day}"
                f" (gap={abs(lg.day_idx - bg.day_idx)} days)"
            )

    # ── Print HC Details ──────────────────────────────────────────────────────
    total_hc_items = sum(len(v) for v in HC_DETAILS.values())
    print(f"\n{Colors.RED}{Colors.BOLD}{'─'*72}")
    print(f"🚨  HARD CONFLICTS: {chromosome.hard_conflicts}  (GA-exact)")
    print(f"{'─'*72}{Colors.RESET}")
    print(f"   Note: GA increments HC once per overlapping PAIR + once per")
    print(f"   duration/alignment/sequence violation. Items below = raw events.\n")

    if not HC_DETAILS:
        print(f"   {Colors.GREEN}✅ No hard conflicts detected!{Colors.RESET}")
    else:
        for code, msgs in sorted(HC_DETAILS.items()):
            print(f"\n{Colors.RED}  📌 {code} ({len(msgs)} events){Colors.RESET}")
            for m in msgs[:10]:
                for line in m.split('\n'):
                    print(f"     {line}")
            if len(msgs) > 10:
                print(f"     ... and {len(msgs) - 10} more")

    # ── Print Soft Details ────────────────────────────────────────────────────
    total_sc_items = sum(len(v) for v in SC1_DETAILS.values()) + sum(len(v) for v in SC2_DETAILS.values())
    print(f"\n{Colors.YELLOW}{Colors.BOLD}{'─'*72}")
    print(f"💡  SOFT CONSTRAINTS: SC-I={chromosome.sc1_violations}  SC-II={chromosome.sc2_violations}")
    print(f"{'─'*72}{Colors.RESET}")

    if not SC1_DETAILS and not SC2_DETAILS:
        print(f"   {Colors.GREEN}✅ No soft violations!{Colors.RESET}")
    else:
        for code, msgs in sorted(SC1_DETAILS.items()):
            print(f"\n{Colors.YELLOW}  📌 {code} ({len(msgs)} events){Colors.RESET}")
            for m in msgs[:8]:
                print(f"     {m}")
            if len(msgs) > 8:
                print(f"     ... and {len(msgs) - 8} more")
        for code, msgs in sorted(SC2_DETAILS.items()):
            print(f"\n{Colors.CYAN}  📌 {code} ({len(msgs)} events){Colors.RESET}")
            for m in msgs[:8]:
                print(f"     {m}")

    # ── Faculty Load Summary ───────────────────────────────────────────────────
    print(f"\n{Colors.BLUE}{Colors.BOLD}{'─'*72}")
    print(f"📋  FACULTY DAILY LOAD SUMMARY (flagged days only)")
    print(f"{'─'*72}{Colors.RESET}")

    fac_day_slots = defaultdict(int)
    for g in genes:
        if g.faculty_id and g.faculty_id not in multi_fac:
            fac_day_slots[(g.faculty_id, g.day_idx)] += g.duration_slots

    overloaded = {}
    for (fid, didx), total in sorted(fac_day_slots.items(), key=lambda x: -x[1]):
        if total > 12:  # > 6 hours
            fac_info = faculty_map.get(fid, {})
            fn  = (fac_info.get('full_name', f'FID={fid}') if isinstance(fac_info, dict)
                   else getattr(fac_info, 'full_name', f'FID={fid}'))
            day = scheduler.days[didx] if 0 <= didx < len(scheduler.days) else '?'
            overloaded.setdefault(fn, []).append(f"{day}: {total/2:.1f}h")

    if overloaded:
        for fn, days in sorted(overloaded.items()):
            print(f"   {Colors.YELLOW}⚠️  {fn}{Colors.RESET} → {', '.join(days)}")
    else:
        print(f"   {Colors.GREEN}All faculty within 6h/day limit.{Colors.RESET}")

    # ── Online Room Overflow Summary ───────────────────────────────────────────
    online_genes = [g for g in genes if g.room_id in online_ids and g.gene_type != 'Async']
    if online_genes:
        print(f"\n{Colors.CYAN}{Colors.BOLD}{'─'*72}")
        print(f"🌐  ONLINE ROOM OVERFLOW ({len(online_genes)} classes pushed to virtual)")
        print(f"{'─'*72}{Colors.RESET}")
        for g in online_genes[:20]:
            print(f"   {gene_label(g)}")
        if len(online_genes) > 20:
            print(f"   ... and {len(online_genes) - 20} more")

    print(f"\n{Colors.GREEN}{Colors.BOLD}{'='*72}{Colors.RESET}")
    print(f"✅  Scan complete — HC={chromosome.hard_conflicts} | SC1={chromosome.sc1_violations} | SC2={chromosome.sc2_violations}")
    print(f"{Colors.GREEN}{'='*72}{Colors.RESET}\n")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main_run(force_simulate, selected_semester):
    print_banner()

    with app.app_context():
        settings = SystemSettings.query.first()
        start_hour   = settings.start_hour   if settings else 7
        end_hour     = settings.end_hour     if settings else 20
        allowed_days = (
            [d.strip() for d in settings.allowed_days.split(',') if d.strip()]
            if (settings and settings.allowed_days)
            else ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        )

        selected_depts = None
        sig = "live_conflicts.json"
        if os.path.exists(sig) and not force_simulate:
            try:
                with open(sig) as f:
                    data = json.load(f)
                selected_semester = data.get('semester', selected_semester)
                selected_depts = data.get('selected_depts', None)
                if selected_depts:
                    print(f"{Colors.GREEN}📌 Live run restricted to departments: {', '.join(selected_depts)}{Colors.RESET}")
            except Exception:
                pass

        print(f"{Colors.BLUE}🔧 Building GeneticScheduler (same config as live run)...{Colors.RESET}")
        scheduler = build_scheduler(selected_semester, start_hour, end_hour, allowed_days, selected_depts)
        
        # Disable stop checks in debugger context to prevent AlgorithmStopException
        scheduler._check_stop = lambda *args, **kwargs: False

        print(f"   Courses: {len(scheduler.courses)} | Sections: {len(scheduler.sections)}"
              f" | Faculty: {len(scheduler.faculty)} | Rooms: {len(scheduler.rooms)}")

        # ── Mode 1: Live running chromosome ────────────────────────────────
        if os.path.exists(sig) and not force_simulate:
            print(f"\n{Colors.GREEN}🔥 live_conflicts.json detected — loading LIVE chromosome state...{Colors.RESET}")
            try:
                with open(sig) as f:
                    data = json.load(f)
                selected_semester = data.get('semester', selected_semester)
                records = data.get('schedules', [])
                chrom = records_to_chromosome(scheduler, records)
                scheduler.calculate_fitness(chrom, hard_only=False)
                print_accurate_report(scheduler, chrom, "LIVE RUNNING GENERATION", selected_semester)
                return
            except Exception as e:
                import traceback
                print(f"{Colors.RED}⚠️  Failed to load live_conflicts.json: {e}{Colors.RESET}")
                traceback.print_exc()

        # ── Mode 2: Saved master schedule ──────────────────────────────────
        existing = ScheduledClass.query.filter_by(
            semester=selected_semester, is_draft=False).count()

        if existing > 0 and not force_simulate:
            print(f"\n{Colors.GREEN}✅ Saved master schedule found — running DB diagnostics...{Colors.RESET}")
            db_classes = ScheduledClass.query.filter_by(
                semester=selected_semester, is_draft=False).all()
            records = [{
                'course_id':    sc.course_id,
                'section_id':   sc.section_id,
                'faculty_id':   sc.faculty_id,
                'room_id':      sc.room_id,
                'day':          sc.day,
                'start_time':   sc.start_time,
                'end_time':     sc.end_time,
                'session_type': sc.session_type,
            } for sc in db_classes]
            chrom = records_to_chromosome(scheduler, records)
            scheduler.calculate_fitness(chrom, hard_only=False)
            print_accurate_report(scheduler, chrom, "SAVED DATABASE SCHEDULE", selected_semester)

        # ── Mode 3: Simulate fresh genome ──────────────────────────────────
        else:
            print(f"\n{Colors.YELLOW}⚠️  No schedule found or --simulate requested. Generating fresh genome...{Colors.RESET}")
            chrom = scheduler.create_genome()
            scheduler._precalc_gene_masks(chrom.genes)
            scheduler.calculate_fitness(chrom, hard_only=False)
            print_accurate_report(scheduler, chrom, "INITIAL CHROMOSOME SIMULATION", selected_semester)


def main():
    parser = argparse.ArgumentParser(description="Accurate CVSU DCS Scheduler Debugger")
    parser.add_argument('--simulate', '-s', action='store_true',
                        help="Force simulate initial chromosome even if DB/live data exists")
    parser.add_argument('--semester', default='1st Semester',
                        help="Target semester to analyze")
    args = parser.parse_args()
    main_run(args.simulate, args.semester)


if __name__ == '__main__':
    main()
