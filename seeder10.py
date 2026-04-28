# seeder10.py — Benchmark Level 10: PRODUCTION-READY DATASET
# This is the most comprehensive seeder, focusing on DCS (BSCS/BSIT) 
# and official department codes (DE for Engineering).

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import (app, db, User, Course, Room, Section, Faculty, Constraint,
                 SystemSettings, CodePrefixRule, ScheduledClass,
                 FacultyAssignment, PreAssignment,
                 section_courses, faculty_courses)
from werkzeug.security import generate_password_hash
from collections import defaultdict

SEEDER_LEVEL   = 10
DESCRIPTION    = "Strict BSCS/BSIT focused dataset with 64+ sections and 60+ faculty."

# ── ROOMS (25 total) ───────────────────────────────────────────────────────────
ROOMS = [
    # ICT Building A — Lecture rooms (DCS Specific)
    {'name': 'A101', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 45, 'func_comp': 0, 'room_depts': 'Department of Computer Studies'},
    {'name': 'A102', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 45, 'func_comp': 0, 'room_depts': 'Department of Computer Studies'},
    {'name': 'A103', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 45, 'func_comp': 0, 'room_depts': 'Department of Computer Studies'},
    {'name': 'A201', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 50, 'func_comp': 0, 'room_depts': 'Department of Computer Studies'},
    {'name': 'A202', 'building': 'ICT Building A', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 50, 'func_comp': 0, 'room_depts': 'Department of Computer Studies'},
    
    # ICT Building B — Computer Labs (DCS Specific)
    {'name': 'CL1', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 35, 'func_comp': 35, 'room_depts': 'Department of Computer Studies'},
    {'name': 'CL2', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 35, 'func_comp': 35, 'room_depts': 'Department of Computer Studies'},
    {'name': 'CL3', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 35, 'func_comp': 30, 'room_depts': 'Department of Computer Studies'},
    {'name': 'CL4', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 35, 'func_comp': 35, 'room_depts': 'Department of Computer Studies'},
    {'name': 'CL5', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 35, 'func_comp': 35, 'room_depts': 'Department of Computer Studies'},
    {'name': 'CL6', 'building': 'ICT Building B', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 35, 'func_comp': 35, 'room_depts': 'Department of Computer Studies'},
    
    # Engineering Building (DE Specific)
    {'name': 'E101', 'building': 'Engineering Building', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 40, 'func_comp': 0, 'room_depts': 'Department of Engineering'},
    {'name': 'E102', 'building': 'Engineering Building', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 40, 'func_comp': 0, 'room_depts': 'Department of Engineering'},
    {'name': 'E201', 'building': 'Engineering Building', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 40, 'func_comp': 0, 'room_depts': 'Department of Engineering'},
    {'name': 'ELAB1', 'building': 'Engineering Building', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 30, 'func_comp': 25, 'room_depts': 'Department of Engineering'},

    # Arts & Sciences Building (DAS Specific)
    {'name': 'AS1', 'building': 'AS Building', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 45, 'func_comp': 0, 'room_depts': 'Department of Arts and Sciences'},
    {'name': 'AS2', 'building': 'AS Building', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 45, 'func_comp': 0, 'room_depts': 'Department of Arts and Sciences'},
    {'name': 'AS3', 'building': 'AS Building', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 45, 'func_comp': 0, 'room_depts': 'Department of Arts and Sciences'},
    {'name': 'AS4', 'building': 'AS Building', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 45, 'func_comp': 0, 'room_depts': 'Department of Arts and Sciences'},
    
    # Large Hall / Field
    {'name': 'University Field', 'building': 'Grounds', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 999, 'func_comp': 0},
    {'name': 'Gymnasium',        'building': 'Grounds', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 500, 'func_comp': 0},
    {'name': 'T.B.A.',           'building': 'Virtual', 'capabilities': 'Lecture,Computer Lab', 'status': 'Available', 'capacity': 999, 'func_comp': 0},
]

# ── FACULTY (62 total, DCS Heavy) ─────────────────────────────────────────────
FACULTY = [
    # Department of Computer Studies (DCS) - 30 Faculty
    {'eid': 'DCS-001', 'name': 'ARIES M. GELERA',       'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'M', 'rank': 'Assistant Professor II', 'attainment': 'MSIT'},
    {'eid': 'DCS-002', 'name': 'DANILO C. ALCANTARA',   'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'M', 'rank': 'Associate Professor I', 'attainment': 'PhD CS'},
    {'eid': 'DCS-003', 'name': 'MARIA TERESA R. PEREZ', 'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'F', 'rank': 'Assistant Professor III', 'attainment': 'MSIT'},
    {'eid': 'DCS-004', 'name': 'JOSEPHINE A. SANTOS',   'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'F', 'rank': 'Instructor I', 'attainment': 'MSIT'},
    {'eid': 'DCS-005', 'name': 'REYNALDO M. REYES',     'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'M', 'rank': 'Assistant Professor I', 'attainment': 'MIT'},
    {'eid': 'DCS-006', 'name': 'ALAN TURING',           'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'M', 'rank': 'Instructor III', 'attainment': 'PhD Math'},
    {'eid': 'DCS-007', 'name': 'ADA LOVELACE',          'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'F', 'rank': 'Instructor II', 'attainment': 'MSCS'},
    {'eid': 'DCS-008', 'name': 'GRACE HOPPER',          'dept': 'Department of Computer Studies', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'F', 'rank': 'Instructor I', 'attainment': 'BSIT'},
    {'eid': 'DCS-009', 'name': 'LINUS TORVALDS',        'dept': 'Department of Computer Studies', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor I', 'attainment': 'BSCS'},
    {'eid': 'DCS-010', 'name': 'GUIDO VAN ROSSUM',      'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'M', 'rank': 'Assistant Professor I', 'attainment': 'MIT'},
    {'eid': 'DCS-011', 'name': 'KATHERINE JOHNSON',     'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'F', 'rank': 'Instructor I', 'attainment': 'MS Math'},
    {'eid': 'DCS-012', 'name': 'TIM BERNERS-LEE',       'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'M', 'rank': 'Instructor II', 'attainment': 'MSCS'},
    {'eid': 'DCS-013', 'name': 'BJARNE STROUSTRUP',     'dept': 'Department of Computer Studies', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor I', 'attainment': 'PhD CS'},
    {'eid': 'DCS-014', 'name': 'DONALD KNUTH',          'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'M', 'rank': 'Associate Professor II', 'attainment': 'PhD CS'},
    {'eid': 'DCS-015', 'name': 'MARGARET HAMILTON',     'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'F', 'rank': 'Assistant Professor III', 'attainment': 'MSCS'},
    {'eid': 'DCS-016', 'name': 'DENNIS RITCHIE',        'dept': 'Department of Computer Studies', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor I', 'attainment': 'MSIT'},
    {'eid': 'DCS-017', 'name': 'KEN THOMPSON',          'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'M', 'rank': 'Instructor I', 'attainment': 'BSCS'},
    {'eid': 'DCS-018', 'name': 'RICHARD STALLMAN',      'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'M', 'rank': 'Instructor III', 'attainment': 'MSCS'},
    {'eid': 'DCS-019', 'name': 'JOHN VON NEUMANN',      'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'M', 'rank': 'Professor I', 'attainment': 'PhD Math'},
    {'eid': 'DCS-020', 'name': 'PACIANO RIZAL',         'dept': 'Department of Computer Studies', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor I', 'attainment': 'BSIT'},
    {'eid': 'DCS-021', 'name': 'JUAN LUNA',             'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'M', 'rank': 'Assistant Professor I', 'attainment': 'MIT'},
    {'eid': 'DCS-022', 'name': 'MARCELO H. DEL PILAR',  'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'M', 'rank': 'Instructor II', 'attainment': 'MSIT'},
    {'eid': 'DCS-023', 'name': 'GREGORIA DE JESUS',     'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'F', 'rank': 'Instructor I', 'attainment': 'BSCS'},
    {'eid': 'DCS-024', 'name': 'EMILIO JACINTO',        'dept': 'Department of Computer Studies', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor I', 'attainment': 'BSIT'},
    {'eid': 'DCS-025', 'name': 'ANDRES BONIFACIO',      'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'M', 'rank': 'Assistant Professor I', 'attainment': 'MIT'},
    {'eid': 'DCS-026', 'name': 'MELCHORA AQUINO',       'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'F', 'rank': 'Instructor II', 'attainment': 'MSCS'},
    {'eid': 'DCS-027', 'name': 'GABRIELA SILANG',       'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'F', 'rank': 'Instructor I', 'attainment': 'BSIT'},
    {'eid': 'DCS-028', 'name': 'LAPU-LAPU',             'dept': 'Department of Computer Studies', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor I', 'attainment': 'BSCS'},
    {'eid': 'DCS-029', 'name': 'ANTONIO LUNA',          'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'M', 'rank': 'Assistant Professor II', 'attainment': 'MIT'},
    {'eid': 'DCS-030', 'name': 'TEODORA ALONSO',        'dept': 'Department of Computer Studies', 'status': 'Full-time', 'max_weekly': 21, 'sex': 'F', 'rank': 'Instructor III', 'attainment': 'MSIT'},

    # Department of Arts and Sciences (DAS) - 10 Faculty
    {'eid': 'DAS-001', 'name': 'JOSE RIZAL',            'dept': 'Department of Arts and Sciences', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Associate Professor III', 'attainment': 'PhD Lit'},
    {'eid': 'DAS-002', 'name': 'EMILIO AGUINALDO',      'dept': 'Department of Arts and Sciences', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Assistant Professor I', 'attainment': 'MA History'},
    {'eid': 'DAS-003', 'name': 'APOLINARIO MABINI',     'dept': 'Department of Arts and Sciences', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor II', 'attainment': 'LLB'},
    {'eid': 'DAS-004', 'name': 'SARA DUTERTE',          'dept': 'Department of Arts and Sciences', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'F', 'rank': 'Assistant Professor I', 'attainment': 'MA SocSci'},
    {'eid': 'DAS-005', 'name': 'LOREN LEGARDA',         'dept': 'Department of Arts and Sciences', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'F', 'rank': 'Instructor III', 'attainment': 'MA Comm'},
    {'eid': 'DAS-006', 'name': 'MANNY PACQUIAO',        'dept': 'Department of Arts and Sciences', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor I', 'attainment': 'BS PE'},
    {'eid': 'DAS-007', 'name': 'MIRIAM SANTIAGO',       'dept': 'Department of Arts and Sciences', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'F', 'rank': 'Professor V', 'attainment': 'SJD'},
    {'eid': 'DAS-008', 'name': 'BENIGNO AQUINO',        'dept': 'Department of Arts and Sciences', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Instructor I', 'attainment': 'BA Philo'},
    {'eid': 'DAS-009', 'name': 'CORAZON AQUINO',        'dept': 'Department of Arts and Sciences', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'F', 'rank': 'Instructor II', 'attainment': 'BA French'},
    {'eid': 'DAS-010', 'name': 'RAMON MAGSAYSAY',       'dept': 'Department of Arts and Sciences', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor I', 'attainment': 'BA PolSci'},

    # Department of Teachers Education (DTE) - 10 Faculty
    {'eid': 'DTE-001', 'name': 'LEONOR BRIONES',        'dept': 'Department of Teachers Education', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'F', 'rank': 'Professor I', 'attainment': 'PhD Ed'},
    {'eid': 'DTE-002', 'name': 'ARMIN LUISTRO',         'dept': 'Department of Teachers Education', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Associate Professor II', 'attainment': 'MA Ed'},
    {'eid': 'DTE-003', 'name': 'EDGARDO ANGARA',        'dept': 'Department of Teachers Education', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor I', 'attainment': 'MA English'},
    {'eid': 'DTE-004', 'name': 'VICENTE SOTTO',         'dept': 'Department of Teachers Education', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Instructor III', 'attainment': 'MA Filipino'},
    {'eid': 'DTE-005', 'name': 'GLORIA ARROYO',         'dept': 'Department of Teachers Education', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'F', 'rank': 'Professor III', 'attainment': 'PhD Econ'},
    {'eid': 'DTE-006', 'name': 'PIA CAYETANO',          'dept': 'Department of Teachers Education', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'F', 'rank': 'Instructor II', 'attainment': 'MA Math'},
    {'eid': 'DTE-007', 'name': 'ROBIN PADILLA',         'dept': 'Department of Teachers Education', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Instructor I', 'attainment': 'BA Educ'},
    {'eid': 'DTE-008', 'name': 'BONG REVILLA',          'dept': 'Department of Teachers Education', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Instructor I', 'attainment': 'BA Educ'},
    {'eid': 'DTE-009', 'name': 'CYNTHIA VILLAR',        'dept': 'Department of Teachers Education', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'F', 'rank': 'Instructor II', 'attainment': 'MA Ed'},
    {'eid': 'DTE-010', 'name': 'GRACE POE',             'dept': 'Department of Teachers Education', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'F', 'rank': 'Instructor I', 'attainment': 'MA Ed'},

    # Department of Engineering (DE) - 10 Faculty
    {'eid': 'DE-001', 'name': 'LAPU-LAPU II',           'dept': 'Department of Engineering', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Assistant Professor I', 'attainment': 'MS Civil'},
    {'eid': 'DE-002', 'name': 'ANTONIO LUNA II',        'dept': 'Department of Engineering', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Assistant Professor II', 'attainment': 'MS Electrical'},
    {'eid': 'DE-003', 'name': 'GREGORIO DEL PILAR',     'dept': 'Department of Engineering', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor I', 'attainment': 'BS ME'},
    {'eid': 'DE-004', 'name': 'ARTEMIO RICARTE',        'dept': 'Department of Engineering', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Instructor III', 'attainment': 'MS Civil'},
    {'eid': 'DE-005', 'name': 'MIGUEL MALVAR',          'dept': 'Department of Engineering', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Instructor II', 'attainment': 'BS EE'},
    {'eid': 'DE-006', 'name': 'FELIPE AGONCILLO',       'dept': 'Department of Engineering', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor I', 'attainment': 'MS Mech'},
    {'eid': 'DE-007', 'name': 'MARCELA AGONCILLO',      'dept': 'Department of Engineering', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'F', 'rank': 'Instructor II', 'attainment': 'MS Civil'},
    {'eid': 'DE-008', 'name': 'GALICANO APACIBLE',      'dept': 'Department of Engineering', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Instructor III', 'attainment': 'BS EE'},
    {'eid': 'DE-009', 'name': 'VITO BELARMINO',         'dept': 'Department of Engineering', 'status': 'Full-time', 'max_weekly': 17, 'sex': 'M', 'rank': 'Instructor I', 'attainment': 'MS Civil'},
    {'eid': 'DE-010', 'name': 'PANTALEON GARCIA',       'dept': 'Department of Engineering', 'status': 'Part-time', 'max_weekly': 35, 'sex': 'M', 'rank': 'Instructor I', 'attainment': 'BS ME'},

    # TBA Entries
    {'eid': 'TBA-01', 'name': 'T.B.A. 1', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999},
    {'eid': 'TBA-02', 'name': 'T.B.A. 2', 'dept': 'Unassigned', 'status': 'Part-time', 'max_weekly': 999},
]

# ── COURSES (BSCS and BSIT ONLY) ─────────────────────────────────────────────
# Format: (code, name, year, program, dept, sync_lec, sync_lab, async_lec, async_lab, sem)
COURSES = [
    # ── Shared GE courses (program='Both') ──
    ('MATH101', 'Mathematics in the Modern World',    1, 'Both', 'Department of Teachers Education', 3, 0, 0, 0, '1st Semester'),
    ('ENGL101', 'Purposive Communication',             1, 'Both', 'Department of Teachers Education', 3, 0, 0, 0, '1st Semester'),
    ('FILI101', 'Kontekstwalisadong Komunikasyon',     1, 'Both', 'Department of Teachers Education', 3, 0, 0, 0, '1st Semester'),
    ('PHED101', 'Physical Education 1',                1, 'Both', 'Department of Arts and Sciences',  2, 0, 0, 0, '1st Semester'),
    ('SOSC101', 'Understanding the Self',              1, 'Both', 'Department of Arts and Sciences',  3, 0, 0, 0, '1st Semester'),
    ('NSTP101', 'NSTP 1',                              1, 'Both', 'NSTP Department',                  3, 0, 0, 0, '1st Semester'),
    
    # ── DCS Shared ICT Courses ──
    ('DCIT101', 'Introduction to Computing',           1, 'Both', 'Department of Computer Studies',   2, 3, 0, 0, '1st Semester'),
    ('DCIT102', 'Computer Programming 1',              1, 'Both', 'Department of Computer Studies',   2, 3, 0, 0, '1st Semester'),
    ('DCIT201', 'Data Structures and Algorithms',      2, 'Both', 'Department of Computer Studies',   2, 3, 0, 0, '1st Semester'),
    ('DCIT202', 'Information Management',              2, 'Both', 'Department of Computer Studies',   2, 3, 0, 0, '1st Semester'),
    ('DCIT301', 'Applications Development',            3, 'Both', 'Department of Computer Studies',   2, 3, 0, 0, '1st Semester'),
    ('DCIT302', 'Social and Professional Issues',      3, 'Both', 'Department of Computer Studies',   3, 0, 0, 0, '1st Semester'),
    
    # ── BSCoS Specific ──
    ('COSC101', 'CS Fundamentals',                     1, 'BSCoS', 'Department of Computer Studies', 3, 0, 0, 0, '1st Semester'),
    ('COSC201', 'Discrete Mathematics for CS',         2, 'BSCoS', 'Department of Computer Studies', 3, 0, 0, 0, '1st Semester'),
    ('COSC202', 'Object Oriented Programming',         2, 'BSCoS', 'Department of Computer Studies', 2, 3, 0, 0, '1st Semester'),
    ('COSC301', 'Operating Systems',                   3, 'BSCoS', 'Department of Computer Studies', 2, 3, 0, 0, '1st Semester'),
    ('COSC302', 'Architecture and Organization',       3, 'BSCoS', 'Department of Computer Studies', 2, 3, 0, 0, '1st Semester'),
    ('COSC401', 'CS Thesis Writing 1',                 4, 'BSCoS', 'Department of Computer Studies', 3, 0, 0, 0, '1st Semester'),
    ('COSC402', 'CS Practicum (162 Hours)',            4, 'BSCoS', 'Department of Computer Studies', 0, 0, 3, 0, '1st Semester'),
    
    # ── BSInfoTech Specific ──
    ('ITEC101', 'IT Fundamentals',                     1, 'BSInfoTech', 'Department of Computer Studies', 3, 0, 0, 0, '1st Semester'),
    ('ITEC201', 'Networking 1',                        2, 'BSInfoTech', 'Department of Computer Studies', 2, 3, 0, 0, '1st Semester'),
    ('ITEC202', 'Web Systems and Technologies',        2, 'BSInfoTech', 'Department of Computer Studies', 2, 3, 0, 0, '1st Semester'),
    ('ITEC301', 'Systems Integration',                 3, 'BSInfoTech', 'Department of Computer Studies', 2, 3, 0, 0, '1st Semester'),
    ('ITEC302', 'Information Assurance and Security',  3, 'BSInfoTech', 'Department of Computer Studies', 3, 0, 0, 0, '1st Semester'),
    ('ITEC401', 'IT Capstone Project 1',               4, 'BSInfoTech', 'Department of Computer Studies', 3, 0, 0, 0, '1st Semester'),
    ('ITEC402', 'IT Practicum (486 Hours)',            4, 'BSInfoTech', 'Department of Computer Studies', 0, 0, 6, 0, '1st Semester'),
    
    # ── Engineering/Math Exceptions (DE) ──
    ('MATH10', 'Advanced Engineering Mathematics',    3, 'BSCoS', 'Department of Engineering',       3, 0, 0, 0, '1st Semester'),
    ('MATH11', 'Differential Equations',               2, 'BSCoS', 'Department of Engineering',       3, 0, 0, 0, '1st Semester'),
]

# ── CURRICULUM MAPS ───────────────────────────────────────────────────────────
_cs_yr1 = ['MATH101', 'ENGL101', 'FILI101', 'PHED101', 'SOSC101', 'NSTP101', 'DCIT101', 'DCIT102', 'COSC101']
_cs_yr2 = ['DCIT201', 'DCIT202', 'COSC201', 'COSC202', 'MATH11']
_cs_yr3 = ['DCIT301', 'DCIT302', 'COSC301', 'COSC302', 'MATH10']
_cs_yr4 = ['COSC401', 'COSC402']

_it_yr1 = ['MATH101', 'ENGL101', 'FILI101', 'PHED101', 'SOSC101', 'NSTP101', 'DCIT101', 'DCIT102', 'ITEC101']
_it_yr2 = ['DCIT201', 'DCIT202', 'ITEC201', 'ITEC202']
_it_yr3 = ['DCIT301', 'DCIT302', 'ITEC301', 'ITEC302']
_it_yr4 = ['ITEC401', 'ITEC402']

CURRICULUM = {}
# Generate 8 sections per year for BSCoS and BSIT (64 total)
for yr in range(1, 5):
    for sec_code in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']:
        name_cs = f"BSCoS {yr}01-{sec_code}"
        CURRICULUM[name_cs] = locals()[f"_cs_yr{yr}"]
        name_it = f"BSIT {yr}01-{sec_code}"
        CURRICULUM[name_it] = locals()[f"_it_yr{yr}"]

# ── SECTIONS (64 total) ───────────────────────────────────────────────────────
SECTIONS = []
for yr in range(1, 5):
    for sec_code in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']:
        SECTIONS.append({'name': f"BSCoS {yr}01-{sec_code}", 'year': yr, 'students': 40})
        SECTIONS.append({'name': f"BSIT {yr}01-{sec_code}",  'year': yr, 'students': 40})

# ── CONSTRAINTS (Standard 37) ────────────────────────────────────────────────
CONSTRAINTS = [
    {'code': 'LOCKED_SCHEDULES',           'cat': 'Administrative', 'type': 'HC',  'name': '(HC-01) Locked Schedules',                    'desc': 'Manually plotted course schedules (Pre-assignments) are immovable.'},
    {'code': 'MINOR_SUBJECT_GAP',          'cat': 'Administrative', 'type': 'HC',  'name': '(HC-02) Space for Minor Subjects',             'desc': 'Ensure sufficient free time slots exist for unscheduled minor courses.'},
    {'code': 'GLOBAL_DAY_RESTRICTION',     'cat': 'Administrative', 'type': 'HC',  'name': '(HC-03) Global Day Restriction',               'desc': 'Courses must NOT be scheduled on declared non-academic days.'},
    {'code': 'LEC_LAB_SEQUENCE',           'cat': 'Course',         'type': 'HC',  'name': '(HC-04) Lecture-Laboratory Sequence',          'desc': 'The Lecture component must be scheduled earlier than the Laboratory component.'},
    {'code': 'STRICT_ALLOC_LEC',           'cat': 'Course',         'type': 'HC',  'name': '(HC-05) Strict Lecture Allocation',            'desc': 'Every section must have a Lecture component scheduled for each required course.'},
    {'code': 'STRICT_ALLOC_LAB',           'cat': 'Course',         'type': 'HC',  'name': '(HC-06) Strict Laboratory Allocation',         'desc': 'Every section must have a Laboratory component scheduled if required by the course.'},
    {'code': 'STRICT_ALLOC_ASYNC',         'cat': 'Course',         'type': 'HC',  'name': '(HC-07) Strict Async Allocation',              'desc': 'Every section must have an Asynchronous component scheduled if required by the course.'},
    {'code': 'STRICT_LEC_DURATION',        'cat': 'Course',         'type': 'HC',  'name': '(HC-08) Strict Lecture Duration',              'desc': 'Face-to-face Lecture hours must exactly match the required hours defined in the course data.'},
    {'code': 'STRICT_LAB_DURATION',        'cat': 'Course',         'type': 'HC',  'name': '(HC-09) Strict Laboratory Duration',           'desc': 'Face-to-face Laboratory hours must exactly match the required hours defined in the course data.'},
    {'code': 'STRICT_ASYNC_LEC_DUR',       'cat': 'Course',         'type': 'HC',  'name': '(HC-10) Strict Async Lecture Duration',        'desc': 'Asynchronous Lecture hours must exactly match the required hours defined in the course data.'},
    {'code': 'STRICT_ASYNC_LAB_DUR',       'cat': 'Course',         'type': 'HC',  'name': '(HC-11) Strict Async Laboratory Duration',     'desc': 'Asynchronous Laboratory hours must exactly match the required hours defined in the course data.'},
    {'code': 'SECTION_CONFLICT',           'cat': 'Course',         'type': 'HC',  'name': '(HC-12) No Section Course Conflict',           'desc': 'A section cannot have two or more different courses scheduled at the same time.'},
    {'code': 'FACULTY_CONFLICT',           'cat': 'Course',         'type': 'HC',  'name': '(HC-13) No Faculty Course Conflict',           'desc': 'A faculty member cannot be assigned to two or more courses at the same time.'},
    {'code': 'COMPLETE_COURSE_SCHEDULING', 'cat': 'Course',         'type': 'HC',  'name': '(HC-25) Complete Course Scheduling',           'desc': 'All courses for the selected semester must be fully plotted in the timetable.'},
    {'code': 'LEC_LAB_WEEKLY_DIST',        'cat': 'Course',         'type': 'SC1', 'name': '(SC-I-01) Lecture-Lab Weekly Distribution',    'desc': 'Lectures should be placed earlier in the week; laboratories later in the week.'},
    {'code': 'ASYNC_STRATEGIC_PLACEMENT',  'cat': 'Course',         'type': 'SC1', 'name': '(SC-I-02) Strategic Asynchronous Placement',   'desc': 'Asynchronous classes should fill 1-hour gaps to preserve larger free blocks.'},
    {'code': 'LEC_LAB_PROXIMITY',          'cat': 'Course',         'type': 'SC1', 'name': '(SC-I-03) Lecture-Lab Proximity',              'desc': 'Lecture and Lab of the same course should be scheduled within 3 days of each other.'},
    {'code': 'PE_MORNING_PLACEMENT',       'cat': 'Course',         'type': 'SC1', 'name': '(SC-I-04) Morning Placement for PE Courses',   'desc': 'PE/FITT courses should be scheduled early in the morning (7:00 AM onwards).'},
    {'code': 'PE_EARLY_WEEK',              'cat': 'Course',         'type': 'SC1', 'name': '(SC-I-05) Early Week Placement for PE Courses','desc': 'PE/FITT courses should ideally be scheduled on Mondays or Tuesdays.'},
    {'code': 'SECTION_DAY_RESTRICTIONS',   'cat': 'Section',        'type': 'HC',  'name': '(HC-14) Section Day Restrictions',             'desc': 'Section schedules must only be assigned within allowed academic days for the year level.'},
    {'code': 'MAX_CONSECUTIVE_STUDENT',    'cat': 'Section',        'type': 'HC',  'name': '(HC-15) Max Consecutive Student Load',         'desc': 'A section must not exceed 6 consecutive hours of scheduled course sessions.'},
    {'code': 'NO_ROOM_MULTI_SECTION',      'cat': 'Section',        'type': 'HC',  'name': '(HC-16) No Multiple Sections in One Room',     'desc': 'Two or more sections must not be assigned to the same room at the same time.'},
    {'code': 'PREASSIGNMENT_EXCLUSIVITY',  'cat': 'Section',        'type': 'HC',  'name': '(HC-26) Pre-assignment Time Exclusivity',      'desc': 'Time slots blocked by pre-assignments cannot be overwritten or double-booked for that section.'},
    {'code': 'EARLY_START',                'cat': 'Administrative', 'type': 'HC',  'name': '(HC-27) Early Start Enforcement',              'desc': 'All scheduled sessions must start at or after the configured earliest start time.'},
    {'code': 'DIV4_SLOT_ALIGNMENT',        'cat': 'Time',           'type': 'HC',  'name': '(HC-28) Divisible-4 Slot Alignment',           'desc': 'Courses in special rooms must align to valid 4-hour slot blocks.'},
    {'code': 'FACULTY_DAY_SPLIT',          'cat': 'Faculty',        'type': 'HC',  'name': '(HC-29) Faculty Day Split',                    'desc': 'When a faculty has a configured day-split, Lab/Lec sessions must be pinned to their assigned days.'},
    {'code': 'NO_ISOLATED_LECTURES',       'cat': 'Section',        'type': 'SC2', 'name': '(SC-II-01) No Isolated Lectures',              'desc': 'A section must not have only one lecture scheduled on a given day.'},
    {'code': 'NO_ISOLATED_LABS',           'cat': 'Section',        'type': 'SC2', 'name': '(SC-II-02) No Isolated Laboratories',          'desc': 'A section must not have only one laboratory scheduled on a given day.'},
    {'code': 'MIN_DAILY_SECTION_LOAD',     'cat': 'Section',        'type': 'SC2', 'name': '(SC-II-05) Minimum Daily Section Load',        'desc': 'A section should have at least two classes scheduled on any active academic day.'},
    {'code': 'SINGLE_FACULTY_PER_TIMESLOT','cat': 'Faculty',        'type': 'HC',  'name': '(HC-17) Single Faculty per Section Timeslot',  'desc': 'A section cannot have two or more faculty members assigned at the same time.'},
    {'code': 'FACULTY_AVAILABILITY',       'cat': 'Faculty',        'type': 'HC',  'name': '(HC-18) Faculty Availability',                 'desc': 'A faculty member must not be scheduled during declared unavailable time slots.'},
    {'code': 'MAX_CONSECUTIVE_FACULTY',    'cat': 'Faculty',        'type': 'HC',  'name': '(HC-19) Max Consecutive Faculty Load',         'desc': 'A faculty member must not teach for more than 6 consecutive hours.'},
    {'code': 'SINGLE_ROOM_PER_SESSION',    'cat': 'Room',           'type': 'HC',  'name': '(HC-20) Single Room per Course Session',       'desc': 'A scheduled course session cannot be assigned to two or more rooms at the same time.'},
    {'code': 'ROOM_SUITABILITY',           'cat': 'Room',           'type': 'HC',  'name': '(HC-21) Room Type Suitability',                'desc': 'Laboratory components must be in Laboratory rooms; Lecture components in Lecture rooms.'},
    {'code': 'ROOM_AVAILABILITY',          'cat': 'Room',           'type': 'HC',  'name': '(HC-22) Room Availability',                    'desc': 'Courses must not be scheduled in rooms marked as unavailable or under maintenance.'},
    {'code': 'ROOM_CAPACITY_PROPORTIONAL', 'cat': 'Room',           'type': 'SC2', 'name': '(SC-II-03) Proportional Room Capacity Allocation','desc': 'Sections with larger student populations should be prioritized for larger rooms.'},
    {'code': 'OPERATING_HOURS',            'cat': 'Time',           'type': 'HC',  'name': '(HC-23) Operating Hours Compliance',           'desc': 'All course sessions must fall within official institutional start and end times.'},
    {'code': 'HOURLY_ALIGNMENT',           'cat': 'Time',           'type': 'HC',  'name': '(HC-24) Hourly Clock Alignment',               'desc': 'All course session start times must begin exactly on the hour.'},
    {'code': 'LUNCH_BREAK',                'cat': 'Time',           'type': 'SC2', 'name': '(SC-II-04) Lunch Break Allocation',            'desc': 'A 1-hour vacant period must be provided between 10:00 AM and 2:00 PM.'},
    {'code': 'EVENING_AVOIDANCE',          'cat': 'Time',           'type': 'SC2', 'name': '(SC-II-06) Evening Class Avoidance',           'desc': 'Avoid scheduling classes in the evening (from 6:00 PM onwards).'},
]

PREFIX_RULES = [
    {'prefix': 'COSC', 'dept': 'Department of Computer Studies'},
    {'prefix': 'DCIT', 'dept': 'Department of Computer Studies'},
    {'prefix': 'ITEC', 'dept': 'Department of Computer Studies'},
    {'prefix': 'SOSC', 'dept': 'Department of Arts and Sciences'},
    {'prefix': 'PHED', 'dept': 'Department of Arts and Sciences'},
    {'prefix': 'HUMN', 'dept': 'Department of Arts and Sciences'},
    {'prefix': 'ECON', 'dept': 'Department of Arts and Sciences'},
    {'prefix': 'ENGL', 'dept': 'Department of Teachers Education'},
    {'prefix': 'FILI', 'dept': 'Department of Teachers Education'},
    {'prefix': 'MATH', 'dept': 'Department of Teachers Education'},
    {'prefix': 'NSTP', 'dept': 'NSTP Department'},
]
PREFIX_EXCEPTIONS = [
    {'code': 'MATH10', 'dept': 'Department of Engineering'},
    {'code': 'MATH11', 'dept': 'Department of Engineering'},
]

def seed_database():
    with app.app_context():
        print(f"Seeder {SEEDER_LEVEL}: Cleaning DB...")
        db.create_all()
        db.session.execute(section_courses.delete())
        db.session.execute(faculty_courses.delete())
        FacultyAssignment.query.delete(); PreAssignment.query.delete()
        ScheduledClass.query.delete(); Course.query.delete()
        Room.query.delete(); Section.query.delete(); Faculty.query.delete()
        Constraint.query.delete(); SystemSettings.query.delete()
        CodePrefixRule.query.delete()
        db.session.commit()

        # 1. Rules and Constraints
        for r in PREFIX_RULES:
            db.session.add(CodePrefixRule(code=r['prefix'], is_prefix=True, department=r['dept']))
        for e in PREFIX_EXCEPTIONS:
            db.session.add(CodePrefixRule(code=e['code'], is_prefix=False, department=e['dept']))
        for c in CONSTRAINTS:
            db.session.add(Constraint(logic_code=c['code'], category=c['cat'], name=c['name'], description=c['desc'], constraint_type=c['type']))

        # 2. Settings
        db.session.add(SystemSettings(
            start_hour=7, end_hour=20,
            allowed_days="Monday,Tuesday,Wednesday,Thursday,Friday,Saturday",
            campus_name="CCAT Campus", address="Rosario, Cavite",
            section_school_name="CAVITE STATE UNIVERSITY",
            fac_dept_label="DEPARTMENT OF COMPUTER STUDIES",
            sem_ay_value="1st Semester / 2024-2025"
        ))

        # 3. Core Entities
        for f in FACULTY:
            db.session.add(Faculty(employee_id=f['eid'], full_name=f['name'], department=f['dept'], employment_status=f['status'], max_weekly_hours=f.get('max_weekly', 35), sex=f.get('sex'), academic_rank=f.get('rank', ''), highest_educational_attainment=f.get('attainment', '')))
        for r in ROOMS:
            db.session.add(Room(room_name=r['name'], building=r['building'], capabilities=r['capabilities'], status=r['status'], capacity=r['capacity'], functional_computers=r['func_comp'], room_departments=r.get('room_depts', '')))
        for c in COURSES:
            db.session.add(Course(course_code=c[0], course_name=c[1], year_level=c[2], program=c[3], department=c[4], synchronous_lec_hours=c[5], synchronous_lab_hours=c[6], asynchronous_lec_hours=c[7], asynchronous_lab_hours=c[8], semester_offered=c[9]))
        for s in SECTIONS:
            db.session.add(Section(section_name=s['name'], year_level=s['year'], number_of_students=s['students']))
        db.session.commit()

        # 4. Link sections and auto-assign workloads
        course_map  = {c.course_code: c for c in Course.query.all()}
        section_map = {s.section_name: s for s in Section.query.all()}
        for sec_name, codes in CURRICULUM.items():
            sec = section_map[sec_name]
            for code in codes:
                sec.courses.append(course_map[code])
        db.session.commit()

        # Automated Assignment (Load Injector)
        dept_faculty = defaultdict(list)
        for f in Faculty.query.all():
            if 'TBA' not in f.employee_id:
                dept_faculty[f.department].append(f)
            
        fac_indices = defaultdict(int)
        fac_loads = defaultdict(float)

        print("  Injecting Faculty Assignments...")
        for sec in Section.query.all():
            for c in sec.courses:
                dept = c.department
                fac_list = dept_faculty.get(dept, [])
                if not fac_list: fac_list = [f for f in Faculty.query.all() if 'TBA' not in f.employee_id]
                
                if fac_list:
                    idx = fac_indices[dept]
                    fac = fac_list[idx % len(fac_list)]
                    course_hours = (c.synchronous_lec_hours or 0) + (c.synchronous_lab_hours or 0)
                    
                    # Round robin if load exceeded
                    if fac_loads[fac.id] + course_hours > fac.max_weekly_hours:
                        fac_indices[dept] += 1
                        fac = fac_list[fac_indices[dept] % len(fac_list)]
                            
                    if c not in fac.courses: fac.courses.append(c)
                    db.session.add(FacultyAssignment(faculty_id=fac.id, course_id=c.id, section_id=sec.id))
                    fac_loads[fac.id] += course_hours
        
        # Ensure Superadmin
        if not User.query.filter_by(role='superadmin').first():
            db.session.add(User(username='Jeremychristian', password_hash=generate_password_hash('sosa'), role='superadmin'))
            
        db.session.commit()
        print(f"Seeder {SEEDER_LEVEL} complete! Sections: {Section.query.count()}, Faculty: {Faculty.query.count()}")

if __name__ == '__main__':
    seed_database()
