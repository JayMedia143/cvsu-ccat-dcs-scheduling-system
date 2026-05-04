# seeder8.py — Benchmark Level 8: ULTIMATE REAL-LIFE (32 sections, ~480 genes)
# Run: python seeder8.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import (app, db, User, Course, Room, Section, Faculty, Constraint,
                 SystemSettings, CodePrefixRule, ScheduledClass,
                 FacultyAssignment, PreAssignment,
                 section_courses, faculty_courses)
from werkzeug.security import generate_password_hash

SEEDER_LEVEL   = 8
GENE_ESTIMATE  = 480
DESCRIPTION    = "32 sections, A1-A5 (Lec), B1-B6 (Lab), 2-3-1 Hour Rule (Lec-Lab-Async), High Saturation."

ROOMS = [
    # Lecture Rooms (Target: 7AM - 7PM Saturation)
    {'name': 'A1', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 45, 'func_comp': 0, 'room_depts': 'Department of Computer Studies'},
    {'name': 'A2', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 45, 'func_comp': 0, 'room_depts': 'Department of Computer Studies'},
    {'name': 'A3', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 45, 'func_comp': 0, 'room_depts': 'Department of Computer Studies'},
    {'name': 'A4', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 45, 'func_comp': 0, 'room_depts': 'Department of Computer Studies'},
    {'name': 'A5', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 45, 'func_comp': 0, 'room_depts': 'Department of Computer Studies'},
    
    # Computer Labs
    {'name': 'B1', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 35, 'func_comp': 35, 'room_depts': 'Department of Computer Studies'},
    {'name': 'B2', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 35, 'func_comp': 35, 'room_depts': 'Department of Computer Studies'},
    {'name': 'B3', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 35, 'func_comp': 35, 'room_depts': 'Department of Computer Studies'},
    {'name': 'B4', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 35, 'func_comp': 35, 'room_depts': 'Department of Computer Studies'},
    {'name': 'B5', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 35, 'func_comp': 35, 'room_depts': 'Department of Computer Studies'},
    {'name': 'B6', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 35, 'func_comp': 35, 'room_depts': 'Department of Computer Studies'},
    
    # Special Rooms
    {'name': 'Court 1',     'building': 'Gymnasium', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 50,  'func_comp': 0},
    {'name': 'Court 2',     'building': 'Gymnasium', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 50,  'func_comp': 0},
    {'name': 'Online Room', 'building': 'Virtual',   'capabilities': 'Lecture', 'status': 'Available', 'capacity': 999, 'func_comp': 0},
    {'name': 'T.B.A.',      'building': 'Virtual',   'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 999, 'func_comp': 0},
]

FACULTY = [
    # DCS Real Names (30 Faculty)
    {'eid': 'DCS-001', 'name': 'ARIES M. GELERA',       'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-002', 'name': 'DANILO C. ALCANTARA',   'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-003', 'name': 'MARIA TERESA R. PEREZ', 'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-004', 'name': 'JOSEPHINE A. SANTOS',   'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-005', 'name': 'REYNALDO M. REYES',     'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-006', 'name': 'ALAN TURING',           'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-007', 'name': 'ADA LOVELACE',          'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-008', 'name': 'GRACE HOPPER',          'dept': 'Department of Computer Studies', 'status': 'Part-time', 'max_weekly': 35},
    {'eid': 'DCS-009', 'name': 'LINUS TORVALDS',        'dept': 'Department of Computer Studies', 'status': 'Part-time', 'max_weekly': 35},
    {'eid': 'DCS-010', 'name': 'GUIDO VAN ROSSUM',      'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-011', 'name': 'KATHERINE JOHNSON',     'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-012', 'name': 'TIM BERNERS-LEE',       'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-013', 'name': 'BJARNE STROUSTRUP',     'dept': 'Department of Computer Studies', 'status': 'Part-time', 'max_weekly': 35},
    {'eid': 'DCS-014', 'name': 'DONALD KNUTH',          'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-015', 'name': 'MARGARET HAMILTON',     'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-016', 'name': 'DENNIS RITCHIE',        'dept': 'Department of Computer Studies', 'status': 'Part-time', 'max_weekly': 35},
    {'eid': 'DCS-017', 'name': 'KEN THOMPSON',          'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-018', 'name': 'RICHARD STALLMAN',      'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-019', 'name': 'JOHN VON NEUMANN',      'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-020', 'name': 'PACIANO RIZAL',         'dept': 'Department of Computer Studies', 'status': 'Part-time', 'max_weekly': 35},
    {'eid': 'DCS-021', 'name': 'JUAN LUNA',             'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-022', 'name': 'MARCELO H. DEL PILAR',  'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-023', 'name': 'GREGORIA DE JESUS',     'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-024', 'name': 'EMILIO JACINTO',        'dept': 'Department of Computer Studies', 'status': 'Part-time', 'max_weekly': 35},
    {'eid': 'DCS-025', 'name': 'ANDRES BONIFACIO',      'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-026', 'name': 'MELCHORA AQUINO',       'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-027', 'name': 'GABRIELA SILANG',       'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-028', 'name': 'LAPU-LAPU',             'dept': 'Department of Computer Studies', 'status': 'Part-time', 'max_weekly': 35},
    {'eid': 'DCS-029', 'name': 'ANTONIO LUNA',          'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    {'eid': 'DCS-030', 'name': 'TEODORA ALONSO',        'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21},
    
    # TBA Pools
    {'eid': 'TBA-01', 'name': 'T.B.A. 1', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999},
    {'eid': 'TBA-02', 'name': 'T.B.A. 2', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999},
    {'eid': 'TBA-03', 'name': 'T.B.A. 3', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999},
    {'eid': 'TBA-04', 'name': 'T.B.A. 4', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999},
    {'eid': 'TBA-05', 'name': 'T.B.A. 5', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999},
]

# (code, name, year, program, dept, sync_lec, sync_lab, async_lec, async_lab, sem)
# ALL Major Subjects follow the 2-3-1 rule (2h Lec, 3h Lab, 1h Async)
COURSES = [
    # --- SHARED GE ---
    ('MATH101', 'Math in Modern World',     1, 'Both', 'Department of Teachers Education', 2, 0, 1, 0, '1st Semester'),
    ('ENGL101', 'Purposive Communication',  1, 'Both', 'Department of Teachers Education', 2, 0, 0, 0, '1st Semester'),
    ('PHED101', 'PE 1 (Fitness)',           1, 'Both', 'Department of Arts and Sciences',  2, 0, 0, 0, '1st Semester'),
    ('NSTP101', 'NSTP 1',                   1, 'Both', 'NSTP Department',                  2, 0, 1, 0, '1st Semester'),
    
    # --- DCS MAJORS (The 2-3-1 Powerhouse) ---
    ('DCIT101', 'Intro to Computing',       1, 'Both', 'Department of Computer Studies',   2, 3, 1, 0, '1st Semester'),
    ('DCIT102', 'Computer Programming 1',    1, 'Both', 'Department of Computer Studies',   2, 3, 1, 0, '1st Semester'),
    ('DCIT201', 'Data Structures',          2, 'Both', 'Department of Computer Studies',   2, 3, 1, 0, '1st Semester'),
    ('DCIT202', 'Information Management',   2, 'Both', 'Department of Computer Studies',   2, 3, 1, 0, '1st Semester'),
    ('DCIT301', 'Apps Development',         3, 'Both', 'Department of Computer Studies',   2, 3, 1, 0, '1st Semester'),
    
    ('COSC201', 'Discrete Mathematics',     2, 'BSCoS', 'Department of Computer Studies',  2, 0, 1, 0, '1st Semester'),
    ('COSC202', 'OOP',                      2, 'BSCoS', 'Department of Computer Studies',  2, 3, 1, 0, '1st Semester'),
    ('COSC301', 'Operating Systems',        3, 'BSCoS', 'Department of Computer Studies',  2, 3, 1, 0, '1st Semester'),
    ('COSC401', 'CS Thesis 1',              4, 'BSCoS', 'Department of Computer Studies',  2, 0, 1, 0, '1st Semester'),
    
    ('ITEC201', 'Networking 1',             2, 'BSIT', 'Department of Computer Studies',   2, 3, 1, 0, '1st Semester'),
    ('ITEC202', 'Web Development',          2, 'BSIT', 'Department of Computer Studies',   2, 3, 1, 0, '1st Semester'),
    ('ITEC301', 'Systems Integration',      3, 'BSIT', 'Department of Computer Studies',   2, 3, 1, 0, '1st Semester'),
    ('ITEC401', 'IT Capstone 1',            4, 'BSIT', 'Department of Computer Studies',   2, 0, 1, 0, '1st Semester'),
]

# Curriculum Maps
_cs_yr1 = ['MATH101', 'ENGL101', 'PHED101', 'NSTP101', 'DCIT101', 'DCIT102']
_cs_yr2 = ['DCIT201', 'DCIT202', 'COSC201', 'COSC202']
_cs_yr3 = ['DCIT301', 'COSC301']
_cs_yr4 = ['COSC401']

_it_yr1 = ['MATH101', 'ENGL101', 'PHED101', 'NSTP101', 'DCIT101', 'DCIT102']
_it_yr2 = ['DCIT201', 'DCIT202', 'ITEC201', 'ITEC202']
_it_yr3 = ['DCIT301', 'ITEC301']
_it_yr4 = ['ITEC401']

CURRICULUM = {}
SECTIONS = []
# Create 32 Sections (A-D x 4 years x 2 progs)
for prog, yr_map in [('BSCoS', [_cs_yr1, _cs_yr2, _cs_yr3, _cs_yr4]), ('BSIT', [_it_yr1, _it_yr2, _it_yr3, _it_yr4])]:
    for yr in range(1, 5):
        for letter in ['A', 'B', 'C', 'D']:
            name = f"{prog} {yr}01-{letter}"
            CURRICULUM[name] = yr_map[yr-1]
            SECTIONS.append({'name': name, 'year': yr, 'students': 40})

CONSTRAINTS = [
    # Standard HCs
    {'code': 'LOCKED_SCHEDULES',           'cat': 'Administrative', 'type': 'HC',  'weight': 1,   'name': '(HC-01) Locked Schedules', 'desc': 'Manually plotted schedules are immovable.'},
    {'code': 'MINOR_SUBJECT_GAP',          'cat': 'Administrative', 'type': 'HC',  'weight': 1,   'name': '(HC-02) Space for Minor Subjects', 'desc': 'Ensure free slots for unscheduled minor courses.'},
    {'code': 'GLOBAL_DAY_RESTRICTION',     'cat': 'Administrative', 'type': 'HC',  'weight': 1,   'name': '(HC-03) Global Day Restriction', 'desc': 'No classes on Sundays or non-academic days.'},
    {'code': 'LEC_LAB_SEQUENCE',           'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-04) Lec-Lab Sequence', 'desc': 'Lecture must be scheduled before Laboratory.'},
    {'code': 'STRICT_ALLOC_LEC',           'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-05) Strict Lecture Allocation', 'desc': 'Every section must have a lecture for required courses.'},
    {'code': 'STRICT_ALLOC_LAB',           'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-06) Strict Laboratory Allocation', 'desc': 'Every section must have a lab if required.'},
    {'code': 'STRICT_ALLOC_ASYNC',         'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-07) Strict Async Allocation', 'desc': 'Every section must have an async part if required.'},
    {'code': 'STRICT_LEC_DURATION',        'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-08) Strict Lecture Duration', 'desc': 'Lec hours must match the required course data.'},
    {'code': 'STRICT_LAB_DURATION',        'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-09) Strict Laboratory Duration', 'desc': 'Lab hours must match the required course data.'},
    {'code': 'STRICT_ASYNC_LEC_DUR',       'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-10) Strict Async Lec Dur', 'desc': 'Async Lec hours must match required data.'},
    {'code': 'STRICT_ASYNC_LAB_DUR',       'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-11) Strict Async Lab Dur', 'desc': 'Async Lab hours must match required data.'},
    {'code': 'SECTION_CONFLICT',           'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-12) No Section Course Conflict', 'desc': 'A section cannot have 2 courses at the same time.'},
    {'code': 'FACULTY_CONFLICT',           'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-13) No Faculty Course Conflict', 'desc': 'A faculty cannot teach 2 courses at the same time.'},
    {'code': 'SECTION_DAY_RESTRICTIONS',   'cat': 'Section',        'type': 'HC',  'weight': 1,   'name': '(HC-14) Section Day Restrictions', 'desc': 'Schedules must be within allowed academic days.'},
    {'code': 'MAX_CONSECUTIVE_STUDENT',    'cat': 'Section',        'type': 'HC',  'weight': 1,   'name': '(HC-15) Max Consecutive Student Load', 'desc': 'Max 6 consecutive hours for students.'},
    {'code': 'NO_ROOM_MULTI_SECTION',      'cat': 'Section',        'type': 'HC',  'weight': 1,   'name': '(HC-16) No Multiple Sections in Room', 'desc': 'One room cannot host 2 sections at once.'},
    {'code': 'SINGLE_FACULTY_PER_TIMESLOT','cat': 'Faculty',        'type': 'HC',  'weight': 1,   'name': '(HC-17) Single Fac per Section Slot', 'desc': 'One section cannot have 2 faculty at once.'},
    {'code': 'FACULTY_AVAILABILITY',       'cat': 'Faculty',        'type': 'HC',  'weight': 1,   'name': '(HC-18) Faculty Availability', 'desc': 'Faculty must be available during scheduled times.'},
    {'code': 'MAX_CONSECUTIVE_FACULTY',    'cat': 'Faculty',        'type': 'HC',  'weight': 1,   'name': '(HC-19) Max Consecutive Faculty Load', 'desc': 'Max 6 consecutive teaching hours for faculty.'},
    {'code': 'SINGLE_ROOM_PER_SESSION',    'cat': 'Room',           'type': 'HC',  'weight': 1,   'name': '(HC-20) Single Room per Session', 'desc': 'One session cannot use 2 rooms at once.'},
    {'code': 'ROOM_SUITABILITY',           'cat': 'Room',           'type': 'HC',  'weight': 1,   'name': '(HC-21) Room Type Suitability', 'desc': 'Lab in Lab rooms, Lec in Lec rooms.'},
    {'code': 'ROOM_AVAILABILITY',          'cat': 'Room',           'type': 'HC',  'weight': 1,   'name': '(HC-22) Room Availability', 'desc': 'Room must be available (not for maintenance).'},
    {'code': 'OPERATING_HOURS',            'cat': 'Time',           'type': 'HC',  'weight': 1,   'name': '(HC-23) Operating Hours Compliance', 'desc': 'Sessions must be within campus hours.'},
    {'code': 'HOURLY_ALIGNMENT',           'cat': 'Time',           'type': 'HC',  'weight': 1,   'name': '(HC-24) Hourly Clock Alignment', 'desc': 'Sessions must start exactly on the hour.'},
    {'code': 'COMPLETE_COURSE_SCHEDULING', 'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-25) Complete Course Scheduling', 'desc': 'All required courses must be fully plotted.'},
    {'code': 'PREASSIGNMENT_EXCLUSIVITY',  'cat': 'Section',        'type': 'HC',  'weight': 1,   'name': '(HC-26) Pre-assignment Exclusivity', 'desc': 'Pre-assigned slots cannot be overwritten.'},
    {'code': 'LECTURE_SLOT_ALIGNMENT',     'cat': 'Room',           'type': 'HC',  'weight': 1,   'name': '(HC-27) Lec Slot Alignment (Div4)', 'desc': 'Lecture classes must start on 2-hour boundaries.'},
    {'code': 'FACULTY_DAY_SPLIT',          'cat': 'Faculty',        'type': 'HC',  'weight': 1,   'name': '(HC-28) Faculty Day Split', 'desc': 'Sessions must land on designated split days.'},

    # Standard SCs
    {'code': 'VIRTUAL_ROOM_USAGE',         'cat': 'Room',           'type': 'SC1', 'weight': 10,  'name': '(SC-I-01) Virtual Room Penalty', 'desc': 'Avoid TBA rooms.'},
    {'code': 'EARLY_START_ENFORCEMENT',    'cat': 'Room',           'type': 'SC1', 'weight': 9,   'name': '(SC-I-02) Early Start Enforcement', 'desc': 'Fill morning slots first.'},
    {'code': 'EVENING_AVOIDANCE',          'cat': 'Time',           'type': 'SC1', 'weight': 9,   'name': '(SC-I-03) Evening Class Avoidance', 'desc': 'Avoid classes starting at 7:00 PM or later.'},
    {'code': 'LEC_LAB_WEEKLY_DIST',        'cat': 'Course',         'type': 'SC1', 'weight': 8,   'name': '(SC-I-08) Lec-Lab Weekly Dist.', 'desc': 'Lec early, Lab late.'},
    {'code': 'LEC_LAB_PROXIMITY',          'cat': 'Course',         'type': 'SC1', 'weight': 7,   'name': '(SC-I-09) Lec-Lab Proximity', 'desc': 'Lec/Lab near each other.'},
    {'code': 'LUNCH_BREAK',                'cat': 'Time',           'type': 'SC2', 'weight': 2,   'name': '(SC-II-04) Lunch Break', 'desc': '12-1 PM break.'},
]

def seed_database():
    with app.app_context():
        print(f"Seeder {SEEDER_LEVEL}: Clearing DB...")
        db.create_all()
        db.session.execute(section_courses.delete())
        db.session.execute(faculty_courses.delete())
        FacultyAssignment.query.delete(); PreAssignment.query.delete()
        ScheduledClass.query.delete(); Course.query.delete()
        Room.query.delete(); Section.query.delete(); Faculty.query.delete()
        Constraint.query.delete(); SystemSettings.query.delete()
        CodePrefixRule.query.delete()
        db.session.commit()

        for c in CONSTRAINTS:
            db.session.add(Constraint(logic_code=c['code'], category=c['cat'], name=c['name'], description=c['desc'], constraint_type=c['type'], weight=c.get('weight', 1)))
        
        db.session.add(SystemSettings(start_hour=7, end_hour=20, allowed_days="Monday,Tuesday,Wednesday,Thursday,Friday,Saturday"))
        db.session.commit()

        for f in FACULTY:
            db.session.add(Faculty(employee_id=f['eid'], full_name=f['name'], department=f.get('dept', 'Department of Computer Studies'), employment_status=f.get('status', 'Full-time'), max_weekly_hours=f.get('max_weekly', 21)))
        for r in ROOMS:
            db.session.add(Room(room_name=r['name'], building=r['building'], capabilities=r['capabilities'], status=r['status'], capacity=r['capacity'], functional_computers=r['func_comp'], room_departments=r.get('room_depts', '')))
        for c in COURSES:
            db.session.add(Course(course_code=c[0], course_name=c[1], year_level=c[2], program=c[3], department=c[4], synchronous_lec_hours=c[5], synchronous_lab_hours=c[6], asynchronous_lec_hours=c[7], asynchronous_lab_hours=c[8], semester_offered=c[9]))
        for s in SECTIONS:
            db.session.add(Section(section_name=s['name'], year_level=s['year'], number_of_students=s['students']))
        db.session.commit()

        course_map = {c.course_code: c for c in Course.query.all()}
        section_map = {s.section_name: s for s in Section.query.all()}
        for sec_name, codes in CURRICULUM.items():
            sec = section_map[sec_name]
            for code in codes:
                sec.courses.append(course_map[code])
        db.session.commit()

        if not User.query.filter_by(role='superadmin').first():
            db.session.add(User(username='Jeremychristian', password_hash=generate_password_hash('sosa'), role='superadmin'))
        db.session.commit()

        # Automatic workload assignment
        print("  Assigning workloads...")
        from collections import defaultdict
        dept_faculty = defaultdict(list)
        for f in Faculty.query.all():
            if 'TBA' not in f.employee_id: dept_faculty[f.department].append(f)
        
        fac_indices = defaultdict(int)
        fac_loads = defaultdict(int)

        for sec in Section.query.all():
            for c in sec.courses:
                dept = c.department
                fac_list = dept_faculty.get(dept, []) or [f for f in Faculty.query.all() if 'TBA' not in f.employee_id]
                if fac_list:
                    idx = fac_indices[dept] % len(fac_list)
                    fac = fac_list[idx]
                    hours = (c.synchronous_lec_hours or 0) + (c.synchronous_lab_hours or 0)
                    if fac_loads[fac.id] + hours > fac.max_weekly_hours:
                        fac_indices[dept] += 1
                        fac = fac_list[fac_indices[dept] % len(fac_list)]
                    if c not in fac.courses: fac.courses.append(c)
                    db.session.add(FacultyAssignment(faculty_id=fac.id, course_id=c.id, section_id=sec.id))
                    fac_loads[fac.id] += hours
        db.session.commit()

        # NSTP Pre-assignment
        nstp = Course.query.filter_by(course_code='NSTP101').first()
        tba = Faculty.query.filter(Faculty.employee_id.like('TBA%')).first()
        court = Room.query.filter_by(room_name='Court 1').first()
        if nstp and tba and court:
            for sec in Section.query.filter_by(year_level=1).all():
                start = '07:00' if 'BSCoS' in sec.section_name else '13:00'
                end = '10:00' if 'BSCoS' in sec.section_name else '16:00'
                db.session.add(PreAssignment(course_id=nstp.id, section_id=sec.id, faculty_id=tba.id, room_id=court.id, day='Saturday', start_time=start, end_time=end))
        db.session.commit()
        print(f"Seeder {SEEDER_LEVEL} complete! — {DESCRIPTION}")

if __name__ == '__main__':
    seed_database()
