# seeder11.py — FIRST SEMESTER 2026-2027 OFFICIAL DATASET (CORRECTED ROOMS)
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import (app, db, User, Course, Room, Section, Faculty, Constraint,
                 SystemSettings, CodePrefixRule, ScheduledClass,
                 FacultyAssignment, PreAssignment, Department, Student,
                 section_courses, faculty_courses)
from werkzeug.security import generate_password_hash
from datetime import datetime
from collections import defaultdict

SEEDER_LEVEL   = 11
DESCRIPTION    = "Official 2026-2027 First Semester Faculty Loading with A1-A5 and B1-B6 Rooms."

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
    {'user': 'admin1', 'role': 'admin', 'dept': 'Department of Computer Studies', 'pass': 'admin123'},
    {'user': 'DAS', 'role': 'user', 'dept': 'Department of Arts and Sciences', 'pass': '1234'},
    {'user': 'DBA', 'role': 'user', 'dept': 'Department of Business Administration', 'pass': '1234'},
    {'user': 'DE', 'role': 'user', 'dept': 'Department of Engineering', 'pass': '1234'},
    {'user': 'DHM', 'role': 'user', 'dept': 'Department of Hospitality Management', 'pass': '1234'},
    {'user': 'DIT', 'role': 'user', 'dept': 'Department of Industrial Technology', 'pass': '1234'},
    {'user': 'DTE', 'role': 'user', 'dept': 'Department of Teachers Education', 'pass': '1234'},
]

# ── ROOMS (Target: A1-A5, B1-B6, Courts) ──────────────────────────────────────
ROOMS = [
    # Lecture Rooms
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
    {'name': 'Court 1',     'building': 'Gymnasium', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 50,  'func_comp': 0, 'room_depts': 'Department of Teachers Education'},
    {'name': 'Court 2',     'building': 'Gymnasium', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 50,  'func_comp': 0, 'room_depts': 'Department of Teachers Education'},
    {'name': 'Online Room', 'building': 'Virtual',   'capabilities': 'Lecture', 'status': 'Available', 'capacity': 999, 'func_comp': 0},
    {'name': 'T.B.A.',      'building': 'Virtual',   'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 999, 'func_comp': 0},
    # Dedicated HM Rooms
    {'name': 'HM-A1',  'building': 'HM Building', 'capabilities': 'Lecture',      'status': 'Available', 'capacity': 45, 'func_comp': 0,  'room_depts': 'Department of Hospitality Management'},
    {'name': 'HM-A2',  'building': 'HM Building', 'capabilities': 'Lecture',      'status': 'Available', 'capacity': 45, 'func_comp': 0,  'room_depts': 'Department of Hospitality Management'},
    {'name': 'HM-Lab', 'building': 'HM Building', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 40, 'func_comp': 40, 'room_depts': 'Department of Hospitality Management'},
    # K-12 Room (Saturday only)
    {'name': 'K-12 Room', 'building': 'K-12 Building', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 50, 'func_comp': 0, 'room_depts': 'Department of Teachers Education'},
]

# ── FACULTY (27 from PDF) ─────────────────────────────────────────────────────
FACULTY = [
    {'eid': 'DCS-01', 'name': 'IAN CHRISTOPHER ADAL', 'dept': 'Department of Computer Studies', 'max': 40},
    {'eid': 'DCS-02', 'name': 'KYLE ANGELO AMBIL', 'dept': 'Department of Computer Studies', 'max': 36},
    {'eid': 'DCS-03', 'name': 'RENATO A. BAUTISTA', 'dept': 'Department of Computer Studies', 'max': 41},
    {'eid': 'DCS-04', 'name': 'ALYANA CABRIDO', 'dept': 'Department of Computer Studies', 'max': 40},
    {'eid': 'DCS-05', 'name': 'CEDRICK KENN CEDILLO', 'dept': 'Department of Computer Studies', 'max': 40},
    {'eid': 'DCS-06', 'name': 'ANGELA C. CLARITO', 'dept': 'Department of Computer Studies', 'max': 35},
    {'eid': 'DCS-07', 'name': 'JANESSA MARIELLE S. CRUZ', 'dept': 'Department of Computer Studies', 'max': 40},
    {'eid': 'DCS-08', 'name': 'VHINCE LORENZ DELA REA', 'dept': 'Department of Computer Studies', 'max': 40},
    {'eid': 'DCS-09', 'name': 'CHRISTOPHER G. ESTONILO', 'dept': 'Department of Computer Studies', 'max': 12},
    {'eid': 'DCS-10', 'name': 'ARIES M. GELERA', 'dept': 'Department of Computer Studies', 'max': 12},
    {'eid': 'DCS-11', 'name': 'MARY ANN E. IGNACO', 'dept': 'Department of Computer Studies', 'max': 15},
    {'eid': 'DCS-12', 'name': 'GIRLIE P. MELITANTE', 'dept': 'Department of Computer Studies', 'max': 37},
    {'eid': 'DCS-13', 'name': 'ALLEN JOHN C. MUYOT', 'dept': 'Department of Computer Studies', 'max': 21},
    {'eid': 'DCS-14', 'name': 'KARLO JOSE E. NABABLIT', 'dept': 'Department of Computer Studies', 'max': 12},
    {'eid': 'DCS-15', 'name': 'YVANA JARDINE R. NOCON', 'dept': 'Department of Computer Studies', 'max': 21},
    {'eid': 'DCS-16', 'name': 'ANA MARIE C. OBON', 'dept': 'Department of Computer Studies', 'max': 21},
    {'eid': 'DCS-17', 'name': 'JOHN CHRISTIAN PERNALA', 'dept': 'Department of Computer Studies', 'max': 39},
    {'eid': 'DCS-18', 'name': 'MARY GRACE P. SILVANO', 'dept': 'Department of Computer Studies', 'max': 35},
    {'eid': 'DCS-19', 'name': 'AARON TINAMBACAN', 'dept': 'Department of Computer Studies', 'max': 40},
    {'eid': 'DCS-20', 'name': 'LESTER D. VILLANUEVA', 'dept': 'Department of Computer Studies', 'max': 21},
    {'eid': 'DCS-21', 'name': 'DCS Teacher E (CS)', 'dept': 'Department of Computer Studies', 'max': 35},
    {'eid': 'DCS-22', 'name': 'DCS Teacher F (CS)', 'dept': 'Department of Computer Studies', 'max': 35},
    {'eid': 'DCS-23', 'name': 'RACQUEL A. CATALAN', 'dept': 'Department of Computer Studies', 'max': 21},
    {'eid': 'DCS-24', 'name': 'IVAN TOLEDO', 'dept': 'Department of Computer Studies', 'max': 21},
    {'eid': 'DCS-25', 'name': 'KARL VINCENT M. ORDOÑA', 'dept': 'Department of Computer Studies', 'max': 21},
    {'eid': 'DCS-26', 'name': 'DCS Teacher G (DON) - IT', 'dept': 'Department of Computer Studies', 'max': 21},
    {'eid': 'DCS-27', 'name': 'DCS Teacher H (JM) - IT', 'dept': 'Department of Computer Studies', 'max': 21},
]

# ── COURSES (Mapped from PDF) ────────────────────────────────────────────────
COURSES = [
    ('ITEC 111', 'Integrated Programming and Technologies', 4, 'BSIT', 'DCS', 2, 3, 0, 0, '1st Semester'),
    ('COSC 80',  'Operating Systems',                   3, 'BSCS', 'DCS', 2, 3, 0, 0, '1st Semester'),
    ('COSC 105', 'Intelligence Systems',                4, 'BSCS', 'DCS', 2, 3, 0, 0, '1st Semester'),
    ('DCIT 65',  'Social and Professional Issues',      3, 'Both', 'DCS', 3, 0, 0, 0, '1st Semester'),
    ('ITEC 116', 'Systems Integration and Architecture', 4, 'BSIT', 'DCS', 2, 3, 0, 0, '1st Semester'),
    ('DCIT 50',  'Object Oriented Programming',         2, 'Both', 'DCS', 2, 3, 0, 0, '1st Semester'),
    ('ITEC 200B','Capstone Project and Research 2',     4, 'BSIT', 'DCS', 3, 0, 0, 0, '1st Semester'),
    ('COSC 75',  'Software Engineering II',             3, 'BSCS', 'DCS', 2, 3, 0, 0, '1st Semester'),
    ('ITEC 110', 'System Administration and Maintenance',4, 'BSIT', 'DCS', 2, 3, 0, 0, '1st Semester'),
    ('ITEC 80',  'Human Computer Interaction',          4, 'Both', 'DCS', 2, 3, 0, 0, '1st Semester'),
    ('DCIT 24',  'Information Management',              2, 'Both', 'DCS', 2, 3, 0, 0, '1st Semester'),
    ('COSC 101', 'Computer Graphics and Visual Computing', 3, 'BSCS', 'DCS', 2, 3, 0, 0, '1st Semester'),
    ('ITEC 55',  'Platform Technologies',               2, 'BSIT', 'DCS', 2, 3, 0, 0, '1st Semester'),
    ('COSC 60',  'Digital Logic and Design',            2, 'BSCS', 'DCS', 2, 3, 0, 0, '1st Semester'),
    ('ITEC 85',  'Information Assurance and Security I', 3, 'BSIT', 'DCS', 2, 3, 0, 0, '1st Semester'),
    ('DCIT 60',  'Methods of Research',                 3, 'Both', 'DCS', 3, 0, 0, 0, '1st Semester'),
    ('COSC 200A','Undergraduate Thesis I',              4, 'BSCS', 'DCS', 3, 0, 0, 0, '1st Semester'),
    ('DCIT 21',  'Introduction to Computing',           1, 'Both', 'DCS', 2, 3, 0, 0, '1st Semester'),
    ('INSY 50',  'Fundamentals of Information Systems', 2, 'BSCS', 'DCS', 3, 0, 0, 0, '1st Semester'),
    ('BSHM 23',  'Applied Business Tools and Technologies', 2, 'BSHM', 'DHM', 2, 3, 0, 0, '1st Semester'),
    ('DCIT 22',  'Computer Programming I',              1, 'Both', 'DCS', 1, 6, 0, 0, '1st Semester'), # 6 hrs Lab!
    ('INSY 55',  'System Analysis and Design',          3, 'BSIT', 'DCS', 2, 3, 0, 0, '1st Semester'),
    ('TLEP 08',  'Teaching Common Competencies in ICT', 3, 'BTVTED', 'DTE', 3, 0, 0, 0, '1st Semester'),
    ('COSC 50',  'Discrete Structures I',               1, 'BSCS', 'DCS', 3, 0, 0, 0, '1st Semester'),
    ('DCIT 26',  'Application Development and Emerging Tech', 3, 'Both', 'DCS', 2, 3, 0, 0, '1st Semester'),
    ('ITEC 90',  'Network Fundamentals',                3, 'BSIT', 'DCS', 2, 3, 0, 0, '1st Semester'),
    ('COSC 55',  'Discrete Structures II',              2, 'BSCS', 'DCS', 3, 0, 0, 0, '1st Semester'),
    ('COSC 111', 'Internet of Things',                  4, 'BSCS', 'DCS', 2, 3, 0, 0, '1st Semester'),
    ('COSC 100', 'Automata Theory and Formal Languages', 4, 'BSCS', 'DCS', 3, 0, 0, 0, '1st Semester'),
    ('COSC 85',  'Networks and Communication',          3, 'BSCS', 'DCS', 2, 3, 0, 0, '1st Semester'),
    ('CvSU 101', 'Institutional Orientation',           1, 'Both', 'DAS', 1, 0, 0, 0, '1st Semester'),
    ('TLE 3',    'Technology and Livelihood',           1, 'K-12', 'DTE', 4, 0, 0, 0, '1st Semester'),
    ('TLE 4',    'ICT Skills and Development',          1, 'K-12', 'DTE', 4, 0, 0, 0, '1st Semester'),
    ('ICT 11',   'Empowerment Technologies',            1, 'K-12', 'DTE', 4, 0, 0, 0, '1st Semester'),
    # --- NEW DCS COURSES ---
    ('COSC 21',  'CS Fundamentals', 1, 'BSCS', 'DCS', 2, 1, 0, 0, '1st Semester'),
    ('DCIT 23',  'Discrete Math', 1, 'Both', 'DCS', 3, 0, 0, 0, '1st Semester'),
    ('COSC 65',  'Programming Languages w/ Compiler Design', 2, 'BSCS', 'DCS', 3, 0, 0, 0, '1st Semester'),
    ('COSC 70',  'Database Systems', 2, 'BSCS', 'DCS', 2, 1, 0, 0, '1st Semester'),
    ('DCIT 55',  'Operating System', 3, 'Both', 'DCS', 2, 1, 0, 0, '1st Semester'),
    ('DCIT 25',  'Professional Ethics', 3, 'Both', 'DCS', 3, 0, 0, 0, '1st Semester'),
    ('DCIT 101', 'Management Information System', 3, 'Both', 'DCS', 2, 1, 0, 0, '1st Semester'),
    ('COSC 121', 'Data Communication', 3, 'BSCS', 'DCS', 2, 1, 0, 0, '1st Semester'),
    ('COSC 199', 'Internship/OJT/Practicum', 4, 'BSCS', 'DCS', 3, 0, 0, 0, '1st Semester'),
    ('COSC 126', 'Open Source Technology', 4, 'BSCS', 'DCS', 3, 0, 0, 0, '1st Semester'),
    ('DCIT 99',  'Inspection Trip and Seminar', 4, 'Both', 'DCS', 3, 0, 0, 0, '1st Semester'),
    ('COSC 131', 'Embedded System', 4, 'BSCS', 'DCS', 3, 0, 0, 0, '1st Semester'),
    ('COSC 200C','Undergraduate Thesis 3', 4, 'BSCS', 'DCS', 3, 0, 0, 0, '1st Semester'),
    ('ITEC 1',   'IT Fundamentals', 1, 'BSIT', 'DCS', 2, 1, 0, 0, '1st Semester'),
    ('CCTN 50',  'Basic Trouble Shooting and Maintenance', 2, 'BSIT', 'DCS', 2, 1, 0, 0, '1st Semester'),
    ('ITEC 50',  'Data Management System', 2, 'BSIT', 'DCS', 2, 1, 0, 0, '1st Semester'),
    ('ITEC 65',  'Advanced Database Management System', 3, 'BSIT', 'DCS', 2, 1, 0, 0, '1st Semester'),
    ('ITEC 70',  'Computer Graphics', 3, 'BSIT', 'DCS', 2, 1, 0, 0, '1st Semester'),
    ('DCEE 28',  'Methods of Research', 3, 'BSIT', 'DCS', 1, 0, 0, 0, '1st Semester'),
    ('ITEC 75',  'Technopreneur', 4, 'BSIT', 'DCS', 3, 0, 0, 0, '1st Semester'),
    ('ITEC 101', 'e-Commerce', 4, 'BSIT', 'DCS', 2, 1, 0, 0, '1st Semester'),
    ('ITEC 106', 'System Security', 4, 'BSIT', 'DCS', 2, 1, 0, 0, '1st Semester'),
    ('DCIT 111', 'Advanced Programming', 4, 'Both', 'DCS', 2, 1, 0, 0, '1st Semester'),
    # --- NEW DTE COURSES ---
    ('ENGL 1',   'Study and Thinking Skills in English', 1, 'Both', 'DTE', 2, 1, 0, 0, '1st Semester'),
    ('FILI I',   'Komunikasyon sa Akademikong Filipino', 1, 'Both', 'DTE', 3, 0, 0, 0, '1st Semester'),
    ('ENGL 2',   'Writing in the Discipline', 1, 'Both', 'DTE', 2, 1, 0, 0, '1st Semester'),
    ('FILI 2',   'Pagbasa at Pagsulat Tungo sa Pananaliksik', 1, 'Both', 'DTE', 3, 0, 0, 0, '1st Semester'),
    ('ENGL 6',   'Speech Communication', 2, 'Both', 'DTE', 2, 1, 0, 0, '1st Semester'),
    ('ENGL 7',   'Scientific Reporting and Thesis Writing', 3, 'Both', 'DTE', 2, 1, 0, 0, '1st Semester'),
    ('STAT 1',   'Elementary Statistics', 3, 'Both', 'DTE', 2, 1, 0, 0, '1st Semester'),
    ('MATH 2a',  'College Algebra', 1, 'Both', 'DTE', 3, 0, 0, 0, '1st Semester'),
    ('MATH 4',   'Trigonometry', 1, 'Both', 'DTE', 3, 0, 0, 0, '1st Semester'),
    ('MATH 22',  'Analytic Geometry w/ Calculus', 2, 'Both', 'DTE', 3, 0, 0, 0, '1st Semester'),
    # --- NEW DE COURSES ---
    ('MATH 10',  'Differential Calculus', 2, 'Both', 'DE', 3, 0, 0, 0, '1st Semester'),
    ('MATH 11',  'Integral Calculus', 2, 'Both', 'DE', 3, 0, 0, 0, '1st Semester'),
    # --- NEW DAS COURSES ---
    ('SOSC 2',   'General Psychology', 1, 'Both', 'DAS', 3, 0, 0, 0, '1st Semester'),
    ('PHED 1',   'Physical Fitness & Aerobics', 1, 'Both', 'DAS', 2, 0, 0, 0, '1st Semester'),
    ('PHED 2',   'Rhythmic Activities', 1, 'Both', 'DAS', 2, 0, 0, 0, '1st Semester'),
    ('PHYS 1a',  'Mechanics and Heat', 2, 'Both', 'DAS', 2, 1, 0, 0, '1st Semester'),
    ('SOSC 3',   'Phil. History, Geography and Institution', 2, 'Both', 'DAS', 3, 0, 0, 0, '1st Semester'),
    ('SOSC 6',   'Rizal\'s Life, Works and Writings', 2, 'Both', 'DAS', 3, 0, 0, 0, '1st Semester'),
    ('PHYS 2a',  'Wave, Magnetism, Sound and Light', 2, 'Both', 'DAS', 2, 1, 0, 0, '1st Semester'),
    ('PHED 4',   'Team Sports', 2, 'Both', 'DAS', 2, 0, 0, 0, '1st Semester'),
    ('ECON 3',   'General Economics with TAR', 3, 'Both', 'DAS', 3, 0, 0, 0, '1st Semester'),
    ('SOSC 5',   'Phil. Gov\'t. Politics and the Constitution', 3, 'Both', 'DAS', 3, 0, 0, 0, '1st Semester'),
    ('BTCH 1',   'Introduction to Biotechnology', 3, 'Both', 'DAS', 3, 0, 0, 0, '1st Semester'),
    ('LITT 1',   'Philippine Literature', 4, 'Both', 'DAS', 3, 0, 0, 0, '1st Semester'),
    ('HUMN 5',   'Art, Man and Society', 1, 'Both', 'DAS', 3, 0, 0, 0, '1st Semester'),
    ('HUMN 6',   'Social Philosophy', 4, 'Both', 'DAS', 3, 0, 0, 0, '1st Semester'),
    # --- NEW NSTP & DBA ---
    ('NSTP 1',   'NSTP 1', 1, 'Both', 'NSTP', 3, 0, 0, 0, '1st Semester'),
    ('NSTP 2',   'NSTP 2', 1, 'Both', 'NSTP', 3, 0, 0, 0, '1st Semester'),
    ('ACTG 1',   'Fundamentals of Accounting', 3, 'Both', 'DBA', 3, 0, 0, 0, '1st Semester'),

]

# ── SECTIONS ─────────────────────────────────────────────────────────────────
SECTION_NAMES = [
    "BSCS 101 - A", "BSCS 101 - B", "BSCS 101 - C",
    "BSCS 201 - A", "BSCS 201 - B", "BSCS 201 - C", "BSCS 201 - D",
    "BSCS 301 - A", "BSCS 301 - B", "BSCS 301 - C", "BSCS 301 - D", "BSCS 301 - E",
    "BSCS 401 - A", "BSCS 401 - B", "BSCS 401 - C",
    "BSINFOTECH 101 - A", "BSINFOTECH 101 - B", "BSINFOTECH 101 - C",
    "BSINFOTECH 201 - A", "BSINFOTECH 201 - B", "BSINFOTECH 201 - C",
    "BSINFOTECH 202 - A", "BSINFOTECH 202 - B", "BSINFOTECH 202 - C",
    "BSINFOTECH 301 - A", "BSINFOTECH 301 - B", "BSINFOTECH 301 - C", "BSINFOTECH 301 - D", "BSINFOTECH 301 - E",
    "BSINFOTECH 401 - A", "BSINFOTECH 401 - B", "BSINFOTECH 401 - C",
    "BSHM 201 - A", "BSHM 201 - B", "BSHM 201 - C", "BSHM 201 - D", "BSHM 201 - E", "BSHM 201 - F",
    "BTVTED 301 - A", "BTVTED 301 - B", "Grade 9", "Grade 10", "Grade 11"
]

# ── ASSIGNMENTS (From PDF) ───────────────────────────────────────────────────
ASSIGNMENTS = [
    ('IAN CHRISTOPHER ADAL', 'ITEC 111', ["BSINFOTECH 401 - A", "BSINFOTECH 401 - B", "BSINFOTECH 401 - C"]),
    ('IAN CHRISTOPHER ADAL', 'COSC 80',  ["BSCS 301 - A", "BSCS 301 - B", "BSCS 301 - C", "BSCS 301 - D", "BSCS 301 - E"]),
    ('KYLE ANGELO AMBIL', 'COSC 105', ["BSCS 401 - A", "BSCS 401 - B", "BSCS 401 - C"]),
    ('KYLE ANGELO AMBIL', 'DCIT 65',  ["BSCS 301 - A", "BSCS 301 - B"]),
    ('KYLE ANGELO AMBIL', 'ITEC 116', ["BSINFOTECH 401 - A", "BSINFOTECH 401 - B", "BSINFOTECH 401 - C"]),
    ('RENATO A. BAUTISTA', 'DCIT 50', ["BSCS 201 - A", "BSCS 201 - B", "BSCS 201 - C", "BSCS 201 - D", "BSINFOTECH 201 - A", "BSINFOTECH 201 - B", "BSINFOTECH 201 - C"]),
    ('RENATO A. BAUTISTA', 'ITEC 200B',["BSINFOTECH 401 - A", "BSINFOTECH 401 - B"]),
    ('ALYANA CABRIDO', 'COSC 75', ["BSCS 301 - A", "BSCS 301 - B", "BSCS 301 - C", "BSCS 301 - D", "BSCS 301 - E"]),
    ('ALYANA CABRIDO', 'ITEC 110', ["BSINFOTECH 401 - A", "BSINFOTECH 401 - B", "BSINFOTECH 401 - C"]),
    ('CEDRICK KENN CEDILLO', 'ITEC 80', ["BSCS 401 - A", "BSCS 401 - B", "BSCS 401 - C", "BSINFOTECH 301 - A", "BSINFOTECH 301 - B", "BSINFOTECH 301 - C", "BSINFOTECH 301 - D", "BSINFOTECH 301 - E"]),
    ('ANGELA C. CLARITO', 'DCIT 24', ["BSINFOTECH 201 - A", "BSINFOTECH 201 - B", "BSINFOTECH 201 - C", "BSCS 201 - A", "BSCS 201 - B", "BSCS 201 - C", "BSCS 201 - D"]),
    ('JANESSA MARIELLE S. CRUZ', 'COSC 101', ["BSCS 301 - A", "BSCS 301 - B", "BSCS 301 - C", "BSCS 301 - D", "BSCS 301 - E"]),
    ('JANESSA MARIELLE S. CRUZ', 'ITEC 55',  ["BSINFOTECH 202 - A", "BSINFOTECH 202 - B", "BSINFOTECH 202 - C"]),
    ('VHINCE LORENZ DELA REA', 'COSC 60', ["BSCS 201 - A", "BSCS 201 - B", "BSCS 201 - C", "BSCS 201 - D"]),
    ('VHINCE LORENZ DELA REA', 'ITEC 85', ["BSINFOTECH 301 - A", "BSINFOTECH 301 - B", "BSINFOTECH 301 - C", "BSINFOTECH 301 - D"]),
    ('CHRISTOPHER G. ESTONILO', 'DCIT 60', ["BSINFOTECH 301 - C"]),
    ('CHRISTOPHER G. ESTONILO', 'COSC 200A', ["BSCS 401 - A"]),
    ('ARIES M. GELERA', 'DCIT 60', ["BSINFOTECH 301 - B"]),
    ('ARIES M. GELERA', 'ITEC 200B', ["BSINFOTECH 401 - C"]),
    ('MARY ANN E. IGNACO', 'DCIT 60', ["BSINFOTECH 301 - D", "BSINFOTECH 301 - E"]),
    ('MARY ANN E. IGNACO', 'COSC 200A', ["BSCS 401 - C"]),
    ('GIRLIE P. MELITANTE', 'DCIT 21', ["BSCS 101 - B", "BSCS 101 - C"]),
    ('GIRLIE P. MELITANTE', 'INSY 50', ["BSCS 201 - A", "BSCS 201 - B", "BSCS 201 - C", "BSCS 201 - D"]),
    ('GIRLIE P. MELITANTE', 'BSHM 23', ["BSHM 201 - D", "BSHM 201 - E", "BSHM 201 - F"]),
    ('ALLEN JOHN C. MUYOT', 'DCIT 22', ["BSCS 101 - A", "BSCS 101 - B"]),
    ('KARLO JOSE E. NABABLIT', 'DCIT 60', ["BSINFOTECH 301 - A"]),
    ('KARLO JOSE E. NABABLIT', 'COSC 200A', ["BSCS 401 - B"]),
    ('YVANA JARDINE R. NOCON', 'INSY 55', ["BSINFOTECH 301 - A", "BSINFOTECH 301 - B", "BSINFOTECH 301 - C"]),
    ('ANA MARIE C. OBON', 'INSY 55', ["BSINFOTECH 301 - D", "BSINFOTECH 301 - E"]),
    ('ANA MARIE C. OBON', 'TLEP 08', ["BTVTED 301 - A", "BTVTED 301 - B"]),
    ('JOHN CHRISTIAN PERNALA', 'COSC 50', ["BSCS 101 - A", "BSCS 101 - B", "BSCS 101 - C"]),
    ('JOHN CHRISTIAN PERNALA', 'DCIT 65', ["BSINFOTECH 301 - A", "BSINFOTECH 301 - B", "BSINFOTECH 301 - C"]),
    ('JOHN CHRISTIAN PERNALA', 'DCIT 22', ["BSINFOTECH 101 - A", "BSINFOTECH 101 - B", "BSINFOTECH 101 - C"]),
    ('MARY GRACE P. SILVANO', 'DCIT 21', ["BSINFOTECH 101 - A", "BSINFOTECH 101 - B", "BSINFOTECH 101 - C", "BSCS 101 - A"]),
    ('MARY GRACE P. SILVANO', 'BSHM 23', ["BSHM 201 - A", "BSHM 201 - B", "BSHM 201 - C"]),
    ('AARON TINAMBACAN', 'DCIT 26', ["BSCS 301 - A", "BSCS 301 - B", "BSCS 301 - C", "BSCS 301 - D", "BSCS 301 - E", "BSINFOTECH 301 - A", "BSINFOTECH 301 - B", "BSINFOTECH 301 - C"]),
    ('LESTER D. VILLANUEVA', 'ITEC 90', ["BSINFOTECH 301 - A", "BSINFOTECH 301 - B", "BSINFOTECH 301 - C"]),
    ('DCS Teacher E (CS)', 'COSC 55', ["BSCS 201 - A", "BSCS 201 - B", "BSCS 201 - C", "BSCS 201 - D"]),
    ('DCS Teacher E (CS)', 'DCIT 22', ["BSCS 101 - C"]),
    ('DCS Teacher E (CS)', 'COSC 111', ["BSCS 401 - A", "BSCS 401 - B", "BSCS 401 - C"]),
    ('DCS Teacher F (CS)', 'DCIT 26', ["BSINFOTECH 301 - D", "BSINFOTECH 301 - E"]),
    ('DCS Teacher F (CS)', 'DCIT 65', ["BSCS 301 - C", "BSCS 301 - D", "BSCS 301 - E"]),
    ('DCS Teacher F (CS)', 'COSC 100', ["BSCS 401 - A", "BSCS 401 - B", "BSCS 401 - C"]),
    ('RACQUEL A. CATALAN', 'COSC 50', ["BSINFOTECH 101 - A", "BSINFOTECH 101 - B", "BSINFOTECH 101 - C"]),
    ('IVAN TOLEDO', 'ITEC 85', ["BSINFOTECH 301 - E"]),
    ('IVAN TOLEDO', 'COSC 85', ["BSCS 301 - C"]),
    ('KARL VINCENT M. ORDOÑA', 'ITEC 90', ["BSINFOTECH 301 - D", "BSINFOTECH 301 - E"]),
    ('DCS Teacher G (DON) - IT', 'COSC 85', ["BSCS 301 - D", "BSCS 301 - E"]),
    ('DCS Teacher H (JM) - IT', 'COSC 85', ["BSCS 301 - A", "BSCS 301 - B"]),
]


# ─── BEST-SEED SCHEDULE DATA (HC-clean, auto-generated) ─────────────────
SEED_SCHEDULES = [
    {'section': 'BSCS 101 - A', 'course': 'COSC 50', 'faculty': 'JOHN CHRISTIAN PERNALA', 'room': 'A1', 'day': 'Monday', 'start': 13, 'end': 16, 'type': 'Lecture'},
    {'section': 'BSCS 101 - A', 'course': 'CvSU 101', 'faculty': None, 'room': 'T.B.A.', 'day': 'Monday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSCS 101 - A', 'course': 'DCIT 21', 'faculty': 'MARY GRACE P. SILVANO', 'room': 'B1', 'day': 'Friday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSCS 101 - A', 'course': 'DCIT 21', 'faculty': 'MARY GRACE P. SILVANO', 'room': 'A1', 'day': 'Monday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSCS 101 - A', 'course': 'DCIT 22', 'faculty': 'ALLEN JOHN C. MUYOT', 'room': 'T.B.A.', 'day': 'Monday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSCS 101 - A', 'course': 'DCIT 22', 'faculty': 'ALLEN JOHN C. MUYOT', 'room': 'B1', 'day': 'Wednesday', 'start': 7, 'end': 13, 'type': 'Laboratory'},
    {'section': 'BSCS 101 - B', 'course': 'COSC 50', 'faculty': 'JOHN CHRISTIAN PERNALA', 'room': 'A1', 'day': 'Monday', 'start': 16, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSCS 101 - B', 'course': 'CvSU 101', 'faculty': None, 'room': 'T.B.A.', 'day': 'Tuesday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSCS 101 - B', 'course': 'DCIT 21', 'faculty': 'GIRLIE P. MELITANTE', 'room': 'A1', 'day': 'Monday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSCS 101 - B', 'course': 'DCIT 21', 'faculty': 'GIRLIE P. MELITANTE', 'room': 'B1', 'day': 'Monday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSCS 101 - B', 'course': 'DCIT 22', 'faculty': 'ALLEN JOHN C. MUYOT', 'room': 'B1', 'day': 'Friday', 'start': 13, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSCS 101 - B', 'course': 'DCIT 22', 'faculty': 'ALLEN JOHN C. MUYOT', 'room': 'T.B.A.', 'day': 'Monday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSCS 101 - C', 'course': 'COSC 50', 'faculty': 'JOHN CHRISTIAN PERNALA', 'room': 'A1', 'day': 'Tuesday', 'start': 16, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSCS 101 - C', 'course': 'CvSU 101', 'faculty': None, 'room': 'T.B.A.', 'day': 'Monday', 'start': 15, 'end': 17, 'type': 'Lecture'},
    {'section': 'BSCS 101 - C', 'course': 'DCIT 21', 'faculty': 'GIRLIE P. MELITANTE', 'room': 'B1', 'day': 'Saturday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSCS 101 - C', 'course': 'DCIT 21', 'faculty': 'GIRLIE P. MELITANTE', 'room': 'A1', 'day': 'Tuesday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSCS 101 - C', 'course': 'DCIT 22', 'faculty': 'DCS Teacher E (CS)', 'room': 'T.B.A.', 'day': 'Monday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSCS 101 - C', 'course': 'DCIT 22', 'faculty': 'DCS Teacher E (CS)', 'room': 'B1', 'day': 'Thursday', 'start': 7, 'end': 13, 'type': 'Laboratory'},
    {'section': 'BSCS 201 - A', 'course': 'COSC 55', 'faculty': 'DCS Teacher E (CS)', 'room': 'A1', 'day': 'Friday', 'start': 7, 'end': 10, 'type': 'Lecture'},
    {'section': 'BSCS 201 - A', 'course': 'COSC 60', 'faculty': 'VHINCE LORENZ DELA REA', 'room': 'A2', 'day': 'Monday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSCS 201 - A', 'course': 'COSC 60', 'faculty': 'VHINCE LORENZ DELA REA', 'room': 'B1', 'day': 'Wednesday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSCS 201 - A', 'course': 'DCIT 24', 'faculty': 'ANGELA C. CLARITO', 'room': 'A2', 'day': 'Monday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSCS 201 - A', 'course': 'DCIT 24', 'faculty': 'ANGELA C. CLARITO', 'room': 'B1', 'day': 'Wednesday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSCS 201 - A', 'course': 'DCIT 50', 'faculty': 'RENATO A. BAUTISTA', 'room': 'A2', 'day': 'Monday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSCS 201 - A', 'course': 'DCIT 50', 'faculty': 'RENATO A. BAUTISTA', 'room': 'B1', 'day': 'Monday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSCS 201 - A', 'course': 'INSY 50', 'faculty': 'GIRLIE P. MELITANTE', 'room': 'A1', 'day': 'Wednesday', 'start': 7, 'end': 10, 'type': 'Lecture'},
    {'section': 'BSCS 201 - B', 'course': 'COSC 55', 'faculty': 'DCS Teacher E (CS)', 'room': 'A1', 'day': 'Friday', 'start': 16, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSCS 201 - B', 'course': 'COSC 60', 'faculty': 'VHINCE LORENZ DELA REA', 'room': 'A3', 'day': 'Monday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSCS 201 - B', 'course': 'COSC 60', 'faculty': 'VHINCE LORENZ DELA REA', 'room': 'B2', 'day': 'Wednesday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSCS 201 - B', 'course': 'DCIT 24', 'faculty': 'ANGELA C. CLARITO', 'room': 'A2', 'day': 'Monday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSCS 201 - B', 'course': 'DCIT 24', 'faculty': 'ANGELA C. CLARITO', 'room': 'B2', 'day': 'Wednesday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSCS 201 - B', 'course': 'DCIT 50', 'faculty': 'RENATO A. BAUTISTA', 'room': 'A3', 'day': 'Monday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSCS 201 - B', 'course': 'DCIT 50', 'faculty': 'RENATO A. BAUTISTA', 'room': 'B2', 'day': 'Monday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSCS 201 - B', 'course': 'INSY 50', 'faculty': 'GIRLIE P. MELITANTE', 'room': 'A1', 'day': 'Wednesday', 'start': 13, 'end': 16, 'type': 'Lecture'},
    {'section': 'BSCS 201 - C', 'course': 'COSC 55', 'faculty': 'DCS Teacher E (CS)', 'room': 'A4', 'day': 'Monday', 'start': 7, 'end': 10, 'type': 'Lecture'},
    {'section': 'BSCS 201 - C', 'course': 'COSC 60', 'faculty': 'VHINCE LORENZ DELA REA', 'room': 'A3', 'day': 'Monday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSCS 201 - C', 'course': 'COSC 60', 'faculty': 'VHINCE LORENZ DELA REA', 'room': 'B2', 'day': 'Wednesday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSCS 201 - C', 'course': 'DCIT 24', 'faculty': 'ANGELA C. CLARITO', 'room': 'A2', 'day': 'Monday', 'start': 15, 'end': 17, 'type': 'Lecture'},
    {'section': 'BSCS 201 - C', 'course': 'DCIT 24', 'faculty': 'ANGELA C. CLARITO', 'room': 'B3', 'day': 'Wednesday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSCS 201 - C', 'course': 'DCIT 50', 'faculty': 'RENATO A. BAUTISTA', 'room': 'B2', 'day': 'Friday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSCS 201 - C', 'course': 'DCIT 50', 'faculty': 'RENATO A. BAUTISTA', 'room': 'A1', 'day': 'Wednesday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSCS 201 - C', 'course': 'INSY 50', 'faculty': 'GIRLIE P. MELITANTE', 'room': 'A1', 'day': 'Friday', 'start': 13, 'end': 16, 'type': 'Lecture'},
    {'section': 'BSCS 201 - D', 'course': 'COSC 55', 'faculty': 'DCS Teacher E (CS)', 'room': 'A1', 'day': 'Saturday', 'start': 16, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSCS 201 - D', 'course': 'COSC 60', 'faculty': 'VHINCE LORENZ DELA REA', 'room': 'A1', 'day': 'Thursday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSCS 201 - D', 'course': 'COSC 60', 'faculty': 'VHINCE LORENZ DELA REA', 'room': 'B1', 'day': 'Thursday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSCS 201 - D', 'course': 'DCIT 24', 'faculty': 'ANGELA C. CLARITO', 'room': 'A1', 'day': 'Tuesday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSCS 201 - D', 'course': 'DCIT 24', 'faculty': 'ANGELA C. CLARITO', 'room': 'B1', 'day': 'Tuesday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSCS 201 - D', 'course': 'DCIT 50', 'faculty': 'RENATO A. BAUTISTA', 'room': 'A1', 'day': 'Tuesday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSCS 201 - D', 'course': 'DCIT 50', 'faculty': 'RENATO A. BAUTISTA', 'room': 'B1', 'day': 'Tuesday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSCS 201 - D', 'course': 'INSY 50', 'faculty': 'GIRLIE P. MELITANTE', 'room': 'A1', 'day': 'Saturday', 'start': 13, 'end': 16, 'type': 'Lecture'},
    {'section': 'BSCS 301 - A', 'course': 'COSC 101', 'faculty': 'JANESSA MARIELLE S. CRUZ', 'room': 'B2', 'day': 'Friday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - A', 'course': 'COSC 101', 'faculty': 'JANESSA MARIELLE S. CRUZ', 'room': 'A2', 'day': 'Wednesday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSCS 301 - A', 'course': 'COSC 75', 'faculty': 'ALYANA CABRIDO', 'room': 'B2', 'day': 'Friday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - A', 'course': 'COSC 75', 'faculty': 'ALYANA CABRIDO', 'room': 'A2', 'day': 'Wednesday', 'start': 15, 'end': 17, 'type': 'Lecture'},
    {'section': 'BSCS 301 - A', 'course': 'COSC 80', 'faculty': 'IAN CHRISTOPHER ADAL', 'room': 'A3', 'day': 'Monday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSCS 301 - A', 'course': 'COSC 80', 'faculty': 'IAN CHRISTOPHER ADAL', 'room': 'B2', 'day': 'Monday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - A', 'course': 'COSC 85', 'faculty': 'DCS Teacher H (JM) - IT', 'room': 'T.B.A.', 'day': 'Tuesday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - A', 'course': 'COSC 85', 'faculty': 'DCS Teacher H (JM) - IT', 'room': 'A2', 'day': 'Wednesday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSCS 301 - A', 'course': 'DCIT 26', 'faculty': 'AARON TINAMBACAN', 'room': 'B3', 'day': 'Friday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - A', 'course': 'DCIT 26', 'faculty': 'AARON TINAMBACAN', 'room': 'A2', 'day': 'Wednesday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSCS 301 - A', 'course': 'DCIT 65', 'faculty': 'KYLE ANGELO AMBIL', 'room': 'A5', 'day': 'Monday', 'start': 7, 'end': 10, 'type': 'Lecture'},
    {'section': 'BSCS 301 - B', 'course': 'COSC 101', 'faculty': 'JANESSA MARIELLE S. CRUZ', 'room': 'B3', 'day': 'Friday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - B', 'course': 'COSC 101', 'faculty': 'JANESSA MARIELLE S. CRUZ', 'room': 'A3', 'day': 'Wednesday', 'start': 15, 'end': 17, 'type': 'Lecture'},
    {'section': 'BSCS 301 - B', 'course': 'COSC 75', 'faculty': 'ALYANA CABRIDO', 'room': 'A4', 'day': 'Monday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSCS 301 - B', 'course': 'COSC 75', 'faculty': 'ALYANA CABRIDO', 'room': 'B4', 'day': 'Wednesday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - B', 'course': 'COSC 80', 'faculty': 'IAN CHRISTOPHER ADAL', 'room': 'B1', 'day': 'Monday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - B', 'course': 'COSC 80', 'faculty': 'IAN CHRISTOPHER ADAL', 'room': 'A2', 'day': 'Wednesday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSCS 301 - B', 'course': 'COSC 85', 'faculty': 'DCS Teacher H (JM) - IT', 'room': 'B4', 'day': 'Friday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - B', 'course': 'COSC 85', 'faculty': 'DCS Teacher H (JM) - IT', 'room': 'A3', 'day': 'Wednesday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSCS 301 - B', 'course': 'DCIT 26', 'faculty': 'AARON TINAMBACAN', 'room': 'A2', 'day': 'Friday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSCS 301 - B', 'course': 'DCIT 26', 'faculty': 'AARON TINAMBACAN', 'room': 'T.B.A.', 'day': 'Tuesday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - B', 'course': 'DCIT 65', 'faculty': 'KYLE ANGELO AMBIL', 'room': 'A4', 'day': 'Monday', 'start': 13, 'end': 16, 'type': 'Lecture'},
    {'section': 'BSCS 301 - C', 'course': 'COSC 101', 'faculty': 'JANESSA MARIELLE S. CRUZ', 'room': 'B2', 'day': 'Thursday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - C', 'course': 'COSC 101', 'faculty': 'JANESSA MARIELLE S. CRUZ', 'room': 'A2', 'day': 'Tuesday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSCS 301 - C', 'course': 'COSC 75', 'faculty': 'ALYANA CABRIDO', 'room': 'B2', 'day': 'Thursday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - C', 'course': 'COSC 75', 'faculty': 'ALYANA CABRIDO', 'room': 'A2', 'day': 'Tuesday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSCS 301 - C', 'course': 'COSC 80', 'faculty': 'IAN CHRISTOPHER ADAL', 'room': 'B1', 'day': 'Thursday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - C', 'course': 'COSC 80', 'faculty': 'IAN CHRISTOPHER ADAL', 'room': 'A2', 'day': 'Tuesday', 'start': 15, 'end': 17, 'type': 'Lecture'},
    {'section': 'BSCS 301 - C', 'course': 'COSC 85', 'faculty': 'IVAN TOLEDO', 'room': 'B1', 'day': 'Saturday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - C', 'course': 'COSC 85', 'faculty': 'IVAN TOLEDO', 'room': 'A2', 'day': 'Tuesday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSCS 301 - C', 'course': 'DCIT 26', 'faculty': 'AARON TINAMBACAN', 'room': 'B1', 'day': 'Saturday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - C', 'course': 'DCIT 26', 'faculty': 'AARON TINAMBACAN', 'room': 'A2', 'day': 'Tuesday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSCS 301 - C', 'course': 'DCIT 65', 'faculty': 'DCS Teacher F (CS)', 'room': 'A1', 'day': 'Saturday', 'start': 7, 'end': 10, 'type': 'Lecture'},
    {'section': 'BSCS 301 - D', 'course': 'COSC 101', 'faculty': 'JANESSA MARIELLE S. CRUZ', 'room': 'B5', 'day': 'Friday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - D', 'course': 'COSC 101', 'faculty': 'JANESSA MARIELLE S. CRUZ', 'room': 'A5', 'day': 'Monday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSCS 301 - D', 'course': 'COSC 75', 'faculty': 'ALYANA CABRIDO', 'room': 'B3', 'day': 'Friday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - D', 'course': 'COSC 75', 'faculty': 'ALYANA CABRIDO', 'room': 'A3', 'day': 'Monday', 'start': 15, 'end': 17, 'type': 'Lecture'},
    {'section': 'BSCS 301 - D', 'course': 'COSC 80', 'faculty': 'IAN CHRISTOPHER ADAL', 'room': 'A3', 'day': 'Wednesday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSCS 301 - D', 'course': 'COSC 80', 'faculty': 'IAN CHRISTOPHER ADAL', 'room': 'B3', 'day': 'Wednesday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - D', 'course': 'COSC 85', 'faculty': 'DCS Teacher G (DON) - IT', 'room': 'B2', 'day': 'Monday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - D', 'course': 'COSC 85', 'faculty': 'DCS Teacher G (DON) - IT', 'room': 'A3', 'day': 'Wednesday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSCS 301 - D', 'course': 'DCIT 26', 'faculty': 'AARON TINAMBACAN', 'room': 'A5', 'day': 'Monday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSCS 301 - D', 'course': 'DCIT 26', 'faculty': 'AARON TINAMBACAN', 'room': 'B3', 'day': 'Wednesday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - D', 'course': 'DCIT 65', 'faculty': 'DCS Teacher F (CS)', 'room': 'A2', 'day': 'Friday', 'start': 13, 'end': 16, 'type': 'Lecture'},
    {'section': 'BSCS 301 - E', 'course': 'COSC 101', 'faculty': 'JANESSA MARIELLE S. CRUZ', 'room': 'B2', 'day': 'Saturday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - E', 'course': 'COSC 101', 'faculty': 'JANESSA MARIELLE S. CRUZ', 'room': 'A3', 'day': 'Tuesday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSCS 301 - E', 'course': 'COSC 75', 'faculty': 'ALYANA CABRIDO', 'room': 'B2', 'day': 'Thursday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - E', 'course': 'COSC 75', 'faculty': 'ALYANA CABRIDO', 'room': 'A3', 'day': 'Tuesday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSCS 301 - E', 'course': 'COSC 80', 'faculty': 'IAN CHRISTOPHER ADAL', 'room': 'B3', 'day': 'Thursday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - E', 'course': 'COSC 80', 'faculty': 'IAN CHRISTOPHER ADAL', 'room': 'A3', 'day': 'Tuesday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSCS 301 - E', 'course': 'COSC 85', 'faculty': 'DCS Teacher G (DON) - IT', 'room': 'B2', 'day': 'Saturday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - E', 'course': 'COSC 85', 'faculty': 'DCS Teacher G (DON) - IT', 'room': 'A3', 'day': 'Tuesday', 'start': 15, 'end': 17, 'type': 'Lecture'},
    {'section': 'BSCS 301 - E', 'course': 'DCIT 26', 'faculty': 'AARON TINAMBACAN', 'room': 'B3', 'day': 'Thursday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSCS 301 - E', 'course': 'DCIT 26', 'faculty': 'AARON TINAMBACAN', 'room': 'A3', 'day': 'Tuesday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSCS 301 - E', 'course': 'DCIT 65', 'faculty': 'DCS Teacher F (CS)', 'room': 'A2', 'day': 'Saturday', 'start': 16, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSCS 401 - A', 'course': 'COSC 100', 'faculty': 'DCS Teacher F (CS)', 'room': 'A1', 'day': 'Thursday', 'start': 13, 'end': 16, 'type': 'Lecture'},
    {'section': 'BSCS 401 - A', 'course': 'COSC 105', 'faculty': 'KYLE ANGELO AMBIL', 'room': 'A4', 'day': 'Tuesday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSCS 401 - A', 'course': 'COSC 105', 'faculty': 'KYLE ANGELO AMBIL', 'room': 'B2', 'day': 'Tuesday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSCS 401 - A', 'course': 'COSC 111', 'faculty': 'DCS Teacher E (CS)', 'room': 'A2', 'day': 'Saturday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSCS 401 - A', 'course': 'COSC 111', 'faculty': 'DCS Teacher E (CS)', 'room': 'B3', 'day': 'Saturday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSCS 401 - A', 'course': 'COSC 200A', 'faculty': 'CHRISTOPHER G. ESTONILO', 'room': 'A1', 'day': 'Thursday', 'start': 16, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSCS 401 - A', 'course': 'ITEC 80', 'faculty': 'CEDRICK KENN CEDILLO', 'room': 'A4', 'day': 'Tuesday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSCS 401 - A', 'course': 'ITEC 80', 'faculty': 'CEDRICK KENN CEDILLO', 'room': 'B2', 'day': 'Tuesday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSCS 401 - B', 'course': 'COSC 100', 'faculty': 'DCS Teacher F (CS)', 'room': 'A2', 'day': 'Friday', 'start': 7, 'end': 10, 'type': 'Lecture'},
    {'section': 'BSCS 401 - B', 'course': 'COSC 105', 'faculty': 'KYLE ANGELO AMBIL', 'room': 'B3', 'day': 'Monday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSCS 401 - B', 'course': 'COSC 105', 'faculty': 'KYLE ANGELO AMBIL', 'room': 'A3', 'day': 'Wednesday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSCS 401 - B', 'course': 'COSC 111', 'faculty': 'DCS Teacher E (CS)', 'room': 'B4', 'day': 'Friday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSCS 401 - B', 'course': 'COSC 111', 'faculty': 'DCS Teacher E (CS)', 'room': 'A4', 'day': 'Wednesday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSCS 401 - B', 'course': 'COSC 200A', 'faculty': 'KARLO JOSE E. NABABLIT', 'room': 'A4', 'day': 'Wednesday', 'start': 13, 'end': 16, 'type': 'Lecture'},
    {'section': 'BSCS 401 - B', 'course': 'ITEC 80', 'faculty': 'CEDRICK KENN CEDILLO', 'room': 'B3', 'day': 'Monday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSCS 401 - B', 'course': 'ITEC 80', 'faculty': 'CEDRICK KENN CEDILLO', 'room': 'A4', 'day': 'Wednesday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSCS 401 - C', 'course': 'COSC 100', 'faculty': 'DCS Teacher F (CS)', 'room': 'A2', 'day': 'Saturday', 'start': 13, 'end': 16, 'type': 'Lecture'},
    {'section': 'BSCS 401 - C', 'course': 'COSC 105', 'faculty': 'KYLE ANGELO AMBIL', 'room': 'B3', 'day': 'Thursday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSCS 401 - C', 'course': 'COSC 105', 'faculty': 'KYLE ANGELO AMBIL', 'room': 'A4', 'day': 'Tuesday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSCS 401 - C', 'course': 'COSC 111', 'faculty': 'DCS Teacher E (CS)', 'room': 'B4', 'day': 'Thursday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSCS 401 - C', 'course': 'COSC 111', 'faculty': 'DCS Teacher E (CS)', 'room': 'A4', 'day': 'Tuesday', 'start': 15, 'end': 17, 'type': 'Lecture'},
    {'section': 'BSCS 401 - C', 'course': 'COSC 200A', 'faculty': 'MARY ANN E. IGNACO', 'room': 'A5', 'day': 'Tuesday', 'start': 7, 'end': 10, 'type': 'Lecture'},
    {'section': 'BSCS 401 - C', 'course': 'ITEC 80', 'faculty': 'CEDRICK KENN CEDILLO', 'room': 'B4', 'day': 'Thursday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSCS 401 - C', 'course': 'ITEC 80', 'faculty': 'CEDRICK KENN CEDILLO', 'room': 'A4', 'day': 'Tuesday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSHM 201 - A', 'course': 'BSHM 23', 'faculty': 'MARY GRACE P. SILVANO', 'room': 'HM-A1', 'day': 'Monday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSHM 201 - A', 'course': 'BSHM 23', 'faculty': 'MARY GRACE P. SILVANO', 'room': 'HM-Lab', 'day': 'Wednesday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSHM 201 - B', 'course': 'BSHM 23', 'faculty': 'MARY GRACE P. SILVANO', 'room': 'HM-A1', 'day': 'Tuesday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSHM 201 - B', 'course': 'BSHM 23', 'faculty': 'MARY GRACE P. SILVANO', 'room': 'HM-Lab', 'day': 'Tuesday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSHM 201 - C', 'course': 'BSHM 23', 'faculty': 'MARY GRACE P. SILVANO', 'room': 'HM-A1', 'day': 'Monday', 'start': 15, 'end': 17, 'type': 'Lecture'},
    {'section': 'BSHM 201 - C', 'course': 'BSHM 23', 'faculty': 'MARY GRACE P. SILVANO', 'room': 'HM-Lab', 'day': 'Wednesday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSHM 201 - D', 'course': 'BSHM 23', 'faculty': 'GIRLIE P. MELITANTE', 'room': 'HM-Lab', 'day': 'Thursday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSHM 201 - D', 'course': 'BSHM 23', 'faculty': 'GIRLIE P. MELITANTE', 'room': 'HM-A1', 'day': 'Tuesday', 'start': 15, 'end': 17, 'type': 'Lecture'},
    {'section': 'BSHM 201 - E', 'course': 'BSHM 23', 'faculty': 'GIRLIE P. MELITANTE', 'room': 'HM-Lab', 'day': 'Thursday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSHM 201 - E', 'course': 'BSHM 23', 'faculty': 'GIRLIE P. MELITANTE', 'room': 'HM-A1', 'day': 'Tuesday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSHM 201 - F', 'course': 'BSHM 23', 'faculty': 'GIRLIE P. MELITANTE', 'room': 'HM-Lab', 'day': 'Thursday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSHM 201 - F', 'course': 'BSHM 23', 'faculty': 'GIRLIE P. MELITANTE', 'room': 'HM-A1', 'day': 'Tuesday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 101 - A', 'course': 'COSC 50', 'faculty': 'RACQUEL A. CATALAN', 'room': 'A3', 'day': 'Friday', 'start': 13, 'end': 16, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 101 - A', 'course': 'CvSU 101', 'faculty': None, 'room': 'T.B.A.', 'day': 'Monday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 101 - A', 'course': 'DCIT 21', 'faculty': 'MARY GRACE P. SILVANO', 'room': 'B4', 'day': 'Friday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 101 - A', 'course': 'DCIT 21', 'faculty': 'MARY GRACE P. SILVANO', 'room': 'A5', 'day': 'Wednesday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 101 - A', 'course': 'DCIT 22', 'faculty': 'JOHN CHRISTIAN PERNALA', 'room': 'T.B.A.', 'day': 'Monday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 101 - A', 'course': 'DCIT 22', 'faculty': 'JOHN CHRISTIAN PERNALA', 'room': 'B4', 'day': 'Wednesday', 'start': 13, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 101 - B', 'course': 'COSC 50', 'faculty': 'RACQUEL A. CATALAN', 'room': 'A5', 'day': 'Tuesday', 'start': 16, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 101 - B', 'course': 'CvSU 101', 'faculty': None, 'room': 'T.B.A.', 'day': 'Monday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 101 - B', 'course': 'DCIT 21', 'faculty': 'MARY GRACE P. SILVANO', 'room': 'A1', 'day': 'Thursday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 101 - B', 'course': 'DCIT 21', 'faculty': 'MARY GRACE P. SILVANO', 'room': 'B4', 'day': 'Thursday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 101 - B', 'course': 'DCIT 22', 'faculty': 'JOHN CHRISTIAN PERNALA', 'room': 'T.B.A.', 'day': 'Monday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 101 - B', 'course': 'DCIT 22', 'faculty': 'JOHN CHRISTIAN PERNALA', 'room': 'B1', 'day': 'Tuesday', 'start': 7, 'end': 13, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 101 - C', 'course': 'COSC 50', 'faculty': 'RACQUEL A. CATALAN', 'room': 'A4', 'day': 'Wednesday', 'start': 16, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 101 - C', 'course': 'CvSU 101', 'faculty': None, 'room': 'T.B.A.', 'day': 'Monday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 101 - C', 'course': 'DCIT 21', 'faculty': 'MARY GRACE P. SILVANO', 'room': 'T.B.A.', 'day': 'Tuesday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 101 - C', 'course': 'DCIT 21', 'faculty': 'MARY GRACE P. SILVANO', 'room': 'A5', 'day': 'Wednesday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 101 - C', 'course': 'DCIT 22', 'faculty': 'JOHN CHRISTIAN PERNALA', 'room': 'B5', 'day': 'Friday', 'start': 13, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 101 - C', 'course': 'DCIT 22', 'faculty': 'JOHN CHRISTIAN PERNALA', 'room': 'T.B.A.', 'day': 'Tuesday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 201 - A', 'course': 'DCIT 24', 'faculty': 'ANGELA C. CLARITO', 'room': 'A3', 'day': 'Friday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 201 - A', 'course': 'DCIT 24', 'faculty': 'ANGELA C. CLARITO', 'room': 'B3', 'day': 'Monday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 201 - A', 'course': 'DCIT 50', 'faculty': 'RENATO A. BAUTISTA', 'room': 'B6', 'day': 'Friday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 201 - A', 'course': 'DCIT 50', 'faculty': 'RENATO A. BAUTISTA', 'room': 'A5', 'day': 'Wednesday', 'start': 15, 'end': 17, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 201 - B', 'course': 'DCIT 24', 'faculty': 'ANGELA C. CLARITO', 'room': 'B5', 'day': 'Thursday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 201 - B', 'course': 'DCIT 24', 'faculty': 'ANGELA C. CLARITO', 'room': 'A5', 'day': 'Tuesday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 201 - B', 'course': 'DCIT 50', 'faculty': 'RENATO A. BAUTISTA', 'room': 'A2', 'day': 'Thursday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 201 - B', 'course': 'DCIT 50', 'faculty': 'RENATO A. BAUTISTA', 'room': 'B3', 'day': 'Tuesday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 201 - C', 'course': 'DCIT 24', 'faculty': 'ANGELA C. CLARITO', 'room': 'B2', 'day': 'Saturday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 201 - C', 'course': 'DCIT 24', 'faculty': 'ANGELA C. CLARITO', 'room': 'A2', 'day': 'Thursday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 201 - C', 'course': 'DCIT 50', 'faculty': 'RENATO A. BAUTISTA', 'room': 'A2', 'day': 'Thursday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 201 - C', 'course': 'DCIT 50', 'faculty': 'RENATO A. BAUTISTA', 'room': 'B6', 'day': 'Thursday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 202 - A', 'course': 'ITEC 55', 'faculty': 'JANESSA MARIELLE S. CRUZ', 'room': 'A3', 'day': 'Thursday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 202 - A', 'course': 'ITEC 55', 'faculty': 'JANESSA MARIELLE S. CRUZ', 'room': 'B2', 'day': 'Tuesday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 202 - B', 'course': 'ITEC 55', 'faculty': 'JANESSA MARIELLE S. CRUZ', 'room': 'B3', 'day': 'Saturday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 202 - B', 'course': 'ITEC 55', 'faculty': 'JANESSA MARIELLE S. CRUZ', 'room': 'A3', 'day': 'Thursday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 202 - C', 'course': 'ITEC 55', 'faculty': 'JANESSA MARIELLE S. CRUZ', 'room': 'B3', 'day': 'Saturday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 202 - C', 'course': 'ITEC 55', 'faculty': 'JANESSA MARIELLE S. CRUZ', 'room': 'A3', 'day': 'Thursday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - A', 'course': 'DCIT 26', 'faculty': 'AARON TINAMBACAN', 'room': 'A3', 'day': 'Saturday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - A', 'course': 'DCIT 26', 'faculty': 'AARON TINAMBACAN', 'room': 'B4', 'day': 'Tuesday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - A', 'course': 'DCIT 60', 'faculty': 'KARLO JOSE E. NABABLIT', 'room': 'A4', 'day': 'Thursday', 'start': 7, 'end': 10, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - A', 'course': 'DCIT 65', 'faculty': 'JOHN CHRISTIAN PERNALA', 'room': 'A3', 'day': 'Saturday', 'start': 16, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - A', 'course': 'INSY 55', 'faculty': 'YVANA JARDINE R. NOCON', 'room': 'A2', 'day': 'Thursday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - A', 'course': 'INSY 55', 'faculty': 'YVANA JARDINE R. NOCON', 'room': 'B3', 'day': 'Tuesday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - A', 'course': 'ITEC 80', 'faculty': 'CEDRICK KENN CEDILLO', 'room': 'B4', 'day': 'Saturday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - A', 'course': 'ITEC 80', 'faculty': 'CEDRICK KENN CEDILLO', 'room': 'A2', 'day': 'Thursday', 'start': 15, 'end': 17, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - A', 'course': 'ITEC 85', 'faculty': 'VHINCE LORENZ DELA REA', 'room': 'A4', 'day': 'Thursday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - A', 'course': 'ITEC 85', 'faculty': 'VHINCE LORENZ DELA REA', 'room': 'B3', 'day': 'Tuesday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - A', 'course': 'ITEC 90', 'faculty': 'LESTER D. VILLANUEVA', 'room': 'T.B.A.', 'day': 'Monday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - A', 'course': 'ITEC 90', 'faculty': 'LESTER D. VILLANUEVA', 'room': 'T.B.A.', 'day': 'Monday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - B', 'course': 'DCIT 26', 'faculty': 'AARON TINAMBACAN', 'room': 'T.B.A.', 'day': 'Monday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - B', 'course': 'DCIT 26', 'faculty': 'AARON TINAMBACAN', 'room': 'T.B.A.', 'day': 'Monday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - B', 'course': 'DCIT 60', 'faculty': 'ARIES M. GELERA', 'room': 'A5', 'day': 'Thursday', 'start': 13, 'end': 16, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - B', 'course': 'DCIT 65', 'faculty': 'JOHN CHRISTIAN PERNALA', 'room': 'A3', 'day': 'Saturday', 'start': 7, 'end': 10, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - B', 'course': 'INSY 55', 'faculty': 'YVANA JARDINE R. NOCON', 'room': 'A5', 'day': 'Thursday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - B', 'course': 'INSY 55', 'faculty': 'YVANA JARDINE R. NOCON', 'room': 'B4', 'day': 'Tuesday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - B', 'course': 'ITEC 80', 'faculty': 'CEDRICK KENN CEDILLO', 'room': 'B4', 'day': 'Saturday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - B', 'course': 'ITEC 80', 'faculty': 'CEDRICK KENN CEDILLO', 'room': 'A3', 'day': 'Thursday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - B', 'course': 'ITEC 85', 'faculty': 'VHINCE LORENZ DELA REA', 'room': 'A5', 'day': 'Thursday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - B', 'course': 'ITEC 85', 'faculty': 'VHINCE LORENZ DELA REA', 'room': 'B4', 'day': 'Tuesday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - B', 'course': 'ITEC 90', 'faculty': 'LESTER D. VILLANUEVA', 'room': 'A4', 'day': 'Saturday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - B', 'course': 'ITEC 90', 'faculty': 'LESTER D. VILLANUEVA', 'room': 'B5', 'day': 'Tuesday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - C', 'course': 'DCIT 26', 'faculty': 'AARON TINAMBACAN', 'room': 'A4', 'day': 'Saturday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - C', 'course': 'DCIT 26', 'faculty': 'AARON TINAMBACAN', 'room': 'B5', 'day': 'Thursday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - C', 'course': 'DCIT 60', 'faculty': 'CHRISTOPHER G. ESTONILO', 'room': 'A4', 'day': 'Saturday', 'start': 16, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - C', 'course': 'DCIT 65', 'faculty': 'JOHN CHRISTIAN PERNALA', 'room': 'T.B.A.', 'day': 'Wednesday', 'start': 7, 'end': 10, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - C', 'course': 'INSY 55', 'faculty': 'YVANA JARDINE R. NOCON', 'room': 'T.B.A.', 'day': 'Monday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - C', 'course': 'INSY 55', 'faculty': 'YVANA JARDINE R. NOCON', 'room': 'A3', 'day': 'Thursday', 'start': 15, 'end': 17, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - C', 'course': 'ITEC 80', 'faculty': 'CEDRICK KENN CEDILLO', 'room': 'T.B.A.', 'day': 'Monday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - C', 'course': 'ITEC 80', 'faculty': 'CEDRICK KENN CEDILLO', 'room': 'A5', 'day': 'Saturday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - C', 'course': 'ITEC 85', 'faculty': 'VHINCE LORENZ DELA REA', 'room': 'A2', 'day': 'Saturday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - C', 'course': 'ITEC 85', 'faculty': 'VHINCE LORENZ DELA REA', 'room': 'B6', 'day': 'Tuesday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - C', 'course': 'ITEC 90', 'faculty': 'LESTER D. VILLANUEVA', 'room': 'A4', 'day': 'Thursday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - C', 'course': 'ITEC 90', 'faculty': 'LESTER D. VILLANUEVA', 'room': 'B5', 'day': 'Tuesday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - D', 'course': 'DCIT 26', 'faculty': 'DCS Teacher F (CS)', 'room': 'T.B.A.', 'day': 'Tuesday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - D', 'course': 'DCIT 26', 'faculty': 'DCS Teacher F (CS)', 'room': 'B5', 'day': 'Wednesday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - D', 'course': 'DCIT 60', 'faculty': 'MARY ANN E. IGNACO', 'room': 'A3', 'day': 'Friday', 'start': 16, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - D', 'course': 'INSY 55', 'faculty': 'ANA MARIE C. OBON', 'room': 'B4', 'day': 'Monday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - D', 'course': 'INSY 55', 'faculty': 'ANA MARIE C. OBON', 'room': 'A5', 'day': 'Wednesday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - D', 'course': 'ITEC 80', 'faculty': 'CEDRICK KENN CEDILLO', 'room': 'B4', 'day': 'Monday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - D', 'course': 'ITEC 80', 'faculty': 'CEDRICK KENN CEDILLO', 'room': 'A5', 'day': 'Wednesday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - D', 'course': 'ITEC 85', 'faculty': 'VHINCE LORENZ DELA REA', 'room': 'A3', 'day': 'Friday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - D', 'course': 'ITEC 85', 'faculty': 'VHINCE LORENZ DELA REA', 'room': 'B4', 'day': 'Monday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - D', 'course': 'ITEC 90', 'faculty': 'KARL VINCENT M. ORDOÑA', 'room': 'A4', 'day': 'Friday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - D', 'course': 'ITEC 90', 'faculty': 'KARL VINCENT M. ORDOÑA', 'room': 'T.B.A.', 'day': 'Tuesday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - E', 'course': 'DCIT 26', 'faculty': 'DCS Teacher F (CS)', 'room': 'T.B.A.', 'day': 'Monday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - E', 'course': 'DCIT 26', 'faculty': 'DCS Teacher F (CS)', 'room': 'B6', 'day': 'Thursday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - E', 'course': 'DCIT 60', 'faculty': 'MARY ANN E. IGNACO', 'room': 'A5', 'day': 'Thursday', 'start': 16, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - E', 'course': 'INSY 55', 'faculty': 'ANA MARIE C. OBON', 'room': 'A4', 'day': 'Saturday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - E', 'course': 'INSY 55', 'faculty': 'ANA MARIE C. OBON', 'room': 'B5', 'day': 'Tuesday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - E', 'course': 'ITEC 80', 'faculty': 'CEDRICK KENN CEDILLO', 'room': 'T.B.A.', 'day': 'Tuesday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - E', 'course': 'ITEC 80', 'faculty': 'CEDRICK KENN CEDILLO', 'room': 'T.B.A.', 'day': 'Wednesday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - E', 'course': 'ITEC 85', 'faculty': 'IVAN TOLEDO', 'room': 'A5', 'day': 'Saturday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - E', 'course': 'ITEC 85', 'faculty': 'IVAN TOLEDO', 'room': 'B5', 'day': 'Thursday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 301 - E', 'course': 'ITEC 90', 'faculty': 'KARL VINCENT M. ORDOÑA', 'room': 'A5', 'day': 'Saturday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 301 - E', 'course': 'ITEC 90', 'faculty': 'KARL VINCENT M. ORDOÑA', 'room': 'B4', 'day': 'Saturday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 401 - A', 'course': 'ITEC 110', 'faculty': 'ALYANA CABRIDO', 'room': 'A4', 'day': 'Friday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 401 - A', 'course': 'ITEC 110', 'faculty': 'ALYANA CABRIDO', 'room': 'B5', 'day': 'Monday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 401 - A', 'course': 'ITEC 111', 'faculty': 'IAN CHRISTOPHER ADAL', 'room': 'A4', 'day': 'Friday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 401 - A', 'course': 'ITEC 111', 'faculty': 'IAN CHRISTOPHER ADAL', 'room': 'B6', 'day': 'Friday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 401 - A', 'course': 'ITEC 116', 'faculty': 'KYLE ANGELO AMBIL', 'room': 'A4', 'day': 'Friday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 401 - A', 'course': 'ITEC 116', 'faculty': 'KYLE ANGELO AMBIL', 'room': 'B5', 'day': 'Wednesday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 401 - A', 'course': 'ITEC 200B', 'faculty': 'RENATO A. BAUTISTA', 'room': 'T.B.A.', 'day': 'Wednesday', 'start': 7, 'end': 10, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 401 - B', 'course': 'ITEC 110', 'faculty': 'ALYANA CABRIDO', 'room': 'A5', 'day': 'Friday', 'start': 7, 'end': 9, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 401 - B', 'course': 'ITEC 110', 'faculty': 'ALYANA CABRIDO', 'room': 'T.B.A.', 'day': 'Tuesday', 'start': 13, 'end': 16, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 401 - B', 'course': 'ITEC 111', 'faculty': 'IAN CHRISTOPHER ADAL', 'room': 'A5', 'day': 'Friday', 'start': 9, 'end': 11, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 401 - B', 'course': 'ITEC 111', 'faculty': 'IAN CHRISTOPHER ADAL', 'room': 'T.B.A.', 'day': 'Thursday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 401 - B', 'course': 'ITEC 116', 'faculty': 'KYLE ANGELO AMBIL', 'room': 'A4', 'day': 'Friday', 'start': 15, 'end': 17, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 401 - B', 'course': 'ITEC 116', 'faculty': 'KYLE ANGELO AMBIL', 'room': 'B6', 'day': 'Wednesday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 401 - B', 'course': 'ITEC 200B', 'faculty': 'RENATO A. BAUTISTA', 'room': 'T.B.A.', 'day': 'Saturday', 'start': 13, 'end': 16, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 401 - C', 'course': 'ITEC 110', 'faculty': 'ALYANA CABRIDO', 'room': 'T.B.A.', 'day': 'Monday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 401 - C', 'course': 'ITEC 110', 'faculty': 'ALYANA CABRIDO', 'room': 'T.B.A.', 'day': 'Thursday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 401 - C', 'course': 'ITEC 111', 'faculty': 'IAN CHRISTOPHER ADAL', 'room': 'A5', 'day': 'Friday', 'start': 17, 'end': 19, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 401 - C', 'course': 'ITEC 111', 'faculty': 'IAN CHRISTOPHER ADAL', 'room': 'T.B.A.', 'day': 'Saturday', 'start': 16, 'end': 19, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 401 - C', 'course': 'ITEC 116', 'faculty': 'KYLE ANGELO AMBIL', 'room': 'A5', 'day': 'Friday', 'start': 13, 'end': 15, 'type': 'Lecture'},
    {'section': 'BSINFOTECH 401 - C', 'course': 'ITEC 116', 'faculty': 'KYLE ANGELO AMBIL', 'room': 'T.B.A.', 'day': 'Thursday', 'start': 7, 'end': 10, 'type': 'Laboratory'},
    {'section': 'BSINFOTECH 401 - C', 'course': 'ITEC 200B', 'faculty': 'ARIES M. GELERA', 'room': 'T.B.A.', 'day': 'Monday', 'start': 7, 'end': 10, 'type': 'Lecture'},
    {'section': 'BTVTED 301 - A', 'course': 'TLEP 08', 'faculty': 'ANA MARIE C. OBON', 'room': 'T.B.A.', 'day': 'Monday', 'start': 13, 'end': 16, 'type': 'Lecture'},
    {'section': 'BTVTED 301 - B', 'course': 'TLEP 08', 'faculty': 'ANA MARIE C. OBON', 'room': 'T.B.A.', 'day': 'Monday', 'start': 16, 'end': 19, 'type': 'Lecture'},
]
# Total: 258 sessions
def seed_database():
    with app.app_context():
        # Preservation skipped — best-seed schedule handles initial data

        print(f"Seeder {SEEDER_LEVEL}: Cleaning DB...")
        db.create_all()
        db.session.execute(section_courses.delete())
        db.session.execute(faculty_courses.delete())
        FacultyAssignment.query.delete(); PreAssignment.query.delete()
        ScheduledClass.query.delete(); Course.query.delete()
        Room.query.delete(); Section.query.delete(); Faculty.query.delete()
        Constraint.query.delete(); SystemSettings.query.delete()
        CodePrefixRule.query.delete(); Department.query.delete()
        Student.query.delete(); User.query.delete()
        db.session.commit()

        dept_map = {}
        for d in DEPARTMENTS:
            obj = Department(name=d['name'], code=d['code'])
            db.session.add(obj)
            dept_map[d['code']] = obj
        db.session.commit()

        for u in USERS:
            db.session.add(User(username=u['user'], role=u['role'], department=u['dept'], password_hash=generate_password_hash(u['pass'])))
        
        for r in ROOMS:
            db.session.add(Room(room_name=r['name'], building=r['building'], capabilities=r['capabilities'], status=r['status'], capacity=r['capacity'], functional_computers=r['func_comp'], room_departments=r.get('room_depts', '')))
        
        fac_map = {}
        for f in FACULTY:
            obj = Faculty(employee_id=f['eid'], full_name=f['name'], department=f['dept'], employment_status='Full-time' if 'Teacher' not in f['name'] else 'Part-time', max_weekly_hours=f['max'])
            db.session.add(obj)
            fac_map[f['name']] = obj
        db.session.commit()

        course_map = {}
        for c in COURSES:
            dept_name = Department.query.filter_by(code=c[4]).first().name if Department.query.filter_by(code=c[4]).first() else 'Department of Computer Studies'
            obj = Course(course_code=c[0], course_name=c[1], year_level=c[2], program=c[3], department=dept_name, synchronous_lec_hours=c[5], synchronous_lab_hours=c[6], asynchronous_lec_hours=c[7], asynchronous_lab_hours=c[8], semester_offered=c[9])
            db.session.add(obj)
            course_map[c[0]] = obj
        db.session.commit()

        section_map = {}
        for name in SECTION_NAMES:
            yr = 1
            if '101' in name: yr = 1
            elif '201' in name or '202' in name: yr = 2
            elif '301' in name: yr = 3
            elif '401' in name: yr = 4
            elif 'Grade 9' in name: yr = 1
            elif 'Grade 10' in name: yr = 2
            elif 'Grade 11' in name: yr = 3
            obj = Section(section_name=name, year_level=yr, number_of_students=40)
            db.session.add(obj)
            section_map[name] = obj
        db.session.commit()

        print("  Injecting Faculty Assignments...")
        for fac_name, course_code, sections in ASSIGNMENTS:
            fac = fac_map.get(fac_name)
            course = course_map.get(course_code)
            if fac and course:
                if course not in fac.courses: fac.courses.append(course)
                for sec_name in sections:
                    sec = section_map.get(sec_name)
                    if sec:
                        if course not in sec.courses: sec.courses.append(course)
                        db.session.add(FacultyAssignment(faculty_id=fac.id, course_id=course.id, section_id=sec.id))
        
        cvsu_course = course_map.get('CvSU 101')
        if cvsu_course:
            for sname, sec in section_map.items():
                if ('BSCS 101' in sname or 'BSINFOTECH 101' in sname): sec.courses.append(cvsu_course)

        k12_map = {'Grade 9': 'TLE 3', 'Grade 10': 'TLE 4', 'Grade 11': 'ICT 11'}
        for sname, ccode in k12_map.items():
            sec = section_map.get(sname); course = course_map.get(ccode)
            if sec and course: sec.courses.append(course)

        db.session.add(SystemSettings(start_hour=7, end_hour=20, allowed_days="Monday,Tuesday,Wednesday,Thursday,Friday,Saturday", campus_name="CCAT Campus", address="Rosario, Cavite", section_school_name="CAVITE STATE UNIVERSITY", fac_dept_label="DEPARTMENT OF COMPUTER STUDIES", sem_ay_value="1st Semester / 2026-2027"))
        
        prefixes = [('COSC', 'DCS'), ('DCIT', 'DCS'), ('ITEC', 'DCS'), ('INSY', 'DCS')]
        for p, dcode in prefixes: db.session.add(CodePrefixRule(code=p, is_prefix=True, department=dept_map[dcode].name))

        CONSTRAINTS = [
            # Standard HCs
            {'code': 'LOCKED_SCHEDULES',           'cat': 'Administrative', 'type': 'HC',  'weight': 1,   'name': '(HC-01) Locked Schedules', 'desc': 'Manually plotted schedules are immovable.'},
            {'code': 'MINOR_SUBJECT_GAP',          'cat': 'Administrative', 'type': 'HC',  'weight': 1,   'name': '(HC-02) Space for Minor Subjects', 'desc': 'Ensure free slots for unscheduled minor courses.'},
            {'code': 'GLOBAL_DAY_RESTRICTION',     'cat': 'Administrative', 'type': 'HC',  'weight': 1,   'name': '(HC-03) Global Day Restriction', 'desc': 'No classes on Sundays or non-academic days.'},
            {'code': 'LEC_LAB_SEQUENCE',           'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-04) Lec-Lab Sequence', 'desc': 'Lecture must be scheduled before Laboratory.'},
            {'code': 'STRICT_ALLOC_LEC',           'cat': 'Course',         'type': 'SC1', 'weight': 50,  'name': '(HC-05) Strict Lecture Allocation', 'desc': 'Every section must have a lecture for required courses.'},
            {'code': 'STRICT_ALLOC_LAB',           'cat': 'Course',         'type': 'SC1', 'weight': 50,  'name': '(HC-06) Strict Laboratory Allocation', 'desc': 'Every section must have a lab if required.'},
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
            {'code': 'VIRTUAL_ROOM_USAGE',         'cat': 'Room',           'type': 'SC1', 'weight': 100, 'name': '(SC-I-01) Virtual Room Penalty', 'desc': 'Avoid TBA rooms.'},
            {'code': 'EARLY_START_ENFORCEMENT',    'cat': 'Room',           'type': 'SC1', 'weight': 9,   'name': '(SC-I-02) Early Start Enforcement', 'desc': 'Fill morning slots first.'},
            {'code': 'EVENING_AVOIDANCE',          'cat': 'Time',           'type': 'SC1', 'weight': 9,   'name': '(SC-I-03) Evening Class Avoidance', 'desc': 'Avoid classes starting at 7:00 PM or later.'},
            {'code': 'LEC_LAB_WEEKLY_DIST',        'cat': 'Course',         'type': 'SC1', 'weight': 8,   'name': '(SC-I-08) Lec-Lab Weekly Dist.', 'desc': 'Lec early, Lab late.'},
            {'code': 'LEC_LAB_PROXIMITY',          'cat': 'Course',         'type': 'SC1', 'weight': 7,   'name': '(SC-I-09) Lec-Lab Proximity', 'desc': 'Lec/Lab near each other.'},
            {'code': 'LUNCH_BREAK',                'cat': 'Time',           'type': 'SC2', 'weight': 2,   'name': '(SC-II-04) Lunch Break', 'desc': '12-1 PM break.'},
        ]
        for c in CONSTRAINTS:
            db.session.add(Constraint(
                logic_code=c['code'],
                category=c['cat'],
                constraint_type=c['type'],
                weight=c['weight'],
                name=c['name'],
                description=c['desc']
            ))

        db.session.commit()



        # ─── INJECT SEED SCHEDULES ───────────────────────────────────────────
        print("  Injecting best-seed schedule (%d sessions)..." % len(SEED_SCHEDULES))
        seed_count = 0
        for ss in SEED_SCHEDULES:
            c_obj = course_map.get(ss['course'])
            s_obj = section_map.get(ss['section'])
            f_obj = Faculty.query.filter_by(full_name=ss['faculty']).first() if ss['faculty'] else None
            r_obj = Room.query.filter_by(room_name=ss['room']).first() if ss['room'] else None
            if c_obj and s_obj:
                db.session.add(ScheduledClass(
                    course_id    = c_obj.id,
                    section_id   = s_obj.id,
                    faculty_id   = f_obj.id if f_obj else None,
                    room_id      = r_obj.id if r_obj else None,
                    day          = ss['day'],
                    start_time   = '%02d:00' % ss['start'],
                    end_time     = '%02d:00' % ss['end'],
                    semester     = '1st Semester',
                    session_type = ss['type'],
                    source       = 'seeder',
                    is_draft     = False,
                ))
                seed_count += 1
        db.session.commit()
        print("  Seed schedule injected: %d/%d sessions." % (seed_count, len(SEED_SCHEDULES)))

        print(f"Seeder {SEEDER_LEVEL} complete! Dataset initialized for 2026-2027 with A1-A5 & B1-B6.")

if __name__ == '__main__':
    seed_database()
