# seed_db.py (KUMPLETO AT FINAL VERSION)

# seed_db.py
from app import app, db, User, Course, Room, Section, Faculty, Constraint, SystemSettings, section_courses, faculty_courses, FacultyAssignment, PreAssignment, ScheduledClass, CodePrefixRule
from werkzeug.security import generate_password_hash

# Function para linisin ang database bago mag-seed
def clear_data():
    with app.app_context():
        try:
            # Burahin muna ang data sa association tables
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
            print("All existing data cleared.")
        except Exception as e:
            db.session.rollback()
            print(f"An error occurred while clearing data: {e}")
# seed_db.py

prefix_rules_to_add = [
    # Department of Computer Studies (DCS)
    {'prefix': 'COSC', 'dept': 'Department of Computer Studies'},
    {'prefix': 'DCIT', 'dept': 'Department of Computer Studies'},
    {'prefix': 'ITEC', 'dept': 'Department of Computer Studies'},
    
    # Department of Arts and Sciences (DAS)
    {'prefix': 'SOSC', 'dept': 'Department of Arts and Sciences'},
    {'prefix': 'PHED', 'dept': 'Department of Arts and Sciences'},
    {'prefix': 'HUMN', 'dept': 'Department of Arts and Sciences'},
    {'prefix': 'PHYS', 'dept': 'Department of Arts and Sciences'},
    {'prefix': 'ECON', 'dept': 'Department of Arts and Sciences'},
    {'prefix': 'BTCH', 'dept': 'Department of Arts and Sciences'},
    {'prefix': 'LITT', 'dept': 'Department of Arts and Sciences'},
    
    # Department of Teachers Education (DTE)
    {'prefix': 'ENGL', 'dept': 'Department of Teachers Education'},
    {'prefix': 'FILI', 'dept': 'Department of Teachers Education'},
    {'prefix': 'MATH', 'dept': 'Department of Teachers Education'},
    {'prefix': 'STAT', 'dept': 'Department of Teachers Education'},
    
    # Department of Engineering (Note: specific codes like MATH 10/11 shouldn't be prefixes)
    # The requirement was to map Calculus to Engineering. The code logic in app.py handles exact exceptions.
    
    # NSTP Department
    {'prefix': 'NSTP', 'dept': 'NSTP Department'}
]

exceptions_to_add = [
    # Department of Engineering Exceptions
    {'code': 'MATH 10', 'dept': 'Department of Engineering'},
    {'code': 'MATH 11', 'dept': 'Department of Engineering'}
]

# Palitan ang luma mong rooms_to_add list nito:
rooms_to_add = [
    {'name': 'A1', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 40, 'func_comp': 0},
    {'name': 'A2', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 40, 'func_comp': 0},
    {'name': 'A3', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Unavailable (Maintenance)', 'capacity': 40, 'func_comp': 0},
    {'name': 'A4', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Unavailable (Maintenance)', 'capacity': 40, 'func_comp': 0},
    {'name': 'A5', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Unavailable (Maintenance)', 'capacity': 40, 'func_comp': 0},
    {'name': 'B1', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 30, 'func_comp': 20, 'room_depts': 'Department of Computer Studies'},
    {'name': 'B2', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 30, 'func_comp': 20, 'room_depts': 'Department of Computer Studies'},
    {'name': 'B3', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 30, 'func_comp': 19, 'room_depts': 'Department of Computer Studies'},
    {'name': 'B4', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 30, 'func_comp': 18, 'room_depts': 'Department of Computer Studies'},
    {'name': 'B5', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 30, 'func_comp': 20, 'room_depts': 'Department of Computer Studies'},
    {'name': 'B6', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 30, 'func_comp': 20, 'room_depts': 'Department of Computer Studies'},
    {'name': 'University Field', 'building': 'Grounds', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 999, 'func_comp': 0, 'room_depts': ''},
    {'name': 'T.B.A.', 'building': 'Virtual', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 999, 'func_comp': 0, 'room_depts': ''},
]

# --- BAGONG DATA PARA SA SECTIONS ---
sections_to_add = [
    # --- BS COMPUTER SCIENCE (BSCoS) ---
    {'name': 'BSCoS 101-A', 'year': 1, 'students': 40},
    {'name': 'BSCoS 101-B', 'year': 1, 'students': 40},
    {'name': 'BSCoS 101-C', 'year': 1, 'students': 40},
    {'name': 'BSCoS 101-D', 'year': 1, 'students': 40},
    {'name': 'BSCoS 201-A', 'year': 2, 'students': 40},
    {'name': 'BSCoS 201-B', 'year': 2, 'students': 40},
    {'name': 'BSCoS 201-C', 'year': 2, 'students': 40},
    {'name': 'BSCoS 201-D', 'year': 2, 'students': 40},
    {'name': 'BSCoS 301-A', 'year': 3, 'students': 40},
    {'name': 'BSCoS 301-B', 'year': 3, 'students': 40},
    {'name': 'BSCoS 301-C', 'year': 3, 'students': 40},
    {'name': 'BSCoS 301-D', 'year': 3, 'students': 40},
    {'name': 'BSCoS 401-A', 'year': 4, 'students': 40},
    {'name': 'BSCoS 401-B', 'year': 4, 'students': 40},
    {'name': 'BSCoS 401-C', 'year': 4, 'students': 40},
    {'name': 'BSCoS 401-D', 'year': 4, 'students': 40},

    # --- BS INFORMATION TECHNOLOGY (BSIT) ---
    {'name': 'BSIT 101-A', 'year': 1, 'students': 40},
    {'name': 'BSIT 101-B', 'year': 1, 'students': 40},
    {'name': 'BSIT 101-C', 'year': 1, 'students': 40},
    {'name': 'BSIT 101-D', 'year': 1, 'students': 40},
    {'name': 'BSIT 201-A', 'year': 2, 'students': 40},
    {'name': 'BSIT 201-B', 'year': 2, 'students': 40},
    {'name': 'BSIT 201-C', 'year': 2, 'students': 40},
    {'name': 'BSIT 201-D', 'year': 2, 'students': 40},
    {'name': 'BSIT 301-A', 'year': 3, 'students': 40},
    {'name': 'BSIT 301-B', 'year': 3, 'students': 40},
    {'name': 'BSIT 301-C', 'year': 3, 'students': 40},
    {'name': 'BSIT 301-D', 'year': 3, 'students': 40},
    {'name': 'BSIT 401-A', 'year': 4, 'students': 40},
    {'name': 'BSIT 401-B', 'year': 4, 'students': 40},
    {'name': 'BSIT 401-C', 'year': 4, 'students': 40},
    {'name': 'BSIT 401-D', 'year': 4, 'students': 40},
]

# --- BAGONG DATA PARA SA FACULTY ---
faculty_to_add = [
    # TBA Entries
    {'eid': 'TBA-01', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'TBA-02', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'TBA-03', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'TBA-04', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'TBA-05', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'TBA-06', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'TBA-07', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'TBA-08', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'TBA-09', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'TBA-10', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'TBA-11', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'TBA-12', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'TBA-13', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'TBA-14', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'TBA-15', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'TBA-16', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'TBA-17', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'TBA-18', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'TBA-19', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'TBA-20', 'name': 'T.B.A.', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999, 'sex': None, 'rank': '', 'attainment': '', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},

    # Department of Arts and Sciences
    {'eid': 'DAS-001', 'name': 'Gabriela Silang',   'dept': 'Arts & Sciences',    'status': 'Full-time', 'max_weekly': 17, 'sex': 'F', 'rank': 'Assistant Professor II',  'attainment': 'Master of Arts in Education',       'days': 'Monday,Tuesday,Wednesday,Thursday,Friday'},
    {'eid': 'DAS-002', 'name': 'Emilio Aguinaldo',  'dept': 'Arts & Sciences',    'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Associate Professor I',   'attainment': 'Doctor of Philosophy',              'days': 'Monday,Tuesday,Wednesday,Thursday,Friday'},
    {'eid': 'DAS-003', 'name': 'Andres Bonifacio',  'dept': 'Arts & Sciences',    'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor I',            'attainment': 'Bachelor of Science',               'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'DAS-004', 'name': 'Melchora Aquino',   'dept': 'Arts & Sciences',    'status': 'Part-time', 'max_weekly': 35, 'sex': 'F', 'rank': 'Instructor II',           'attainment': 'Master of Arts',                    'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'DAS-005', 'name': 'Jose Rizal',        'dept': 'Arts & Sciences',    'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Associate Professor III', 'attainment': 'Doctor of Philosophy',              'days': 'Monday,Tuesday,Wednesday,Thursday,Friday'},

    # Department of Teachers Education
    {'eid': 'DTE-001', 'name': 'Apolinario Mabini', 'dept': 'Teachers Education', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Assistant Professor I',   'attainment': 'Master of Arts in Teaching',        'days': 'Monday,Tuesday,Wednesday,Thursday,Friday'},
    {'eid': 'DTE-002', 'name': 'Leonor Briones',    'dept': 'Teachers Education', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'F', 'rank': 'Instructor III',          'attainment': 'Master of Education',               'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'DTE-003', 'name': 'Sara Duterte',      'dept': 'Teachers Education', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'F', 'rank': 'Associate Professor II',  'attainment': 'Doctor of Education',               'days': 'Monday,Tuesday,Wednesday,Thursday,Friday'},
    {'eid': 'DTE-004', 'name': 'Armin Luistro',     'dept': 'Teachers Education', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor II',           'attainment': 'Master of Arts in Education',       'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},

    # Department of Engineering
    {'eid': 'CEN-001', 'name': 'Lapu-Lapu',         'dept': 'Engineering',        'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Assistant Professor III', 'attainment': 'Master of Engineering',             'days': 'Monday,Tuesday,Wednesday,Thursday,Friday'},
    {'eid': 'CEN-002', 'name': 'Antonio Luna',      'dept': 'Engineering',        'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor I',            'attainment': 'Bachelor of Science in Engineering', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
]
# FINAL CONSTRAINT LIST — updated to match latest specification
# HC-01 to HC-26 + SC-I-01 to SC-I-08 + SC-II-01 to SC-II-03
constraints_to_add = [
    # ── ADMINISTRATIVE ──────────────────────────────────────────────────────────
    {'code': 'LOCKED_SCHEDULES',          'cat': 'Administrative', 'type': 'HC',
     'name': '(HC-01) Locked Schedules',
     'desc': 'Manually plotted course schedules (Pre-assignments) are immovable.'},
    {'code': 'MINOR_SUBJECT_GAP',         'cat': 'Administrative', 'type': 'HC',
     'name': '(HC-02) Space for Minor Subjects',
     'desc': 'Ensure sufficient free time slots exist for unscheduled minor courses.'},
    {'code': 'GLOBAL_DAY_RESTRICTION',    'cat': 'Administrative', 'type': 'HC',
     'name': '(HC-03) Global Day Restriction',
     'desc': 'Courses must NOT be scheduled on declared non-academic days (e.g. Sunday, optionally Saturday).'},

    # ── COURSE ──────────────────────────────────────────────────────────────────
    {'code': 'LEC_LAB_SEQUENCE',          'cat': 'Course', 'type': 'HC',
     'name': '(HC-04) Lecture–Laboratory Sequence',
     'desc': 'The Lecture component must be scheduled earlier than the Laboratory component.'},
    {'code': 'STRICT_ALLOC_LEC',          'cat': 'Course', 'type': 'HC',
     'name': '(HC-05) Strict Lecture Allocation',
     'desc': 'Every section must have a Lecture component scheduled for each required course.'},
    {'code': 'STRICT_ALLOC_LAB',          'cat': 'Course', 'type': 'HC',
     'name': '(HC-06) Strict Laboratory Allocation',
     'desc': 'Every section must have a Laboratory component scheduled if required by the course.'},
    {'code': 'STRICT_ALLOC_ASYNC',        'cat': 'Course', 'type': 'HC',
     'name': '(HC-07) Strict Async Allocation',
     'desc': 'Every section must have an Asynchronous component scheduled if required by the course.'},
    {'code': 'STRICT_LEC_DURATION',       'cat': 'Course', 'type': 'HC',
     'name': '(HC-08) Strict Lecture Duration',
     'desc': 'Face-to-face Lecture hours must exactly match the required hours defined in the course data.'},
    {'code': 'STRICT_LAB_DURATION',       'cat': 'Course', 'type': 'HC',
     'name': '(HC-09) Strict Laboratory Duration',
     'desc': 'Face-to-face Laboratory hours must exactly match the required hours defined in the course data.'},
    {'code': 'STRICT_ASYNC_LEC_DUR',      'cat': 'Course', 'type': 'HC',
     'name': '(HC-10) Strict Async Lecture Duration',
     'desc': 'Asynchronous Lecture hours must exactly match the required hours defined in the course data.'},
    {'code': 'STRICT_ASYNC_LAB_DUR',      'cat': 'Course', 'type': 'HC',
     'name': '(HC-11) Strict Async Laboratory Duration',
     'desc': 'Asynchronous Laboratory hours must exactly match the required hours defined in the course data.'},
    {'code': 'SECTION_CONFLICT',          'cat': 'Course', 'type': 'HC',
     'name': '(HC-12) No Section Course Conflict',
     'desc': 'A section cannot have two or more different courses scheduled at the same time.'},
    {'code': 'FACULTY_CONFLICT',          'cat': 'Course', 'type': 'HC',
     'name': '(HC-13) No Faculty Course Conflict',
     'desc': 'A faculty member cannot be assigned to two or more courses at the same time.'},
    {'code': 'COMPLETE_COURSE_SCHEDULING','cat': 'Course', 'type': 'HC',
     'name': '(HC-25) Complete Course Scheduling',
     'desc': 'All courses for the selected semester must be fully plotted in the timetable.'},
    {'code': 'LEC_LAB_WEEKLY_DIST',       'cat': 'Course', 'type': 'SC1',
     'name': '(SC-I-01) Lecture-Lab Weekly Distribution',
     'desc': 'Lectures should be placed earlier in the week; laboratories later in the week.'},
    {'code': 'ASYNC_STRATEGIC_PLACEMENT', 'cat': 'Course', 'type': 'SC1',
     'name': '(SC-I-02) Strategic Asynchronous Placement',
     'desc': 'Asynchronous classes should fill 1-hour gaps to preserve larger free blocks.'},
    {'code': 'LEC_LAB_PROXIMITY',         'cat': 'Course', 'type': 'SC1',
     'name': '(SC-I-03) Lecture-Lab Proximity',
     'desc': 'Lecture and Lab of the same course should be scheduled within 3 days of each other.'},
    {'code': 'PE_MORNING_PLACEMENT',      'cat': 'Course', 'type': 'SC1',
     'name': '(SC-I-04) Morning Placement for PE Courses',
     'desc': 'PE/FITT courses should be scheduled early in the morning (7:00 AM onwards).'},
    {'code': 'PE_EARLY_WEEK',             'cat': 'Course', 'type': 'SC1',
     'name': '(SC-I-05) Early Week Placement for PE Courses',
     'desc': 'PE/FITT courses should ideally be scheduled on Mondays or Tuesdays.'},

    # ── SECTION ─────────────────────────────────────────────────────────────────
    {'code': 'SECTION_DAY_RESTRICTIONS',  'cat': 'Section', 'type': 'HC',
     'name': '(HC-14) Section Day Restrictions',
     'desc': 'Section schedules must only be assigned within allowed academic days for the year level.'},
    {'code': 'MAX_CONSECUTIVE_STUDENT',   'cat': 'Section', 'type': 'HC',
     'name': '(HC-15) Max Consecutive Student Load',
     'desc': 'A section must not exceed 6 consecutive hours of scheduled course sessions.'},
    {'code': 'NO_ROOM_MULTI_SECTION',     'cat': 'Section', 'type': 'HC',
     'name': '(HC-16) No Multiple Sections in One Room',
     'desc': 'Two or more sections must not be assigned to the same room at the same time.'},
    {'code': 'PREASSIGNMENT_EXCLUSIVITY', 'cat': 'Section', 'type': 'HC',
     'name': '(HC-26) Pre-assignment Time Exclusivity',
     'desc': 'Time slots blocked by pre-assignments cannot be overwritten or double-booked for that section.'},
    {'code': 'NO_ISOLATED_LECTURES',      'cat': 'Section', 'type': 'SC2',
     'name': '(SC-II-01) No Isolated Lectures',
     'desc': 'A section must not have only one lecture scheduled on a given day.'},
    {'code': 'NO_ISOLATED_LABS',          'cat': 'Section', 'type': 'SC2',
     'name': '(SC-II-02) No Isolated Laboratories',
     'desc': 'A section must not have only one laboratory scheduled on a given day.'},
    {'code': 'MIN_DAILY_SECTION_LOAD',    'cat': 'Section', 'type': 'SC2',
     'name': '(SC-II-05) Minimum Daily Section Load',
     'desc': 'A section should have at least two classes scheduled on any active academic day.'},

    # ── FACULTY ─────────────────────────────────────────────────────────────────
    {'code': 'SINGLE_FACULTY_PER_TIMESLOT','cat': 'Faculty', 'type': 'HC',
     'name': '(HC-17) Single Faculty per Section Timeslot',
     'desc': 'A section cannot have two or more faculty members assigned at the same time.'},
    {'code': 'FACULTY_AVAILABILITY',      'cat': 'Faculty', 'type': 'HC',
     'name': '(HC-18) Faculty Availability',
     'desc': 'A faculty member must not be scheduled during declared unavailable time slots.'},
    {'code': 'MAX_CONSECUTIVE_FACULTY',   'cat': 'Faculty', 'type': 'HC',
     'name': '(HC-19) Max Consecutive Faculty Load',
     'desc': 'A faculty member must not teach for more than 6 consecutive hours.'},

    # ── ROOM ────────────────────────────────────────────────────────────────────
    {'code': 'SINGLE_ROOM_PER_SESSION',   'cat': 'Room', 'type': 'HC',
     'name': '(HC-20) Single Room per Course Session',
     'desc': 'A scheduled course session cannot be assigned to two or more rooms at the same time.'},
    {'code': 'ROOM_SUITABILITY',          'cat': 'Room', 'type': 'HC',
     'name': '(HC-21) Room Type Suitability',
     'desc': 'Laboratory components must be in Laboratory rooms; Lecture components in Lecture rooms.'},
    {'code': 'ROOM_AVAILABILITY',         'cat': 'Room', 'type': 'HC',
     'name': '(HC-22) Room Availability',
     'desc': 'Courses must not be scheduled in rooms marked as unavailable or under maintenance.'},
    {'code': 'ROOM_CAPACITY_PROPORTIONAL','cat': 'Room', 'type': 'SC2',
     'name': '(SC-II-03) Proportional Room Capacity Allocation',
     'desc': 'Sections with larger student populations should be prioritized for larger rooms.'},

    # ── TIME ────────────────────────────────────────────────────────────────────
    {'code': 'OPERATING_HOURS',           'cat': 'Time', 'type': 'HC',
     'name': '(HC-23) Operating Hours Compliance',
     'desc': 'All course sessions must fall within official institutional start and end times.'},
    {'code': 'HOURLY_ALIGNMENT',          'cat': 'Time', 'type': 'HC',
     'name': '(HC-24) Hourly Clock Alignment',
     'desc': 'All course session start times must begin exactly on the hour (e.g. 7:00, 8:00).'},
    {'code': 'EARLY_START',               'cat': 'Time', 'type': 'HC',
     'name': '(HC-27) Early Start Enforcement',
     'desc': 'Schedules must begin at the earliest allowed time slot to maximize room utilization.'},
    {'code': 'DIV4_SLOT_ALIGNMENT',       'cat': 'Time', 'type': 'HC',
     'name': '(HC-28) Divisible-4 Slot Alignment',
     'desc': 'Lecture sessions must start on slots divisible by 4 to avoid overlapping adjacent sections.'},
    {'code': 'FACULTY_DAY_SPLIT',         'cat': 'Faculty', 'type': 'HC',
     'name': '(HC-29) Faculty Day Split',
     'desc': 'When a faculty day-split is configured, each sub-gene must be locked to its designated day.'},
    {'code': 'LUNCH_BREAK',               'cat': 'Time', 'type': 'SC2',
     'name': '(SC-II-04) Lunch Break Allocation',
     'desc': 'A 1-hour vacant period must be provided between 10:00 AM and 2:00 PM.'},
    {'code': 'EVENING_AVOIDANCE',         'cat': 'Time', 'type': 'SC2',
     'name': '(SC-II-06) Evening Class Avoidance',
     'desc': 'Avoid scheduling classes in the evening (from 6:00 PM onwards).'},
]

# seed_db.py (CLEAN VERSION)

def seed_database():
    with app.app_context():
        print("Cleaning database (Preserving Users)...")
        # Ensure tables exist
        db.create_all()
        
        # Burahin ang data para sa seed (HINDI KASAMA ANG User)
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
        db.session.commit()

        
        # 1. Faculty
        print("Seeding Faculty...")
        for f in faculty_to_add:
            db.session.add(Faculty(
                employee_id=f['eid'], full_name=f['name'],
                department=f['dept'], employment_status=f['status'],
                max_weekly_hours=f['max_weekly'],
                sex=f.get('sex'),
                academic_rank=f.get('rank', ''),
                highest_educational_attainment=f.get('attainment', ''),
                available_days=f.get('days', 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday')
            ))

        print("Seeding Prefix Rules...")
        for rule in prefix_rules_to_add:
            db.session.add(CodePrefixRule(
                code=rule['prefix'], 
                is_prefix=True, 
                department=rule['dept'], 
                is_archived=False
            ))
            
        print("Seeding Exceptions...")
        for exc in exceptions_to_add:
            db.session.add(CodePrefixRule(
                code=exc['code'],
                is_prefix=False,
                department=exc['dept'],
                is_archived=False
            ))

        # 2. Rooms
        print("Seeding Rooms...")
        for r in rooms_to_add:
            db.session.add(Room(
                room_name=r['name'], building=r['building'],
                capabilities=r['capabilities'], status=r['status'],
                capacity=r['capacity'], functional_computers=r['func_comp'],
                room_departments=r.get('room_depts', '')
            ))

        # 3. Sections
        print("Seeding Sections...")
        for s in sections_to_add:
            db.session.add(Section(
                section_name=s['name'], year_level=s['year'], 
                number_of_students=s['students']
            ))

        # 4. Constraints
        print("Seeding Constraints...")
        for c in constraints_to_add:
            db.session.add(Constraint(
                logic_code=c['code'], category=c['cat'], 
                name=c['name'], description=c['desc'], constraint_type=c['type']
            ))
        
        db.session.commit()

        # 5. System Settings
        print("Initializing System Settings...")
        db.session.add(SystemSettings(
            start_hour=7, end_hour=20,
            allowed_days="Monday,Tuesday,Wednesday,Thursday,Friday,Saturday",
            campus_name="CCAT Campus", address="Rosario, Cavite",
            section_school_name="CAVITE STATE UNIVERSITY",
            section_signatory_1="SCHEDULE COMMITTEE",
            section_signatory_2="ARIEL G. SANTOS, EdD",
            section_signatory_3="LAURO B. PASCUA, EdD",
            faculty_school_name="CAVITE STATE UNIVERSITY",
            faculty_signatory_1="DEPT CHAIRPERSON",
            faculty_signatory_2="DEAN",
            faculty_signatory_3="HR HEAD",
            room_school_name="CAVITE STATE UNIVERSITY",
            room_signatory_1="SCHEDULE COMMITTEE",
            room_signatory_2="ARIEL G. SANTOS, EdD",
            room_signatory_3="LAURO B. PASCUA, EdD",
            course_school_name="CAVITE STATE UNIVERSITY",
            course_signatory_1="SCHEDULE COMMITTEE",
            course_signatory_2="ARIEL G. SANTOS, EdD",
            course_signatory_3="LAURO B. PASCUA, EdD"
        ))
        db.session.commit()

        # 6. Ensure Superadmin Exists
        print("Ensuring Superadmin exists...")
        admin_user = User.query.filter_by(role='superadmin').first()
        if not admin_user:
            admin_user = User(username='Jeremychristian', password_hash=generate_password_hash('sosa'), role='superadmin')
            db.session.add(admin_user)
            db.session.commit()
            print("Created default superadmin 'Jeremychristian'.")

        print("✅ Database seeded successfully (Clean & Ready for PDF Import)!")

if __name__ == '__main__':
    seed_database()