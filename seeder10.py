# seeder10.py — Benchmark Level 10: PRODUCTION-READY DATASET
# This is the most comprehensive seeder, focusing on DCS (BSCS/BSIT) 
# and official department codes (DE for Engineering).

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import (app, db, User, Course, Room, Section, Faculty, Constraint,
                 SystemSettings, CodePrefixRule, ScheduledClass,
                 FacultyAssignment, PreAssignment, Department, Student,
                 section_courses, faculty_courses)
from werkzeug.security import generate_password_hash
from datetime import datetime
from collections import defaultdict

SEEDER_LEVEL   = 10
DESCRIPTION    = "Production-ready dataset with Users, Departments, and 200 Students."

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
    {'user': 'DAS', 'role': 'user', 'dept': 'Department of Arts and Sciences', 'pass': 'user123'},
    {'user': 'DBA', 'role': 'user', 'dept': 'Department of Business Administration', 'pass': 'user123'},
    {'user': 'DE', 'role': 'user', 'dept': 'Department of Engineering', 'pass': 'user123'},
    {'user': 'DHM', 'role': 'user', 'dept': 'Department of Hospitality Management', 'pass': 'user123'},
    {'user': 'DIT', 'role': 'user', 'dept': 'Department of Industrial Technology', 'pass': 'user123'},
    {'user': 'DTE', 'role': 'user', 'dept': 'Department of Teachers Education', 'pass': 'user123'},
]

# ── STUDENT NAMES (Filipino context) ──────────────────────────────────────────
STUDENT_NAMES = [
    "Juan Dela Cruz", "Maria Clara", "Jose Rizal", "Andres Bonifacio", "Emilio Aguinaldo",
    "Apolinario Mabini", "Melchora Aquino", "Gabriela Silang", "Lapu-Lapu", "Antonio Luna",
    "Gregoria de Jesus", "Marcelo H. Del Pilar", "Juan Luna", "Paciano Rizal", "Teresa Magbanua",
    "Emilio Jacinto", "Mariano Ponce", "Galicano Apacible", "Felipe Agoncillo", "Gregorio Del Pilar",
    "Vito Belarmino", "Artemio Ricarte", "Miguel Malvar", "Macario Sakay", "Julian Felipe",
    "Pascual Poblete", "Deodato Arellano", "Roman Basa", "Ladislao Diwa", "Teodoro Plata"
]

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
    {'name': 'Online Room', 'building': 'Virtual', 'capabilities': 'Lecture', 'status': 'Available', 'capacity': 999, 'func_comp': 0, 'room_depts': ''},
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
        CodePrefixRule.query.delete(); Department.query.delete()
        Student.query.delete(); User.query.delete()
        db.session.commit()

        # 1. Rules and Constraints
        for r in PREFIX_RULES:
            db.session.add(CodePrefixRule(code=r['prefix'], is_prefix=True, department=r['dept']))
        for e in PREFIX_EXCEPTIONS:
            db.session.add(CodePrefixRule(code=e['code'], is_prefix=False, department=e['dept']))
        for c in CONSTRAINTS:
            db.session.add(Constraint(logic_code=c['code'], category=c['cat'], name=c['name'], description=c['desc'], constraint_type=c['type'], weight=c.get('weight', 1)))

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
        for d in DEPARTMENTS:
            db.session.add(Department(name=d['name'], code=d['code']))
        for u in USERS:
            db.session.add(User(username=u['user'], role=u['role'], department=u['dept'], password_hash=generate_password_hash(u['pass'])))
        for f in FACULTY:
            db.session.add(Faculty(employee_id=f['eid'], full_name=f['name'], department=f['dept'], employment_status=f['status'], max_weekly_hours=f.get('max_weekly', 35), sex=f.get('sex'), academic_rank=f.get('rank', ''), highest_educational_attainment=f.get('attainment', '')))
        for r in ROOMS:
            db.session.add(Room(room_name=r['name'], building=r['building'], capabilities=r['capabilities'], status=r['status'], capacity=r['capacity'], functional_computers=r['func_comp'], room_departments=r.get('room_depts', '')))
        for c in COURSES:
            db.session.add(Course(course_code=c[0], course_name=c[1], year_level=c[2], program=c[3], department=c[4], synchronous_lec_hours=c[5], synchronous_lab_hours=c[6], asynchronous_lec_hours=c[7], asynchronous_lab_hours=c[8], semester_offered=c[9]))
        for s in SECTIONS:
            db.session.add(Section(section_name=s['name'], year_level=s['year'], number_of_students=s['students']))
        
        # 4. Generate 200 Students
        all_sections = Section.query.all()
        for i in range(200):
            sid = str(202200101 + i)
            name = STUDENT_NAMES[i % len(STUDENT_NAMES)]
            if i >= len(STUDENT_NAMES):
                name += f" {i // len(STUDENT_NAMES) + 1}"
            
            is_irregular = (i >= 150) # Last 50 are irregular
            section_id = None if is_irregular else all_sections[i % len(all_sections)].id
            year_level = (i % 4) + 1
            
            db.session.add(Student(
                student_id=sid,
                full_name=name.upper(),
                year_level=year_level,
                section_id=section_id,
                is_irregular=is_irregular,
                email=f"student{sid}@cvsu.edu.ph"
            ))
            
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
        
        db.session.commit()

        # 5. Populate Recycle Bin (11 items per category)
        print("  Populating Recycle Bin (Trash)...")
        # Reuse existing objects for relationships where needed
        sample_course = Course.query.first()
        sample_section = Section.query.first()
        sample_faculty = Faculty.query.first()
        sample_room = Room.query.first()

        for i in range(1, 12):
            suffix = f"{i:02d}"
            # 1. Courses
            db.session.add(Course(course_code=f"DEL-CRS-{suffix}", course_name=f"Deleted Course {suffix}", year_level=1, program='Both', department='Department of Computer Studies', semester_offered='1st Semester', is_archived=True, deleted_at=datetime.utcnow()))
            # 2. Sections
            db.session.add(Section(section_name=f"DEL-SEC-{suffix}", year_level=1, number_of_students=40, is_archived=True, deleted_at=datetime.utcnow()))
            # 3. Students
            db.session.add(Student(student_id=f"2022009{suffix}", full_name=f"DELETED STUDENT {suffix}", year_level=1, is_archived=True, deleted_at=datetime.utcnow()))
            # 4. Faculty
            db.session.add(Faculty(employee_id=f"DEL-FAC-{suffix}", full_name=f"Deleted Faculty {suffix}", department='Department of Computer Studies', is_archived=True, deleted_at=datetime.utcnow()))
            # 5. Rooms
            db.session.add(Room(room_name=f"DEL-RM-{suffix}", building='Trash Building', capabilities='Lecture', is_archived=True, deleted_at=datetime.utcnow()))
            # 6. Schedules (PreAssignments)
            if sample_course and sample_section and sample_faculty and sample_room:
                db.session.add(PreAssignment(course_id=sample_course.id, section_id=sample_section.id, faculty_id=sample_faculty.id, room_id=sample_room.id, day='Monday', start_time='07:00', end_time='10:00', is_archived=True, deleted_at=datetime.utcnow()))
            # 7. Code Rules
            db.session.add(CodePrefixRule(code=f"DEL-RULE-{suffix}", is_prefix=True, department='Department of Computer Studies', is_archived=True, deleted_at=datetime.utcnow()))
            # 8. Departments
            db.session.add(Department(name=f"Deleted Dept {suffix}", code=f"D-DEL-{suffix}", is_archived=True, deleted_at=datetime.utcnow()))
            # 9. Users
            db.session.add(User(username=f"del_user_{suffix}", role='user', is_deleted=True, deleted_at=datetime.utcnow(), password_hash=generate_password_hash('user123')))

        db.session.commit()
        print(f"Seeder {SEEDER_LEVEL} complete! Masterlist: 200 Students, Recycle Bin: 99 Items.")

if __name__ == '__main__':
    seed_database()
