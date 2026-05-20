# seeder11.py — FIRST SEMESTER 2026-2027 OFFICIAL DATASET (FINAL SYNC)
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import (app, db, User, Course, Room, Section, Faculty, Constraint,
                 SystemSettings, CodePrefixRule, ScheduledClass,
                 FacultyAssignment, PreAssignment, Department, Student,
                 section_courses, faculty_courses)
from werkzeug.security import generate_password_hash
from datetime import datetime

SEEDER_LEVEL   = 11
DESCRIPTION    = "Final Sync with Genetic Algorithm (28 Hard Constraints) + Full Curriculum."

# ── DEPARTMENTS ──────────────────────────────────────────────────────────────
DEPARTMENTS = [
    {'name': 'Department of Computer Studies', 'code': 'DCS'},
    {'name': 'Department of Teachers Education', 'code': 'DTE'},
    {'name': 'Department of Hospitality Management', 'code': 'DHM'},
    {'name': 'NSTP Department', 'code': 'NSTP'},
    {'name': 'Department of Industrial Technology', 'code': 'DIT'},
    {'name': 'Department of Arts and Sciences', 'code': 'DAS'},
    {'name': 'Department of Engineering', 'code': 'DE'},
    {'name': 'Department of Business Administration', 'code': 'DBA'},
]

# ── USERS ────────────────────────────────────────────────────────────────────
USERS = [
    {'user': 'Jeremychristian', 'role': 'superadmin', 'dept': None, 'pass': 'sosa'},
    {'user': 'admin', 'role': 'admin', 'dept': 'Department of Computer Studies', 'pass': 'admin'},
    {'user': 'DAS', 'role': 'user', 'dept': 'Department of Arts and Sciences', 'pass': '1234'},
    {'user': 'DBA', 'role': 'user', 'dept': 'Department of Business Administration', 'pass': '1234'},
    {'user': 'DE', 'role': 'user', 'dept': 'Department of Engineering', 'pass': '1234'},
    {'user': 'DHM', 'role': 'user', 'dept': 'Department of Hospitality Management', 'pass': '1234'},
    {'user': 'DIT', 'role': 'user', 'dept': 'Department of Industrial Technology', 'pass': '1234'},
    {'user': 'DTE', 'role': 'user', 'dept': 'Department of Teachers Education', 'pass': '1234'},
]

# ── ROOM INFRASTRUCTURE ──────────────────────────────────────────────────────
ROOMS = [
    # Lecture Rooms (ICT A1-A6)
    {'name': 'ICT A1', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 45, 'room_depts': 'Department of Computer Studies', 'room_type': 'Sync'},
    {'name': 'ICT A2', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 45, 'room_depts': 'Department of Computer Studies', 'room_type': 'Sync'},
    {'name': 'ICT A3', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 45, 'room_depts': 'Department of Computer Studies', 'room_type': 'Sync'},
    {'name': 'ICT A4', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 45, 'room_depts': 'Department of Computer Studies', 'room_type': 'Sync'},
    {'name': 'ICT A5', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 45, 'room_depts': 'Department of Computer Studies', 'room_type': 'Sync'},
    {'name': 'ICT A6', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 45, 'room_depts': 'Department of Computer Studies', 'room_type': 'Sync'},
    
    # Laboratory Rooms (ICT B1-B6)
    {'name': 'ICT B1', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 40, 'room_depts': 'Department of Computer Studies', 'room_type': 'Sync'},
    {'name': 'ICT B2', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 40, 'room_depts': 'Department of Computer Studies', 'room_type': 'Sync'},
    {'name': 'ICT B3', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 40, 'room_depts': 'Department of Computer Studies', 'room_type': 'Sync'},
    {'name': 'ICT B4', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 40, 'room_depts': 'Department of Computer Studies', 'room_type': 'Sync'},
    {'name': 'ICT B5', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 40, 'room_depts': 'Department of Computer Studies', 'room_type': 'Sync'},
    {'name': 'ICT B6', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 40, 'room_depts': 'Department of Computer Studies', 'room_type': 'Sync'},
    
    # Gymnasium
    {'name': 'Court 1', 'building': 'Gymnasium', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 100, 'room_depts': 'NSTP Department', 'room_type': 'Sync'},
    {'name': 'Court 2', 'building': 'Gymnasium', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 100, 'room_depts': 'NSTP Department', 'room_type': 'Sync'},

    # Virtual fallback rooms
    {'name': 'Online Room', 'building': 'Virtual', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 999, 'room_type': 'Async'},
    {'name': 'T.B.A.',      'building': 'Virtual', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 999, 'room_type': 'Async'},
]

# ── FACULTY (Mon-Thu restriction, Permanent NO Thu, Pelina NO Mon) ────────────
FACULTY_DATA = [
    {'name': 'GELERA, ARIES M.',            'status': 'Permanent',  'days': 'Monday,Tuesday,Wednesday',                 'assign_status': 'Announced'},
    {'name': 'PELIÑA, MARY ANN E.',         'status': 'Permanent',  'days': 'Tuesday,Wednesday',                         'assign_status': 'Announced'},
    {'name': 'ESTONILO, CHRISTOPHER G.',    'status': 'Permanent',  'days': 'Monday,Tuesday,Wednesday',                 'assign_status': 'Announced'},
    {'name': 'NOCON, YVANA JARDINE R.',     'status': 'Permanent',  'days': 'Monday,Tuesday,Wednesday',                 'assign_status': 'Announced'},
    {'name': 'NABABLIT, KARLO JOSE E.',     'status': 'Permanent',  'days': 'Monday,Tuesday,Wednesday',                 'assign_status': 'Announced'},
    {'name': 'VILLANUEVA, LESTER D.',       'status': 'Permanent',  'days': 'Monday,Tuesday,Wednesday',                 'assign_status': 'Announced'},
    {'name': 'MUYOT, ALLEN JOHN C.',        'status': 'Permanent',  'days': 'Monday,Tuesday,Wednesday',                 'assign_status': 'Announced'},
    {'name': 'OBON, ANA MARIE C.',          'status': 'Permanent',  'days': 'Monday,Tuesday,Wednesday,Thursday',         'assign_status': 'Announced'},
    {'name': 'SILVANO, MARY GRACE P.',      'status': 'Instructor', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'Announced'},
    {'name': 'CRUZ, JANESSA MARIELLE S.',   'status': 'Instructor', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'Announced'},
    {'name': 'AMBIL, KYLE ANGELO',          'status': 'Instructor', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'Announced'},
    {'name': 'MELITANTE, GIRLIE P.',        'status': 'Instructor', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'Announced'},
    {'name': 'BAUTISTA, RENATO A.',         'status': 'Instructor', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'Announced'},
    {'name': 'CABRIDO, ALYANA',             'status': 'Instructor', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'Announced'},
    {'name': 'CEDILLO, CEDRICK KENN',       'status': 'Instructor', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'Announced'},
    {'name': 'CLARITO, ANGELA C.',          'status': 'Instructor', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'Announced'},
    {'name': 'PERNALA, JOHN CHRISTIAN',     'status': 'Instructor', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'Announced'},
    {'name': 'TINAMBACAN, AARON',           'status': 'Instructor', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'Announced'},
    {'name': 'TOLEDO, IVAN',                'status': 'Instructor', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'Announced'},
    {'name': 'ORDOÑA, KARL VINCENT M.',     'status': 'Instructor', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'Announced'},
    {'name': 'CATALAN, RACQUEL A.',         'status': 'Part-timer', 'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'Announced'},
    {'name': 'DCS Teacher A (IT)',          'status': 'TBA',        'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'TBA'},
    {'name': 'DCS Teacher B (CS)',          'status': 'TBA',        'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'TBA'},
    {'name': 'DCS Teacher C (CS)',          'status': 'TBA',        'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'TBA'},
    {'name': 'DCS Teacher D (CS)',          'status': 'TBA',        'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'TBA'},
    {'name': 'DCS Teacher E (DON) - IT',    'status': 'TBA',        'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'TBA'},
    {'name': 'DCS Teacher F (JM) - IT',     'status': 'TBA',        'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'TBA'},
    {'name': 'T.B.A.',                      'status': 'TBA',        'days': 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday', 'assign_status': 'TBA'},
]

# ── REVISED LOADINGS (FROM IMAGES) ────────────────────────────────────────────
# Format: (Fac_Name, Code, Name, Lec_Units, Lab_Units, Lec_Hrs, Lab_Hrs, Sections_List)
LOADINGS = [
    ('AMBIL, KYLE ANGELO', 'COSC 60', 'Digital Logic and Design', 2, 1, 2, 3, ['BSCS 201 A', 'BSCS 201 B', 'BSCS 201 C', 'BSCS 201 D']),
    ('AMBIL, KYLE ANGELO', 'ITEC 85', 'Information Assurance and Security I', 2, 1, 2, 3, ['BSIT 301 A', 'BSIT 301 B', 'BSIT 301 C', 'BSIT 301 D']),
    ('BAUTISTA, RENATO A.', 'DCIT 50', 'Object Oriented Programming', 2, 1, 2, 3, ['BSCS 201 A', 'BSCS 201 B', 'BSCS 201 C', 'BSCS 201 D']),
    ('BAUTISTA, RENATO A.', 'DCIT 50', 'Object Oriented Programming', 2, 1, 2, 3, ['BSIT 201 A', 'BSIT 201 B', 'BSIT 201 C']),
    ('BAUTISTA, RENATO A.', 'ITEC 200B', 'Capstone Project and Research 2', 3, 0, 3, 0, ['BSIT 401 A', 'BSIT 401 B']),
    ('CABRIDO, ALYANA', 'COSC 75', 'Software Engineering II', 2, 1, 2, 3, ['BSCS 301 A', 'BSCS 301 B', 'BSCS 301 C', 'BSCS 301 D', 'BSCS 301 E']),
    ('CABRIDO, ALYANA', 'ITEC 110', 'System Administration and Maintenance', 2, 1, 2, 3, ['BSIT 401 A', 'BSIT 401 B', 'BSIT 401 C']),
    ('CEDILLO, CEDRICK KENN', 'ITEC 80', 'Human Computer Interaction', 2, 1, 2, 3, ['BSCS 401 A', 'BSCS 401 B', 'BSCS 401 C']),
    ('CEDILLO, CEDRICK KENN', 'ITEC 80', 'Introduction to Human Computer Interaction', 2, 1, 2, 3, ['BSIT 301 A', 'BSIT 301 B', 'BSIT 301 C', 'BSIT 301 D', 'BSIT 301 E']),
    ('CLARITO, ANGELA C.', 'DCIT 24', 'Information Management', 2, 1, 2, 3, ['BSIT 201 A', 'BSIT 201 B', 'BSIT 201 C']),
    ('CLARITO, ANGELA C.', 'DCIT 24', 'Information Management', 2, 1, 2, 3, ['BSCS 201 A', 'BSCS 201 B', 'BSCS 201 C', 'BSCS 201 D']),
    ('CLARITO, ANGELA C.', 'ICT 11', 'Empowerment Technologies (E-Tech: ICT for Professional Track', 4, 0, 4, 0, ['Grade 11']),
    ('CRUZ, JANESSA MARIELLE S.', 'COSC 101', 'Computer Graphics and Visual Computing', 2, 1, 2, 3, ['BSCS 301 A', 'BSCS 301 B', 'BSCS 301 C', 'BSCS 301 D', 'BSCS 301 E']),
    ('CRUZ, JANESSA MARIELLE S.', 'ITEC 55', 'Platform Technologies', 2, 1, 2, 3, ['BSIT 202 A', 'BSIT 202 B', 'BSIT 202 C']),
    ('ESTONILO, CHRISTOPHER G.', 'DCIT 60', 'Methods of Research', 3, 0, 3, 0, ['BSIT 301 C']),
    ('ESTONILO, CHRISTOPHER G.', 'COSC 200A', 'Undergraduate Thesis I', 3, 0, 3, 0, ['BSCS 401 A']),
    ('GELERA, ARIES M.', 'DCIT 60', 'Methods of Research', 3, 0, 3, 0, ['BSIT 301 B']),
    ('GELERA, ARIES M.', 'COSC 200A', 'Undergraduate Thesis I', 3, 0, 3, 0, ['BSCS 401 C']),
    ('MELITANTE, GIRLIE P.', 'DCIT 21', 'Introduction to Computing', 2, 1, 2, 3, ['BSCS 101 B', 'BSCS 101 C']),
    ('MELITANTE, GIRLIE P.', 'INSY 50', 'Fundamentals of Information Systems', 3, 0, 3, 0, ['BSCS 201 A', 'BSCS 201 B', 'BSCS 201 C', 'BSCS 201 D']),
    ('MELITANTE, GIRLIE P.', 'BSHM 23', 'Applied Business Tools and Technologies', 2, 1, 2, 3, ['BSHM 201 D', 'BSHM 201 E', 'BSHM 201 F']),
    ('MELITANTE, GIRLIE P.', 'CvSU 101', 'Institutional Orientation', 1, 0, 1, 0, ['BSIT 101 A', 'BSIT 101 B', 'BSIT 101 C']),
    ('MUYOT, ALLEN JOHN C.', 'DCIT 22', 'Computer Programming I', 1, 2, 1, 6, ['BSCS 101 A', 'BSCS 101 B']),
    ('NABABLIT, KARLO JOSE E.', 'DCIT 60', 'Methods of Research', 3, 0, 3, 0, ['BSIT 301 A']),
    ('NABABLIT, KARLO JOSE E.', 'COSC 200A', 'Undergraduate Thesis I', 3, 0, 3, 0, ['BSCS 401 B']),
    ('NOCON, YVANA JARDINE R.', 'INSY 55', 'System Analysis and Design', 2, 1, 2, 3, ['BSIT 301 A', 'BSIT 301 B', 'BSIT 301 C']),
    ('OBON, ANA MARIE C.', 'DCIT 65', 'Social and Professional Issues', 3, 0, 3, 0, ['BSIT 401 A', 'BSIT 401 B', 'BSIT 401 C']),
    ('OBON, ANA MARIE C.', 'TLEP 08', 'Teaching Common Competencies in ICT', 3, 0, 3, 0, ['BTVTED 301 A', 'BTVTED 301 B']),
    ('PELIÑA, MARY ANN E.', 'DCIT 60', 'Methods of Research', 3, 0, 3, 0, ['BSIT 301 D', 'BSIT 301 E']),
    ('PELIÑA, MARY ANN E.', 'ITEC 200B', 'Capstone Project and Research 2', 3, 0, 3, 0, ['BSIT 401 C']),
    ('PERNALA, JOHN CHRISTIAN', 'COSC 50', 'Discreet Structures I', 3, 0, 3, 0, ['BSCS 101 A', 'BSCS 101 B', 'BSCS 101 C']),
    ('PERNALA, JOHN CHRISTIAN', 'DCIT 22', 'Computer Programming I', 1, 2, 1, 6, ['BSCS 101 C']),
    ('PERNALA, JOHN CHRISTIAN', 'DCIT 22', 'Computer Programming I', 1, 2, 1, 6, ['BSIT 101 A', 'BSIT 101 B', 'BSIT 101 C']),
    ('SILVANO, MARY GRACE P.', 'DCIT 21', 'Introduction to Computing', 2, 1, 2, 3, ['BSIT 101 A', 'BSIT 101 B', 'BSIT 101 C']),
    ('SILVANO, MARY GRACE P.', 'DCIT 21', 'Introduction to Computing', 2, 1, 2, 3, ['BSCS 101 A']),
    ('SILVANO, MARY GRACE P.', 'BSHM 23', 'Applied Business Tools and Technologies', 2, 1, 2, 3, ['BSHM 201 A', 'BSHM 201 B', 'BSHM 201 C']),
    ('SILVANO, MARY GRACE P.', 'CvSU 101', 'Institutional Orientation', 1, 0, 1, 0, ['BSCS 101 A', 'BSCS 101 B', 'BSCS 101 C']),
    ('TINAMBACAN, AARON', 'DCIT 26', 'Application Development and Emerging Technologies', 2, 1, 2, 3, ['BSCS 301 A', 'BSCS 301 B', 'BSCS 301 C', 'BSCS 301 D', 'BSCS 301 E']),
    ('TINAMBACAN, AARON', 'DCIT 26', 'Application Development and Emerging Technologies', 2, 1, 2, 3, ['BSIT 301 A', 'BSIT 301 B', 'BSIT 301 C']),
    ('VILLANUEVA, LESTER D.', 'ITEC 90', 'Network Fundamentals', 2, 1, 2, 3, ['BSIT 301 A', 'BSIT 301 B', 'BSIT 301 C']),
    ('DCS Teacher A (IT)', 'ITEC 111', 'Integrated Programming and Gtechnologies 2', 2, 1, 2, 3, ['BSIT 401 A', 'BSIT 401 B', 'BSIT 401 C']),
    ('DCS Teacher A (IT)', 'COSC 80', 'Operating Systems', 2, 1, 2, 3, ['BSCS 301 A', 'BSCS 301 B', 'BSCS 301 C', 'BSCS 301 D', 'BSCS 301 E']),
    ('DCS Teacher B (CS)', 'COSC 105', 'Intelligence Systems', 2, 1, 2, 3, ['BSCS 401 A', 'BSCS 401 B', 'BSCS 401 C']),
    ('DCS Teacher B (CS)', 'TLE 3', 'Technology and Livelihood', 4, 0, 4, 0, ['Grade 9']),
    ('DCS Teacher B (CS)', 'TLE 4', 'ICT Skills and Development', 4, 0, 4, 0, ['Grade 10']),
    ('DCS Teacher B (CS)', 'ITEC 116', 'Systems Integration and Architecture 2', 2, 1, 2, 3, ['BSIT 401 A', 'BSIT 401 B', 'BSIT 401 C']),
    ('DCS Teacher C (CS)', 'COSC 55', 'Discreet Structures II', 3, 0, 3, 0, ['BSCS 201 A', 'BSCS 201 B', 'BSCS 201 C', 'BSCS 201 D']),
    ('DCS Teacher C (CS)', 'INSY 55', 'System Analysis and Design', 2, 1, 2, 3, ['BSIT 301 D', 'BSIT 301 E']),
    ('DCS Teacher C (CS)', 'COSC 111', 'Internet of Things', 2, 1, 2, 3, ['BSCS 401 A', 'BSCS 401 B', 'BSCS 401 C']),
    ('DCS Teacher D (CS)', 'DCIT 26', 'Application Development and Emerging Technologies', 2, 1, 2, 3, ['BSIT 301 D', 'BSIT 301 E']),
    ('DCS Teacher D (CS)', 'DCIT 65', 'Social and Professional Issues', 3, 0, 3, 0, ['BSCS 301 A', 'BSCS 301 B', 'BSCS 301 C', 'BSCS 301 D', 'BSCS 301 E']),
    ('DCS Teacher D (CS)', 'COSC 100', 'Automata Theory and Formal Languages', 3, 0, 3, 0, ['BSCS 401 A', 'BSCS 401 B', 'BSCS 401 C']),
    ('CATALAN, RACQUEL A.', 'COSC 50', 'Discreet Structure', 3, 0, 3, 0, ['BSIT 101 A', 'BSIT 101 B', 'BSIT 101 C']),
    ('TOLEDO, IVAN', 'ITEC 85', 'Information Assurance and Security I', 2, 1, 2, 3, ['BSIT 301 E']),
    ('TOLEDO, IVAN', 'COSC 85', 'Networks and Communication', 2, 1, 2, 3, ['BSCS 301 C']),
    ('ORDOÑA, KARL VINCENT M.', 'ITEC 90', 'Network Fundamentals', 2, 1, 2, 3, ['BSIT 301 D', 'BSIT 301 E']),
    ('DCS Teacher E (DON) - IT', 'COSC 85', 'Networks and Communication', 2, 1, 2, 3, ['BSCS 301 D', 'BSCS 301 E']),
    ('DCS Teacher F (JM) - IT', 'COSC 85', 'Networks and Communication', 2, 1, 2, 3, ['BSCS 301 A', 'BSCS 301 B']),
]

IMAGE_EXTRA = []

# ── NEW CURRICULUM COURSES (NOT IN LOADING IMAGES) ────────────────────────────
# Format: (Code, Title, Lec_Units, Lab_Units, Lec_Hrs, Lab_Hrs, Department_Code)
CURRICULUM_COURSES = [
    # DTE (Teachers Education)
    ('ENGL 1', 'Study and Thinking Skills in English', 2, 1, 2, 3, 'DTE'),
    ('FILI I', 'Komunikasyon sa Akademikong Filipino', 3, 0, 3, 0, 'DTE'),
    ('MATH 2a', 'College Algebra', 3, 0, 3, 0, 'DTE'),
    ('FILI 2', 'Pagbasa at Pagsulat Tungo sa Pananaliksik', 3, 0, 3, 0, 'DTE'),
    ('MATH 4', 'Trigonometry', 3, 0, 3, 0, 'DTE'),
    ('ENGL 2', 'Writing in the Discipline', 2, 1, 2, 3, 'DTE'),
    ('ENGL 6', 'Speech Communication', 2, 1, 2, 3, 'DTE'),
    ('ENGL 7', 'Scientific Reporting and Thesis Writing', 2, 1, 2, 3, 'DTE'),
    ('STAT 1', 'Elementary Statistics', 2, 1, 2, 3, 'DTE'),
    ('MATH 22', 'Analytic Geometry w/ Calculus', 3, 0, 3, 0, 'DTE'),

    # DAS (Arts and Sciences)
    ('LITT 1', 'Philippine Literature', 3, 0, 3, 0, 'DAS'),
    ('HUMN 6', 'Social Philosophy 1', 3, 0, 3, 0, 'DAS'),
    ('PHYS 1a', 'Mechanics and Heat', 2, 1, 2, 3, 'DAS'),
    ('PHYS 2a', 'Wave, Magnetism, Sound and Light', 2, 1, 2, 3, 'DAS'),
    ('SOSC 2', 'General Psychology', 3, 0, 3, 0, 'DAS'),
    ('HUMN 5', 'Art, Man and Society', 3, 0, 3, 0, 'DAS'),
    ('SOSC 3', 'Phil. History, Geography and Institution', 3, 0, 3, 0, 'DAS'),
    ('SOSC 5', "Phil. Gov't. Politics and the Constitution", 3, 0, 3, 0, 'DAS'),
    ('SOSC 6', "Rizal's Life, Works and Writings", 3, 0, 3, 0, 'DAS'),
    ('PHED 1', 'Physical Fitness & Aerobics', 2, 0, 2, 0, 'DAS'),
    ('PHED 2', 'Rhythmic Activities', 2, 0, 2, 0, 'DAS'),
    ('PHED 3', 'Individual/Dual Sports', 2, 0, 2, 0, 'DAS'),
    ('PHED 4', 'Team Sports', 2, 0, 2, 0, 'DAS'),

    # DE (Engineering)
    ('MATH 10', 'Differential Calculus', 3, 0, 3, 0, 'DE'),
    ('MATH 11', 'Integral Calculus', 3, 0, 3, 0, 'DE'),

    # DBA (Business Administration)
    ('ECON 3', 'General Economics with TAR', 3, 0, 3, 0, 'DBA'),
    ('ACTG 1', 'Fundamentals of Accounting', 3, 0, 3, 0, 'DBA'),

    # NSTP
    ('NSTP 1', 'Literacy Training Service 1 / ROTC', 3, 0, 3, 0, 'NSTP'),
    ('NSTP 2', 'Literacy Training Service 2 / ROTC', 3, 0, 3, 0, 'NSTP'),

    # DCS (Computer Studies - Additional)
    ('COSC 21', 'CS Fundamentals', 2, 1, 2, 3, 'DCS'),
    ('DCIT 23', 'Discrete Math', 3, 0, 3, 0, 'DCS'),
    ('COSC 65', "Prog. Languages w/ Compiler Design", 3, 0, 3, 0, 'DCS'),
    ('COSC 70', 'Database Systems', 2, 1, 2, 3, 'DCS'),
    ('COSC 80', 'Modeling and Simulation', 2, 1, 2, 3, 'DCS'),
    ('DCIT 25', 'Professional Ethics', 3, 0, 3, 0, 'DCS'),
    ('DCIT 101', 'Management Information System', 2, 1, 2, 3, 'DCS'),
    ('COSC 121', 'Data Communication', 2, 1, 2, 3, 'DCS'),
    ('BTCH 1', 'Introduction to Biotechnology', 3, 0, 3, 0, 'DCS'),
    ('COSC 199', 'Internship/OJT/Practicum', 3, 0, 3, 0, 'DCS'),
    ('COSC 126', 'Open Source Technology', 3, 0, 3, 0, 'DCS'),
    ('DCIT 99', 'Inspection Trip and Seminar', 3, 0, 3, 0, 'DCS'),
    ('COSC 131', 'Embedded System', 3, 0, 3, 0, 'DCS'),
    ('COSC 200C', 'Undergraduate Thesis (Final Part)', 3, 0, 3, 0, 'DCS'),
    ('ITEC 1', 'IT Fundamentals', 2, 1, 2, 3, 'DCS'),
    ('CCTN 50', 'Basic Trouble Shooting and Maintenance', 2, 1, 2, 3, 'DCS'),
    ('ITEC 50', 'Data Management System', 2, 1, 2, 3, 'DCS'),
    ('ITEC 65', 'Advanced Database Management System', 2, 1, 2, 3, 'DCS'),
    ('ITEC 70', 'Computer Graphics', 2, 1, 2, 3, 'DCS'),
    ('ITEC 75', 'Technopreneur', 3, 0, 3, 0, 'DCS'),
    ('ITEC 101', 'e-Commerce', 2, 1, 2, 3, 'DCS'),
    ('ITEC 106', 'System Security', 2, 1, 2, 3, 'DCS'),
    ('ITEC 200', 'Undergraduate Thesis (Part 3)', 3, 0, 3, 0, 'DCS'),
    ('ITEC 2008', 'Undergraduate Thesis (Part 2)', 2, 0, 2, 0, 'DCS'),
    ('ITEC 85', 'Quality Consciousness Habits and Processes', 3, 0, 3, 0, 'DCS'),
    ('DCEE 28', 'Methods of Research (IT)', 1, 0, 1, 0, 'DCS'),
    ('TLE 3', 'Technology and Livelihood', 4, 0, 4, 0, 'DCS'),
    ('TLE 4', 'ICT Skills and Development', 4, 0, 4, 0, 'DCS'),
    ('BSHM 23', 'Applied Business Tools and Technologies', 2, 1, 2, 3, 'DCS'),
    ('TLEP 08', 'Teaching Common Competencies in ICT', 3, 0, 3, 0, 'DCS'),
    ('CvSU 101', 'Institutional Orientation', 1, 0, 1, 0, 'DCS'),
    ('ICT 11', 'Empowerment Technologies', 4, 0, 4, 0, 'DCS'),
    # DE, DBA, NSTP
    ('MATH 10', 'Differential Calculus', 3, 0, 3, 0, 'DE'),
    ('MATH 11', 'Integral Calculus', 3, 0, 3, 0, 'DE'),
    ('ECON 3', 'General Economics with TAR', 3, 0, 3, 0, 'DBA'),
    ('ACTG 1', 'Fundamentals of Accounting', 3, 0, 3, 0, 'DBA'),
    ('NSTP 1', 'Literacy Training Service 1 / ROTC', 3, 0, 3, 0, 'NSTP'),
    ('NSTP 2', 'Literacy Training Service 2 / ROTC', 3, 0, 3, 0, 'NSTP'),
]


def seed_database():
    with app.app_context():
        print(f"Seeder {SEEDER_LEVEL}: Resetting Database Schema...")
        db.drop_all() # Ensure new columns are added
        db.create_all()
        db.session.commit()
        print("Schema reset complete.")

        # 1. Departments
        dept_map = {}
        for d in DEPARTMENTS:
            obj = Department(name=d['name'], code=d['code'])
            db.session.add(obj)
            dept_map[d['code']] = obj
        db.session.commit()

        # 2. Users
        for u in USERS:
            db.session.add(User(username=u['user'], role=u['role'], department=u['dept'], password_hash=generate_password_hash(u['pass'])))
        
        # 3. Rooms
        for r in ROOMS:
            db.session.add(Room(
                room_name=r['name'], building=r['building'], 
                capabilities=r['capabilities'], status=r['status'], 
                capacity=r['capacity'], room_departments=r.get('room_depts', ''),
                room_type=r.get('room_type', 'Sync')
            ))
        
        # 4. Faculty
        fac_map = {}
        for f in FACULTY_DATA:
            obj = Faculty(
                employee_id=f'DCS-{f["name"][:3].upper()}', 
                full_name=f['name'], 
                department='Department of Computer Studies', 
                employment_status=f['status'], 
                assignment_status=f.get('assign_status', 'Announced'),
                max_weekly_hours=45,
                available_days=f['days']
            )
            db.session.add(obj)
            fac_map[f['name']] = obj
        db.session.commit()

        # 5. Sections
        section_map = {}
        all_section_names = set()
        for item in (LOADINGS + IMAGE_EXTRA):
            sections = item[-1]
            for s in sections: 
                name = s.replace('BSINFOTECH', 'BSIT').replace(' - ', ' ').replace(' ,', ',').strip()
                all_section_names.add(name)
            
        for name in sorted(list(all_section_names)):
            yr = 1
            if '101' in name: yr = 1
            elif '201' in name or '202' in name: yr = 2
            elif '301' in name: yr = 3
            elif '401' in name: yr = 4
            elif 'Grade 9' in name: yr = 1
            elif 'Grade 10' in name: yr = 2
            elif 'Grade 11' in name: yr = 3
            
            if yr == 1:
                # 1st Years: Friday is unassigned/blank (due to NSTP)
                avail_days = 'Monday,Tuesday,Wednesday,Thursday,Saturday,Sunday'
            else:
                avail_days = 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday'
                
            obj = Section(section_name=name, year_level=yr, number_of_students=40, available_days=avail_days)
            db.session.add(obj)
            section_map[name] = obj
        db.session.commit()

        # 6. Courses (All Sources Combined)
        course_map = {}
        
        # A. Courses from Loading Images (Fac_Name, Code, Name, Lec_U, Lab_U, Lec_H, Lab_H, Sections)
        for item in (LOADINGS + IMAGE_EXTRA):
            ccode = item[1]
            cname = item[2]
            lec_u = item[3]
            lab_u = item[4]
            lec_h = item[5]
            lab_h = item[6]
            if ccode not in course_map:
                # Determine Department (Directly DCS as requested)
                dcode = 'DCS'
                dept_name = next((d['name'] for d in DEPARTMENTS if d['code'] == dcode), 'Department of Computer Studies')
                obj = Course(
                    course_code=ccode, course_name=cname, year_level=1, 
                    program=dcode, department=dept_name, 
                    lec_units=lec_u, lab_units=lab_u,
                    synchronous_lec_hours=lec_h, synchronous_lab_hours=lab_h, 
                    asynchronous_lec_hours=0, asynchronous_lab_hours=0, 
                    semester_offered='1st Semester'
                )
                db.session.add(obj)
                course_map[ccode] = obj
        
        # B. Courses from Full Curriculum (Code, Name, Lec_U, Lab_U, Lec_H, Lab_H, Dept)
        for ccode, cname, lec_u, lab_u, lec_h, lab_h, dcode in CURRICULUM_COURSES:
            if ccode not in course_map:
                dept_name = next((d['name'] for d in DEPARTMENTS if d['code'] == dcode), 'Department of Computer Studies')
                obj = Course(
                    course_code=ccode, course_name=cname, year_level=1, 
                    program=dcode, department=dept_name, 
                    lec_units=lec_u, lab_units=lab_u,
                    synchronous_lec_hours=lec_h, synchronous_lab_hours=lab_h, 
                    asynchronous_lec_hours=0, asynchronous_lab_hours=0, 
                    semester_offered='1st Semester'
                )
                db.session.add(obj)
                course_map[ccode] = obj
        
        db.session.commit()

        # 7. Assignments
        for item in (LOADINGS + IMAGE_EXTRA):
            fac_name = item[0]
            ccode = item[1]
            sections = item[-1]
            fac = fac_map.get(fac_name)
            course = course_map.get(ccode)
            if fac and course:
                if course not in fac.courses: fac.courses.append(course)
                for s in sections:
                    sec_name = s.replace('BSINFOTECH', 'BSIT').replace(' - ', ' ').strip()
                    sec = section_map.get(sec_name)
                    if sec:
                        if course not in sec.courses: sec.courses.append(course)
                        db.session.add(FacultyAssignment(faculty_id=fac.id, course_id=course.id, section_id=sec.id))
        db.session.commit()

        # 8. System Settings
        db.session.add(SystemSettings(
            start_hour=7, end_hour=21, allowed_days="Monday,Tuesday,Wednesday,Thursday,Friday", 
            campus_name="CCAT Campus", address="Rosario, Cavite", 
            section_school_name="CAVITE STATE UNIVERSITY", fac_dept_label="DEPARTMENT OF COMPUTER STUDIES", 
            sem_ay_value="1st Semester / 2026-2027",
            blocked_slots_json='[{"day": "Monday", "start": "07:00", "end": "08:00"}]'
        ))
        
        # 9. Constraints (MASTER LIST: HC-01 to HC-28, SC-I-01 to SC-II-04)
        CONSTRAINTS = [
            # ── HARD CONSTRAINTS (HC-01 to HC-26) ──────────────────────────────────────
            # A1: Built-In / Structural Hard Constraints (HC-01 to HC-19)
            {'code': 'LOCKED_SCHEDULES',           'cat': 'Administrative', 'type': 'HC',  'weight': 1,   'name': '(HC-01) Locked Schedules', 'desc': 'Manually plotted schedules are immovable.'},
            {'code': 'GLOBAL_DAY_RESTRICTION',     'cat': 'Administrative', 'type': 'HC',  'weight': 1,   'name': '(HC-02) Global Day Restriction', 'desc': 'No classes on Sundays or non-academic days.'},
            {'code': 'STRICT_LEC_DURATION',        'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-03) Strict Lecture Duration', 'desc': 'Lec hours must match curriculum.'},
            {'code': 'STRICT_LAB_DURATION',        'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-04) Strict Laboratory Duration', 'desc': 'Lab hours must match curriculum.'},
            {'code': 'STRICT_ASYNC_LEC_DUR',       'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-05) Strict Async Lecture Duration', 'desc': 'Async hours must match curriculum.'},
            {'code': 'STRICT_ASYNC_LAB_DUR',       'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-06) Strict Async Lab Duration', 'desc': 'Async hours must match curriculum.'},
            {'code': 'SECTION_OVERLAP',            'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-07) Section Overlap Prevention', 'desc': 'Section cannot have 2 courses at once.'},
            {'code': 'FACULTY_OVERLAP',            'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-08) Faculty Overlap Prevention', 'desc': 'Faculty cannot teach 2 courses at once.'},
            {'code': 'ROOM_OVERLAP',               'cat': 'Section',        'type': 'HC',  'weight': 1,   'name': '(HC-09) Room Overlap Prevention', 'desc': 'Room cannot host 2 sections at once.'},
            {'code': 'SINGLE_FACULTY_PER_TIMESLOT','cat': 'Faculty',        'type': 'HC',  'weight': 1,   'name': '(HC-10) Single Faculty per Section Slot', 'desc': 'Section cannot have 2 faculty at once.'},
            {'code': 'FACULTY_AVAILABILITY',       'cat': 'Faculty',        'type': 'HC',  'weight': 1,   'name': '(HC-11) Faculty Day Off / Availability', 'desc': 'Faculty must be available.'},
            {'code': 'SINGLE_ROOM_PER_SESSION',    'cat': 'Room',           'type': 'HC',  'weight': 1,   'name': '(HC-12) Single Room per Session', 'desc': 'Session cannot use 2 rooms at once.'},
            {'code': 'ROOM_AVAILABILITY',          'cat': 'Room',           'type': 'HC',  'weight': 1,   'name': '(HC-13) Room Calendar Availability', 'desc': 'Room must be available.'},
            {'code': 'OPERATING_HOURS',            'cat': 'Time',           'type': 'HC',  'weight': 1,   'name': '(HC-14) Operating Hours Compliance', 'desc': 'Sessions must be within campus hours.'},
            {'code': 'HOURLY_ALIGNMENT',           'cat': 'Time',           'type': 'HC',  'weight': 1,   'name': '(HC-15) Hourly Slot Alignment', 'desc': 'Classes must start exactly on the hour.'},
            {'code': 'COMPLETE_COURSE_SCHEDULING', 'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-16) Complete Course Plotting', 'desc': 'All curriculum subjects must be plotted.'},
            {'code': 'PREASSIGNMENT_EXCLUSIVITY',  'cat': 'Section',        'type': 'HC',  'weight': 1,   'name': '(HC-17) Pre-assignment Exclusivity', 'desc': 'Locked slots cannot be overwritten.'},
            {'code': 'FACULTY_DAY_SPLIT',          'cat': 'Faculty',        'type': 'HC',  'weight': 1,   'name': '(HC-18) Faculty Day Split Rule', 'desc': 'Sessions must land on designated split days.'},
            {'code': 'LUNCH_BREAK',                'cat': 'Time',           'type': 'HC',  'weight': 1,   'name': '(HC-19) Lunch Break Allocation', 'desc': '1-hour break after 1 class, or after max 6 consecutive hours.'},

            # A2: Evaluated Constraints (HC-20 to HC-25)
            {'code': 'MAX_CONSECUTIVE_STUDENT',    'cat': 'Section',        'type': 'HC',  'weight': 1,   'name': '(HC-20) Max Consecutive Student Load', 'desc': 'Max 6 consecutive hours for students.'},
            {'code': 'MAX_CONSECUTIVE_FACULTY',    'cat': 'Faculty',        'type': 'HC',  'weight': 1,   'name': '(HC-21) Max Consecutive Faculty Load', 'desc': 'Max 6 consecutive hours for faculty.'},
            {'code': 'MIN_DAILY_SECTION_LOAD',     'cat': 'Section',        'type': 'NC',  'weight': 1,   'name': '(HC-22) Min Daily Section Load', 'desc': 'Ensure at least 3 hours of class per active day.'},
            {'code': 'LEC_IN_LAB_FALLBACK',        'cat': 'Room',           'type': 'NC',  'weight': 1,   'name': '(HC-23) Lecture in Lab Fallback', 'desc': 'Allow lectures in labs only if no classrooms are free.'},
            {'code': 'LEC_LAB_SEQUENCE',           'cat': 'Course',         'type': 'NC',  'weight': 1,   'name': '(HC-24) Lec-Lab Sequence', 'desc': 'Lecture should be scheduled before Laboratory.'},
            {'code': 'ROOM_SUITABILITY',           'cat': 'Room',           'type': 'NC',  'weight': 1,   'name': '(HC-25) Room Type Suitability', 'desc': 'Match subject type with room capabilities.'},

            # ── SOFT CONSTRAINTS I (SC-I-01 to SC-I-04) ────────────────────────────────
            {'code': 'VIRTUAL_ROOM_USAGE',         'cat': 'Room',           'type': 'NC',  'weight': 10,  'name': '(SC-I-01) Virtual Room (Online) Penalty', 'desc': 'Avoid Online rooms for physical classes.'},
            {'code': 'EVENING_AVOIDANCE',          'cat': 'Time',           'type': 'NC',  'weight': 1,   'name': '(SC-I-02) Evening Class Avoidance', 'desc': 'Avoid scheduling classes late in the evening.'},
            {'code': 'ROOM_IDLE_GAP',              'cat': 'Room',           'type': 'NC',  'weight': 10,  'name': '(SC-I-03) Room Idle Gap Penalty', 'desc': 'Incentivize compact room usage.'},
            {'code': 'LEC_LAB_WEEKLY_DIST',        'cat': 'Course',         'type': 'NC',  'weight': 1,   'name': '(SC-I-04) Lec-Lab Weekly Dist.', 'desc': 'Lec and Lab must be scheduled on different days.'},

            # ── SOFT CONSTRAINTS II (SC-II-01) ───────────────────────────────
            {'code': 'ROOM_CAPACITY_PROPORTIONAL', 'cat': 'Room',           'type': 'NC',  'weight': 1,   'name': '(SC-II-01) Room Capacity Allocation', 'desc': 'Prioritize closest absolute fit for room capacity.'},
        ]
        for c in CONSTRAINTS:
            db.session.add(Constraint(logic_code=c['code'], category=c['cat'], constraint_type=c['type'], weight=c['weight'], name=c['name'], description=c['desc']))
        db.session.commit()

        # 10. Students (200 Total: 150 Regular, 50 Irregular)
        print(f"Generating 200 Students...")
        sections_list = list(section_map.values())
        for i in range(1, 201):
            is_irreg = (i > 150)
            stud_type = "Irregular" if is_irreg else "Regular"
            sec = None
            if not is_irreg and sections_list:
                # Distribute regular students among sections
                sec = sections_list[i % len(sections_list)]
            
            new_stud = Student(
                student_id=f"2026-{10000 + i}",
                full_name=f"{stud_type} Student {i}",
                year_level=sec.year_level if sec else 1,
                section_id=sec.id if sec else None,
                is_irregular=is_irreg
            )
            db.session.add(new_stud)
        db.session.commit()
        print(f"Seeder {SEEDER_LEVEL} complete! FINAL Dataset with Full Curriculum initialized.")

if __name__ == '__main__':
    seed_database()
