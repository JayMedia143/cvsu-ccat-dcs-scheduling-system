# seed_db.py (KUMPLETO AT FINAL VERSION)

from app import app, db, User, Course, Room, Section, Faculty, Constraint, SystemSettings, section_courses, faculty_courses, FacultyAssignment, PreAssignment, ScheduledClass, CodePrefixRule
from werkzeug.security import generate_password_hash

def clear_data():
    with app.app_context():
        try:
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

prefix_rules_to_add = [
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
    {'prefix': 'NSTP', 'dept': 'NSTP Department'}
]

exceptions_to_add = [
    {'code': 'MATH 10', 'dept': 'Department of Engineering'},
    {'code': 'MATH 11', 'dept': 'Department of Engineering'}
]

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
    {'name': 'Online Room', 'building': 'Virtual', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 999, 'func_comp': 0, 'room_depts': ''},
]

sections_to_add = [
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

faculty_to_add = [
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
    {'eid': 'DAS-001', 'name': 'Gabriela Silang',   'dept': 'Arts & Sciences',    'status': 'Full-time', 'max_weekly': 17, 'sex': 'F', 'rank': 'Assistant Professor II',  'attainment': 'Master of Arts in Education',       'days': 'Monday,Tuesday,Wednesday,Thursday,Friday'},
    {'eid': 'DAS-002', 'name': 'Emilio Aguinaldo',  'dept': 'Arts & Sciences',    'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Associate Professor I',   'attainment': 'Doctor of Philosophy',              'days': 'Monday,Tuesday,Wednesday,Thursday,Friday'},
    {'eid': 'DAS-003', 'name': 'Andres Bonifacio',  'dept': 'Arts & Sciences',    'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor I',            'attainment': 'Bachelor of Science',               'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'DAS-004', 'name': 'Melchora Aquino',   'dept': 'Arts & Sciences',    'status': 'Part-time', 'max_weekly': 35, 'sex': 'F', 'rank': 'Instructor II',           'attainment': 'Master of Arts',                    'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'DAS-005', 'name': 'Jose Rizal',        'dept': 'Arts & Sciences',    'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Associate Professor III', 'attainment': 'Doctor of Philosophy',              'days': 'Monday,Tuesday,Wednesday,Thursday,Friday'},
    {'eid': 'DTE-001', 'name': 'Apolinario Mabini', 'dept': 'Teachers Education', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Assistant Professor I',   'attainment': 'Master of Arts in Teaching',        'days': 'Monday,Tuesday,Wednesday,Thursday,Friday'},
    {'eid': 'DTE-002', 'name': 'Leonor Briones',    'dept': 'Teachers Education', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'F', 'rank': 'Instructor III',          'attainment': 'Master of Education',               'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'DTE-003', 'name': 'Sara Duterte',      'dept': 'Teachers Education', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'F', 'rank': 'Associate Professor II',  'attainment': 'Doctor of Education',               'days': 'Monday,Tuesday,Wednesday,Thursday,Friday'},
    {'eid': 'DTE-004', 'name': 'Armin Luistro',     'dept': 'Teachers Education', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor II',           'attainment': 'Master of Arts in Education',       'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
    {'eid': 'CEN-001', 'name': 'Lapu-Lapu',         'dept': 'Engineering',        'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Assistant Professor III', 'attainment': 'Master of Engineering',             'days': 'Monday,Tuesday,Wednesday,Thursday,Friday'},
    {'eid': 'CEN-002', 'name': 'Antonio Luna',      'dept': 'Engineering',        'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor I',            'attainment': 'Bachelor of Science in Engineering', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'},
]

constraints_to_add = [

        # ── HARD CONSTRAINTS (HC-01 to HC-28) ──────────────────────────────────────
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

        # ── SOFT CONSTRAINTS I (SC-I-01 to SC-I-12) ────────────────────────────────
        {'code': 'VIRTUAL_ROOM_USAGE',         'cat': 'Room',           'type': 'SC1', 'weight': 500, 'name': '(SC-I-01) Virtual Room (TBA) Penalty', 'desc': 'Prioritize physical rooms (A101-A103) over TBA.'},
        {'code': 'EARLY_START_ENFORCEMENT',    'cat': 'Room',           'type': 'SC1', 'weight': 200, 'name': '(SC-I-02) Early Start Enforcement', 'desc': 'Prioritize filling the earliest morning slots (7 AM).'},
        {'code': 'EVENING_AVOIDANCE',          'cat': 'Time',           'type': 'SC1', 'weight': 150, 'name': '(SC-I-03) Evening Class Avoidance', 'desc': 'Avoid scheduling classes after 6:00 PM.'},
        {'code': 'ROOM_IDLE_GAP',              'cat': 'Room',           'type': 'SC1', 'weight': 120, 'name': '(SC-I-04) Room Idle Gap Penalty', 'desc': 'Avoid leaving large empty gaps in room schedules.'},
        {'code': 'NO_ISOLATED_LECTURES',       'cat': 'Section',        'type': 'SC1', 'weight': 100, 'name': '(SC-I-05) No Isolated Lectures', 'desc': 'Sections should have at least 2 lectures in a day.'},
        {'code': 'NO_ISOLATED_LABS',           'cat': 'Section',        'type': 'SC1', 'weight': 100, 'name': '(SC-I-06) No Isolated Laboratories', 'desc': 'Sections should have at least 2 laboratories in a day.'},
        {'code': 'MIN_DAILY_SECTION_LOAD',     'cat': 'Section',        'type': 'SC1', 'weight': 100, 'name': '(SC-I-07) Min Daily Section Load', 'desc': 'Sections should have a compact daily schedule.'},
        {'code': 'LEC_LAB_WEEKLY_DIST',        'cat': 'Course',         'type': 'SC1', 'weight': 80,  'name': '(SC-I-08) Lec-Lab Weekly Dist.', 'desc': 'Lec early in week, Lab later in week.'},
        {'code': 'LEC_LAB_PROXIMITY',          'cat': 'Course',         'type': 'SC1', 'weight': 70,  'name': '(SC-I-09) Lec-Lab Proximity', 'desc': 'Lec and Lab should be within 3 days.'},
        {'code': 'PE_MORNING_PLACEMENT',       'cat': 'Course',         'type': 'SC2', 'weight': 5,  'name': '(SC-II-01) Morning PE Placement', 'desc': 'PE courses early in the morning.'},
        {'code': 'PE_EARLY_WEEK',              'cat': 'Course',         'type': 'SC2', 'weight': 5,  'name': '(SC-II-02) Early Week PE Placement', 'desc': 'PE courses on Mondays or Tuesdays.'},
        {'code': 'ASYNC_STRATEGIC_PLACEMENT',  'cat': 'Course',         'type': 'SC2', 'weight': 5,  'name': '(SC-II-03) Strategic Async Placement', 'desc': 'Async classes fill 1-hour gaps.'},

        # ── SOFT CONSTRAINTS II (SC-II-01 to SC-II-05) ───────────────────────────────
        {'code': 'LUNCH_BREAK',                'cat': 'Time',           'type': 'SC2', 'weight': 2,  'name': '(SC-II-04) Lunch Break Allocation', 'desc': '1-hour break between 10 AM and 2 PM.'},
        {'code': 'ROOM_CAPACITY_PROPORTIONAL', 'cat': 'Room',           'type': 'SC2', 'weight': 2,  'name': '(SC-II-05) Room Capacity Allocation', 'desc': 'Large sections prioritized for large rooms.'},
    
    ]

def seed_database():
    with app.app_context():
        print("Cleaning database (Preserving Users)...")
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

        print("Seeding Rooms...")
        for r in rooms_to_add:
            db.session.add(Room(
                room_name=r['name'], building=r['building'],
                capabilities=r['capabilities'], status=r['status'],
                capacity=r['capacity'], functional_computers=r['func_comp'],
                room_departments=r.get('room_depts', '')
            ))

        print("Seeding Sections...")
        for s in sections_to_add:
            db.session.add(Section(
                section_name=s['name'], year_level=s['year'], 
                number_of_students=s['students']
            ))

        print("Seeding Constraints...")
        for c in constraints_to_add:
            db.session.add(Constraint(
                logic_code=c['code'], category=c['cat'], 
                name=c['name'], description=c['desc'], 
                constraint_type=c['type'], weight=c['weight']
            ))
        
        db.session.commit()

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

        print("Ensuring Superadmin exists...")
        admin_user = User.query.filter_by(role='superadmin').first()
        if not admin_user:
            admin_user = User(username='Jeremychristian', password_hash=generate_password_hash('sosa'), role='superadmin')
            db.session.add(admin_user)
            db.session.commit()
            print("Created default superadmin 'Jeremychristian'.")

        print("✅ Database seeded successfully!")

if __name__ == '__main__':
    seed_database()