import sys
import os
import argparse
from collections import defaultdict

# Force eventlet monkey patching to prevent any import warnings if app.py is loaded
try:
    import eventlet
    eventlet.monkey_patch()
except ImportError:
    pass

# Import Flask app context and database models
from sqlalchemy import or_, and_, func
try:
    from app import app, db, ScheduledClass, Course, Section, Faculty, Room, Constraint, SystemSettings, PreAssignment, FacultyAssignment
    from genetic_algorithm import GeneticScheduler
except ImportError as e:
    print("\033[91mError: Could not import app.py models or genetic_algorithm.py. Please make sure you are running this from the project root.\033[0m")
    print(e)
    sys.exit(1)

class SafeObject:
    """Helper class to pass database data to threads safely."""
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

# CLI Colors
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    RESET = '\033[0m'

def print_banner():
    banner = f"""
{Colors.HEADER}{Colors.BOLD}========================================================================
🧬 CVSU CCAT DCS SCHEDULER: ADVANCED CONSTRAINT DEEP-SCAN DEBUGGER 🧬
========================================================================{Colors.RESET}
This debugger scans the live database, builds occupation state tables,
and isolates precisely which courses, faculty, sections, or room shortages
are causing constraint violations or trapping the Genetic Algorithm.
"""
    print(banner)

def build_diagnostic_report(schedules, courses, sections, faculty, rooms, online_room_ids, start_hour, end_hour, allowed_days, selected_semester, mode_title):
    total_slots = (end_hour - start_hour) * 2

    print(f"\n{Colors.BLUE}⚙️ Loading Settings...{Colors.RESET}")
    print(f"   - Operating Hours: {start_hour}:00 AM - {end_hour}:00 PM ({total_slots} 30-min slots)")
    print(f"   - Allowed Days: {', '.join(allowed_days)}")
    print(f"   - Target Semester: {Colors.CYAN}{selected_semester}{Colors.RESET}")
    print(f"   - Total Scheduled Classes Loaded: {Colors.CYAN}{len(schedules)}{Colors.RESET}")

    # Violations Scorecards
    hc_scorecard = defaultdict(int)
    sc_scorecard = defaultdict(int)

    # Details list
    violations_details = defaultdict(list)

    # Occupation tables for overlap detection
    room_use = defaultdict(list)    # (room_id, day_str) -> [(start_slot, end_slot, scheduled_class_obj)]
    fac_use = defaultdict(list)     # (faculty_id, day_str) -> [(start_slot, end_slot, scheduled_class_obj)]
    sec_use = defaultdict(list)     # (section_id, day_str) -> [(start_slot, end_slot, scheduled_class_obj)]

    # Faculty workload tracker
    fac_weekly_hours = defaultdict(float)

    def to_slot(time_str):
        try:
            h, m = map(int, time_str.split(':'))
            return ((h - start_hour) * 2) + (1 if m >= 30 else 0)
        except Exception:
            return None

    def _norm_dept(s):
        return (s or '').lower().replace('department of ', '').replace(' and ', ' & ').strip()

    # Scan and compile
    for sc in schedules:
        c = courses.get(sc.course_id)
        sec = sections.get(sc.section_id)
        fac = faculty.get(sc.faculty_id) if sc.faculty_id else None
        r = rooms.get(sc.room_id) if sc.room_id else None

        day = sc.day
        start_slot = to_slot(sc.start_time)
        end_slot = to_slot(sc.end_time)

        if start_slot is None or end_slot is None:
            continue

        duration_slots = end_slot - start_slot
        duration_hours = duration_slots / 2.0

        c_code = c.course_code if c else f"Course ID {sc.course_id}"
        sec_name = sec.section_name if sec else f"Section ID {sc.section_id}"
        fac_name = fac.full_name if fac else "T.B.A."
        room_name = r.room_name if r else "No Room Specified"

        # 1. Operating Hours Out-of-bounds (HC-19)
        if start_slot < 0 or end_slot > total_slots:
            hc_scorecard['HC-19'] += 1
            violations_details['HC-19 (Operating Hours Violation)'].append(
                f"{c_code} ({sec_name}) scheduled at {sc.day} {sc.start_time}-{sc.end_time}, which is outside operating limits."
            )

        # 2. Hourly Alignment (HC-20)
        if start_slot % 2 != 0:
            hc_scorecard['HC-20'] += 1
            violations_details['HC-20 (Hourly Alignment Violation)'].append(
                f"{c_code} ({sec_name}) scheduled at {sc.day} {sc.start_time}-{sc.end_time}, starting on a half-hour boundary."
            )

        # 3. Room Suitability
        if r:
            if r.status != 'Available':
                hc_scorecard['HC-18'] += 1
                violations_details['HC-18 (Room Availability Violation)'].append(
                    f"Room {room_name} is set as Unavailable, but {c_code} ({sec_name}) is scheduled in it."
                )
            
            # Exclusivity departments check
            if r.room_departments and c and c.department:
                # Use _norm_dept for comparison to align perfectly with the GA
                r_depts_normalized = {_norm_dept(d) for d in r.room_departments.split(',') if d.strip()}
                c_dept_normalized = _norm_dept(c.department)
                if c_dept_normalized not in r_depts_normalized:
                    # In genetic_algorithm.py, this is SC-I-14 Room Suitability
                    sc_scorecard['SC-I-14'] += 1
                    violations_details['SC-I-14 (Room Suitability Violation - Dept Exclusivity)'].append(
                        f"Room {room_name} is restricted to department {r.room_departments}, but {c_code} of department {c.department} is scheduled there."
                    )

            # Room capabilities match (SC-I-14 Room Suitability)
            if sc.session_type == 'Lab' and 'Computer Lab' not in (r.capabilities or ''):
                sc_scorecard['SC-I-14'] += 1
                violations_details['SC-I-14 (Room Suitability Violation - Capability Match)'].append(
                    f"Lab class {c_code} ({sec_name}) is scheduled in Room {room_name} which lacks Computer Lab capabilities."
                )
            elif sc.session_type == 'Lec' and 'Lecture' not in (r.capabilities or '') and sc.room_id not in online_room_ids:
                if 'Computer Lab' in (r.capabilities or ''):
                    sc_scorecard['SC-I-10'] += 1
                    violations_details['SC-I-10 (Lecture in Lab Fallback)'].append(
                        f"Lecture class {c_code} ({sec_name}) is scheduled in Lab room {room_name} as a fallback."
                    )
                else:
                    sc_scorecard['SC-I-14'] += 1
                    violations_details['SC-I-14 (Room Suitability Violation - Capability Match)'].append(
                        f"Lecture class {c_code} ({sec_name}) is scheduled in Room {room_name} which lacks Lecture capabilities."
                    )

        # 4. Curriculum Duration Checks (HC-05 / HC-06)
        expected_slots = None
        if c:
            # Query split assignments from DB inside the active context
            from app import FacultyAssignment
            fa = FacultyAssignment.query.filter_by(course_id=sc.course_id, section_id=sc.section_id).first()
            if fa:
                if sc.session_type == 'Lab':
                    splits = []
                    if fa.split_day_1 == sc.day and fa.split_hours_1:
                        splits.append(fa.split_hours_1)
                    if fa.split_day_2 == sc.day and fa.split_hours_2:
                        splits.append(fa.split_hours_2)
                    if splits:
                        expected_slots = int(max(splits) * 2)
                    else:
                        expected_slots = int((c.synchronous_lab_hours or c.lab_units or 0) * 2)
                elif sc.session_type == 'Lec':
                    splits = []
                    if fa.split_lec_day_1 == sc.day and fa.split_lec_hours_1:
                        splits.append(fa.split_lec_hours_1)
                    if fa.split_lec_day_2 == sc.day and fa.split_lec_hours_2:
                        splits.append(fa.split_lec_hours_2)
                    if splits:
                        expected_slots = int(max(splits) * 2)
                    else:
                        expected_slots = int((c.synchronous_lec_hours or c.lec_units or 0) * 2)
            else:
                if sc.session_type == 'Lab':
                    expected_slots = int((c.synchronous_lab_hours or c.lab_units or 0) * 2)
                elif sc.session_type == 'Lec':
                    expected_slots = int((c.synchronous_lec_hours or c.lec_units or 0) * 2)

        if expected_slots is not None and expected_slots > 0:
            if duration_slots != expected_slots:
                if sc.session_type == 'Lec':
                    hc_scorecard['HC-05'] += 1
                    violations_details['HC-05 (Strict Lec Duration Mismatch)'].append(
                        f"{c_code} ({sec_name}) expected {expected_slots} slots ({expected_slots/2.0}h), but scheduled for {duration_slots} slots ({duration_hours}h) on {day}."
                    )
                elif sc.session_type == 'Lab':
                    hc_scorecard['HC-06'] += 1
                    violations_details['HC-06 (Strict Lab Duration Mismatch)'].append(
                        f"{c_code} ({sec_name}) expected {expected_slots} slots ({expected_slots/2.0}h), but scheduled for {duration_slots} slots ({duration_hours}h) on {day}."
                    )

        # 5. Faculty Day Split Checks (HC-23)
        if c:
            from app import FacultyAssignment
            fa = FacultyAssignment.query.filter_by(course_id=sc.course_id, section_id=sc.section_id).first()
            if fa:
                if sc.session_type == 'Lab':
                    split_days = []
                    if fa.split_day_1: split_days.append(fa.split_day_1)
                    if fa.split_day_2: split_days.append(fa.split_day_2)
                    if split_days and sc.day not in split_days:
                        hc_scorecard['HC-23'] += 1
                        violations_details['HC-23 (Faculty Day Split Violation)'].append(
                            f"Lab for {c_code} ({sec_name}) scheduled on {sc.day}, but curriculum split requires it on: {', '.join(split_days)}."
                        )
                elif sc.session_type == 'Lec':
                    split_days = []
                    if fa.split_lec_day_1: split_days.append(fa.split_lec_day_1)
                    if fa.split_lec_day_2: split_days.append(fa.split_lec_day_2)
                    if split_days and sc.day not in split_days:
                        hc_scorecard['HC-23'] += 1
                        violations_details['HC-23 (Faculty Day Split Violation)'].append(
                            f"Lec for {c_code} ({sec_name}) scheduled on {sc.day}, but curriculum split requires it on: {', '.join(split_days)}."
                        )

        # 4. Faculty Availability (HC-15)
        if fac:
            fac_weekly_hours[fac.id] += duration_hours
            if fac.available_days:
                f_avail = [d.strip() for d in fac.available_days.split(',') if d.strip()]
                if day not in f_avail:
                    hc_scorecard['HC-15'] += 1
                    violations_details['HC-15 (Faculty Availability Violation)'].append(
                        f"Guro {fac_name} is not available on {day}, but {c_code} ({sec_name}) is scheduled then."
                    )

        # Store in occupation lists for overlap scanning
        if r and r.id not in online_room_ids:
            room_use[(r.id, day)].append((start_slot, end_slot, sc, c_code, sec_name, room_name))
        if fac:
            fac_use[(fac.id, day)].append((start_slot, end_slot, sc, c_code, sec_name, fac_name))
        if sec:
            sec_use[(sec.id, day)].append((start_slot, end_slot, sc, c_code, sec_name))

    # Room Overlaps (HC-13)
    for (room_id, day), usages in room_use.items():
        usages.sort()
        for i in range(len(usages)):
            for j in range(i + 1, len(usages)):
                s1, e1, sc1, cc1, sec1, rname = usages[i]
                s2, e2, sc2, cc2, sec2, _ = usages[j]
                if max(s1, s2) < min(e1, e2):
                    hc_scorecard['HC-13'] += 1
                    violations_details['HC-13 (Room Overlap)'].append(
                        f"Room {Colors.RED}{rname}{Colors.RESET} has overlapping classes on {day}:\n"
                        f"     * {sc1.start_time}-{sc1.end_time}: {cc1} ({sec1})\n"
                        f"     * {sc2.start_time}-{sc2.end_time}: {cc2} ({sec2})"
                    )

    # Faculty Overlaps (HC-10)
    for (fac_id, day), usages in fac_use.items():
        usages.sort()
        for i in range(len(usages)):
            for j in range(i + 1, len(usages)):
                s1, e1, sc1, cc1, sec1, fname = usages[i]
                s2, e2, sc2, cc2, sec2, _ = usages[j]
                if max(s1, s2) < min(e1, e2):
                    hc_scorecard['HC-10'] += 1
                    violations_details['HC-10 (Faculty Overlap)'].append(
                        f"Guro {Colors.YELLOW}{fname}{Colors.RESET} is double-booked on {day}:\n"
                        f"     * {sc1.start_time}-{sc1.end_time}: {cc1} ({sec1}) in {rooms.get(sc1.room_id).room_name if rooms.get(sc1.room_id) else 'None'}\n"
                        f"     * {sc2.start_time}-{sc2.end_time}: {cc2} ({sec2}) in {rooms.get(sc2.room_id).room_name if rooms.get(sc2.room_id) else 'None'}"
                    )

    # Section Overlaps (HC-09)
    for (sec_id, day), usages in sec_use.items():
        usages.sort()
        for i in range(len(usages)):
            for j in range(i + 1, len(usages)):
                s1, e1, sc1, cc1, sec1 = usages[i]
                s2, e2, sc2, cc2, sec2 = usages[j]
                if max(s1, s2) < min(e1, e2):
                    hc_scorecard['HC-09'] += 1
                    violations_details['HC-09 (Section Overlap)'].append(
                        f"Section {Colors.CYAN}{sec1}{Colors.RESET} has clashing classes on {day}:\n"
                        f"     * {sc1.start_time}-{sc1.end_time}: {cc1} in {rooms.get(sc1.room_id).room_name if rooms.get(sc1.room_id) else 'None'}\n"
                        f"     * {sc2.start_time}-{sc2.end_time}: {cc2} in {rooms.get(sc2.room_id).room_name if rooms.get(sc2.room_id) else 'None'}"
                    )

    # Informational Faculty Workloads
    for f_id, hrs in fac_weekly_hours.items():
        fac_obj = faculty.get(f_id)
        if fac_obj and fac_obj.max_weekly_hours and hrs > fac_obj.max_weekly_hours:
            sc_scorecard['SC-I-15'] += 1
            violations_details['SC-I-15 (Faculty Workload Overload)'].append(
                f"Guro {fac_obj.full_name} has loaded {hrs} contact hours, exceeding their configured limit of {fac_obj.max_weekly_hours} hours."
            )

    # Virtual Room Usage details
    virtual_schedules = [s for s in schedules if s.room_id in online_room_ids and s.session_type != 'Async']
    if virtual_schedules:
        sc_scorecard['SC-I-01'] = len(virtual_schedules)
        for s in virtual_schedules:
            cc = courses.get(s.course_id).course_code if courses.get(s.course_id) else f"Course ID {s.course_id}"
            sn = sections.get(s.section_id).section_name if sections.get(s.section_id) else f"Section ID {s.section_id}"
            violations_details['SC-I-01 (Virtual Room Usage)'].append(
                f"{cc} ({sn}) is pushed to the virtual Online Room due to physical room saturation."
            )
            
    # 6. Consecutive Load Checks (HC-12 Student / HC-16 Faculty)
    for (sec_id, dname), usages in sec_use.items():
        slot_occupied = [False] * total_slots
        for s, e, sc, cc, sn in usages:
            # Set slots as occupied
            for slot in range(max(0, s), min(total_slots, e)):
                slot_occupied[slot] = True
        
        # Find max consecutive slots
        max_consec = 0
        current_consec = 0
        for occ in slot_occupied:
            if occ:
                current_consec += 1
                max_consec = max(max_consec, current_consec)
            else:
                current_consec = 0
                
        if max_consec > 8: # More than 4 hours (8 slots)
            hc_scorecard['HC-12'] += 1
            sec_name = sections.get(sec_id).section_name if sections.get(sec_id) else f"Section ID {sec_id}"
            violations_details['HC-12 (Max Consecutive Student Load Violation)'].append(
                f"Section {Colors.CYAN}{sec_name}{Colors.RESET} has {max_consec/2.0} consecutive hours of classes on {dname}, exceeding the 4.0 hours limit."
            )

    for (fac_id, dname), usages in fac_use.items():
        slot_occupied = [False] * total_slots
        for s, e, sc, cc, sn, fname in usages:
            for slot in range(max(0, s), min(total_slots, e)):
                slot_occupied[slot] = True
                
        # Find max consecutive slots
        max_consec = 0
        current_consec = 0
        for occ in slot_occupied:
            if occ:
                current_consec += 1
                max_consec = max(max_consec, current_consec)
            else:
                current_consec = 0
                
        if max_consec > 8: # More than 4 hours (8 slots)
            hc_scorecard['HC-16'] += 1
            fac_name = faculty.get(fac_id).full_name if faculty.get(fac_id) else f"Faculty ID {fac_id}"
            violations_details['HC-16 (Max Consecutive Faculty Load Violation)'].append(
                f"Guro {Colors.YELLOW}{fac_name}{Colors.RESET} has {max_consec/2.0} consecutive hours of classes on {dname}, exceeding the 4.0 hours limit."
            )

    # 7. Lec/Lab Sequence Check (SC-I-11)
    sec_course_schedules = defaultdict(list)
    for sc in schedules:
        sec_course_schedules[(sc.section_id, sc.course_id)].append(sc)
        
    day_indices = {'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6}
    
    for (sec_id, course_id), sc_list in sec_course_schedules.items():
        lec_classes = [sc for sc in sc_list if sc.session_type == 'Lec']
        lab_classes = [sc for sc in sc_list if sc.session_type == 'Lab']
        if lec_classes and lab_classes:
            for lec_sc in lec_classes:
                for lab_sc in lab_classes:
                    lec_day_idx = day_indices.get(lec_sc.day, 9)
                    lab_day_idx = day_indices.get(lab_sc.day, 9)
                    if lec_day_idx >= lab_day_idx:
                        sc_scorecard['SC-I-11'] += 1
                        cc = courses.get(course_id).course_code if courses.get(course_id) else f"Course ID {course_id}"
                        sn = sections.get(sec_id).section_name if sections.get(sec_id) else f"Section ID {sec_id}"
                        violations_details['SC-I-11 (Lec/Lab Sequence Violation)'].append(
                            f"For {Colors.CYAN}{cc} ({sn}){Colors.RESET}, Lecture is on {lec_sc.day} but Laboratory is on {lab_sc.day} (Lecture must precede Lab)."
                        )

    # --- REPORT DISPLAY ──────────────────────────────────────────────────
    print(f"\n{Colors.GREEN}{Colors.BOLD}========================================================================{Colors.RESET}")
    print(f"📊 {Colors.BOLD}DIAGNOSTIC SCORECARD: {mode_title} ({selected_semester.upper()}){Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}========================================================================{Colors.RESET}")

    total_hc = sum(hc_scorecard.values())
    total_sc = sum(sc_scorecard.values())

    print(f"\n🚨 {Colors.RED}{Colors.BOLD}HARD CONFLICTS DETECTED: {total_hc}{Colors.RESET}")
    if total_hc > 0:
        for hc_code, count in sorted(hc_scorecard.items()):
            print(f"   * [{Colors.RED}{hc_code}{Colors.RESET}] {count} violations")
    else:
        print(f"   * {Colors.GREEN}No Hard Conflicts! System is 100% mathematically feasible.{Colors.RESET}")

    print(f"\n💡 {Colors.YELLOW}{Colors.BOLD}SOFT CONSTRAINTS DETECTED: {total_sc}{Colors.RESET}")
    if total_sc > 0:
        for sc_code, count in sorted(sc_scorecard.items()):
            print(f"   * [{Colors.YELLOW}{sc_code}{Colors.RESET}] {count} violations / fallbacks")
    else:
        print(f"   * {Colors.GREEN}No soft constraint violations!{Colors.RESET}")

    print(f"\n{Colors.GREEN}{Colors.BOLD}========================================================================{Colors.RESET}")
    print(f"🔍 {Colors.BOLD}DETAILED VIOLATION REPORT (ROOT CAUSE ANALYSIS){Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}========================================================================{Colors.RESET}")

    if not violations_details:
        print(f"\n{Colors.GREEN}🎉 Excellent! No anomalies detected. The current schedule layout is completely clean!{Colors.RESET}")
    else:
        for category, msgs in sorted(violations_details.items()):
            print(f"\n📌 {Colors.BOLD}{category}{Colors.RESET} ({len(msgs)} occurrences):")
            for m in msgs[:15]:
                print(f"   - {m}")
            if len(msgs) > 15:
                print(f"   - ...and {len(msgs) - 15} more occurrences.")

    print(f"\n{Colors.GREEN}{Colors.BOLD}========================================================================{Colors.RESET}")

def main():
    parser = argparse.ArgumentParser(description="Advanced CVSU DCS Scheduler Debugger")
    parser.add_argument('--simulate', '-s', action='store_true', help="Force-simulate initial chromosome GA placement diagnostics even if DB has saved schedules")
    parser.add_argument('--semester', default='1st Semester', help="The target semester to analyze")
    args = parser.parse_args()

    main_run(args.simulate, args.semester)

def main_run(force_simulate, selected_semester):
    print_banner()

    with app.app_context():
        # Get System Settings
        settings = SystemSettings.query.first()
        start_hour = settings.start_hour if settings else 7
        end_hour = settings.end_hour if settings else 20
        allowed_days_str = settings.allowed_days if (settings and settings.allowed_days) else 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'
        allowed_days = [d.strip() for d in allowed_days_str.split(',') if d.strip()]
        day_map = {d: i for i, d in enumerate(allowed_days)}

        # Check if there's a live running schedule file from the background thread
        if os.path.exists("live_conflicts.json") and not force_simulate:
            print(f"{Colors.GREEN}🔥 Active generation detected! Loading LIVE RUNNING CHROMOSOME state...{Colors.RESET}")
            try:
                import json
                with open("live_conflicts.json") as f:
                    data = json.load(f)
                
                selected_semester = data.get('semester', selected_semester)
                schedules_raw = data.get('schedules', [])
                
                schedules = [SafeObject(**item) for item in schedules_raw]
                
                courses = {c.id: c for c in Course.query.all()}
                sections = {s.id: s for s in Section.query.all()}
                faculty = {f.id: f for f in Faculty.query.all()}
                rooms = {r.id: r for r in Room.query.all()}
                online_room_ids = {r.id for r in Room.query.filter(
                    (Room.room_name.ilike('%online%')) | (Room.room_name.ilike('%virtual%'))
                ).all()}
                
                build_diagnostic_report(schedules, courses, sections, faculty, rooms, online_room_ids, start_hour, end_hour, allowed_days, selected_semester, "LIVE RUNNING GENERATION")
                return
            except Exception as e:
                print(f"{Colors.RED}⚠️ Failed to load live_conflicts.json, falling back to database: {e}{Colors.RESET}")

        # Check existing schedules
        existing_count = ScheduledClass.query.filter_by(semester=selected_semester, is_draft=False).count()

        # Decide whether to run Database mode or Simulation mode
        if existing_count > 0 and not force_simulate:
            print(f"{Colors.GREEN}✅ Saved master schedule records found. Running LIVE DB DIAGNOSTICS...{Colors.RESET}")
            # Fetch mappings
            courses = {c.id: c for c in Course.query.all()}
            sections = {s.id: s for s in Section.query.all()}
            faculty = {f.id: f for f in Faculty.query.all()}
            rooms = {r.id: r for r in Room.query.all()}
            online_room_ids = {r.id for r in Room.query.filter(
                (Room.room_name.ilike('%online%')) | (Room.room_name.ilike('%virtual%'))
            ).all()}

            schedules = ScheduledClass.query.filter_by(semester=selected_semester, is_draft=False).all()
            build_diagnostic_report(schedules, courses, sections, faculty, rooms, online_room_ids, start_hour, end_hour, allowed_days, selected_semester, "LIVE DATABASE")
        else:
            print(f"{Colors.YELLOW}⚠️ No master schedule records found or --simulate requested. Simulating GA's Initial Population...{Colors.RESET}")
            
            # Gather raw data
            raw_courses = Course.query.filter_by(is_archived=False, semester_offered=selected_semester).all()
            courses_data = [{
                'id': c.id, 'course_code': c.course_code, 'department': c.department or '',
                'lec_units': c.lec_units or 0, 'lab_units': c.lab_units or 0,
                'synchronous_lec_hours': c.synchronous_lec_hours or 0,
                'synchronous_lab_hours': c.synchronous_lab_hours or 0,
                'asynchronous_lec_hours': c.asynchronous_lec_hours or 0,
                'asynchronous_lab_hours': c.asynchronous_lab_hours or 0,
            } for c in raw_courses]

            raw_rooms = Room.query.filter_by(is_archived=False).all()
            rooms_data = [{'id': r.id, 'room_name': r.room_name, 'capabilities': r.capabilities, 'status': r.status, 'capacity': r.capacity, 'special_course_ids': r.special_course_ids or '', 'room_departments': r.room_departments or ''} for r in raw_rooms]

            # Collect active faculty assignment IDs
            _fa_faculty_ids = [r[0] for r in db.session.query(FacultyAssignment.faculty_id).join(Course, FacultyAssignment.course_id == Course.id).filter(Course.semester_offered == selected_semester).distinct().all() if r[0]]
            raw_faculty = Faculty.query.filter(
                Faculty.is_archived == False,
                Faculty.max_weekly_hours > 0,
                or_(Faculty.full_name == 'T.B.A.', Faculty.id.in_(_fa_faculty_ids))
            ).all()
            faculty_data = [{'id': f.id, 'full_name': f.full_name, 'available_days': f.available_days or '', 'max_weekly_hours': f.max_weekly_hours if f.max_weekly_hours is not None else 35, 'department': f.department or ''} for f in raw_faculty]

            raw_sections = Section.query.filter_by(is_archived=False).all()
            sections_data = [{'id': s.id, 'course_ids': [c.id for c in s.courses], 'number_of_students': s.number_of_students} for s in raw_sections]

            valid_course_ids = {c['id'] for c in courses_data}
            raw_pre = PreAssignment.query.filter_by(is_archived=False).all()
            pre_assignments = []
            for pa in raw_pre:
                if pa.course_id in valid_course_ids:
                    pre_assignments.append(SafeObject(
                        course_id=pa.course_id, section_id=pa.section_id, 
                        faculty_id=pa.faculty_id, room_id=pa.room_id, 
                        day=pa.day, start_time=pa.start_time, end_time=pa.end_time
                    ))

            constraints_config = {c.logic_code: {'type': c.constraint_type, 'weight': c.weight} for c in Constraint.query.all()}

            raw_splits = FacultyAssignment.query.join(Course, FacultyAssignment.course_id == Course.id).filter(Course.semester_offered == selected_semester).all()
            split_assignments = []
            for fa in raw_splits:
                if fa.course_id not in valid_course_ids:
                    continue
                lab_splits = []
                if fa.split_day_1 and fa.split_hours_1:
                    lab_splits.append({'day': fa.split_day_1, 'hours': fa.split_hours_1})
                if fa.split_day_2 and fa.split_hours_2:
                    lab_splits.append({'day': fa.split_day_2, 'hours': fa.split_hours_2})
                if lab_splits:
                    split_assignments.append({
                        'faculty_id': fa.faculty_id, 'course_id': fa.course_id, 'section_id': fa.section_id, 'gtype': 'Lab', 'splits': lab_splits
                    })
                lec_splits = []
                if fa.split_lec_day_1 and fa.split_lec_hours_1:
                    lec_splits.append({'day': fa.split_lec_day_1, 'hours': fa.split_lec_hours_1})
                if fa.split_lec_day_2 and fa.split_lec_hours_2:
                    lec_splits.append({'day': fa.split_lec_day_2, 'hours': fa.split_lec_hours_2})
                if lec_splits:
                    split_assignments.append({
                        'faculty_id': fa.faculty_id, 'course_id': fa.course_id, 'section_id': fa.section_id, 'gtype': 'Lec', 'splits': lec_splits
                    })

            fa_map = { (fa.course_id, fa.section_id): fa.faculty_id for fa in raw_splits if fa.course_id in valid_course_ids }

            print(f"📊 {Colors.BLUE}Initializing GeneticScheduler Engine...{Colors.RESET}")
            scheduler = GeneticScheduler(
                courses_data, sections_data, faculty_data, rooms_data, pre_assignments, constraints_config,
                start_time=start_hour, end_time=end_hour, allowed_days=allowed_days,
                split_assignments=split_assignments, fa_map=fa_map
            )

            # Generate initial chromosome using FFD & Compaction logic exactly as run_algorithm does!
            print(f"🧬 {Colors.BLUE}Generating simulated initial chromosome layout...{Colors.RESET}")
            try:
                chrom = scheduler.create_genome()
            except Exception as e:
                print(f"{Colors.RED}Simulation Failed: {e}{Colors.RESET}")
                import traceback
                traceback.print_exc()
                return

            # Convert simulated chromosome genes to mock ScheduledClass objects for the report generator
            schedules = []
            for g in chrom.genes:
                day_str = allowed_days[g.day_idx] if 0 <= g.day_idx < len(allowed_days) else "Unknown"
                start_str = scheduler.slot_to_time(g.start_idx)
                end_str = scheduler.slot_to_time(g.end_idx)
                
                # Create a mock ScheduledClass-like object
                mock_sc = SafeObject(
                    course_id=g.course_id,
                    section_id=g.section_id,
                    faculty_id=g.faculty_id,
                    room_id=g.room_id,
                    day=day_str,
                    start_time=start_str,
                    end_time=end_str,
                    session_type=g.gene_type
                )
                schedules.append(mock_sc)

            # Dictionaries for quick lookup in reporter
            courses_map = {c.id: c for c in Course.query.all()}
            sections_map = {s.id: s for s in Section.query.all()}
            faculty_map = {f.id: f for f in Faculty.query.all()}
            rooms_map = {r.id: r for r in Room.query.all()}
            online_room_ids = scheduler.online_room_ids

            build_diagnostic_report(schedules, courses_map, sections_map, faculty_map, rooms_map, online_room_ids, start_hour, end_hour, allowed_days, selected_semester, "INITIAL CHROMOSOME SIMULATION")

if __name__ == '__main__':
    main()
