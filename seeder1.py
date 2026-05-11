# seeder1.py — Benchmark Level 1: TRIVIAL (1 section, ~5 genes)
# Run: python seeder1.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import (app, db, User, Course, Room, Section, Faculty, Constraint,
                 SystemSettings, CodePrefixRule, ScheduledClass,
                 FacultyAssignment, PreAssignment,
                 section_courses, faculty_courses)
from werkzeug.security import generate_password_hash

SEEDER_LEVEL   = 1
GENE_ESTIMATE  = 5
DESCRIPTION    = "1 section (BSCoS Yr1), 5 Lec-only courses"

# ── ROOMS ─────────────────────────────────────────────────────────────────────
ROOMS = [
    {'name': 'A1', 'building': 'ICT Building A', 'capabilities': 'Lecture',             'status': 'Available',                 'capacity': 40,  'func_comp': 0},
    {'name': 'B1', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available',                 'capacity': 30,  'func_comp': 20, 'room_depts': 'Department of Computer Studies'},
    {'name': 'University Field', 'building': 'Grounds', 'capabilities': 'Lecture',       'status': 'Available',                 'capacity': 999, 'func_comp': 0},
    {'name': 'T.B.A.',           'building': 'Virtual',  'capabilities': 'Lecture,Computer Lab',       'status': 'Available',                 'capacity': 999, 'func_comp': 0},
    {'name': 'Online Room', 'building': 'Virtual', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 999, 'func_comp': 0, 'room_depts': ''},
]

# ── FACULTY ───────────────────────────────────────────────────────────────────
FACULTY = [
    {'eid': 'TBA-01', 'name': 'T.B.A.', 'dept': 'Unassigned',         'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'name': 'Online Room', 'building': 'Virtual', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 999, 'func_comp': 0, 'room_depts': ''},
    {'eid': 'TBA-02', 'name': 'T.B.A.', 'dept': 'Unassigned',         'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'name': 'Online Room', 'building': 'Virtual', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 999, 'func_comp': 0, 'room_depts': ''},
    {'eid': 'TBA-03', 'name': 'T.B.A.', 'dept': 'Unassigned',         'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'name': 'Online Room', 'building': 'Virtual', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 999, 'func_comp': 0, 'room_depts': ''},
    {'eid': 'DAS-001', 'name': 'Gabriela Silang', 'dept': 'Arts & Sciences',     'status': 'Full-time', 'max_weekly': 17, 'sex': 'F', 'rank': 'Assistant Professor II', 'attainment': 'Master of Arts in Education', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday'},
    {'eid': 'DTE-001', 'name': 'Apolinario Mabini', 'dept': 'Teachers Education', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Assistant Professor I', 'attainment': 'Master of Arts in Teaching', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday'},
    # Department of Computer Studies
    {'eid': 'DCS-001', 'name': 'Juan Luna',             'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'M', 'rank': 'Assistant Professor I',   'attainment': 'Master of Science in Computer Science',        'days': 'Monday,Tuesday,Wednesday,Thursday,Friday'},
    {'eid': 'DCS-002', 'name': 'Nicolas Zafra',         'dept': 'Department of Computer Studies', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor I',            'attainment': 'Bachelor of Science in Information Technology', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
]

# ── COURSES ───────────────────────────────────────────────────────────────────
# (code, name, year, program, dept, sync_lec, sync_lab, async_lec, async_lab, sem)
COURSES = [
    ('COSC101', 'Introduction to Computing',              1, 'BSCoS', 'Department of Computer Studies',    3, 0, 0, 0, '1st Semester'),
    ('MATH101', 'Calculus I',                             1, 'Both',  'Department of Teachers Education',  3, 0, 0, 0, '1st Semester'),
    ('ENGL101', 'Communication Arts 1',                   1, 'Both',  'Department of Teachers Education',  3, 0, 0, 0, '1st Semester'),
    ('FILI101', 'Komunikasyon sa Akademikong Filipino',   1, 'Both',  'Department of Teachers Education',  3, 0, 0, 0, '1st Semester'),
    ('PHED101', 'Physical Education 1',                   1, 'Both',  'Department of Arts and Sciences',   2, 0, 0, 0, '1st Semester'),
]

# ── CURRICULUM — which courses each section takes ─────────────────────────────
CURRICULUM = {
    'BSCoS 101-A': ['COSC101', 'MATH101', 'ENGL101', 'FILI101', 'PHED101'],
}

# ── SECTIONS ──────────────────────────────────────────────────────────────────
SECTIONS = [
    {'name': 'BSCoS 101-A', 'year': 1, 'students': 40},
]

# ── CONSTRAINTS (identical to seed_db.py) ─────────────────────────────────────
CONSTRAINTS = [
    # ── HARD CONSTRAINTS (HC-01 to HC-28) ──────────────────────────────────────
    {'code': 'LOCKED_SCHEDULES',           'cat': 'Administrative', 'type': 'HC',  'weight': 1,   'name': '(HC-01) Locked Schedules', 'desc': 'Manually plotted schedules are immovable.'},
    {'code': 'MINOR_SUBJECT_GAP',          'cat': 'Administrative', 'type': 'HC',  'weight': 1,   'name': '(HC-21) Minor Subject Gap Space', 'desc': 'Ensure free slots for unscheduled minor courses.'},
    {'code': 'GLOBAL_DAY_RESTRICTION',     'cat': 'Administrative', 'type': 'HC',  'weight': 1,   'name': '(HC-02) Global Day Restriction', 'desc': 'No classes on Sundays or non-academic days.'},
    {'code': 'LEC_LAB_SEQUENCE',           'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-26) Lec-Lab Sequence', 'desc': 'Lecture should be scheduled before Laboratory.'},
    {'code': 'STRICT_ALLOC_LEC',           'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(SC-I-06) Strict Lecture Allocation', 'desc': 'Lecture must be in a physical room (Non-Virtual).'},
    {'code': 'STRICT_ALLOC_LAB',           'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(SC-I-07) Strict Laboratory Allocation', 'desc': 'Laboratory must be in a Lab room.'},
    {'code': 'STRICT_ALLOC_ASYNC',         'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-03) Strict Async Allocation', 'desc': 'Online classes must be in Virtual rooms.'},
    {'code': 'STRICT_LEC_DURATION',        'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-04) Strict Lecture Duration', 'desc': 'Lec hours must match curriculum.'},
    {'code': 'STRICT_LAB_DURATION',        'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-05) Strict Laboratory Duration', 'desc': 'Lab hours must match curriculum.'},
    {'code': 'STRICT_ASYNC_LEC_DUR',       'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-06) Strict Async Lecture Duration', 'desc': 'Async hours must match curriculum.'},
    {'code': 'STRICT_ASYNC_LAB_DUR',       'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-07) Strict Async Lab Duration', 'desc': 'Async hours must match curriculum.'},
    {'code': 'SECTION_CONFLICT',           'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-08) Section Overlap Prevention', 'desc': 'Section cannot have 2 courses at once.'},
    {'code': 'FACULTY_CONFLICT',           'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-09) Faculty Overlap Prevention', 'desc': 'Faculty cannot teach 2 courses at once.'},
    {'code': 'SECTION_DAY_RESTRICTIONS',   'cat': 'Section',        'type': 'HC',  'weight': 1,   'name': '(HC-27) Section Day Restrictions', 'desc': 'Schedules must be within allowed academic days.'},
    {'code': 'MAX_CONSECUTIVE_STUDENT',    'cat': 'Section',        'type': 'HC',  'weight': 1,   'name': '(HC-22) Max Consecutive Student Load', 'desc': 'Max 6 consecutive hours for students.'},
    {'code': 'NO_ROOM_MULTI_SECTION',      'cat': 'Section',        'type': 'HC',  'weight': 1,   'name': '(HC-10) Room Overlap Prevention', 'desc': 'Room cannot host 2 sections at once.'},
    {'code': 'SINGLE_FACULTY_PER_TIMESLOT','cat': 'Faculty',        'type': 'HC',  'weight': 1,   'name': '(HC-11) Single Faculty per Section Slot', 'desc': 'Section cannot have 2 faculty at once.'},
    {'code': 'FACULTY_AVAILABILITY',       'cat': 'Faculty',        'type': 'HC',  'weight': 1,   'name': '(HC-12) Faculty Day Off / Availability', 'desc': 'Faculty must be available.'},
    {'code': 'MAX_CONSECUTIVE_FACULTY',    'cat': 'Faculty',        'type': 'HC',  'weight': 1,   'name': '(HC-23) Max Consecutive Faculty Load', 'desc': 'Max 6 consecutive hours for faculty.'},
    {'code': 'SINGLE_ROOM_PER_SESSION',    'cat': 'Room',           'type': 'HC',  'weight': 1,   'name': '(HC-13) Single Room per Session', 'desc': 'Session cannot use 2 rooms at once.'},
    {'code': 'ROOM_SUITABILITY',           'cat': 'Room',           'type': 'HC',  'weight': 1,   'name': '(SC-I-08) Room Type Suitability', 'desc': 'Match subject type with room capabilities.'},
    {'code': 'ROOM_AVAILABILITY',          'cat': 'Room',           'type': 'HC',  'weight': 1,   'name': '(HC-14) Room Calendar Availability', 'desc': 'Room must be available.'},
    {'code': 'OPERATING_HOURS',            'cat': 'Time',           'type': 'HC',  'weight': 1,   'name': '(HC-15) Operating Hours Compliance', 'desc': 'Sessions must be within campus hours.'},
    {'code': 'HOURLY_ALIGNMENT',           'cat': 'Time',           'type': 'HC',  'weight': 1,   'name': '(HC-16) Hourly Slot Alignment', 'desc': 'Classes must start exactly on the hour.'},
    {'code': 'COMPLETE_COURSE_SCHEDULING', 'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-17) Complete Course Plotting', 'desc': 'All curriculum subjects must be plotted.'},
    {'code': 'PREASSIGNMENT_EXCLUSIVITY',  'cat': 'Section',        'type': 'HC',  'weight': 1,   'name': '(HC-18) Pre-assignment Exclusivity', 'desc': 'Locked slots cannot be overwritten.'},
    {'code': 'LECTURE_SLOT_ALIGNMENT',     'cat': 'Room',           'type': 'HC',  'weight': 1,   'name': '(HC-28) Lecture Slot Alignment', 'desc': 'Lecture classes must start on designated boundaries.'},
    {'code': 'FACULTY_DAY_SPLIT',          'cat': 'Faculty',        'type': 'HC',  'weight': 1,   'name': '(HC-19) Faculty Day Split Rule', 'desc': 'Sessions must land on designated split days.'},

    # ── SOFT CONSTRAINTS I (SC-I-01 to SC-I-10) ────────────────────────────────
    {'code': 'VIRTUAL_ROOM_USAGE',         'cat': 'Room',           'type': 'SC1', 'weight': 100, 'name': '(SC-I-01) Virtual Room (Online) Penalty', 'desc': 'Avoid Online rooms for physical classes.'},
    {'code': 'EARLY_START_ENFORCEMENT',    'cat': 'Room',           'type': 'SC1', 'weight': 9,   'name': '(SC-I-09) Early Start Enforcement', 'desc': 'Prioritize filling early morning slots.'},
    {'code': 'EVENING_AVOIDANCE',          'cat': 'Time',           'type': 'SC1', 'weight': 9,   'name': '(SC-I-02) Evening Class Avoidance', 'desc': 'Avoid scheduling classes late in the evening.'},
    {'code': 'ROOM_IDLE_GAP',              'cat': 'Room',           'type': 'SC1', 'weight': 15,  'name': '(SC-I-03) Room Idle Gap Penalty', 'desc': 'Incentivize compact room usage.'},
    {'code': 'MIN_DAILY_SECTION_LOAD',     'cat': 'Section',        'type': 'SC1', 'weight': 15,  'name': '(HC-24) Min Daily Section Load', 'desc': 'Ensure at least 3 hours of class per active day.'},
    {'code': 'LEC_LAB_WEEKLY_DIST',        'cat': 'Course',         'type': 'SC1', 'weight': 8,   'name': '(SC-I-04) Lec-Lab Weekly Dist.', 'desc': 'Lec and Lab must be scheduled on different days.'},
    {'code': 'LEC_LAB_PROXIMITY',          'cat': 'Course',         'type': 'SC1', 'weight': 7,   'name': '(SC-I-05) Lec-Lab Proximity', 'desc': 'Max gap between Lecture and Laboratory.'},
    {'code': 'LEC_IN_LAB_FALLBACK',        'cat': 'Room',           'type': 'SC1', 'weight': 50,  'name': '(HC-25) Lecture in Lab Fallback', 'desc': 'Allow lectures in labs only if no classrooms are free.'},

    # ── SOFT CONSTRAINTS II (SC-II-01 to SC-II-04) ───────────────────────────────
    {'code': 'LUNCH_BREAK',                'cat': 'Time',           'type': 'SC2', 'weight': 30,  'name': '(HC-20) Lunch Break Allocation', 'desc': '1-hour break for all (Students & Faculty) between 10 AM-2 PM.'},
    {'code': 'ROOM_CAPACITY_PROPORTIONAL', 'cat': 'Room',           'type': 'SC2', 'weight': 5,   'name': '(SC-II-01) Room Capacity Allocation', 'desc': 'Prioritize closest absolute fit for room capacity.'},
]

# ── PREFIX RULES (identical to seed_db.py) ────────────────────────────────────
PREFIX_RULES = [
    {'prefix': 'COSC', 'dept': 'Department of Computer Studies'},
    {'prefix': 'DCIT', 'dept': 'Department of Computer Studies'},
    {'prefix': 'ITEC', 'dept': 'Department of Computer Studies'},
    {'prefix': 'SOSC', 'dept': 'Department of Arts and Sciences'},
    {'prefix': 'PHED', 'dept': 'Department of Arts and Sciences'},
    {'prefix': 'HUMN', 'dept': 'Department of Arts and Sciences'},
    {'prefix': 'PHYS', 'dept': 'Department of Arts and Sciences'},
    {'prefix': 'ECON', 'dept': 'Department of Arts and Sciences'},
    {'prefix': 'BTCH', 'dept': 'Department of Arts and Sciences'},
    {'prefix': 'LITT', 'dept': 'Department of Arts and Sciences'},
    {'prefix': 'ENGL', 'dept': 'Department of Teachers Education'},
    {'prefix': 'FILI', 'dept': 'Department of Teachers Education'},
    {'prefix': 'MATH', 'dept': 'Department of Teachers Education'},
    {'prefix': 'STAT', 'dept': 'Department of Teachers Education'},
    {'prefix': 'NSTP', 'dept': 'NSTP Department'},
]
PREFIX_EXCEPTIONS = [
    {'code': 'MATH 10', 'dept': 'Department of Engineering'},
    {'code': 'MATH 11', 'dept': 'Department of Engineering'},
]


def seed_database():
    with app.app_context():
        print(f"Seeder {SEEDER_LEVEL}: Clearing DB...")
        db.create_all()

        db.session.execute(section_courses.delete())
        db.session.execute(faculty_courses.delete())
        FacultyAssignment.query.delete()
        PreAssignment.query.delete()
        ScheduledClass.query.delete()
        Course.query.delete()
        Room.query.delete()
        Section.query.delete()
        Faculty.query.delete()
        Constraint.query.delete()
        SystemSettings.query.delete()
        CodePrefixRule.query.delete()
        db.session.commit()

        # ── Prefix Rules ──
        for r in PREFIX_RULES:
            db.session.add(CodePrefixRule(code=r['prefix'], is_prefix=True, department=r['dept'], is_archived=False))
        for e in PREFIX_EXCEPTIONS:
            db.session.add(CodePrefixRule(code=e['code'], is_prefix=False, department=e['dept'], is_archived=False))

        # ── Constraints ──
        for c in CONSTRAINTS:
            db.session.add(Constraint(logic_code=c['code'], category=c['cat'], name=c['name'], description=c['desc'], constraint_type=c['type'], weight=c.get('weight', 1)))

        # ── System Settings (ALL fields) ──
        db.session.add(SystemSettings(
            start_hour=7, end_hour=20,
            allowed_days="Monday,Tuesday,Wednesday,Thursday,Friday,Saturday",
            campus_name="CCAT Campus",
            address="Rosario, Cavite",
            section_school_name="CAVITE STATE UNIVERSITY",
            section_signatory_1="SCHEDULE COMMITTEE",
            section_signatory_2="ARIEL G. SANTOS, EdD",
            section_signatory_3="LAURO B. PASCUA, EdD",
            section_sig2_title="Director, Instruction",
            section_sig3_title="Campus Administrator",
            section_signatories_json=None,
            faculty_school_name="CAVITE STATE UNIVERSITY",
            faculty_signatory_1="DEPT CHAIRPERSON",
            faculty_signatory_2="DEAN",
            faculty_signatory_3="HR HEAD",
            faculty_signatories_json=None,
            room_school_name="CAVITE STATE UNIVERSITY",
            room_signatory_1="SCHEDULE COMMITTEE",
            room_signatory_2="ARIEL G. SANTOS, EdD",
            room_signatory_3="LAURO B. PASCUA, EdD",
            room_sig2_title="Director, Instruction",
            room_sig3_title="Campus Administrator",
            room_signatories_json=None,
            course_school_name="CAVITE STATE UNIVERSITY",
            course_signatory_1="SCHEDULE COMMITTEE",
            course_signatory_2="ARIEL G. SANTOS, EdD",
            course_signatory_3="LAURO B. PASCUA, EdD",
            course_sig2_title="Director, Instruction",
            course_sig3_title="Campus Administrator",
            course_signatories_json=None,
            republic_text="Republic of the Philippines",
            contact_details="(046) 437-9505 / (046) 437-6659",
            email="cvsurosario@cvsu.edu.ph",
            website="www.cvsu-rosario.edu.ph",
            prepared_by_label="Prepared by:",
            rec_approval_label="Recommending Approval:",
            approved_label="APPROVED:",
            class_label="CLASS",
            room_label="ROOM",
            course_label="COURSE",
            sem_ay_label="Semester / Academic Year",
            sem_ay_value="1st Semester / 2024-2025",
            margin_top=1.0, margin_bottom=1.0, margin_left=1.0, margin_right=1.0,
            paper_size='A4',
            fac_margin_top=1.0, fac_margin_bottom=1.0,
            fac_margin_left=1.0, fac_margin_right=1.0,
            fac_paper_size='A4',
            fac_republic_text="Republic of the Philippines",
            fac_univ_name="CAVITE STATE UNIVERSITY",
            fac_campus_name="CCAT Campus",
            fac_address="Rosario, Cavite",
            fac_contact_details="(046) 437-9505 / (046) 437-6659",
            fac_email="cvsurosario@cvsu.edu.ph",
            fac_website="www.cvsu-rosario.edu.ph",
            fac_dept_label="DEPARTMENT OF COMPUTER STUDIES",
            fac_sched_title="FACULTY CLASS SCHEDULE",
            fac_sem_ay_label="FIRST SEMESTER SY 2024-2025",
            fac_name_label="Name:",
            fac_educ_label="Highest Educ. Attainment:",
            fac_prep_label="No. of Preparation/s:",
            fac_hours_label="Total no. of contact hours per week:",
            fac_conforme_label="Conforme:",
            fac_rec_approval_label="Recommending Approval:",
            fac_reviewed_label="Reviewed by:",
            fac_approved_label="Approved:",
            fac_registrar_label="OIC, Registrar",
            fac_chair_name="ARIES M. GELERA",
            fac_chair_title="Department Chairperson",
            fac_director_name="ARIEL G. SANTOS, EdD",
            fac_director_title="Director, Instruction",
            fac_registrar_name="MARLYN A. QUINEZ",
            fac_admin_name="LAURO B. PASCUA, EdD",
            fac_admin_title="Campus Administrator",
            fac_form_num_top="VPAA-QF-11",
            fac_form_num_bottom="V01-2018-07-24",
            fac_consultation="Consultation:",
            fac_research="Research:",
            fac_designation="Designation :",
            fac_extension="Extension:",
            sig1_name="ARIES M. GELERA",
            sig1_title="Department Chairperson",
            sig2_name="ARIEL G. SANTOS, EdD",
            sig_registrar_name="MARLYN A. QUINEZ",
            sig3_name="LAURO B. PASCUA, EdD",
        ))
        db.session.commit()

        # ── Faculty ──
        for f in FACULTY:
            db.session.add(Faculty(employee_id=f['eid'], full_name=f['name'],
                                   department=f['dept'], employment_status=f['status'],
                                   max_weekly_hours=f['max_weekly'],
                                   sex=f.get('sex'),
                                   academic_rank=f.get('rank', ''),
                                   highest_educational_attainment=f.get('attainment', ''),
                                   available_days=f.get('days', 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday')))

        # ── Rooms ──
        for r in ROOMS:
            db.session.add(Room(room_name=r['name'], building=r['building'],
                                capabilities=r['capabilities'], status=r['status'],
                                capacity=r['capacity'], functional_computers=r['func_comp'],
                                room_departments=r.get('room_depts', '')))

        # ── Courses ──
        for c in COURSES:
            db.session.add(Course(
                course_code=c[0], course_name=c[1], year_level=c[2],
                program=c[3], department=c[4],
                synchronous_lec_hours=c[5], synchronous_lab_hours=c[6],
                asynchronous_lec_hours=c[7], asynchronous_lab_hours=c[8],
                semester_offered=c[9], is_archived=False
            ))

        # ── Sections ──
        for s in SECTIONS:
            db.session.add(Section(section_name=s['name'], year_level=s['year'],
                                   number_of_students=s['students']))
        db.session.commit()

        # ── Link Sections → Courses ──
        course_map  = {c.course_code: c for c in Course.query.all()}
        section_map = {s.section_name: s for s in Section.query.all()}
        for sec_name, codes in CURRICULUM.items():
            sec = section_map[sec_name]
            for code in codes:
                sec.courses.append(course_map[code])
        db.session.commit()

        # ── Superadmin ──
        if not User.query.filter_by(role='superadmin').first():
            db.session.add(User(username='Jeremychristian',
                                password_hash=generate_password_hash('sosa'),
                                role='superadmin'))
            db.session.commit()

        
        

        
        
        
        # === NEW: AUTOMATED ALL-DEPARTMENTS WORKLOAD INJECTOR ===
        print("  Assigning automatic workloads for ALL departments...")
        from collections import defaultdict
        
        dept_faculty = defaultdict(list)
        for f in Faculty.query.all():
            if 'TBA' not in f.employee_id:
                dept_faculty[f.department].append(f)
            
        fac_indices = defaultdict(int)
        fac_loads = defaultdict(int)

        for sec in Section.query.all():
            for c in sec.courses:
                dept = getattr(c, 'department', '')
                if not dept: continue
                
                fac_list = dept_faculty.get(dept, [])
                if not fac_list:
                    fac_list = [f for f in Faculty.query.all() if 'TBA' not in f.employee_id]
                
                if fac_list:
                    idx = fac_indices[dept]
                    if idx >= len(fac_list):
                        idx = idx % len(fac_list) 
                        
                    fac = fac_list[idx]
                    course_hours = (c.synchronous_lec_hours or 0) + (c.synchronous_lab_hours or 0)
                    
                    if fac_loads[fac.id] + course_hours > fac.max_weekly_hours:
                        fac_indices[dept] += 1
                        idx = fac_indices[dept] % len(fac_list)
                        fac = fac_list[idx]
                            
                    # --- FIX: Append to Teachable Subjects (faculty_courses) ---
                    if c not in fac.courses:
                        fac.courses.append(c)
                        
                    # --- Assign Final Load (FacultyAssignment) ---
                    db.session.add(FacultyAssignment(
                        faculty_id=fac.id,
                        course_id=c.id,
                        section_id=sec.id
                    ))
                    fac_loads[fac.id] += course_hours
                    
        db.session.commit()
        print(f"Seeder {SEEDER_LEVEL} complete! — {DESCRIPTION}")
        print(f"  Sections : {Section.query.count()}")
        print(f"  Courses  : {Course.query.count()}")
        print(f"  Faculty  : {Faculty.query.count()}")
        print(f"  Rooms    : {Room.query.count()}")
        print(f"  Expected genes: ~{GENE_ESTIMATE}")


if __name__ == '__main__':
    seed_database()
