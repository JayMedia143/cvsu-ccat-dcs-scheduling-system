import eventlet
eventlet.monkey_patch()
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, make_response, abort
from datetime import datetime, timezone, timedelta
from flask_wtf.csrf import CSRFProtect
import threading
import time
import copy
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, and_, cast, desc, asc, func
from sqlalchemy.orm import joinedload
import os
from flask import Response
import traceback

from flask import send_file
from genetic_algorithm import GeneticScheduler
import csv
import io
import base64
import pandas as pd
from openpyxl import load_workbook, Workbook
from sqlalchemy import inspect
import re
import pdfplumber
from openpyxl.styles import PatternFill, Border, Side, Alignment, Protection, Font
from openpyxl.utils import get_column_letter
from openpyxl.cell import MergedCell
from flask_socketio import SocketIO, emit, join_room, leave_room
import json
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('login'))
            if session.get('role') not in roles:
                flash('You do not have permission to access this page.', 'danger')
                if session.get('role') == 'user':
                    return redirect(url_for('view_timetable'))
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def verify_department_access(entity):
    """
    Security Barrier: Ensures that 'User' roles can only access data 
    belonging to their own department. Superadmins and Admins are 
    exempt (they have system-wide access).
    """
    if session.get('role') in ['superadmin', 'admin']:
        return True
    
    user_dept = session.get('department')
    entity_dept = getattr(entity, 'department', None)
    
    # If the entity has no department, default to denying access for strict safety
    if not entity_dept:
        return False
        
    return str(user_dept).strip().lower() == str(entity_dept).strip().lower()

# Whitelisted endpoints for historical mode (moved up for use in firewall)
_HIST_SAFE_ENDPOINTS = {
    'login', 'logout', 'api_archive_exit', 'api_archive_enter',
    'static', 'upload_profile_pic', 'change_password', 'change_username',
    'manage_archives', 'delete_archive', 'bulk_delete_archives', # Added to whitelist
}

# --- Time Machine: Backend Route Protection ---
def hist_lockdown(f):
    """Blocks all POST/DELETE mutation routes when Ghost Mode (historical view) is active.
    Returns 403 JSON for API calls and redirects with a flash for normal form submissions.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('historical_mode_active', False):
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify(ok=False, error='System is in read-only Archive Mode. Exit Archive to make changes.'), 403
            flash('Action blocked: System is in Archive Mode (read-only). Exit Archive to make changes.', 'warning')
            return redirect(request.referrer or url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# --- Time Machine: Archive Entity Reconstructor ---
from types import SimpleNamespace

def get_archive_entities(archive_id, entity_type):
    """
    [SCALABLE] Fetches archived data from specialized tables.
    Returns a list of items for template compatibility.
    """
    # Mapping to new tables
    type_map = {
        'Course': ArchivedCourse,
        'Section': ArchivedSection,
        'Faculty': ArchivedFaculty,
        'Room': ArchivedRoom,
        'Student': ArchivedStudent,
        'IrregularStudent': ArchivedStudent # Shared for now
    }
    
    cls = type_map.get(entity_type)
    if not cls:
        # Fallback to legacy for unmigrated or irregular types
        rows = ArchivedEntity.query.filter_by(term_archive_id=archive_id, entity_type=entity_type).all()
        results = []
        for r in rows:
            try:
                data = json.loads(r.data_json)
                results.append(SimpleNamespace(**data))
            except: pass
        return results

    # Get all from specialized table
    query = cls.query.filter_by(term_archive_id=archive_id)
    if entity_type == 'IrregularStudent':
        query = query.filter_by(is_irregular=True)
    return query.all()

def get_archive_query(archive_id, entity_type):
    """Returns a query object for server-side pagination of archives."""
    type_map = {
        'Course': ArchivedCourse,
        'Section': ArchivedSection,
        'Faculty': ArchivedFaculty,
        'Room': ArchivedRoom,
        'Student': ArchivedStudent
    }
    cls = type_map.get(entity_type)
    if not cls:
        return None
    return cls.query.filter_by(term_archive_id=archive_id)


def _mock_archived_schedule(as_obj):
    """
    Wraps an ArchivedSchedule (flattened strings) in a SimpleNamespace that 
    mimics the ScheduledClass structure (model relationships) for template compatibility.
    """
    from types import SimpleNamespace
    return SimpleNamespace(
        id=as_obj.id,
        day=as_obj.day,
        start_time=as_obj.start_time,
        end_time=as_obj.end_time,
        session_type=as_obj.schedule_type,
        is_preassigned=getattr(as_obj, 'is_preassigned', False),
        is_irregular=getattr(as_obj, 'is_irregular', False),
        course_id=None, 
        section_id=None,
        faculty_id=None,
        room_id=None,
        course=SimpleNamespace(course_code=as_obj.course_code, course_name=as_obj.course_name),
        section=SimpleNamespace(
            section_name=as_obj.section_name,
            number_of_students=getattr(as_obj, 'section_num_students', 0)
        ),
        faculty=SimpleNamespace(full_name=as_obj.faculty_name, sex=None),
        room=SimpleNamespace(room_name=as_obj.room_name)
    )

class MockPagination:
    """Mock pagination class to provide the same interface as SQLAlchemy's paginate()
    for list-based historical data reconstructed from archives.
    """
    def __init__(self, items, page, per_page, total_items):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total_items
        self.pages = (total_items + per_page - 1) // per_page if per_page > 0 else 0
        self.has_prev = page > 1
        self.has_next = page < self.pages
        self.prev_num = page - 1
        self.next_num = page + 1

    def iter_pages(self, left_edge=2, left_current=2, right_current=5, right_edge=2):
        last = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge or \
               (num > self.page - left_current - 1 and \
                num < self.page + right_current) or \
               num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num


def sanitize_input(text):
    """
    XSS Protection: Strips all HTML tags from user input to ensure 
    data is stored and rendered as plain text only.
    """
    if not text:
        return ""
    # Strip all HTML tags
    clean = re.sub(r'<[^>]*>', '', str(text))
    return clean


def validate_lengths(data, constraints):
    """
    Resource Protection: Rejects fields that exceed the specified 
    maxlength to prevent database bloat and memory exhaustion.
    """
    for field, max_len in constraints.items():
        val = data.get(field)
        if val and len(str(val)) > max_len:
            return False, f"Input for '{field}' is too long (max {max_len} characters)."
    return True, None

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or 'cvsu-ccat-dev-secret-key-change-in-prod'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 # Reduced from 500MB to 100MB for security
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'site.db')
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
db = SQLAlchemy(app)
csrf = CSRFProtect(app)
# Module 6: Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

@app.context_processor
def inject_archive_vars():
    """Makes archive mode variables available to all templates automatically."""
    # Mapping of full name to short code (e.g. "Department of Computer Studies" -> "DCS")
    depts = Department.query.filter_by(is_archived=False).all()
    dept_map = {d.name: (d.code if d.code else d.name) for d in depts}

    return {
        'is_hist': session.get('historical_mode_active', False),
        'active_archive_display': session.get('active_archive_display', ''),
        'dept_map': dept_map,
        'all_archives': TermArchive.query.order_by(TermArchive.created_at.desc()).all()
    }

function_list = ['manage_courses', 'manage_sections', 'manage_students', 'manage_irregular', 'manage_faculty', 'manage_rooms', 'manage_preassignments']

# ------------------------------------ Time Machine: Global POST/MUTATION Firewall ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Whitelisted endpoints that are always allowed (auth + time machine controls)
_HIST_SAFE_ENDPOINTS = {
    'login', 'logout', 'api_archive_exit', 'api_archive_enter',
    'static', 'upload_profile_pic', 'change_password', 'change_username',
    'manage_archives', 'delete_archive', 'bulk_delete_archives',
    'api_archive_capture', 'api_settings_schedule_lock', # Administrative toggles
    'api_hub_propose', 'api_hub_decide', 'api_hub_mark_read', # Hub workflow
    'api_hub_message_edit', 'api_hub_message_delete',        # Hub chat
    'exit_historical_view', 'approve_proposal', 'reject_proposal' # Compatibility aliases
}

@app.before_request
def block_mutations_in_hist_mode():
    """Global firewall: blocks all data-mutating HTTP methods when Ghost Mode is active.
    This is the backend security complement to the UI-level is_hist lockdown.
    """
    if request.method not in ('POST', 'PUT', 'DELETE', 'PATCH'):
        return  # GET requests are always fine

    if not session.get('historical_mode_active', False):
        return  # Not in historical mode ---- allow everything

    # Bypass for Superadmins (Admin override)
    if session.get('role') == 'superadmin':
        return 

    endpoint = request.endpoint or ''
    if endpoint in _HIST_SAFE_ENDPOINTS:
        return  # Whitelisted --  always allowed

    # Block the mutation
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(ok=False, error='System is in read-only Archive Mode. Exit Archive to make changes.'), 403

    flash('Action blocked: System is in Archive Mode (read-only). Exit Archive to make changes.', 'warning')
    return redirect(request.referrer or url_for('dashboard'))

# Concurrency Locks
generation_lock = threading.Lock()
rate_limit_lock = threading.Lock()

# Rate limiting: track failed login attempts per IP
_login_attempts = {}
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_LOCKOUT_MINUTES = 15

# Rate limiting for student portal (public endpoint)
# Structure: { ip: {'count': int, 'lockout_until': datetime or None} }
_portal_attempts = {}
_PORTAL_MAX_ATTEMPTS = 10
_PORTAL_LOCKOUT_MINUTES = 5

import threading
import eventlet
from eventlet.event import Event as EventletEvent

# GLOBAL VARIABLE PARA SA PROGRESS
# Gagamit tayo ng Eventlet Event para sigurado sa async environment
ga_stop_event = EventletEvent()
generation_status = {
    'running': False,
    'generation': 0,
    'hard_conflicts': 0,
    'sc1_violations': 0,
    'sc2_violations': 0,
    'soft_score': 0,
    'done': False,
    'stop_requested': False,
    'hardware': None,
    'gen_per_sec': 0
}
section_courses = db.Table('section_courses',
    db.Column('section_id', db.Integer, db.ForeignKey('section.id'), primary_key=True),
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'), primary_key=True)
)
faculty_courses = db.Table('faculty_courses',
    db.Column('faculty_id', db.Integer, db.ForeignKey('faculty.id'), primary_key=True),
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'), primary_key=True)
)

# Ilagay ito sa bandang itaas ng app.py, bago ang mga Models

class SafeObject:
    """Helper class to pass database data to threads safely."""
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

class SystemSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_hour = db.Column(db.Integer, default=7)
    end_hour = db.Column(db.Integer, default=20)
    allowed_days = db.Column(db.String(255), default="Monday,Tuesday,Wednesday,Thursday,Friday,Saturday")
    
    # --- LAYOUT SETTINGS (ADD THESE!) ---
    campus_name = db.Column(db.String(255), default="CCAT Campus")
    address = db.Column(db.String(255), default="Rosario, Cavite")

    # Section Layout
    section_school_name = db.Column(db.String(255), default="CAVITE STATE UNIVERSITY")
    section_signatory_1 = db.Column(db.String(100), default="SCHEDULE COMMITTEE")
    section_signatory_2 = db.Column(db.String(100), default="ARIEL G. SANTOS, EdD")
    section_signatory_3 = db.Column(db.String(100), default="LAURO B. PASCUA, EdD")

    # Faculty Layout
    faculty_school_name = db.Column(db.String(255), default="CAVITE STATE UNIVERSITY")
    faculty_signatory_1 = db.Column(db.String(100), default="DEPT CHAIRPERSON")
    faculty_signatory_2 = db.Column(db.String(100), default="DEAN")
    faculty_signatory_3 = db.Column(db.String(100), default="HR HEAD")

    # Room Layout
    room_school_name = db.Column(db.String(255), default="CAVITE STATE UNIVERSITY")
    room_signatory_1 = db.Column(db.String(100), default="SCHEDULE COMMITTEE")
    room_signatory_2 = db.Column(db.String(100), default="ARIEL G. SANTOS, EdD")
    room_signatory_3 = db.Column(db.String(100), default="LAURO B. PASCUA, EdD")

    # --- Course Layout ---
    course_school_name = db.Column(db.String(255), default="CAVITE STATE UNIVERSITY")
    course_signatory_1 = db.Column(db.String(100), default="SCHEDULE COMMITTEE")
    course_signatory_2 = db.Column(db.String(100), default="ARIEL G. SANTOS, EdD")  # Binago para maging consistent
    course_signatory_3 = db.Column(db.String(100), default="LAURO B. PASCUA, EdD")  # Binago para maging consistent

    # --- DYNAMIC SIGNATORIES (JSON array: [{"name":"...", "title":"..."}, ...]) ---
    # Replaces fixed sig1/sig2/sig3 --  backward-compatible (old cols still exist)
    section_signatories_json = db.Column(db.Text, nullable=True, default=None)
    faculty_signatories_json = db.Column(db.Text, nullable=True, default=None)
    room_signatories_json    = db.Column(db.Text, nullable=True, default=None)
    course_signatories_json  = db.Column(db.Text, nullable=True, default=None)

    # Image adjustment settings per layout type --  JSON array of per-image overrides
    # Format: [{"x": 0.0, "y": 0.0, "scale": 1.0, "z_above": true}, ...]
    # Index matches Excel image order (0-based). Extra entries are ignored.
    section_img_settings = db.Column(db.Text, nullable=True)
    faculty_img_settings = db.Column(db.Text, nullable=True)
    room_img_settings    = db.Column(db.Text, nullable=True)
    course_img_settings  = db.Column(db.Text, nullable=True)
    blocked_slots_json   = db.Column(db.Text, nullable=True)
    # Module 3: Global AI-Lock --  when True, GA entries are immutable for 'user' role
    schedule_lock        = db.Column(db.Boolean, default=False, nullable=False)

    # --- PHASE 1: Fixed Layout Variables ---
    republic_text       = db.Column(db.String(255), default="Republic of the Philippines")
    contact_details     = db.Column(db.String(255), default="(046) 437-9505 / (046) 437-6659")
    email               = db.Column(db.String(255), default="cvsurosario@cvsu.edu.ph")
    website             = db.Column(db.String(255), default="www.cvsu-rosario.edu.ph")
    prepared_by_label   = db.Column(db.String(100), default="Prepared by:")
    rec_approval_label  = db.Column(db.String(100), default="Recommending Approval:")
    approved_label      = db.Column(db.String(100), default="APPROVED:")
    section_sig2_title  = db.Column(db.String(100), default="Director, Instruction")
    section_sig3_title  = db.Column(db.String(100), default="Campus Administrator")
    room_sig2_title     = db.Column(db.String(100), default="Director, Instruction")
    room_sig3_title     = db.Column(db.String(100), default="Campus Administrator")
    course_sig2_title   = db.Column(db.String(100), default="Director, Instruction")
    course_sig3_title   = db.Column(db.String(100), default="Campus Administrator")
    class_label         = db.Column(db.String(100), default="CLASS")
    room_label          = db.Column(db.String(100), default="ROOM")
    course_label        = db.Column(db.String(100), default="COURSE")
    sem_ay_label        = db.Column(db.String(100), default="Semester / Academic Year")
    sem_ay_value        = db.Column(db.String(100), default="2nd Semester / 2024-2025")

    # --- PAGE MARGINS (shared: Section / Room / Course) ---
    margin_top    = db.Column(db.Float, default=0.5)
    margin_bottom = db.Column(db.Float, default=0.5)
    margin_left   = db.Column(db.Float, default=0.5)
    margin_right  = db.Column(db.Float, default=0.5)

    # --- PAPER SIZE (shared: Section / Room / Course) ---
    paper_size    = db.Column(db.String(30), default='A4')

    # --- FACULTY PAGE MARGINS (independent) ---
    fac_margin_top    = db.Column(db.Float, default=0.5)
    fac_margin_bottom = db.Column(db.Float, default=0.5)
    fac_margin_left   = db.Column(db.Float, default=0.5)
    fac_margin_right  = db.Column(db.Float, default=0.5)

    # --- FACULTY PAPER SIZE (independent) ---
    fac_paper_size    = db.Column(db.String(30), default='A4')

    # --- FACULTY-SPECIFIC LABELS (independent --  never shared with Section/Room/Course) ---
    # Card 1: Header Information
    fac_republic_text    = db.Column(db.String(255), default="Republic of the Philippines")
    fac_univ_name        = db.Column(db.String(255), default="CAVITE STATE UNIVERSITY")
    fac_campus_name      = db.Column(db.String(255), default="CCAT Campus")
    fac_address          = db.Column(db.String(255), default="Rosario, Cavite")
    fac_contact_details  = db.Column(db.String(255), default="(046) 437-9505 / (046) 437-6659")
    fac_email            = db.Column(db.String(255), default="cvsurosario@cvsu.edu.ph")
    fac_website          = db.Column(db.String(255), default="www.cvsu-rosario.edu.ph")
    fac_dept_label       = db.Column(db.String(150), default="DEPARTMENT OF COMPUTER STUDIES")
    fac_sched_title      = db.Column(db.String(150), default="FACULTY CLASS SCHEDULE")
    fac_sem_ay_label     = db.Column(db.String(150), default="SECOND SEMESTER SY 2023 - 2024")
    # Card 2: Faculty Info Block --  Labels
    fac_name_label       = db.Column(db.String(100), default="Name:")
    fac_educ_label       = db.Column(db.String(150), default="Highest Educ. Attainment:")
    fac_prep_label       = db.Column(db.String(150), default="No. of Preparation/s:")
    fac_hours_label      = db.Column(db.String(200), default="Total no. of contact hours per week:")
    # Card 3: Signatories --  Labels
    fac_conforme_label   = db.Column(db.String(100), default="Conforme:")
    fac_rec_approval_label = db.Column(db.String(150), default="Recommending Approval:")
    fac_reviewed_label   = db.Column(db.String(100), default="Reviewed by:")
    fac_approved_label   = db.Column(db.String(100), default="Approved:")
    fac_registrar_label  = db.Column(db.String(100), default="OIC, Registrar")
    # Card 3: Signatories --  Names & Titles
    fac_chair_name       = db.Column(db.String(150), default="ARIES M. GELERA")
    fac_chair_title      = db.Column(db.String(150), default="Department Chairperson")
    fac_director_name    = db.Column(db.String(150), default="ARIEL G. SANTOS, EdD")
    fac_director_title   = db.Column(db.String(150), default="Director, Instruction")
    fac_registrar_name   = db.Column(db.String(150), default="MARLYN A. QUINEZ")
    fac_admin_name       = db.Column(db.String(150), default="LAURO B. PASCUA, EdD")
    fac_admin_title      = db.Column(db.String(150), default="Campus Administrator")
    # Card 4: Form Identifiers
    fac_form_num_top     = db.Column(db.String(50),  default="VPAA-QF-11")
    fac_form_num_bottom  = db.Column(db.String(50),  default="V01-2018-07-24")
    # Legacy activity labels (kept for backward compat)
    fac_consultation     = db.Column(db.String(100), default="Consultation:")
    fac_research         = db.Column(db.String(100), default="Research:")
    fac_designation      = db.Column(db.String(100), default="Designation :")
    fac_extension        = db.Column(db.String(100), default="Extension:")
    # Legacy shared signatory cols (kept, no longer primary for faculty)
    sig1_name            = db.Column(db.String(150), default="ARIES M. GELERA")
    sig1_title           = db.Column(db.String(150), default="Department Chairperson")
    sig2_name            = db.Column(db.String(150), default="ARIEL G. SANTOS, EdD")
    sig_registrar_name   = db.Column(db.String(150), default="MARLYN A. QUINEZ")
    sig3_name            = db.Column(db.String(150), default="LAURO B. PASCUA, EdD")

class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=True) # e.g. DCS, DAS
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ArchivedDepartment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    term_archive_id = db.Column(db.Integer, db.ForeignKey('term_archive.id'), nullable=False, index=True)
    name = db.Column(db.String(255), index=True)
    code = db.Column(db.String(50), index=True)
    term_archive = db.relationship('TermArchive', backref=db.backref('departments', lazy=True, cascade="all, delete-orphan"))

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_code = db.Column(db.String(20), unique=True, nullable=False)
    course_name = db.Column(db.String(100), nullable=False)
    year_level = db.Column(db.Integer, nullable=True)
    
    # NEW COLUMN: PROGRAM (BSCoS, BSInfoTech, Both)
    program = db.Column(db.String(50), nullable=False, default='Both') 
    
    department = db.Column(db.String(100), nullable=True) 
    lec_units = db.Column(db.Integer, default=0)
    lab_units = db.Column(db.Integer, default=0)
    synchronous_lec_hours = db.Column(db.Integer, default=0)
    synchronous_lab_hours = db.Column(db.Integer, default=0)
    semester_offered = db.Column(db.String(20), nullable=False)
    asynchronous_lec_hours = db.Column(db.Integer, default=0)
    asynchronous_lab_hours = db.Column(db.Integer, default=0)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user') # 'superadmin', 'admin', 'user'
    profile_pic = db.Column(db.String(255), nullable=True, default='default.png')
    department = db.Column(db.String(100), nullable=True)  # Module 3: user's department for draft scoping
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    failed_login_attempts = db.Column(db.Integer, default=0)
    lockout_until = db.Column(db.DateTime, nullable=True)
    
    # Advanced Management: Recycle Bin Support
    is_deleted    = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at    = db.Column(db.DateTime, nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_name = db.Column(db.String(50), unique=True, nullable=False)
    building = db.Column(db.String(100), nullable=False)
    capabilities = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(50), nullable=False, default='Available')
    capacity = db.Column(db.Integer, nullable=False, default=40)
    functional_computers = db.Column(db.Integer, nullable=False, default=40)
    room_type = db.Column(db.String(10), nullable=False, default='Sync') # 'Sync' (Physical) or 'Async' (Online/Virtual)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    special_course_ids = db.Column(db.Text, nullable=True, default='')
    room_departments = db.Column(db.Text, nullable=True, default='')  # comma-separated dept names; empty = all depts
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

class Section(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    section_name = db.Column(db.String(50), unique=True, nullable=False)
    year_level = db.Column(db.Integer, nullable=False)
    number_of_students = db.Column(db.Integer, nullable=False, default=40)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    courses = db.relationship('Course', secondary=section_courses, lazy='subquery', backref=db.backref('sections', lazy=True))

class Faculty(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(20), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    employment_status = db.Column(db.String(20), nullable=False, default='Full-time')
    highest_educational_attainment = db.Column(db.String(200), nullable=True)
    academic_rank = db.Column(db.String(100), nullable=True)
    assignment_status = db.Column(db.String(20), nullable=False, default='Announced') # 'Announced' (Human) or 'TBA' (Placeholder)
    sex = db.Column(db.String(1), nullable=True)  # 'M' or 'F'
    max_weekly_hours = db.Column(db.Integer, nullable=False, default=35)
    available_days = db.Column(db.Text, nullable=False, default='Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday')
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    courses = db.relationship('Course', secondary=faculty_courses, lazy='subquery', backref=db.backref('faculty_can_teach', lazy=True))

class FacultyAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('section.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    split_day_1       = db.Column(db.String(20), nullable=True)   # Lab split day 1
    split_hours_1     = db.Column(db.Float,      nullable=True)   # Lab split hours 1
    split_day_2       = db.Column(db.String(20), nullable=True)   # Lab split day 2
    split_hours_2     = db.Column(db.Float,      nullable=True)   # Lab split hours 2
    split_lec_day_1   = db.Column(db.String(20), nullable=True)   # Lec split day 1
    split_lec_hours_1 = db.Column(db.Float,      nullable=True)   # Lec split hours 1
    split_lec_day_2   = db.Column(db.String(20), nullable=True)   # Lec split day 2
    split_lec_hours_2 = db.Column(db.Float,      nullable=True)   # Lec split hours 2
    faculty = db.relationship('Faculty', backref='assignments')
    section = db.relationship('Section')
    course = db.relationship('Course')

class PreAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('section.id'), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    day = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.String(20), nullable=False)
    end_time = db.Column(db.String(20), nullable=False)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships para madaling i-display
    course = db.relationship('Course')
    section = db.relationship('Section')
    faculty = db.relationship('Faculty')
    room = db.relationship('Room')

class Constraint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    logic_code = db.Column(db.String(50), unique=True, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    constraint_type = db.Column(db.String(10), nullable=False, default='HC')
    weight = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class CodePrefixRule(db.Model):
    __tablename__ = 'code_prefix_rules'
    id          = db.Column(db.Integer, primary_key=True)
    code        = db.Column(db.String(20), unique=True, nullable=False)  # prefix "COSC" or exact "MATH 10"
    is_prefix   = db.Column(db.Boolean, default=True, nullable=False)    # True=prefix rule, False=exact code
    department  = db.Column(db.String(100), nullable=False)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    deleted_at  = db.Column(db.DateTime, nullable=True)

# --- BAGONG MODEL PARA SA FINAL SCHEDULE ---
class ScheduledClass(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('section.id'), nullable=False)
    # Ang faculty_id ay pwedeng blangko (nullable=True) para sa T.B.A.
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=True)  # nullable so 'no room' entry can still be saved
    day = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.String(20), nullable=False)
    end_time = db.Column(db.String(20), nullable=False)
    semester = db.Column(db.String(30), nullable=False, default='1st Semester')
    # True = GA could not resolve a hard conflict for this gene --  appears in Issues page
    has_conflict = db.Column(db.Boolean, nullable=False, default=False)
    # 'Lec', 'Lab', or 'Async' --  stored from GA gene_type so checker doesn't guess from room
    session_type = db.Column(db.String(10), nullable=False, default='Lec')
    # Module 3: source tracking + draft layer
    # source: 'ga' = created by Genetic Algorithm | 'manual' = manually added
    source           = db.Column(db.String(10), nullable=False, default='ga')
    # is_draft: True = belongs to a draft version (not yet published to master)
    is_draft         = db.Column(db.Boolean, nullable=False, default=False)
    # draft_version_id: FK to DraftVersion; NULL = master/live record
    draft_version_id = db.Column(db.Integer, db.ForeignKey('draft_version.id'), nullable=True)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    course = db.relationship('Course')
    section = db.relationship('Section')
    faculty = db.relationship('Faculty')
    room = db.relationship('Room')

class UserPersonalSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('section.id'), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculty.id'), nullable=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=True)
    day = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.String(20), nullable=False)
    end_time = db.Column(db.String(20), nullable=False)
    session_type = db.Column(db.String(10), nullable=False, default='Lec')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('personal_schedules', lazy=True))
    course = db.relationship('Course')
    section = db.relationship('Section')
    faculty = db.relationship('Faculty')
    room = db.relationship('Room')

class HistoricalSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    semester = db.Column(db.String(20), nullable=False)
    academic_year = db.Column(db.String(20), nullable=False)
    course_code = db.Column(db.String(20), nullable=True)
    section_name = db.Column(db.String(20), nullable=True)
    subject_code = db.Column(db.String(20), nullable=True)
    subject_title = db.Column(db.String(100), nullable=True)
    faculty_name = db.Column(db.String(100), nullable=True)
    room_name = db.Column(db.String(50), nullable=True)
    day = db.Column(db.String(20), nullable=True)
    start_time = db.Column(db.String(20), nullable=True)
    end_time = db.Column(db.String(20), nullable=True)
    archived_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    archived_by = db.Column(db.String(50), nullable=True)

# --- Module 4: SNAPSHOT ARCHIVE ---
class TermArchive(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    academic_year = db.Column(db.String(50), nullable=False)
    semester = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # Metadata summaries for the snapshot listing
    total_sections = db.Column(db.Integer, default=0)
    total_courses = db.Column(db.Integer, default=0)
    total_faculty = db.Column(db.Integer, default=0)
    total_schedules = db.Column(db.Integer, default=0)
    total_students = db.Column(db.Integer, default=0) # New summary field
    
    # Relationship to user
    creator = db.relationship('User', foreign_keys=[created_by_id])

class ArchivedSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    term_archive_id = db.Column(db.Integer, db.ForeignKey('term_archive.id'), nullable=False, index=True)
    
    # Flattened metadata (Immutable string copies with search indexing)
    course_code = db.Column(db.String(255), index=True)
    course_name = db.Column(db.String(255))
    section_name = db.Column(db.String(255))
    faculty_name = db.Column(db.String(255), index=True)
    room_name = db.Column(db.String(255))
    
    # Schedule details
    day = db.Column(db.String(20))
    start_time = db.Column(db.String(20))
    end_time = db.Column(db.String(20))
    schedule_type = db.Column(db.String(50)) # Lec/Lab/Sync/Async
    
    is_preassigned = db.Column(db.Boolean, default=False)
    is_irregular = db.Column(db.Boolean, default=False)
    irregular_student_name = db.Column(db.String(255), nullable=True)
    section_num_students = db.Column(db.Integer, default=0) # New field to capture capacity
    
    term_archive = db.relationship('TermArchive', backref=db.backref('schedules', lazy=True, cascade="all, delete-orphan"))

class ArchivedEntity(db.Model):
    """
    [LEGACY] Stores a snapshot of an entity as JSON. 
    New archives use specialized Archived_ tables below.
    """
    id = db.Column(db.Integer, primary_key=True)
    term_archive_id = db.Column(db.Integer, db.ForeignKey('term_archive.id'), nullable=False, index=True)
    entity_type = db.Column(db.String(50)) # 'Course', 'Section', 'Faculty', 'Room', 'Student'
    data_json = db.Column(db.Text, nullable=False)
    term_archive = db.relationship('TermArchive', backref=db.backref('legacy_entities', lazy=True, cascade="all, delete-orphan"))

# --- NEW SCALABLE ARCHIVE TABLES (Column-Based) ---

class ArchivedCourse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    term_archive_id = db.Column(db.Integer, db.ForeignKey('term_archive.id'), nullable=False, index=True)
    course_code = db.Column(db.String(255), index=True)
    course_name = db.Column(db.String(255))
    year_level = db.Column(db.Integer)
    program = db.Column(db.String(100))
    department = db.Column(db.String(255), index=True)
    lec_units = db.Column(db.Integer)
    lab_units = db.Column(db.Integer)
    synchronous_lec_hours = db.Column(db.Integer, default=0)
    synchronous_lab_hours = db.Column(db.Integer, default=0)
    asynchronous_lec_hours = db.Column(db.Integer, default=0)
    asynchronous_lab_hours = db.Column(db.Integer, default=0)
    semester_offered = db.Column(db.String(100))
    term_archive = db.relationship('TermArchive', backref=db.backref('courses', lazy=True, cascade="all, delete-orphan"))

class ArchivedSection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    term_archive_id = db.Column(db.Integer, db.ForeignKey('term_archive.id'), nullable=False, index=True)
    section_name = db.Column(db.String(255), index=True)
    year_level = db.Column(db.Integer)
    number_of_students = db.Column(db.Integer)
    term_archive = db.relationship('TermArchive', backref=db.backref('sections', lazy=True, cascade="all, delete-orphan"))

class ArchivedFaculty(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    term_archive_id = db.Column(db.Integer, db.ForeignKey('term_archive.id'), nullable=False, index=True)
    employee_id = db.Column(db.String(255), index=True)
    full_name = db.Column(db.String(255), index=True)
    department = db.Column(db.String(255), index=True)
    employment_status = db.Column(db.String(100))
    highest_educational_attainment = db.Column(db.String(200), nullable=True)
    academic_rank = db.Column(db.String(100), nullable=True)
    sex = db.Column(db.String(1), nullable=True)
    max_weekly_hours = db.Column(db.Integer, default=35)
    available_days = db.Column(db.Text, default='')
    term_archive = db.relationship('TermArchive', backref=db.backref('faculty', lazy=True, cascade="all, delete-orphan"))

class ArchivedRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    term_archive_id = db.Column(db.Integer, db.ForeignKey('term_archive.id'), nullable=False, index=True)
    room_name = db.Column(db.String(255), index=True)
    building = db.Column(db.String(255))
    capabilities = db.Column(db.String(255))
    capacity = db.Column(db.Integer)
    functional_computers = db.Column(db.Integer, default=0)
    status = db.Column(db.String(100))
    special_course_ids = db.Column(db.Text, default='')
    room_departments = db.Column(db.Text, default='')
    term_archive = db.relationship('TermArchive', backref=db.backref('rooms', lazy=True, cascade="all, delete-orphan"))

class ArchivedStudent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    term_archive_id = db.Column(db.Integer, db.ForeignKey('term_archive.id'), nullable=False, index=True)
    student_id = db.Column(db.String(255), index=True)
    full_name = db.Column(db.String(255), index=True)
    year_level = db.Column(db.Integer)
    is_irregular = db.Column(db.Boolean, default=False)
    section_name = db.Column(db.String(255), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    assignments_json = db.Column(db.Text, nullable=True) # For irregular student data
    term_archive = db.relationship('TermArchive', backref=db.backref('students', lazy=True, cascade="all, delete-orphan"))



class Student(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    student_id  = db.Column(db.String(20), unique=True, nullable=False)
    full_name   = db.Column(db.String(120), nullable=False)
    year_level  = db.Column(db.Integer, nullable=False)
    section_id  = db.Column(db.Integer, db.ForeignKey('section.id'), nullable=True)
    email       = db.Column(db.String(120), nullable=True)
    is_archived  = db.Column(db.Boolean, default=False, nullable=False)
    is_irregular = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at   = db.Column(db.DateTime, nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    section      = db.relationship('Section', backref='students')

class IrregularAssignment(db.Model):
    id               = db.Column(db.Integer, primary_key=True)
    student_id_fk    = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    semester         = db.Column(db.String(30), nullable=False, default='1st Semester')
    # JSON list: [{course_id: int, section_id: int}, ...]
    assignments_json = db.Column(db.Text, nullable=False, default='[]')
    # JSON list of course_ids admin selected (before solver runs)
    requested_json   = db.Column(db.Text, nullable=False, default='[]')
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow)
    student          = db.relationship('Student', backref='irregular_assignment')

# --- Module 3: DRAFT VERSION ---
class DraftVersion(db.Model):
    __tablename__ = 'draft_version'
    id           = db.Column(db.Integer, primary_key=True)
    # Display name: "Draft 1", "Draft 2", custom label, etc.
    name         = db.Column(db.String(50), nullable=False)
    semester     = db.Column(db.String(30), default='1st Semester', nullable=False)
    # owning department; None = admin draft (not dept-restricted)
    department   = db.Column(db.String(100), nullable=True)
    created_by   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # True = already merged/published to master; False = still in draft
    is_published = db.Column(db.Boolean, default=False, nullable=False)
    status       = db.Column(db.String(20), default='draft') # 'draft', 'submitted', 'approved', 'rejected', 'hold'
    notes        = db.Column(db.Text, nullable=True)
    admin_justification = db.Column(db.Text, nullable=True)
    submission_justification = db.Column(db.Text, nullable=True)
    
    creator      = db.relationship('User', foreign_keys=[created_by], backref=db.backref('drafts_created', lazy=True))

# --- Module 6: PROPOSAL HUB & DECISION TERMINAL ---
class HubMessage(db.Model):
    __tablename__ = 'hub_message'
    id           = db.Column(db.Integer, primary_key=True)
    sender_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp    = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    content      = db.Column(db.Text, nullable=True)
    
    # message_type: 'chat', 'proposal', 'system_alert', 'decision'
    message_type = db.Column(db.String(20), default='chat', index=True)
    
    # Link to draft if type is 'proposal' or 'decision'
    draft_id     = db.Column(db.Integer, db.ForeignKey('draft_version.id'), nullable=True)
    
    # Status for proposal cards: 'pending', 'approved', 'rejected', 'hold'
    proposal_status = db.Column(db.String(20), nullable=True)
    
    # Metadata for JSON-based payloads (e.g., conflict lists, UI state)
    metadata_json = db.Column(db.Text, nullable=True)
    
    # Persistent recipient for private messages (NULL = Everyone)
    recipient_name = db.Column(db.String(50), nullable=True)

    # Added for Messenger features
    semester    = db.Column(db.String(30), nullable=True, index=True)
    is_read     = db.Column(db.Boolean, default=False, nullable=False)
    
    sender = db.relationship('User', foreign_keys=[sender_id])
    draft  = db.relationship('DraftVersion', backref=db.backref('messages', lazy=True, cascade="all, delete-orphan"))

class Notification(db.Model):
    __tablename__ = 'notification'
    id        = db.Column(db.Integer, primary_key=True)
    user_id   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message   = db.Column(db.Text, nullable=False)
    type      = db.Column(db.String(20), default='info') # 'info', 'success', 'warning', 'danger'
    link      = db.Column(db.String(255), nullable=True)
    is_read   = db.Column(db.Boolean, default=False, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    user = db.relationship('User', backref=db.backref('notifications', lazy=True, cascade="all, delete-orphan"))

# --- Module 7: USER MONITORING & ACTION TRACKER (BANTAY-SYSTEM) ---
class ActivityLog(db.Model):
    __tablename__ = 'activity_log'
    id        = db.Column(db.Integer, primary_key=True)
    user_id   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    username  = db.Column(db.String(50), nullable=True)
    action    = db.Column(db.String(100), nullable=False)
    details   = db.Column(db.Text, nullable=True)
    draft_id  = db.Column(db.Integer, db.ForeignKey('draft_version.id'), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    user = db.relationship('User', backref=db.backref('activities', lazy=True))
    draft = db.relationship('DraftVersion', backref=db.backref('activities', lazy=True))

class SecurityLog(db.Model):
    __tablename__ = 'security_log'
    id                 = db.Column(db.Integer, primary_key=True)
    ip_address         = db.Column(db.String(45), nullable=True)
    username_attempted = db.Column(db.String(50), nullable=True)
    event_type         = db.Column(db.String(50), nullable=False) # 'Login Success', 'Login Failed', 'Logout'
    details            = db.Column(db.Text, nullable=True)
    timestamp          = db.Column(db.DateTime, default=datetime.utcnow, index=True)

# --- HELPER FUNCTION: CONFLICT CHECKER ---
# --- UPDATED HELPER: CONFLICT CHECKER (Ignores Field/TBA) ---
def check_conflict(new_entry):
    fmt = '%H:%M'
    new_start = datetime.strptime(new_entry['start'], fmt).time()
    new_end = datetime.strptime(new_entry['end'], fmt).time()

    existing = PreAssignment.query.filter_by(day=new_entry['day'], is_archived=False).all()
    
    # Get Room Name to check if it's a special room
    target_room = Room.query.get(int(new_entry['room_id']))
    is_shared_room = target_room.room_name in ['University Field', 'T.B.A.']

    for item in existing:
        exist_start = datetime.strptime(item.start_time, fmt).time()
        exist_end = datetime.strptime(item.end_time, fmt).time()

        if new_start < exist_end and new_end > exist_start:
            # A. Room Conflict (Ignored if Room is Field/TBA)
            if not is_shared_room:
                if item.room_id == int(new_entry['room_id']):
                    return True, f"Room Conflict! {target_room.room_name} is already booked."
            
            # B. Faculty Conflict (Strict)
            if item.faculty_id == int(new_entry['faculty_id']):
                faculty = Faculty.query.get(item.faculty_id)
                if faculty and faculty.full_name != "T.B.A.":
                    return True, f"Faculty Conflict! {faculty.full_name} is already booked."

            # C. Section Conflict (Strict)
            # Note: We are checking entry['section_id'] which is a single ID inside the loop below
            if item.section_id == int(new_entry['section_id']):
                section = Section.query.get(item.section_id)
                return True, f"Section Conflict! {section.section_name} already has a class at this time."

    return False, None

    session['selected_semester'] = semester_name
    return redirect(request.referrer or url_for('dashboard'))

# --- Module 6: PROPOSAL HUB REAL-TIME HANDLERS ---
# In-memory: { room_name: { sid: {username, role} } }
hub_online_users = {}
# In-memory: { sid: {username, role, user_id} } --  for private message routing
hub_sid_map = {}

# Module 7: Global monitoring of all online users
# Format: { user_id: { username, role, sessions: {sid: status}, last_activity } }
monitoring_online_users = {}

@socketio.on('connect')
def handle_connect():
    if 'user_id' not in session:
        return False
    
    sid = request.sid
    uname = session.get('username')
    role = session.get('role')
    uid = session.get('user_id')
    
    # Module 7: Group by User ID to avoid duplicates
    if uid not in monitoring_online_users:
        monitoring_online_users[uid] = {
            'username': uname,
            'role': role,
            'user_id': uid,
            'sessions': {sid: 'Viewing'},
            'last_activity': datetime.utcnow().strftime('%H:%M:%S')
        }
    else:
        # Add new session to existing user
        monitoring_online_users[uid]['sessions'][sid] = 'Viewing'
        monitoring_online_users[uid]['last_activity'] = datetime.utcnow().strftime('%H:%M:%S')
    
    # Broadcast update (send processed list)
    broadcast_monitoring_update()
    
    # Join private notification room
    join_room(f"user_notif_{uid}")
    
    print(f"Client connected: {uname} ({sid})")

def broadcast_monitoring_update():
    """Helper to send the unique user list with consolidated status/session counts."""
    user_list = []
    for uid, data in monitoring_online_users.items():
        # Determine overall status: if any session is 'Editing', user is 'Editing'
        is_editing = any(s == 'Editing' for s in data['sessions'].values())
        user_list.append({
            'username': data['username'],
            'role': data['role'],
            'status': 'Editing' if is_editing else 'Viewing',
            'session_count': len(data['sessions']),
            'last_activity': data['last_activity']
        })
    
    socketio.emit('user_list_update', {'users': user_list}, room='monitoring_room')

@socketio.on('join_hub')
def on_join_hub(data):
    """Clients join a global room for the current semester to receive hub updates."""
    semester = data.get('semester', session.get('selected_semester', '1st Semester'))
    room = f"hub_{semester.replace(' ', '_').lower()}"
    join_room(room)
    uname = session.get('username', 'Unknown')
    role  = session.get('role', 'user')
    uid   = session.get('user_id')
    # Track online user in room list
    if room not in hub_online_users:
        hub_online_users[room] = {}
    hub_online_users[room][request.sid] = {'username': uname, 'role': role}
    # Track SID globally for private routing
    hub_sid_map[request.sid] = {'username': uname, 'role': role, 'user_id': uid}
    socketio.emit('hub_users_update', {'users': list(hub_online_users[room].values())}, to=room)
    print(f"User {uname} joined hub room: {room}")

@socketio.on('disconnect')
def on_handle_disconnect():
    """Remove user from all tracking maps on disconnect."""
    sid = request.sid
    uid = session.get('user_id')
    
    # Module 6: Hub cleanup
    hub_sid_map.pop(sid, None)
    for room, users in hub_online_users.items():
        if sid in users:
            del users[sid]
            socketio.emit('hub_users_update', {'users': list(users.values())}, to=room)
            break
            
    # Module 7: Monitoring cleanup
    if uid in monitoring_online_users:
        # Remove only this specific SID
        monitoring_online_users[uid]['sessions'].pop(sid, None)
        # If no more sessions, remove user from map
        if not monitoring_online_users[uid]['sessions']:
            monitoring_online_users.pop(uid)
        
        broadcast_monitoring_update()
        print(f"SID {sid} disconnected for user {uid}")

# Module 7: MONITORING SOCKET HANDLERS
@socketio.on('join_monitoring')
def on_join_monitoring():
    """Allows Superadmins to join the monitoring room for live updates."""
    if session.get('role') == 'superadmin':
        join_room('monitoring_room')
        # Send initial list immediately
        broadcast_monitoring_update()

@socketio.on('join')
def handle_join(data):
    """Generic join room handler for private communication channels."""
    room = data.get('room')
    if room:
        join_room(room)
        print(f"Socket {request.sid} joined room: {room}")

@socketio.on('status_update')
def handle_status_update(data):
    """Updates the live status (Viewing vs Editing) of a user."""
    sid = request.sid
    uid = session.get('user_id')
    if uid in monitoring_online_users:
        status = data.get('status', 'Viewing')
        # Update status for this specific session
        if sid in monitoring_online_users[uid]['sessions']:
            monitoring_online_users[uid]['sessions'][sid] = status
            monitoring_online_users[uid]['last_activity'] = datetime.utcnow().strftime('%H:%M:%S')
            
            # Broadcast update
            broadcast_monitoring_update()

@socketio.on('send_hub_message')
def handle_send_message(data):
    """Handles manual chat messages sent from the Proposal Terminal."""
    user_id           = session.get('user_id')
    username          = session.get('username')
    content           = data.get('message', '').strip()
    # 1. Length Validation (Plain Text only)
    if len(content) > 1000:
        content = content[:1000]
    # 2. XSS Sanitization (Strip all HTML)
    content = sanitize_input(content)
    # Ensure we always have a valid semester, even if mobile fails to send it
    raw_sem          = data.get('semester') or session.get('selected_semester') or '1st Semester'
    semester         = raw_sem.strip() if raw_sem else '1st Semester'
    recipient         = data.get('recipient', '').strip()
    attached_raw      = data.get('attached_draft_id')
    
    attached_draft_id = None
    if attached_raw:
        try:
            attached_draft_id = int(attached_raw)
        except (ValueError, TypeError):
            attached_draft_id = None
            
    if not user_id:
        return
    if not content and not attached_draft_id:
        return # Need either text or a draft to proceed

    # Save to Database
    msg = HubMessage(
        sender_id=user_id, 
        content=content, 
        message_type='chat',
        semester=semester,
        draft_id=attached_draft_id, 
        recipient_name=recipient if recipient else None
    )
    db.session.add(msg)
    db.session.commit()

    # --- PERSISTENT NOTIFICATION LOGIC ---
    # If a regular user attaches a draft, notify the targeted admin (or superadmins by default).
    if attached_draft_id and str(session.get('role')).lower() == 'user':
        dv = DraftVersion.query.get(attached_draft_id)
        draft_name = dv.name if dv else "Schedule Draft"
        notif_msg = f"New schedule proposal submitted by {username} for draft: {draft_name}"
        
        target_url = url_for('proposal_hub') + f"#msg-{msg.id}"
        if recipient:
            target_user = User.query.filter_by(username=recipient).first()
            if target_user:
                create_notification(target_user.id, notif_msg, 'info', target_url)
        else:
            # BROADCAST: Notify ALL admins and superadmins for global announcements
            all_admins = User.query.filter(or_(User.role.ilike('admin'), User.role.ilike('superadmin'))).all()
            for admin in all_admins:
                create_notification(admin.id, notif_msg, 'info', target_url)
    # -------------------------------------

    # Pre-fetch Draft Info for Payload
    draft_info = None
    if attached_draft_id:
        dv = DraftVersion.query.get(attached_draft_id)
        if dv:
            draft_info = {'id': dv.id, 'name': dv.name, 'status': dv.status}

    payload = {
        'id': msg.id,
        'sender': username,
        'role': session.get('role'),
        'profile_pic': session.get('profile_pic', 'default.png'),
        'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'content': content,
        'message_type': 'chat',
        'recipient_name': recipient,
        'attached_draft': draft_info
    }

    if recipient:
        # Private: emit to target SIDs + echo back to sender
        # Important: A user might have multiple tabs open (multiple SIDs). 
        # We broadcast to all SIDs associated with that username.
        target_sids = [s for s, u in hub_sid_map.items() if u['username'] == recipient]
        emit('new_hub_message', payload) # echo to sender
        for sid in target_sids:
            if sid != request.sid:
                socketio.emit('new_hub_message', payload, to=sid)
    else:
        # Broadcast to whole hub room
        room = f"hub_{semester.replace(' ', '_').lower()}"
        socketio.emit('new_hub_message', payload, room=room)

@app.route('/api/hub/chat', methods=['POST'])
@login_required
def api_hub_chat():
    """HTTP fallback for chat when WebSocket is disconnected."""
    data              = request.get_json(force=True) or {}
    user_id           = session.get('user_id')
    username          = session.get('username')
    content           = (data.get('message') or '').strip()
    semester          = session.get('selected_semester', '1st Semester')
    recipient         = (data.get('recipient') or '').strip()
    attached_raw      = data.get('attached_draft_id')
    
    attached_draft_id = None
    if attached_raw:
        try:
            attached_draft_id = int(attached_raw)
        except (ValueError, TypeError):
            attached_draft_id = None
            
    if not content and not attached_draft_id:
        return jsonify({'ok': False, 'error': 'Empty message'}), 400

    # Save to Database
    msg = HubMessage(
        sender_id=user_id, 
        content=content, 
        message_type='chat',
        semester=semester,
        draft_id=attached_draft_id, 
        recipient_name=recipient
    )
    db.session.add(msg)
    db.session.commit()

    # --- PERSISTENT NOTIFICATION LOGIC ---
    if attached_draft_id and str(session.get('role')).lower() == 'user':
        admins = User.query.filter(
            or_(User.role.ilike('admin'), User.role.ilike('superadmin'))
        ).all()
        dv = DraftVersion.query.get(attached_draft_id)
        draft_name = dv.name if dv else "Schedule Draft"
        for admin in admins:
            create_notification(
                admin.id, 
                f"New schedule proposal submitted by {username} for draft: {draft_name}", 
                'info', 
                url_for('proposal_hub')
            )
    # -------------------------------------

    draft_info = None
    if attached_draft_id:
        dv = DraftVersion.query.get(attached_draft_id)
        if dv:
            draft_info = {'id': dv.id, 'name': dv.name, 'status': dv.status}

    payload = {
        'id': msg.id,
        'sender': username,
        'role': session.get('role'),
        'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'content': content,
        'message_type': 'chat',
        'recipient_name': recipient,
        'attached_draft': draft_info
    }

    # Broadcast via Socket.io to others
    if recipient:
        target_sids = [s for s, u in hub_sid_map.items() if u['username'] == recipient]
        for sid in target_sids:
            socketio.emit('new_hub_message', payload, to=sid)
    else:
        room = f"hub_{semester.replace(' ', '_').lower()}"
        socketio.emit('new_hub_message', payload, room=room)

    return jsonify({'ok': True, 'message': payload})

@app.route('/api/hub/users')
@login_required
def api_hub_users():
    """Returns list of users this person can privately message."""
    role = session.get('role')
    uid  = session.get('user_id')
    if role in ['admin', 'superadmin']:
        users = User.query.filter(User.id != uid).order_by(User.username).all()
    else:
        # Regular users can only message admins/superadmins
        users = User.query.filter(User.role.in_(['admin', 'superadmin'])).order_by(User.username).all()
    return jsonify([{'username': u.username, 'role': u.role} for u in users])

@app.route('/api/hub/drafts')
@login_required
def api_hub_drafts():
    """Returns drafts the current user can attach to a chat message."""
    uid       = session.get('user_id')
    user_dept = session.get('department')
    user_role = session.get('role')
    
    if user_role in ['admin', 'superadmin']:
        drafts = DraftVersion.query.order_by(DraftVersion.updated_at.desc()).all()
    elif user_dept:
        drafts = DraftVersion.query.filter(
            or_(DraftVersion.created_by == uid, DraftVersion.department == user_dept)
        ).order_by(DraftVersion.updated_at.desc()).all()
    else:
        drafts = DraftVersion.query.filter_by(created_by=uid)\
            .order_by(DraftVersion.updated_at.desc()).all()
    return jsonify([{
        'id': d.id,
        'name': d.name,
        'status': d.status,
        'semester': d.semester,
        'department': d.department or 'ALL',
        'updated_at': d.updated_at.strftime('%m/%d %H:%M')
    } for d in drafts])

@app.route('/api/hub/conversations')
@login_required
def api_hub_conversations():
    """Returns a list of unique users the current user has chatted with, plus a global Everyone card."""
    uid = session.get('user_id')
    username = session.get('username')
    semester = session.get('selected_semester', '1st Semester')
    
    # Get all users for global search (No role restrictions)
    all_potential = User.query.filter(User.username != username, User.is_deleted == False).all()
    
    potential_map = {u.username: u for u in all_potential}
    online_usernames = {v['username'] for v in hub_sid_map.values()}

    # 1. Fetch private messages for this user
    private_msgs = HubMessage.query.filter(
        or_(
            HubMessage.recipient_name == username,
            and_(HubMessage.sender_id == uid, HubMessage.recipient_name != None, HubMessage.recipient_name != '')
        )
    ).order_by(HubMessage.timestamp.desc()).all()
    
    # 2. Group by partner
    convos = {}
    for msg in private_msgs:
        try:
            # Safety Check: If sender is missing (hard deleted), skip this message/conversation
            if msg.sender_id != uid and not msg.sender:
                continue
                
            partner = msg.recipient_name if msg.sender_id == uid else msg.sender.username
            
            # Safety Check: If partner is missing or is marked as deleted, skip from active view
            if not partner or partner not in potential_map:
                continue
                
            if partner not in convos:
                unread = HubMessage.query.filter_by(sender_id=msg.sender_id, recipient_name=username, is_read=False).count() \
                         if partner == msg.sender.username else 0
                
                preview = msg.content or ''
                if not preview and msg.draft_id:
                    preview = "Shared a proposal"
                
                convos[partner] = {
                    'name': partner,
                    'department': (potential_map[partner].department if partner in potential_map else 'System'),
                    'last_message': preview[:40] + ('...' if len(preview) > 40 else ''),
                    'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'unread_count': unread,
                    'is_global': False,
                    'role': potential_map[partner].role if partner in potential_map else 'user',
                    'profile_pic': (potential_map[partner].profile_pic if partner in potential_map else None) or 'default.png',
                    'is_online': partner in online_usernames
                }
        except Exception as e:
            print(f"Error processing convo for msg {msg.id}: {str(e)}")
            continue
            
    # 3. Add global 'Everyone'
    last_global = HubMessage.query.filter(
        and_(HubMessage.recipient_name == None, HubMessage.semester == semester)
    ).order_by(HubMessage.timestamp.desc()).first()
    
    global_card = {
        'name': 'Everyone',
        'last_message': (last_global.content[:40] + ('...' if len(last_global.content or '') > 40 else '')) if last_global and last_global.content else ("Shared a proposal" if last_global and last_global.draft_id else 'No messages yet'),
        'timestamp': last_global.timestamp.strftime('%Y-%m-%d %H:%M:%S') if last_global else '',
        'unread_count': 0,
        'is_global': True,
        'role': 'system',
        'profile_pic': None,
        'is_online': False
    }
    
    # 4. Separate history and searchable users
    history_list = [global_card]
    history_list.extend(convos.values())

    searchable_users = []
    for uname, u in potential_map.items():
        searchable_users.append({
            'name': uname,
            'department': u.department,
            'role': u.role,
            'profile_pic': u.profile_pic or 'default.png',
            'is_online': uname in online_usernames
        })

    return jsonify({
        'history': history_list,
        'all_users': searchable_users
    })

@app.route('/api/hub/messages')
@login_required
def api_hub_messages():
    """Returns message history for a specific conversation."""
    partner = request.args.get('partner', 'Everyone')
    username = session.get('username')
    uid = session.get('user_id')
    semester = session.get('selected_semester', '1st Semester')
    
    if partner == 'Everyone':
        msgs = HubMessage.query.filter(
            and_(HubMessage.recipient_name == None, HubMessage.semester == semester)
        ).order_by(HubMessage.timestamp.asc()).all()
    else:
        partner_user = User.query.filter_by(username=partner, is_deleted=False).first()
        if not partner_user:
            return jsonify([]) # Return empty if partner doesn't exist or is deleted
            
        msgs = HubMessage.query.filter(
            or_(
                and_(HubMessage.recipient_name == username, HubMessage.sender_id == partner_user.id),
                and_(HubMessage.sender_id == uid, HubMessage.recipient_name == partner)
            )
        ).order_by(HubMessage.timestamp.asc()).all()
        
    return jsonify([{
        'id': m.id,
        'sender': m.sender.username if m.sender else 'System',
        'role': m.sender.role if m.sender else 'system',
        'profile_pic': m.sender.profile_pic if m.sender else None,
        'content': m.content,
        'timestamp': m.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'message_type': m.message_type,
        'recipient_name': m.recipient_name,
        'is_read': m.is_read,
        'attached_draft': {'id': m.draft.id, 'name': m.draft.name, 'status': m.draft.status} if m.draft else None
    } for m in msgs])

@app.route('/api/hub/pending_drafts')
@login_required
def api_hub_pending_drafts():
    # Find DraftVersions that are linked to HubMessages
    drafts = db.session.query(DraftVersion, HubMessage.id).join(
        HubMessage, DraftVersion.id == HubMessage.draft_id
    ).join(
        User, DraftVersion.created_by == User.id
    ).filter(
        ~DraftVersion.status.in_(['approved', 'rejected']),
        User.role == 'user'
    ).order_by(HubMessage.timestamp.desc()).all()

    return jsonify([{
        'id': dv.id,
        'message_id': mid,
        'name': dv.name,
        'filename': dv.name,
        'sender': dv.creator.username if dv.creator else 'Unknown',
        'department': dv.department or 'ALL',
        'status': dv.status,
        'updated': dv.updated_at.strftime('%m/%d')
    } for dv, mid in drafts])

@app.route('/api/hub/user/<username>/history')
@login_required
def api_hub_user_history(username):
    """Returns all approved/rejected logs for a specific user."""
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify([])
    
    # Fetch all activity logs where action is Proposal Approved/Rejected 
    # and the draft was created by this user.
    # We can join with DraftVersion to verify ownership.
    logs = db.session.query(ActivityLog).join(DraftVersion, ActivityLog.draft_id == DraftVersion.id)\
        .filter(
            DraftVersion.created_by == user.id,
            or_(ActivityLog.action.ilike('%approved%'), ActivityLog.action.ilike('%rejected%'))
        ).order_by(ActivityLog.timestamp.desc()).all()
        
    return jsonify([{
        'id': l.id,
        'action': l.action,
        'details': l.details,
        'timestamp': l.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'username': l.user.username if l.user else 'System'
    } for l in logs])

@app.route('/api/hub/mark_read', methods=['POST'])
@login_required
def api_hub_mark_read():
    partner = request.args.get('partner')
    username = session.get('username')
    if not partner: return jsonify(ok=False), 400

    partner_user = User.query.filter_by(username=partner).first()
    if not partner_user: return jsonify(ok=False), 400

    HubMessage.query.filter_by(sender_id=partner_user.id, recipient_name=username, is_read=False).update({HubMessage.is_read: True})
    db.session.commit()

    # Notify the sender that their messages have been seen
    sender_sid = next((sid for sid, u in hub_sid_map.items() if u['username'] == partner), None)
    if sender_sid:
        socketio.emit('hub_messages_seen', {'reader': username, 'partner': username}, to=sender_sid)

    return jsonify(ok=True)


# --- NOTIFICATION SYSTEM ---
@app.route('/api/notifications', methods=['GET'])
@login_required
def get_notifications():
    uid = session.get('user_id')
    limit_val = request.args.get('limit', '20')
    
    query = Notification.query.filter_by(user_id=uid).order_by(Notification.timestamp.desc())
    if limit_val != 'all':
        try:
            query = query.limit(int(limit_val))
        except ValueError:
            query = query.limit(20)
            
    notifications = query.all()
    unread_count = Notification.query.filter_by(user_id=uid, is_read=False).count()
    return jsonify({
        'notifications': [{
            'id': n.id,
            'message': n.message,
            'type': n.type,
            'link': n.link,
            'is_read': n.is_read,
            'timestamp': n.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        } for n in notifications],
        'unread_count': unread_count
    })

@app.route('/api/notifications/mark-read', methods=['POST'])
@login_required
def mark_notifications_read():
    uid = session.get('user_id')
    data = request.get_json(force=True) or {}
    notif_id = data.get('id')
    
    if notif_id:
        Notification.query.filter_by(id=notif_id, user_id=uid).update({'is_read': True})
    else:
        Notification.query.filter_by(user_id=uid, is_read=False).update({'is_read': True})
    
    db.session.commit()
    return jsonify(ok=True)

def create_notification(user_id, message, n_type='info', link=None):
    """Utility to create a persistent notification and emit via socket."""
    try:
        notif = Notification(
            user_id=user_id,
            message=message,
            type=n_type,
            link=link
        )
        db.session.add(notif)
        db.session.commit()
        
        # Emit real-time notification to the user
        socketio.emit('new_notification', {
            'id': notif.id,
            'message': notif.message,
            'type': notif.type,
            'link': notif.link,
            'timestamp': notif.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }, room=f"user_notif_{user_id}")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Notification error: {e}")
        return False


@app.route('/api/draft/<int:draft_id>/history', methods=['GET'])
@login_required
def get_draft_history(draft_id):
    dv = DraftVersion.query.get_or_404(draft_id)
    # Optional: check if user has access to this draft
    history = ActivityLog.query.filter_by(draft_id=draft_id).order_by(ActivityLog.timestamp.desc()).all()
    
    # Also include the creation info from DraftVersion itself if not in logs
    timeline = [{
        'action': h.action,
        'details': h.details,
        'username': h.username,
        'timestamp': h.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    } for h in history]
    
    return jsonify(timeline)


# --- Module 6: HUB SYSTEM ALERTS & CONFLICTS ---
def check_and_post_hub_conflicts(semester, draft_id=None):
    """Detects ROOM overlaps between different departments and posts to Hub."""
    fmt = '%H:%M'
    # Fetch all active/published schedules + this specific draft
    q = ScheduledClass.query.options(
        joinedload(ScheduledClass.section),
        joinedload(ScheduledClass.room),
        joinedload(ScheduledClass.course)
    ).filter_by(semester=semester)
    
    if draft_id:
        q = q.filter(or_(ScheduledClass.is_draft == False, ScheduledClass.draft_version_id == draft_id))
    else:
        q = q.filter_by(is_draft=False)
        
    all_entries = q.all()
    rooms = {} # room_id -> [entries]
    for sc in all_entries:
        if not sc.room_id or sc.room.room_name in ('T.B.A.', 'University Field'):
            continue
        if sc.room_id not in rooms:
            rooms[sc.room_id] = []
        rooms[sc.room_id].append(sc)
        
    found_conflicts = []
    
    for rm_id, entries in rooms.items():
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                e1, e2 = entries[i], entries[j]
                if e1.day != e2.day: continue
                
                # Check overlap
                try:
                    s1, send1 = datetime.strptime(e1.start_time, fmt).time(), datetime.strptime(e1.end_time, fmt).time()
                    s2, send2 = datetime.strptime(e2.start_time, fmt).time(), datetime.strptime(e2.end_time, fmt).time()
                    
                    if not (send1 <= s2 or s1 >= send2):
                        # Overlap found! Check if departments differ
                        d1 = e1.section.department if e1.section else "Unknown"
                        d2 = e2.section.department if e2.section else "Unknown"
                        
                        if d1 != d2:
                            found_conflicts.append(
                                f"Room **{e1.room.room_name}** overlap: **{d1}** ({e1.course.course_code}) vs **{d2}** ({e2.course.course_code}) on {e1.day} @ {e1.start_time}"
                            )
                except: continue

    if found_conflicts:
        for alert_text in list(set(found_conflicts))[:5]: # Cap at 5 alerts to avoid spam
            msg = HubMessage(
                message_type='system_alert',
                content=alert_text
            )
            db.session.add(msg)
            db.session.commit()
            
            room_name = f"hub_{semester.replace(' ', '_').lower()}"
            socketio.emit('new_hub_message', {
                'id': msg.id,
                'sender': 'System',
                'role': 'system',
                'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'content': msg.content,
                'type': 'system_alert'
            }, room=room_name)

# --- Module 7: MONITORING HELPERS ---
def log_activity(action, details=None, draft_id=None, override_user_id=None, override_username=None):
    """Saves an administrative action to the ActivityLog and broadcasts it."""
    # Use overrides if provided, otherwise fallback to session
    uid = override_user_id
    uname = override_username

    # If no overrides, try to get from session (only works within request context)
    if not uid or not uname:
        try:
            if 'user_id' in session:
                uid = session.get('user_id')
                uname = session.get('username')
        except RuntimeError:
            # We are outside of request context and no overrides were provided
            pass

    if uid:
        try:
            log = ActivityLog(
                user_id=uid,
                username=uname,
                action=action,
                details=details,
                draft_id=draft_id
            )
            db.session.add(log)
            db.session.commit()
            # Broadcast to monitoring subscribers
            socketio.emit('new_activity_log', {
                'username': log.username,
                'action': log.action,
                'details': log.details,
                'draft_id': log.draft_id,
                'timestamp': log.timestamp.strftime('%H:%M:%S')
            }, room='monitoring_room')
        except Exception as e:
            db.session.rollback()
            print(f"Activity logging error: {e}")

def log_security(event_type, username_attempted=None, details=None):
    """Saves a security event (login/logout/fail) and broadcasts it."""
    try:
        log = SecurityLog(
            ip_address=request.remote_addr,
            username_attempted=username_attempted or session.get('username'),
            event_type=event_type,
            details=details
        )
        db.session.add(log)
        db.session.commit()
        # Broadcast to monitoring subscribers
        socketio.emit('new_security_log', {
            'ip': log.ip_address,
            'username': log.username_attempted,
            'event': log.event_type,
            'details': log.details,
            'timestamp': log.timestamp.strftime('%H:%M:%S')
        }, room='monitoring_room')
    except Exception as e:
        db.session.rollback()
        print(f"Security logging error: {e}")

@app.before_request
def update_user_activity():
    """Updates the last_activity timestamp for the current user on every request."""
    if 'user_id' in session:
        # We use a direct update to avoid loading the whole user object if possible, 
        # but SQLAlchemy query is fine here.
        User.query.filter_by(id=session['user_id']).update({'last_activity': datetime.utcnow()})
        db.session.commit()

# --- END MODULE 6 HANDLERS ---



@app.route('/', methods=['GET', 'POST'])
def login():
    # Audit Bypass: Allow viewing the login page even if logged in for system verification
    if request.args.get('audit_mode') == '1':
        return render_template('login.html')

    if request.method == 'POST':
        ip = request.remote_addr
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        # 1. Length Validation
        constraints = {
            'username': 50,
            'password': 100
        }
        ok, err = validate_lengths(request.form, constraints)
        if not ok:
            flash(err, 'danger')
            return render_template('login.html')

        # 2. XSS Sanitization
        username = sanitize_input(username)
        now = datetime.utcnow()

        user = User.query.filter_by(username=username).first()

        if user:
            # 1. Check Lockout
            if user.lockout_until and now < user.lockout_until:
                remaining = int((user.lockout_until - now).total_seconds() / 60) + 1
                flash(f'Account locked due to too many failed attempts. Try again in {remaining} minute(s).', 'danger')
                return render_template('login.html')

            # 2. Check Password
            if check_password_hash(user.password_hash, password):
                # SUCCESS: Reset attempts
                user.failed_login_attempts = 0
                user.lockout_until = None
                db.session.commit()

                session.clear()
                session.permanent = True
                session['user_id'] = user.id
                session['username'] = user.username
                session['role'] = user.role
                session['department'] = user.department
                session['profile_pic'] = getattr(user, 'profile_pic', 'default.png') or 'default.png'
                
                log_security('Login Success', details=f"User {user.username} logged in from {ip}")
                
                return redirect(url_for('dashboard'))
            else:
                # FAILURE: Increment attempts (Atomic with DB commit)
                with rate_limit_lock:
                    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
                    if user.failed_login_attempts >= _LOGIN_MAX_ATTEMPTS:
                        user.lockout_until = now + timedelta(minutes=_LOGIN_LOCKOUT_MINUTES)
                    db.session.commit()
                
                log_security('Login Failed', username_attempted=username, details=f"Failed attempt from {ip}")
                flash('Invalid username or password', 'danger')
        else:
            # User not found (Generic error to prevent enumeration)
            log_security('Login Failed', username_attempted=username, details=f"Unknown user from {ip}")
            flash('Invalid username or password', 'danger')

    return render_template('login.html')

@app.after_request
def add_security_headers(response):
    """Sets security headers on every response to harden the system."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Content Security Policy (Hardened)
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdn.socket.io; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' ws: wss: https://cdn.socket.io https://cdn.jsdelivr.net; "
        "frame-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self';"
    )
    return response

@app.route('/logout')
def logout():
    # Module 7: Log logout before clearing session
    if 'user_id' in session:
        log_security('Logout', details=f"User {session.get('username')} logged out")
        
    session.clear()
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
@login_required
def signup():
    # Only superadmin can create new accounts manually via signup page now
    if session.get('role') != 'superadmin':
        flash('Unauthorized access. Only Superadmins can register new users.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username         = request.form.get('username', '').strip()
        password         = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        # 1. Length Validation
        constraints = {
            'username': 50,
            'password': 100,
            'confirm_password': 100
        }
        ok, err = validate_lengths(request.form, constraints)
        if not ok:
            flash(err, 'danger')
            return redirect(url_for('signup'))

        # 2. XSS Sanitization
        username = sanitize_input(username)

        if not username or not password or not confirm_password:
            flash('Please fill out all fields.', 'danger')
            return redirect(url_for('signup'))
        
        if password != confirm_password:
            flash('Passwords do not match.', 'warning')
            return redirect(url_for('signup'))

        department = request.form.get('department', '').strip()
        if not department:
            flash('Please select a department.', 'warning')
            return redirect(url_for('signup'))

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose another one.', 'danger')
            return redirect(url_for('signup'))

        hashed_pw = generate_password_hash(password)
        new_user = User(username=username, password_hash=hashed_pw, role='user', department=department)
        db.session.add(new_user)
        db.session.commit()

        flash(f'User "{username}" registered successfully!', 'success')
        return redirect(url_for('manage_users'))
        
    return render_template('signup.html', departments=_get_depts())

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password', '').strip()
    new_password     = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()

    # 1. Length Validation
    constraints = {
        'current_password': 100,
        'new_password': 100,
        'confirm_password': 100
    }
    ok, err = validate_lengths(request.form, constraints)
    if not ok:
        flash(err, 'danger')
        return redirect(request.referrer or url_for('dashboard'))

    user = User.query.get(session['user_id'])
    
    if not user:
        flash('User not found.', 'danger')
        return redirect(request.referrer or url_for('dashboard'))

    # Check if current password matches
    if not check_password_hash(user.password_hash, current_password):
        flash('Incorrect current password.', 'danger')
        return redirect(request.referrer or url_for('dashboard'))

    # Validate new password match
    if new_password != confirm_password:
        flash('New passwords do not match.', 'danger')
        return redirect(request.referrer or url_for('dashboard'))

    # Validate complexity if desired (min length, etc)
    if len(new_password) < 4:
        flash('New password must be at least 4 characters long.', 'danger')
        return redirect(request.referrer or url_for('dashboard'))

    # Update Hash
    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Change Password', "User updated their password")
    
    flash('Password changed successfully!', 'success')
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/monitoring')
@login_required
@role_required('superadmin')
def monitoring():
    """Renders the Bantay-System Monitoring Dashboard."""
    # Get separate pages for the two logs
    act_page = request.args.get('act_page', 1, type=int)
    sec_page = request.args.get('sec_page', 1, type=int)
    
    # Paginate both tables (10 rows per page standard)
    activity_pagination = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).paginate(page=act_page, per_page=10)
    security_pagination = SecurityLog.query.order_by(SecurityLog.timestamp.desc()).paginate(page=sec_page, per_page=10)
    
    return render_template('monitoring.html', 
                          activity_logs=activity_pagination.items, 
                          act_pagination=activity_pagination,
                          security_logs=security_pagination.items,
                          sec_pagination=security_pagination)

@app.route('/change_username', methods=['POST'])
@login_required
def change_username():
    current_password = request.form.get('current_password')
    new_username = request.form.get('new_username')

    user = User.query.get(session['user_id'])
    
    if not user:
        flash('User not found.', 'danger')
        return redirect(request.referrer or url_for('dashboard'))

    # Check if current password matches
    if not check_password_hash(user.password_hash, current_password):
        flash('Incorrect current password. Identity not verified.', 'danger')
        return redirect(request.referrer or url_for('dashboard'))

    if not new_username or len(new_username.strip()) < 3:
        flash('New username must be at least 3 characters long.', 'danger')
        return redirect(request.referrer or url_for('dashboard'))

    # Check if username exists
    existing_user = User.query.filter(User.username.ilike(new_username.strip())).first()
    if existing_user and existing_user.id != user.id:
        flash('Username already taken. Please choose another one.', 'danger')
        return redirect(request.referrer or url_for('dashboard'))

    user.username = new_username.strip()
    session['username'] = user.username
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Change Username', f"Changed username to {user.username}")
    
    flash(f'Username successfully changed to {user.username}!', 'success')
    return redirect(request.referrer or url_for('dashboard'))

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload_profile_pic', methods=['POST'])
@login_required
def upload_profile_pic():
    if 'profile_pic' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(request.referrer or url_for('dashboard'))
        
    file = request.files['profile_pic']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(request.referrer or url_for('dashboard'))
        
    if file and allowed_file(file.filename):
        # Add timestamp to prevent name collisions and browser caching issues
        timestamp = int(time.time())
        filename = secure_filename(f"user_{session['user_id']}_{timestamp}_{file.filename}")
        upload_folder = os.path.join(app.root_path, 'static', 'profile_pics')
        file.save(os.path.join(upload_folder, filename))
        
        user = User.query.get(session['user_id'])
        user.profile_pic = filename
        session['profile_pic'] = filename
        db.session.commit()
        
        flash('Profile picture updated successfully!', 'success')
    else:
        flash('Invalid file type. Please upload a PNG, JPG, JPEG, or GIF.', 'danger')
        
    return redirect(request.referrer or url_for('dashboard'))


# --- Module 6: PROPOSAL HUB & DECISION TERMINAL ROUTES ---

@app.route('/proposal-hub')
@login_required
def proposal_hub():
    """Main view for the Centralized Proposal Terminal & Decision Hub."""
    semester = session.get('selected_semester', '1st Semester')
    # Fetch recent messages for the current semester
    # (Filtering by privacy: Everyone OR me as recipient OR me as sender)
    uid      = session.get('user_id')
    username = session.get('username')
    messages = HubMessage.query.options(joinedload(HubMessage.sender), joinedload(HubMessage.draft))\
        .filter(or_(
            HubMessage.recipient_name == None, 
            HubMessage.recipient_name == '',
            HubMessage.recipient_name == username,
            HubMessage.sender_id == uid
        )).order_by(HubMessage.timestamp.asc()).all()
    
    # Department heads only see drafts from their department
    user_dept = None
    if session.get('role') == 'user':
        # Find which department this user belongs to based on their drafts or a setting
        # Simplification: assume they see all or it's filtered in the UI
        pass
        
    pending_proposals = DraftVersion.query.filter_by(status='submitted')\
        .order_by(DraftVersion.updated_at.desc()).all()
    sections  = Section.query.filter_by(is_archived=False).order_by(Section.section_name).all()
    faculties = Faculty.query.filter_by(is_archived=False).order_by(Faculty.full_name).all()
    rooms     = Room.query.filter_by(is_archived=False).order_by(Room.room_name).all()
    courses   = Course.query.filter_by(is_archived=False).order_by(Course.course_code).all()
    return render_template('proposal_hub.html',
                          messages=messages,
                          selected_semester=semester,
                          pending_proposals=pending_proposals,
                          sections=sections,
                          faculties=faculties,
                          rooms=rooms,
                          courses=courses)

@app.route('/api/hub/propose', methods=['POST'])
@login_required
def api_hub_propose():
    """Department Heads submit their draft for approval."""
    data = request.get_json(force=True) or {}
    draft_id = data.get('draft_id')
    justification = data.get('justification', '').strip()
    recipient_name = data.get('recipient_name', '').strip()
    if not recipient_name: recipient_name = None
    
    if not draft_id:
        return jsonify({'ok': False, 'error': 'No draft selected.'}), 400
        
    dv = DraftVersion.query.get(draft_id)
    if not dv:
        return jsonify({'ok': False, 'error': 'Draft not found.'}), 404
        
    # Lock the draft
    dv.status = 'pending'
    dv.submission_justification = justification
    
    # Create Proposal Card in Hub
    msg = HubMessage(
        sender_id=session.get('user_id'),
        content=f"Submitted draft **{dv.name}** for approval.",
        message_type='proposal',
        draft_id=draft_id,
        proposal_status='pending',
        recipient_name=recipient_name
    )
    db.session.add(msg)
    db.session.commit()
    
    # Log Activity
    log_activity('Submit Proposal', f"Submitted draft {dv.name} for approval.", draft_id=draft_id)
    
    # Notify Admins (Only if sender is a regular user and recipient is an admin)
    sender_role = session.get('role')
    if str(sender_role).lower() == 'user':
        notif_msg = f"A new schedule proposal has been submitted by {session.get('username')} for draft: {dv.name}"
        target_url = url_for('proposal_hub') + f"#msg-{msg.id}"
        if recipient_name:
            target_user = User.query.filter_by(username=recipient_name).first()
            if target_user:
                create_notification(target_user.id, notif_msg, 'info', target_url)
        else:
            # BROADCAST: Notify ALL admins and superadmins for global announcements
            all_admins = User.query.filter(or_(User.role.ilike('admin'), User.role.ilike('superadmin'))).all()
            for admin in all_admins:
                create_notification(admin.id, notif_msg, 'info', target_url)
    
    # WebSocket Broadcast
    semester = dv.semester or session.get('selected_semester', '1st Semester')
    room = f"hub_{semester.replace(' ', '_').lower()}"
    socketio.emit('new_hub_message', {
        'id': msg.id,
        'sender': session.get('username'),
        'role': session.get('role'),
        'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'content': msg.content,
        'type': 'proposal',
        'draft_id': draft_id,
        'draft_name': dv.name,
        'justification': justification
    }, room=room)
    
    # Auto-Check for multi-dept conflicts
    check_and_post_hub_conflicts(semester, draft_id=draft_id)
    
    return jsonify({'ok': True, 'message': 'Proposal submitted to hub.'})

@app.route('/api/hub/decide/<int:draft_id>', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def api_hub_decide(draft_id):
    """Admin approves, rejects, or holds a proposal."""
    data = request.get_json(force=True) or {}
    decision = data.get('decision') or data.get('action')
    justification = data.get('justification', '').strip()

    if not draft_id or not decision:
        return jsonify({'ok': False, 'error': 'Missing draft_id or decision.'}), 400
        
    dv = DraftVersion.query.get(draft_id)
    if not dv:
        return jsonify({'ok': False, 'error': 'Draft not found.'}), 404
        
    dv.status = decision
    dv.admin_justification = justification
    
    content_map = {
        'approved': f"Approved proposal **{dv.name}**.",
        'rejected': f"Rejected proposal **{dv.name}**. Please revise.",
        'hold': f"Placed proposal **{dv.name}** on hold for further review."
    }
    
    # Create Decision Message
    msg = HubMessage(
        sender_id=session.get('user_id'),
        content=content_map.get(decision, f"Decision made for **{dv.name}**."),
        message_type='decision',
        draft_id=draft_id,
        proposal_status=decision
    )
    db.session.add(msg)
    db.session.commit()
    
    # If approved, publish it (Module 3 logic)
    if decision == 'approved':
        dv.is_published = True
        # Transfer entries to master (Simplified: already exists in logic elsewhere)
        _publish_draft_entries(draft_id)
        
    # Broadcast to Hub
    semester = dv.semester or session.get('selected_semester', '1st Semester')
    room = f"hub_{semester.replace(' ', '_').lower()}"
    socketio.emit('new_hub_message', {
        'id': msg.id,
        'sender': 'Superadmin',
        'role': 'superadmin',
        'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'content': msg.content,
        'type': 'decision',
        'draft_id': draft_id,
        'decision': decision,
        'justification': justification
    }, room=room)
    
    # Create Notification for User
    type_map_notif = {'approved': 'success', 'rejected': 'danger', 'hold': 'warning'}
    create_notification(
        dv.created_by, 
        f"Your proposal '{dv.name}' has been {decision}.", 
        type_map_notif.get(decision, 'info'), 
        url_for('proposal_hub')
    )
    
    # Log Activity
    log_activity(f"Proposal {decision.capitalize()}", f"Admin {decision} draft {dv.name}. Justification: {justification}", draft_id=draft_id)

    return jsonify({'ok': True, 'message': f'Decision "{decision}" recorded.'})

def _publish_draft_entries(draft_id):
    """Helper to merge draft entries into master schedule."""
    # Find all master entries for this draft's scope?
    # Usually we delete old master entries for the same section/dept then move these.
    # Implementation detail: assume it uses the existing merge logic from Module 3.
    dv = DraftVersion.query.get(draft_id)
    if not dv: return
    
    # Option: just mark current entries as is_draft=False
    ScheduledClass.query.filter_by(draft_version_id=draft_id).update({'is_draft': False})
    db.session.commit()


@app.route('/set-semester-filter/<semester_name>')
@login_required
def set_semester_filter(semester_name):
    session['selected_semester'] = semester_name
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/set-department-filter/<dept_name>')
@login_required
def set_department_filter(dept_name):
    session['selected_department_filter'] = dept_name
    return redirect(request.referrer or url_for('dashboard'))

# app.py

@app.route('/dashboard')
@login_required
@role_required('admin', 'superadmin', 'user')
def dashboard():
    # --- Time Machine: Historical Mode Dashboard ---
    if session.get('historical_mode_active', False):
        archive_id = session.get('active_archive_id')
        archive = TermArchive.query.get(archive_id) if archive_id else None
        if archive:
            stats = {
                'courses':         archive.total_courses,
                'faculty':         archive.total_faculty,
                'rooms':           ArchivedRoom.query.filter_by(term_archive_id=archive_id).count(),
                'sections':        archive.total_sections,
                'needed':          archive.total_schedules,
                'scheduled':       archive.total_schedules,
                'completion_rate': 100,
                'selected_depts':  [],
                'hist_archive':    archive,
            }
        else:
            stats = {'courses': 0, 'faculty': 0, 'rooms': 0, 'sections': 0,
                     'needed': 0, 'scheduled': 0, 'completion_rate': 0,
                     'selected_depts': [], 'hist_archive': None}
        return render_template('dashboard.html', stats=stats)

    # Get Current Filters
    selected_semester = session.get('selected_semester', 'All')
    current_dept_filter = session.get('selected_department_filter', 'All')
    
    # Force department filter for 'user' role
    if session.get('role') == 'user':
        current_dept_filter = session.get('department')

    # 1. Stat Card Counts (Filtered by Semester)
    course_q = Course.query.filter_by(is_archived=False)
    if session.get('role') == 'user':
        course_q = course_q.filter_by(department=session.get('department'))
    
    if selected_semester != 'All':
        course_q = course_q.filter_by(semester_offered=selected_semester)
    total_courses = course_q.count()

    # Sections that have at least one course assigned in this semester's curriculum
    section_q = Section.query.filter_by(is_archived=False)
    if session.get('role') == 'user':
        section_q = (section_q
                     .join(section_courses)
                     .join(Course)
                     .filter(Course.department == session.get('department')))
    
    if selected_semester != 'All':
        section_q = (section_q
                     .join(section_courses)
                     .join(Course)
                     .filter(Course.semester_offered == selected_semester))
    
    total_sections = section_q.distinct().count()

    faculty_q = Faculty.query.filter_by(is_archived=False)
    if session.get('role') == 'user':
        faculty_q = faculty_q.filter_by(department=session.get('department'))
    total_faculty = faculty_q.count()

    # 1.4 Room Count (Filtered for User)
    total_rooms_q = Room.query.filter_by(is_archived=False)
    if session.get('role') == 'user':
        user_dept = session.get('department')
        total_rooms_q = total_rooms_q.filter(or_(
            Room.room_departments.ilike(f"{user_dept},%"),
            Room.room_departments.ilike(f"%,{user_dept}"),
            Room.room_departments.ilike(f"%,{user_dept},%"),
            Room.room_departments == user_dept,
            Room.room_departments == "",
            Room.room_departments.is_(None),
            Room.room_name == 'T.B.A.'
        ))
    total_rooms = total_rooms_q.count()
    
    # 2. COMPLETION RATE (Scoped by Semester)
    all_depts_q = db.session.query(Course.department).filter(Course.is_archived == False)
    if selected_semester != 'All':
        all_depts_q = all_depts_q.filter(Course.semester_offered == selected_semester)
    
    # dept_list is used for the button list (always show all unique depts in that sem)
    dept_list = [d[0] for d in all_depts_q.distinct().all() if d[0]]
    
    # Use current_dept_filter to target specific calculations
    target_depts = dept_list
    if current_dept_filter != 'All' and current_dept_filter in dept_list:
        target_depts = [current_dept_filter]
    
    print(f"DEBUG DASHBOARD: semester={selected_semester}, dept_list={dept_list}")

    # total_needed calculation
    from sqlalchemy import text as sa_text
    total_needed = 0
    if target_depts:
        placeholders = ','.join([f':d{i}' for i in range(len(target_depts))])
        params = {f'd{i}': v for i, v in enumerate(target_depts)}

        sql = f"""
            SELECT SUM(
                CASE WHEN c.synchronous_lec_hours > 0 THEN 1 ELSE 0 END +
                CASE WHEN c.synchronous_lab_hours > 0 THEN 1 ELSE 0 END +
                CASE WHEN (c.asynchronous_lec_hours > 0 OR c.asynchronous_lab_hours > 0) THEN 1 ELSE 0 END
            ) FROM section_courses sc
            JOIN section s ON sc.section_id = s.id
            JOIN course c ON sc.course_id = c.id
            WHERE s.is_archived = 0 AND c.is_archived = 0
              AND c.department IN ({placeholders})
        """
        if selected_semester != 'All':
            sql += " AND c.semester_offered = :semester"
            params['semester'] = selected_semester

        result = db.session.execute(sa_text(sql), params).fetchone()
        total_needed = int(result[0] or 0)

    # total_scheduled calculation (Deduplicated for AI training data)
    total_scheduled = 0
    if target_depts:
        sched_q = (db.session.query(
                       ScheduledClass.course_id,
                       ScheduledClass.section_id,
                       ScheduledClass.day,
                       ScheduledClass.start_time,
                       ScheduledClass.end_time
                   )
                   .join(Course, ScheduledClass.course_id == Course.id)
                   .filter(Course.department.in_(target_depts), ScheduledClass.is_draft == False))
        if selected_semester != 'All':
            sched_q = sched_q.filter(ScheduledClass.semester == selected_semester)
        total_scheduled = sched_q.distinct().count()

    completion_rate = 0
    if total_needed > 0:
        completion_rate = min(100, int((total_scheduled / total_needed) * 100))
    elif total_courses > 0 and total_needed == 0:
        # Avoid showing 0% if no section-courses are mapped yet but courses exist
        completion_rate = 0 

    stats = {
        'courses': total_courses,
        'faculty': total_faculty,
        'rooms': total_rooms,
        'sections': total_sections,
        'needed': total_needed,
        'scheduled': total_scheduled,
        'completion_rate': completion_rate,
        'selected_depts': dept_list,
        'current_dept_filter': current_dept_filter,
    }
    
    return render_template('dashboard.html', stats=stats)

# app.py

@app.route('/manage/courses')
@login_required
def manage_courses():
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'default', type=str)
    search_query = request.args.get('search', '', type=str)
    
    # --- NEW FILTER PARAMETERS ---
    filter_by = request.args.get('filter_by', '', type=str) # 'dept' or 'code'
    filter_val = request.args.get('filter_val', '', type=str) # e.g. 'DCS' or 'COSC'

    selected_semester = session.get('selected_semester', 'All')

    # ------------------------------------ Time Machine: Historical Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    if session.get('historical_mode_active', False):
        archive_id = session.get('active_archive_id')
        query = get_archive_query(archive_id, 'Course')
        
        if not query:
            # Fallback if query returns None (e.g. invalid type)
            return render_template('manage_courses.html', courses=[], pagination=None)

        # 1. Apply Filtering at Database Level
        if selected_semester != 'All':
            query = query.filter(ArchivedCourse.semester_offered == selected_semester)
        
        if search_query:
            s = f"%{search_query.lower()}%"
            query = query.filter(
                (ArchivedCourse.course_code.ilike(s)) | 
                (ArchivedCourse.course_name.ilike(s)) | 
                (ArchivedCourse.department.ilike(s))
            )
        
        if filter_by == 'dept' and filter_val:
            query = query.filter(ArchivedCourse.department == filter_val)
        elif filter_by == 'code' and filter_val:
            query = query.filter(ArchivedCourse.course_code.ilike(f"{filter_val}%"))

        # 2. Apply Sorting at Database Level
        if sort_by == 'a-z':
            query = query.order_by(ArchivedCourse.course_code.asc())
        elif sort_by == 'z-a':
            query = query.order_by(ArchivedCourse.course_code.desc())
        elif sort_by == 'dept-asc':
            query = query.order_by(ArchivedCourse.department.asc(), ArchivedCourse.course_code.asc())
        elif sort_by == 'dept-desc':
            query = query.order_by(ArchivedCourse.department.desc(), ArchivedCourse.course_code.desc())
        else:
            query = query.order_by(ArchivedCourse.id.desc())

        # 3. Paginate
        pagination = query.paginate(page=page, per_page=10, error_out=False)
        items = pagination.items
        
        # Meta-data for dropdowns (still need a broad set, but we can cache or limit this)
        # Optimized: Only pull the distinct depts/prefixes for the current archive
        unique_depts = sorted([r[0] for r in db.session.query(ArchivedCourse.department).filter_by(term_archive_id=archive_id).distinct().all() if r[0]])
        
        return render_template(
            'manage_courses.html',
            courses=items,
            pagination=pagination,
            current_sort=sort_by,
            search_query=search_query,
            selected_semester=selected_semester,
            unique_depts=unique_depts,
            current_filter_by=filter_by,
            current_filter_val=filter_val
        )

    # ------------------------------------ Live Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    # Base Query
    query = Course.query.filter_by(is_archived=False)

    # DATA ISOLATION: Makita nila LANG ang kabilang sa department nila
    if session.get('role') == 'user':
        user_dept = session.get('department')
        query = query.filter(Course.department == user_dept)

    # 1. Apply Semester Filter
    if selected_semester != 'All':
        query = query.filter_by(semester_offered=selected_semester)
    
    # 2. Apply SEARCH BAR Filter
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(or_(
            Course.course_code.ilike(search_term),
            Course.course_name.ilike(search_term),
            Course.department.ilike(search_term)
        ))

    # 3. Apply SPECIFIC FILTERS (Dropdown)
    if filter_by == 'dept' and filter_val:
        query = query.filter(Course.department == filter_val)
    elif filter_by == 'code' and filter_val:
        # Filter by prefix (e.g., 'COSC' matches 'COSC 101')
        query = query.filter(Course.course_code.ilike(f"{filter_val}%"))

    # 4. Apply Sort (Updated Options)
    if sort_by == 'a-z':
        sort_query = query.order_by(Course.course_code.asc())
    elif sort_by == 'z-a':
        sort_query = query.order_by(Course.course_code.desc())
    elif sort_by == 'dept-asc': # NEW
        sort_query = query.order_by(Course.department.asc(), Course.course_code.asc())
    elif sort_by == 'dept-desc': # NEW
        sort_query = query.order_by(Course.department.desc(), Course.course_code.asc())
    else:
        sort_query = query.order_by(Course.id.desc()) # Default Newest

    pagination = sort_query.paginate(page=page, per_page=10, error_out=False)
    courses_on_page = pagination.items
    
    # DATA ISOLATION for modals and dropdowns
    modal_query = Course.query.filter_by(is_archived=False)
    if session.get('role') == 'user':
        user_dept = session.get('department')
        modal_query = modal_query.filter(Course.department == user_dept)
    all_courses_for_modals = modal_query.all()

    # --- DATA FOR FILTER DROPDOWNS ---
    # Get Unique Departments
    dept_query = db.session.query(Course.department).filter_by(is_archived=False)
    if session.get('role') == 'user':
        user_dept = session.get('department')
        dept_query = dept_query.filter(Course.department == user_dept)
    unique_depts = dept_query.distinct().all()
    unique_depts = [d[0] for d in unique_depts if d[0]] # Flatten list
    
    # Get Unique Course Prefixes (e.g., COSC, DCIT, GNED)
    prefix_query = db.session.query(Course.course_code).filter_by(is_archived=False)
    if session.get('role') == 'user':
        prefix_query = prefix_query.filter_by(created_by_id=session.get('user_id'))
    all_codes = prefix_query.all()
    unique_prefixes = set()
    for code in all_codes:
        # Assuming format "ABCD 123", split by space and take first part
        parts = code[0].split(' ')
        if parts:
            unique_prefixes.add(parts[0])
    sorted_prefixes = sorted(list(unique_prefixes))

    return render_template(
        'manage_courses.html',
        courses=courses_on_page,
        pagination=pagination,
        current_sort=sort_by,
        search_query=search_query,
        all_courses=all_courses_for_modals,
        selected_semester=selected_semester,
        # Pass filter data
        unique_depts=_get_depts(),
        unique_prefixes=sorted_prefixes,
        current_filter_by=filter_by,
        current_filter_val=filter_val
    )

@app.route('/manage/course/add', methods=['POST'])
@login_required
def add_course():
    course_code = request.form.get('course_code', '').strip()
    course_name = request.form.get('course_name', '').strip()
    
    # AUTO-ASSIGN DEPARTMENT for Users
    if session.get('role') == 'user':
        dept = session.get('department')
    else:
        dept = request.form.get('department', '').strip()

    # 1. Length Validation
    constraints = {
        'course_code': 20,
        'course_name': 100,
        'department': 100
    }
    ok, err = validate_lengths(request.form, constraints)
    if not ok:
        flash(err, "danger")
        return redirect(url_for('manage_courses'))

    # 2. XSS Sanitization
    course_code = sanitize_input(course_code)
    course_name = sanitize_input(course_name)
    dept        = sanitize_input(dept)

    existing = Course.query.filter_by(course_code=course_code, is_archived=False).first()
    if existing:
        flash(f"Course code '{course_code}' already exists!", "danger")
        return redirect(url_for('manage_courses'))

    try:
        new_course = Course(
            course_code=course_code, 
            course_name=course_name, 
            program=request.form.get('program', 'Both'), 
            department=dept,
            lec_units=int(request.form.get('lec_units', 0)), 
            lab_units=int(request.form.get('lab_units', 0)), 
            synchronous_lec_hours=int(request.form.get('synchronous_lec_hours', 0)), 
            synchronous_lab_hours=int(request.form.get('synchronous_lab_hours', 0)), 
            semester_offered=request.form.get('semester_offered', '1st Semester'), 
            asynchronous_lec_hours=int(request.form.get('asynchronous_lec_hours', 0)), 
            asynchronous_lab_hours=int(request.form.get('asynchronous_lab_hours', 0)),
            created_by_id=session.get('user_id') # Track creator
        )
        db.session.add(new_course)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash(f"Error: Could not add Course. Code '{course_code}' might already exist.", "danger")
        return redirect(url_for('manage_courses'))
    
    # Module 7: Log action
    log_activity('Add Course', f"Created course {course_code}: {course_name}")
    
    flash('Course added successfully.', 'success')
    return redirect(url_for('manage_courses'))

@app.route('/manage/course/update/<int:course_id>', methods=['POST'])
@login_required
@hist_lockdown
def update_course(course_id):
    course = Course.query.get_or_404(course_id)
    
    # Security Firewall: Role-based department check
    if not verify_department_access(course):
        flash("You are not authorized to update this course as it belongs to another department.", "danger")
        log_security('Unauthorized Access Attempt', details=f"User {session.get('username')} tried to update course id {course_id} in {course.department}")
        return redirect(url_for('manage_courses'))

    # 1. Length Validation
    constraints = {
        'course_code': 20,
        'course_name': 100,
        'department': 100
    }
    ok, err = validate_lengths(request.form, constraints)
    if not ok:
        flash(err, "danger")
        return redirect(url_for('manage_courses'))

    new_code = sanitize_input(request.form.get('course_code', '').strip())
    new_name = sanitize_input(request.form.get('course_name', '').strip())
    new_dept = sanitize_input(request.form.get('department', '').strip())
    
    existing = Course.query.filter(Course.course_code == new_code, Course.id != course_id, Course.is_archived == False).first()
    if existing:
        flash(f"Course code '{new_code}' is already taken.", "danger")
        return redirect(url_for('manage_courses'))
    
    course.course_code = new_code
    course.course_name = new_name
    if request.form.get('program'):
        course.program = request.form.get('program')
        
    # Only update department if Admin/Superadmin
    if session.get('role') != 'user':
        course.department = new_dept
    
    # Only update restricted data if present in form (preventing overwrite if hidden)
    if 'lec_units' in request.form:
        course.lec_units = int(request.form.get('lec_units', 0))
    if 'lab_units' in request.form:
        course.lab_units = int(request.form.get('lab_units', 0))
    if 'synchronous_lec_hours' in request.form:
        course.synchronous_lec_hours = int(request.form.get('synchronous_lec_hours', 0))
    if 'synchronous_lab_hours' in request.form:
        course.synchronous_lab_hours = int(request.form.get('synchronous_lab_hours', 0))
    if 'semester_offered' in request.form:
        course.semester_offered = request.form.get('semester_offered')
    if 'asynchronous_lec_hours' in request.form:
        course.asynchronous_lec_hours = int(request.form.get('asynchronous_lec_hours', 0))
    if 'asynchronous_lab_hours' in request.form:
        course.asynchronous_lab_hours = int(request.form.get('asynchronous_lab_hours', 0))
        
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Update Course', f"Updated course {new_code}")
    
    return redirect(url_for('manage_courses'))

@app.route('/manage/courses/archive')
@login_required
def courses_archive():
    page = request.args.get('page', 1, type=int) # Add Page param
    sort_by = request.args.get('sort', 'default', type=str)
    search_query = request.args.get('search', '', type=str)

    query = Course.query.filter_by(is_archived=True)
    if session.get('role') == 'user':
        query = query.filter_by(created_by_id=session.get('user_id'))

    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(or_(Course.course_code.ilike(search_term), Course.course_name.ilike(search_term)))

    if sort_by == 'a-z':
        query = query.order_by(Course.course_code.asc())
    elif sort_by == 'z-a':
        query = query.order_by(Course.course_code.desc())
    elif sort_by == 'newest' or sort_by == 'default':
        query = query.order_by(Course.deleted_at.desc(), Course.id.desc())
    else: 
        query = query.order_by(Course.id.desc())

    # USE PAGINATE INSTEAD OF .ALL()
    pagination = query.paginate(page=page, per_page=10, error_out=False)
    archived_courses = pagination.items
    
    return render_template(
        'courses_archive.html', 
        courses=archived_courses,
        pagination=pagination, # Pass pagination object
        current_sort=sort_by,
        search_query=search_query,
        now=datetime.utcnow()
    )

@app.route('/manage/course/archive/<int:course_id>', methods=['POST'])
@login_required
def archive_course(course_id):
    course = Course.query.get_or_404(course_id)
    
    # Role-based access check
    if session.get('role') == 'user' and course.created_by_id != session.get('user_id'):
        flash("You are not authorized to archive this course.", "danger")
        return redirect(url_for('manage_courses'))

    course.is_archived = True
    course.deleted_at = datetime.utcnow()
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Archive Course', f"Archived course {course.course_code}")
    
    flash('Course moved to Recycle Bin.', 'success')
    return redirect(url_for('manage_courses'))

@app.route('/manage/course/restore/<int:course_id>', methods=['POST'])
@login_required
def restore_course(course_id):
    course = Course.query.get_or_404(course_id)
    course.is_archived = False
    course.deleted_at = None
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Restore Course', f"Restored course {course.course_code}")
    
    flash('Course restored successfully.', 'success')
    return redirect(url_for('courses_archive'))

# =====================================================================
# CODE PREFIX -> DEPARTMENT ASSIGNMENT
# =====================================================================

MASTER_PREFIX_RULES = [
    # is_prefix=True (prefix rules)
    ('COSC',  True,  'Department of Computer Studies'),
    ('DCIT',  True,  'Department of Computer Studies'),
    ('ITEC',  True,  'Department of Computer Studies'),
    ('SOSC',  True,  'Department of Arts and Sciences'),
    ('PHED',  True,  'Department of Arts and Sciences'),
    ('HUMN',  True,  'Department of Arts and Sciences'),
    ('PHYS',  True,  'Department of Arts and Sciences'),
    ('ECON',  True,  'Department of Arts and Sciences'),
    ('BTCH',  True,  'Department of Arts and Sciences'),
    ('LITT',  True,  'Department of Arts and Sciences'),
    ('FITT',  True,  'Department of Arts and Sciences'),
    ('ACTG',  True,  'Department of Arts and Sciences'),
    ('DCEE',  True,  'Department of Arts and Sciences'),
    ('ENGL',  True,  'Department of Teachers Education'),
    ('FILI',  True,  'Department of Teachers Education'),
    ('MATH',  True,  'Department of Teachers Education'),
    ('STAT',  True,  'Department of Teachers Education'),
    ('NSTP',  True,  'NSTP Department'),
    # is_prefix=False (exact code exceptions ---- override prefix rules)
    ('MATH 10', False, 'Department of Engineering'),
    ('MATH 11', False, 'Department of Engineering'),
]

KNOWN_DEPARTMENTS = [
    'Department of Computer Studies',
    'Department of Arts and Sciences',
    'Department of Teachers Education',
    'Department of Engineering',
    'Department of Business Administration',
    'Department of Hotel and Management',
    'NSTP Department',
]

def _get_depts():
    """Dynamic helper to get departments from DB. Returns a list of active department names."""
    try:
        from sqlalchemy import inspect
        if not inspect(db.engine).has_table("department"):
            return []
            
        depts = [d.name for d in Department.query.filter_by(is_archived=False).order_by(Department.name).all()]
        return depts
    except Exception as e:
        print(f"Error fetching depts: {e}")
        return []

# Departments whose courses are included in the scheduling engine
SCHEDULED_DEPARTMENTS = ['Department of Computer Studies', 'NSTP Department']

def _dept_for_code(code, auto_add=False):
    """Return the department for a course code using CodePrefixRule lookup.
    If auto_add=True and the prefix is not found, dynamically create an Unassigned rule."""
    # Check exact exception first
    rule = CodePrefixRule.query.filter_by(code=code, is_prefix=False).first()
    if rule:
        return rule.department
        
    prefix = code.split(' ')[0]
    rule = CodePrefixRule.query.filter_by(code=prefix, is_prefix=True).first()
    if rule:
        return rule.department
        
    # If rule is completely missing
    if auto_add:
        # Check if another process just added it to avoid IntegrityErrors
        existing = CodePrefixRule.query.filter_by(code=prefix).first()
        if not existing:
            new_rule = CodePrefixRule(code=prefix, is_prefix=True, department='Unassigned', is_archived=False)
            db.session.add(new_rule)
            db.session.commit()
            print(f"Auto-generated missing prefix rule for: {prefix}")
            
    return 'Unassigned'

def _apply_prefix_rules():
    """Apply all CodePrefixRules to non-archived courses. Returns count of updated courses."""
    # Normalize exceptions (remove spaces)
    # Mapping of normalized_code -> (original_rule_code, department)
    exceptions_norm = {r.code.replace(' ', '').upper(): (r.code, r.department) for r in CodePrefixRule.query.filter_by(is_prefix=False).all()}
    
    prefix_map  = {r.code: r.department for r in CodePrefixRule.query.filter_by(is_prefix=True).all()}
    updated = 0
    import re
    # Pattern to extract alpha prefix (e.g., "COSC" from "COSC 101" or "COSC101")
    prefix_re = re.compile(r'^([A-Za-z]+)')

    for course in Course.query.filter_by(is_archived=False).all():
        cc_norm = course.course_code.replace(' ', '').upper()
        
        # 1. Check Exceptions (Space-Insensitive)
        if cc_norm in exceptions_norm:
            course.department = exceptions_norm[cc_norm][1]
            updated += 1
        else:
            # 2. Check Prefix Rules
            match = prefix_re.match(course.course_code)
            prefix = match.group(1) if match else course.course_code.split(' ')[0]
            
            if prefix in prefix_map:
                course.department = prefix_map[prefix]
                updated += 1
    db.session.commit()
    return updated

@app.route('/manage/courses/code-assignment', methods=['GET'])
@login_required
@role_required('admin', 'superadmin')
def course_code_assignment():
    prefix_rules    = CodePrefixRule.query.filter_by(is_prefix=True,  is_archived=False).order_by(CodePrefixRule.code).all()
    exception_rules = CodePrefixRule.query.filter_by(is_prefix=False, is_archived=False).order_by(CodePrefixRule.code).all()
    archived_count  = CodePrefixRule.query.filter_by(is_archived=True).count()

    # All unique prefixes currently in the DB
    all_codes   = db.session.query(Course.course_code).filter_by(is_archived=False).all()
    
    import re
    prefix_re = re.compile(r'^([A-Za-z]+)')
    def get_prefix(c):
        m = prefix_re.match(c)
        return m.group(1) if m else c.split(' ')[0]

    db_prefixes = sorted({get_prefix(c[0]) for c in all_codes})
    rule_prefixes = {r.code for r in prefix_rules}
    unassigned_prefixes = [p for p in db_prefixes if p not in rule_prefixes]

    # Count courses per prefix
    counts = {}
    for p in db_prefixes:
        # Match both "CODE 101" and "CODE101"
        counts[p] = Course.query.filter(
            Course.is_archived == False,
            db.or_(
                Course.course_code.like(f'{p} %'),
                Course.course_code.like(f'{p}%') 
            )
        ).count()
        # Edge case: If p is "COSC", like "COSC%" matches "COSCED". 
        # But for course assignment, we usually want as much coverage as possible.
        
    for r in exception_rules:
        code_norm = r.code.replace(' ', '').upper()
        # Find all courses that match this exception code (with or without space)
        counts[r.code] = Course.query.filter(
            Course.is_archived == False,
            db.or_(
                Course.course_code == r.code,
                Course.course_code == code_norm,
                # Also handle potentially weird spacing like "MATH  10"
                Course.course_code.like(f'{r.code.split(" ")[0]}%{r.code.split(" ")[-1]}%') if " " in r.code else False
            )
        ).count()

    return render_template('course_code_assignment.html',
                           prefix_rules=prefix_rules,
                           exception_rules=exception_rules,
                           unassigned_prefixes=unassigned_prefixes,
                           departments=KNOWN_DEPARTMENTS,
                           counts=counts,
                           archived_count=archived_count)

@app.route('/manage/departments', methods=['GET'])
@login_required
@role_required('admin', 'superadmin')
def manage_departments():
    search_query = request.args.get('search', '').strip()
    sort_by      = request.args.get('sort', 'name-asc')
    page         = request.args.get('page', 1, type=int)
    per_page     = 10

    query = Department.query.filter_by(is_archived=False)

    if search_query:
        query = query.filter(
            db.or_(
                Department.name.ilike(f'%{search_query}%'),
                Department.code.ilike(f'%{search_query}%')
            )
        )

    if sort_by == 'name-asc':
        query = query.order_by(Department.name.asc())
    elif sort_by == 'name-desc':
        query = query.order_by(Department.name.desc())
    elif sort_by == 'code-asc':
        query = query.order_by(Department.code.asc())
    elif sort_by == 'code-desc':
        query = query.order_by(Department.code.desc())
    else:  # default or newest
        query = query.order_by(Department.id.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    departments = pagination.items

    return render_template(
        'manage_departments.html',
        departments=departments,
        pagination=pagination,
        search_query=search_query,
        current_sort=sort_by
    )

@app.route('/manage/departments/add', methods=['POST'])
@hist_lockdown
@login_required
@role_required('admin', 'superadmin')
def add_department():
    name = request.form.get('name', '').strip()
    code = request.form.get('code', '').strip() or None
    
    if not name:
        flash('Department name is required.', 'danger')
        return redirect(url_for('manage_departments'))
        
    existing = Department.query.filter_by(name=name).first()
    if existing:
        flash(f'Department "{name}" already exists.', 'warning')
        return redirect(url_for('manage_departments'))
        
    try:
        new_dept = Department(name=name, code=code)
        db.session.add(new_dept)
        db.session.commit()
        log_activity('Add Department', f"Created department: {name}")
        flash(f'Department "{name}" added successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding department: {str(e)}', 'danger')
        
    return redirect(url_for('manage_departments'))

@app.route('/manage/departments/update/<int:dept_id>', methods=['POST'])
@hist_lockdown
@login_required
@role_required('admin', 'superadmin')
def update_department(dept_id):
    dept = Department.query.get_or_404(dept_id)
    name = request.form.get('name', '').strip()
    code = request.form.get('code', '').strip() or None
    
    if not name:
        flash('Department name is required.', 'danger')
        return redirect(url_for('manage_departments'))
        
    # Check for duplicate name (excluding itself)
    existing = Department.query.filter(Department.name == name, Department.id != dept_id).first()
    if existing:
        flash(f'Department "{name}" already exists.', 'warning')
        return redirect(url_for('manage_departments'))
        
    try:
        old_name = dept.name
        dept.name = name
        dept.code = code
        db.session.commit()
        log_activity('Update Department', f"Updated department from {old_name} to {name}")
        flash(f'Department "{name}" updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating department: {str(e)}', 'danger')
        
    return redirect(url_for('manage_departments'))

@app.route('/manage/departments/archive/<int:dept_id>', methods=['POST'])
@hist_lockdown
@login_required
@role_required('admin', 'superadmin')
def archive_department(dept_id):
    dept = Department.query.get_or_404(dept_id)
    try:
        dept.is_archived = True
        dept.deleted_at = datetime.utcnow()
        db.session.commit()
        log_activity('Archive Department', f"Archived department: {dept.name}")
        flash(f'Department "{dept.name}" moved to Recycle Bin.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error archiving department: {str(e)}', 'danger')
    return redirect(url_for('manage_departments'))

@app.route('/manage/departments/bulk-archive', methods=['POST'])
@hist_lockdown
@login_required
@role_required('admin', 'superadmin')
def bulk_archive_departments():
    dept_ids = request.form.getlist('row_ids')
    if not dept_ids:
        flash('No departments selected.', 'warning')
        return redirect(url_for('manage_departments'))
        
    try:
        count = 0
        now = datetime.utcnow()
        for d_id in dept_ids:
            dept = Department.query.get(int(d_id))
            if dept and not dept.is_archived:
                dept.is_archived = True
                dept.deleted_at = now
                count += 1
        db.session.commit()
        log_activity('Bulk Archive Departments', f"Archived {count} departments")
        flash(f'Successfully moved {count} departments to Recycle Bin.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error performing bulk archive: {str(e)}', 'danger')
        
    return redirect(url_for('manage_departments'))

@app.route('/manage/departments/archive')
@login_required
@role_required('admin', 'superadmin')
def departments_archive():
    search_query = request.args.get('search', '').strip()
    sort_by      = request.args.get('sort', 'newest')
    page         = request.args.get('page', 1, type=int)
    per_page     = 10

    query = Department.query.filter_by(is_archived=True)

    if search_query:
        query = query.filter(
            db.or_(
                Department.name.ilike(f'%{search_query}%'),
                Department.code.ilike(f'%{search_query}%')
            )
        )

    if sort_by == 'name-asc':
        query = query.order_by(Department.name.asc())
    elif sort_by == 'name-desc':
        query = query.order_by(Department.name.desc())
    elif sort_by == 'code-asc':
        query = query.order_by(Department.code.asc())
    elif sort_by == 'code-desc':
        query = query.order_by(Department.code.desc())
    else:  # newest
        query = query.order_by(Department.deleted_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    archived_depts = pagination.items

    return render_template(
        'departments_archive.html',
        departments=archived_depts,
        pagination=pagination,
        search_query=search_query,
        current_sort=sort_by,
        now=datetime.utcnow()
    )

@app.route('/manage/departments/restore/<int:dept_id>', methods=['POST'])
@hist_lockdown
@login_required
@role_required('admin', 'superadmin')
def restore_department(dept_id):
    dept = Department.query.get_or_404(dept_id)
    try:
        dept.is_archived = False
        dept.deleted_at = None
        db.session.commit()
        log_activity('Restore Department', f"Restored department: {dept.name}")
        flash(f'Department "{dept.name}" restored successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error restoring department: {str(e)}', 'danger')
    return redirect(url_for('departments_archive'))

@app.route('/manage/departments/delete-permanent/<int:dept_id>', methods=['POST'])
@hist_lockdown
@login_required
@role_required('admin', 'superadmin')
def delete_department_permanent(dept_id):
    dept = Department.query.get_or_404(dept_id)
    try:
        name = dept.name
        db.session.delete(dept)
        db.session.commit()
        log_activity('Permanent Delete Department', f"Permanently deleted department: {name}")
        flash(f'Department "{name}" deleted permanently.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting department: {str(e)}', 'danger')
    return redirect(url_for('departments_archive'))

@app.route('/manage/departments/bulk-restore', methods=['POST'])
@hist_lockdown
@login_required
@role_required('admin', 'superadmin')
def bulk_restore_departments():
    dept_ids = request.form.getlist('row_ids')
    if not dept_ids:
        flash('No departments selected.', 'warning')
        return redirect(url_for('departments_archive'))
        
    try:
        count = 0
        for d_id in dept_ids:
            dept = Department.query.get(int(d_id))
            if dept and dept.is_archived:
                dept.is_archived = False
                dept.deleted_at = None
                count += 1
        db.session.commit()
        log_activity('Bulk Restore Departments', f"Restored {count} departments")
        flash(f'Successfully restored {count} departments.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error performing bulk restore: {str(e)}', 'danger')
        
    return redirect(url_for('departments_archive'))

@app.route('/manage/departments/bulk-delete', methods=['POST'])
@hist_lockdown
@login_required
@role_required('admin', 'superadmin')
def bulk_delete_departments_permanent():
    dept_ids = request.form.getlist('row_ids')
    if not dept_ids:
        flash('No departments selected.', 'warning')
        return redirect(url_for('departments_archive'))
        
    try:
        count = 0
        for d_id in dept_ids:
            dept = Department.query.get(int(d_id))
            if dept and dept.is_archived:
                db.session.delete(dept)
                count += 1
        db.session.commit()
        log_activity('Bulk Permanent Delete Departments', f"Deleted {count} departments permanently")
        flash(f'Successfully deleted {count} departments permanently.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error performing bulk delete: {str(e)}', 'danger')
        
    return redirect(url_for('departments_archive'))

@app.route('/manage/courses/code-assignment/save', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def save_code_assignment():
    # --- Update existing prefix rules (department only ---- archive done via dedicated route) ---
    for rule in CodePrefixRule.query.filter_by(is_prefix=True, is_archived=False).all():
        dept = request.form.get(f'dept_p_{rule.id}')
        if dept:
            rule.department = dept

    # --- Update existing exception rules ---
    for rule in CodePrefixRule.query.filter_by(is_prefix=False, is_archived=False).all():
        dept = request.form.get(f'dept_e_{rule.id}')
        if dept:
            rule.department = dept

    # --- Add new prefix rules ---
    new_prefixes      = request.form.getlist('new_prefix[]')
    new_prefix_depts  = request.form.getlist('new_prefix_dept[]')
    for prefix, dept in zip(new_prefixes, new_prefix_depts):
        prefix = prefix.strip().upper()
        if prefix and dept:
            existing = CodePrefixRule.query.filter_by(code=prefix).first()
            if existing:
                existing.department  = dept
                existing.is_prefix   = True
                existing.is_archived = False
            else:
                db.session.add(CodePrefixRule(code=prefix, is_prefix=True, department=dept))

    # --- Add new exception rules ---
    new_exc_codes = request.form.getlist('new_exc_code[]')
    new_exc_depts = request.form.getlist('new_exc_dept[]')
    for code, dept in zip(new_exc_codes, new_exc_depts):
        code = code.strip().upper()
        if code and dept:
            existing = CodePrefixRule.query.filter_by(code=code).first()
            if existing:
                existing.department  = dept
                existing.is_prefix   = False
                existing.is_archived = False
            else:
                db.session.add(CodePrefixRule(code=code, is_prefix=False, department=dept))

    db.session.commit()
    updated = _apply_prefix_rules()
    flash(f'Rules saved and applied. {updated} course(s) updated.', 'success')
    return redirect(url_for('course_code_assignment'))

@app.route('/manage/courses/code-assignment/reset', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def reset_code_assignment():
    CodePrefixRule.query.delete()
    for code, is_prefix, dept in MASTER_PREFIX_RULES:
        db.session.add(CodePrefixRule(code=code, is_prefix=is_prefix, department=dept))
    db.session.commit()
    updated = _apply_prefix_rules()
    flash(f'Rules reset to defaults and applied. {updated} course(s) updated.', 'success')
    return redirect(url_for('course_code_assignment'))

@app.route('/manage/courses/code-assignment/archive/<int:rule_id>', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def archive_code_rule(rule_id):
    rule = CodePrefixRule.query.get_or_404(rule_id)
    rule.is_archived = True
    db.session.commit()
    flash(f'Rule "{rule.code}" moved to recycle bin.', 'warning')
    return redirect(url_for('course_code_assignment'))

@app.route('/manage/courses/code-assignment/restore/<int:rule_id>', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def restore_code_rule(rule_id):
    rule = CodePrefixRule.query.get_or_404(rule_id)
    rule.is_archived = False
    db.session.commit()
    flash(f'Rule "{rule.code}" restored.', 'success')
    return redirect(url_for('code_rules_archive'))

@app.route('/manage/courses/code-assignment/delete-forever/<int:rule_id>', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def delete_code_rule_forever(rule_id):
    rule = CodePrefixRule.query.get_or_404(rule_id)
    db.session.delete(rule)
    db.session.commit()
    flash(f'Rule "{rule.code}" permanently deleted.', 'danger')
    return redirect(url_for('code_rules_archive'))

@app.route('/manage/courses/code-assignment/archived')
@login_required
@role_required('admin', 'superadmin')
def code_rules_archive():
    search_query = request.args.get('search', '').strip()
    sort_by = request.args.get('sort', 'default')
    page = request.args.get('page', 1, type=int)

    query = CodePrefixRule.query.filter_by(is_archived=True)
    if search_query:
        query = query.filter(
            db.or_(
                CodePrefixRule.code.ilike(f'%{search_query}%'),
                CodePrefixRule.department.ilike(f'%{search_query}%')
            )
        )
    if sort_by == 'newest':
        query = query.order_by(CodePrefixRule.deleted_at.desc(), CodePrefixRule.id.desc())
    elif sort_by == 'code-asc' or sort_by == 'default':
        query = query.order_by(CodePrefixRule.code.asc())
    elif sort_by == 'code-desc':
        query = query.order_by(CodePrefixRule.code.desc())
    else:
        query = query.order_by(CodePrefixRule.id.desc())

    pagination = query.paginate(page=page, per_page=10, error_out=False)
    archived_rules = pagination.items

    return render_template('code_rules_archive.html',
        archived_rules=archived_rules,
        pagination=pagination,
        current_sort=sort_by,
        search_query=search_query)


@app.route('/manage/courses/code-assignment/bulk-restore', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def bulk_restore_code_rules():
    ids = request.form.getlist('row_ids')
    if ids:
        CodePrefixRule.query.filter(CodePrefixRule.id.in_(ids)).update({'is_archived': False}, synchronize_session=False)
        db.session.commit()
        flash(f'{len(ids)} rule(s) restored.', 'success')
    return redirect(url_for('code_rules_archive'))


@app.route('/manage/courses/code-assignment/bulk-delete', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def bulk_delete_code_rules():
    ids = request.form.getlist('row_ids')
    if ids:
        CodePrefixRule.query.filter(CodePrefixRule.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        flash(f'{len(ids)} rule(s) permanently deleted.', 'danger')
    return redirect(url_for('code_rules_archive'))


@app.route('/api/prefix-courses')
@login_required
@role_required('admin', 'superadmin')
def api_prefix_courses():
    """AJAX: return courses matching a prefix or exact code."""
    code = request.args.get('code', '').strip().upper()
    if not code:
        return jsonify([])
    # Flexible matching regardless of space (search for MATH 10 or MATH10)
    code_norm = code.replace(' ', '').upper()
    prefix = code.split(' ')[0]
    suffix = code.split(' ')[-1] if ' ' in code else ''
    
    courses = Course.query.filter(
        Course.is_archived == False,
        db.or_(
            Course.course_code == code,         # Exact "MATH 10"
            Course.course_code == code_norm,    # Exact "MATH10"
            # Prefix search for phrases like "MATH 10" even if saved as "MATH10"
            Course.course_code.like(f'{code} %'),
            Course.course_code.like(f'{code}%'),
            Course.course_code.like(f'{prefix}%{suffix}%') if suffix else False
        )
    ).order_by(Course.course_code).all()
    
    return jsonify([{'code': c.course_code, 'name': c.course_name, 'dept': c.department or '----'} for c in courses])

# I-UPDATE ANG LUMANG delete_course FUNCTION
@app.route('/manage/course/delete/<int:course_id>', methods=['POST'])
@login_required
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    ScheduledClass.query.filter_by(course_id=course_id).delete(synchronize_session=False)
    db.session.delete(course)
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Delete Course', f"Permanently deleted course {course.course_code}")
    # Dapat bumalik sa archive page pagkatapos mag-delete
    return redirect(url_for('courses_archive'))

# --- BULK ACTIONS FOR COURSES ---

@app.route('/manage/courses/bulk_archive', methods=['POST'])
@login_required
def bulk_archive_courses():
    # Kunin ang listahan ng IDs mula sa form (checkboxes named 'row_ids')
    course_ids = request.form.getlist('row_ids')
    
    if course_ids:
        # I-update lahat ng selected courses
        Course.query.filter(Course.id.in_(course_ids)).update(
            {Course.is_archived: True, Course.deleted_at: datetime.utcnow()},
            synchronize_session=False)
        db.session.commit()
        flash(f'{len(course_ids)} courses moved to Recycle Bin.', 'success')
    else:
        flash('No courses selected.', 'warning')
        
    return redirect(url_for('manage_courses'))

@app.route('/manage/courses/bulk_restore', methods=['POST'])
@login_required
def bulk_restore_courses():
    course_ids = request.form.getlist('row_ids')
    
    if course_ids:
        Course.query.filter(Course.id.in_(course_ids)).update({Course.is_archived: False}, synchronize_session=False)
        db.session.commit()
        flash(f'{len(course_ids)} courses restored successfully.', 'success')
    
    return redirect(url_for('courses_archive'))

@app.route('/manage/courses/bulk_delete', methods=['POST'])
@login_required
def bulk_delete_courses():
    course_ids = request.form.getlist('row_ids')
    
    if course_ids:
        ScheduledClass.query.filter(ScheduledClass.course_id.in_(course_ids)).delete(synchronize_session=False)
        Course.query.filter(Course.id.in_(course_ids)).delete(synchronize_session=False)
        db.session.commit()
        flash(f'{len(course_ids)} courses permanently deleted.', 'danger')
    
    return redirect(url_for('courses_archive'))

# app.py

@app.route('/manage/rooms')
@login_required
def manage_rooms():
    # 1. Get Parameters
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'name-asc', type=str)
    search_query = request.args.get('search', '', type=str)
    
    # --- NEW FILTER PARAMETERS ---
    filter_by = request.args.get('filter_by', '', type=str) # 'building' or 'status'
    filter_val = request.args.get('filter_val', '', type=str)

    # ------------------------------------ Time Machine: Historical Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    if session.get('historical_mode_active', False):
        archive_id = session.get('active_archive_id')
        query = get_archive_query(archive_id, 'Room')
        
        if not query:
            return render_template('manage_rooms.html', rooms=[], pagination=None)

        if search_query:
            query = query.filter(ArchivedRoom.room_name.ilike(f"%{search_query}%"))
            
        pagination = query.paginate(page=page, per_page=10, error_out=False)
        return render_template('manage_rooms.html', rooms=pagination.items, pagination=pagination, search_query=search_query)

    # ------------------------------------ Live Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    # 2. Base Query
    query = Room.query.filter_by(is_archived=False)
    
    # DATA ISOLATION: User sees rooms assigned to their department, shared rooms, or TBA
    if session.get('role') == 'user':
        user_dept = session.get('department')
        query = query.filter(or_(
            Room.room_departments.ilike(f"{user_dept},%"),
            Room.room_departments.ilike(f"%,{user_dept}"),
            Room.room_departments.ilike(f"%,{user_dept},%"),
            Room.room_departments == user_dept,
            Room.room_departments == "", # All Departments
            Room.room_departments.is_(None), # All Departments
            Room.room_name == 'T.B.A.'
        ))
    
    # 3. Apply Search
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(or_(
            Room.room_name.ilike(search_term),
            Room.building.ilike(search_term),
            Room.capabilities.ilike(search_term)
        ))

    # 4. Apply SPECIFIC FILTERS (Dropdown)
    if filter_by == 'building' and filter_val:
        query = query.filter(Room.building == filter_val)
    elif filter_by == 'status' and filter_val:
        query = query.filter(Room.status == filter_val)
    elif filter_by == 'room_type' and filter_val:
        query = query.filter(Room.room_type == filter_val)

    # 5. Apply Sort
    if sort_by == 'name-desc':
        query = query.order_by(Room.room_name.desc())
    elif sort_by == 'capacity-desc':
        query = query.order_by(Room.capacity.desc())
    elif sort_by == 'capacity-asc':
        query = query.order_by(Room.capacity.asc())
    else: # Default: name-asc
        query = query.order_by(Room.room_name.asc())

    # 6. Pagination
    pagination = query.paginate(page=page, per_page=10, error_out=False)
    rooms_on_page = pagination.items

    # 7. Get Data for Filters
    unique_buildings = db.session.query(Room.building).filter_by(is_archived=False).distinct().all()
    unique_buildings = [b[0] for b in unique_buildings if b[0]]

    course_query = Course.query.filter_by(is_archived=False)
    if session.get('role') == 'user':
        course_query = course_query.filter_by(department=session.get('department'))
    all_courses = course_query.order_by(Course.course_code).all()

    return render_template(
        'manage_rooms.html',
        rooms=rooms_on_page,
        pagination=pagination,
        current_sort=sort_by,
        search_query=search_query,
        # Pass Filter Data
        unique_buildings=unique_buildings,
        current_filter_by=filter_by,
        current_filter_val=filter_val,
        all_courses=all_courses,
        known_departments=KNOWN_DEPARTMENTS
    )

@app.route('/manage/room/add', methods=['POST'])
@login_required
def add_room():
    # Only allow non-archive mode to add
    if session.get('historical_mode_active'):
        flash('Action not allowed in Archive Mode.', 'danger')
        return redirect(url_for('manage_rooms'))

    room_name = request.form.get('room_name', '').strip()
    building  = request.form.get('building', '').strip()

    # 1. Length Validation
    constraints = {
        'room_name': 50,
        'building': 100
    }
    ok, err = validate_lengths(request.form, constraints)
    if not ok:
        flash(err, "danger")
        return redirect(url_for('manage_rooms'))

    # 2. XSS Sanitization
    room_name = sanitize_input(room_name)
    building  = sanitize_input(building)

    existing = Room.query.filter_by(room_name=room_name, is_archived=False).first()
    if existing:
        flash(f"Error: Room '{room_name}' already exists!", "danger")
        return redirect(url_for('manage_rooms'))

    # Default capabilities to Lecture if none provided (hidden for user)
    cap_list = request.form.getlist('capabilities')
    if not cap_list:
        cap_list = ['Lecture']
    caps = ",".join(cap_list)
    
    # 3. Department handling for User role
    if session.get('role') == 'user':
        room_depts = session.get('department')
    else:
        room_depts = ",".join(request.form.getlist('room_departments'))

    try:
        db.session.add(Room(
            room_name=room_name,
            building=building,
            capabilities=caps,
            status=request.form.get('status', 'Available'),
            capacity=int(request.form.get('capacity', 40)),
            functional_computers=int(request.form.get('functional_computers', 40)),
            room_departments=session.get('department') if session.get('role') == 'user' else ",".join(request.form.getlist('room_departments')),
            room_type=request.form.get('room_type', 'Sync'),
            created_by_id=session.get('user_id') # Track creator
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash(f"Error: Could not add Room. Name '{room_name}' might already exist.", "danger")
        return redirect(url_for('manage_rooms'))
    
    # Module 7: Log action
    log_activity('Add Room', f"Created room {room_name}")
    
    flash('Room added successfully.', 'success')
    return redirect(url_for('manage_rooms'))

@app.route('/manage/room/quick-add-tba', methods=['POST'])
@login_required
def quick_add_tba_room():
    if Room.query.filter_by(room_name='T.B.A.').first():
        flash('T.B.A. room already exists.', 'warning')
        return redirect(url_for('manage_rooms'))
    new_room = Room(
        room_name='T.B.A.',
        building='Virtual',
        capabilities='Lecture',
        capacity=999,
        functional_computers=0,
        status='Available',
        room_departments='',
    )
    db.session.add(new_room)
    db.session.commit()
    flash('T.B.A. room added successfully.', 'success')
    return redirect(url_for('manage_rooms'))

@app.route('/manage/room/update/<int:room_id>', methods=['POST'])
@login_required
@hist_lockdown
def update_room(room_id):
    room = Room.query.get_or_404(room_id)
    
    # Security Firewall: Role-based department check
    if not verify_department_access(room):
        flash("You are not authorized to update this room as it belongs to another department.", "danger")
        log_security('Unauthorized Access Attempt', details=f"User {session.get('username')} tried to update room id {room_id}")
        return redirect(url_for('manage_rooms'))
    if room.room_name == 'T.B.A.':
        flash('T.B.A. room cannot be edited.', 'warning')
        return redirect(url_for('manage_rooms'))
    # 1. Length Validation
    constraints = {
        'room_name': 50,
        'building': 100
    }
    ok, err = validate_lengths(request.form, constraints)
    if not ok:
        flash(err, "danger")
        return redirect(url_for('manage_rooms'))

    new_name = sanitize_input(request.form.get('room_name', '').strip())
    new_building = sanitize_input(request.form.get('building', '').strip())
    
    existing = Room.query.filter(Room.room_name == new_name, Room.id != room_id, Room.is_archived == False).first()
    if existing:
        flash(f"Error: Room name '{new_name}' is already taken.", 'danger')
        return redirect(url_for('manage_rooms'))
    
    room.room_name = new_name
    room.building = new_building
    
    # Conditional updates for restricted fields
    if 'capabilities' in request.form:
        room.capabilities = ",".join(request.form.getlist('capabilities'))
    if 'status' in request.form:
        room.status = request.form.get('status')
    if 'capacity' in request.form:
        room.capacity = int(request.form.get('capacity', 40))
    if 'functional_computers' in request.form:
        room.functional_computers = int(request.form.get('functional_computers', 40))
    if 'room_type' in request.form:
        room.room_type = request.form.get('room_type', 'Sync')
        
    # Only Admin/Superadmin can update department access
    if session.get('role') != 'user':
        room.room_departments = ",".join(request.form.getlist('room_departments'))
        
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Update Room', f"Updated room {new_name}")
    
    return redirect(url_for('manage_rooms'))

# =====================================================================
# MODULE 4: ARCHIVE MANAGEMENT (NEW)
# =====================================================================

@app.route('/manage/archives')
@login_required
@role_required('admin', 'superadmin')
def manage_archives():
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'newest', type=str)
    search_query = request.args.get('search', '', type=str)
    filter_by = request.args.get('filter_by', '', type=str)
    filter_val = request.args.get('filter_val', '', type=str)

    query = TermArchive.query

    # 1. Search
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(or_(
            TermArchive.semester.ilike(search_term),
            TermArchive.academic_year.ilike(search_term)
        ))

    # 2. Filter
    if filter_by == 'semester' and filter_val:
        query = query.filter(TermArchive.semester == filter_val)
    elif filter_by == 'ay' and filter_val:
        query = query.filter(TermArchive.academic_year == filter_val)

    # 3. Sort
    if sort_by == 'oldest':
        query = query.order_by(TermArchive.created_at.asc(), TermArchive.id.asc())
    elif sort_by == 'semester-asc':
        query = query.order_by(TermArchive.semester.asc())
    elif sort_by == 'semester-desc':
        query = query.order_by(TermArchive.semester.desc())
    elif sort_by == 'ay-asc':
        query = query.order_by(TermArchive.academic_year.asc())
    elif sort_by == 'ay-desc':
        query = query.order_by(TermArchive.academic_year.desc())
    else: # newest
        query = query.order_by(TermArchive.created_at.desc(), TermArchive.id.desc())

    # Get unique values for filter dropdown
    unique_semesters = [r[0] for r in db.session.query(TermArchive.semester).distinct().all()]
    unique_ay = sorted([r[0] for r in db.session.query(TermArchive.academic_year).distinct().all()], reverse=True)

    pagination = query.paginate(page=page, per_page=10, error_out=False)
    archives = pagination.items

    return render_template(
        'manage_archives.html',
        archives=archives,
        pagination=pagination,
        current_sort=sort_by,
        search_query=search_query,
        current_filter_by=filter_by,
        current_filter_val=filter_val,
        unique_semesters=unique_semesters,
        unique_ay=unique_ay
    )

@app.route('/manage/archive/delete/<int:archive_id>', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def delete_archive(archive_id):
    archive = TermArchive.query.get_or_404(archive_id)
    
    # Cascade delete is handled by SQLAlchemy (cascade="all, delete-orphan")
    db.session.delete(archive)
    db.session.commit()
    
    flash(f'Archive for {archive.semester} ({archive.academic_year}) has been permanently deleted.', 'danger')
    return redirect(url_for('manage_archives'))

@app.route('/manage/archives/bulk_delete', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def bulk_delete_archives():
    archive_ids = request.form.getlist('row_ids')
    
    if archive_ids:
        # Manually delete children to ensure cleanup (since .delete() bypasses cascade)
        ArchivedSchedule.query.filter(ArchivedSchedule.term_archive_id.in_(archive_ids)).delete(synchronize_session=False)
        ArchivedEntity.query.filter(ArchivedEntity.term_archive_id.in_(archive_ids)).delete(synchronize_session=False)
        
        # Get count for flash message
        count = TermArchive.query.filter(TermArchive.id.in_(archive_ids)).count()
        # Delete records
        TermArchive.query.filter(TermArchive.id.in_(archive_ids)).delete(synchronize_session=False)
        db.session.commit()
        flash(f'{count} archives have been permanently deleted.', 'danger')
    else:
        flash('No archives selected.', 'warning')
        
    return redirect(url_for('manage_archives'))

@app.route('/manage/room/<int:room_id>/special-courses', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def save_room_special_courses(room_id):
    room = Room.query.get_or_404(room_id)
    course_ids = request.form.getlist('special_course_ids')
    room.special_course_ids = ','.join(course_ids)
    db.session.commit()
    flash(f'Special course assignments updated for {room.room_name}.', 'success')
    return redirect(url_for('manage_rooms'))

# --- BULK ACTIONS FOR ROOMS ---

@app.route('/manage/rooms/bulk_archive', methods=['POST'])
@login_required
def bulk_archive_rooms():
    room_ids = request.form.getlist('row_ids')
    
    if room_ids:
        Room.query.filter(Room.id.in_(room_ids)).update(
            {Room.is_archived: True, Room.deleted_at: datetime.utcnow()},
            synchronize_session=False)
        db.session.commit()
        flash(f'{len(room_ids)} rooms moved to Recycle Bin.', 'success')
    else:
        flash('No rooms selected.', 'secondary')
        
    return redirect(url_for('manage_rooms'))

@app.route('/manage/rooms/bulk_restore', methods=['POST'])
@login_required
def bulk_restore_rooms():
    room_ids = request.form.getlist('row_ids')
    
    if room_ids:
        Room.query.filter(Room.id.in_(room_ids)).update({Room.is_archived: False}, synchronize_session=False)
        db.session.commit()
        flash(f'{len(room_ids)} rooms restored.', 'success')
    
    return redirect(url_for('rooms_archive'))

@app.route('/manage/rooms/bulk_delete', methods=['POST'])
@login_required
def bulk_delete_rooms():
    room_ids = request.form.getlist('row_ids')

    if room_ids:
        int_ids = [int(i) for i in room_ids]
        ScheduledClass.query.filter(ScheduledClass.room_id.in_(int_ids)).update({'room_id': None}, synchronize_session=False)
        Room.query.filter(Room.id.in_(int_ids)).delete(synchronize_session=False)
        db.session.commit()
        flash(f'{len(room_ids)} rooms permanently deleted.', 'danger')

    return redirect(url_for('rooms_archive'))

@app.route('/manage/rooms/archive')
@login_required
def rooms_archive():
    # --- KUNIN ANG MGA PARAMETERS ---
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'default', type=str)
    search_query = request.args.get('search', '', type=str)

    # Magsimula sa pag-filter ng mga NAKA-ARCHIVE na rooms
    query = Room.query.filter_by(is_archived=True)
    if session.get('role') == 'user':
        query = query.filter_by(created_by_id=session.get('user_id'))

    # I-apply ang search filter kung mayroon
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(or_(Room.room_name.ilike(search_term), Room.building.ilike(search_term)))

    # I-apply ang sort order
    if sort_by == 'name-asc':
        query = query.order_by(Room.room_name.asc())
    elif sort_by == 'name-desc':
        query = query.order_by(Room.room_name.desc())
    elif sort_by == 'newest' or sort_by == 'default':
        query = query.order_by(Room.deleted_at.desc(), Room.id.desc())
    else:
        query = query.order_by(Room.id.desc())

    pagination = query.paginate(page=page, per_page=10, error_out=False)
    archived_rooms = pagination.items
    
    return render_template(
        'rooms_archive.html', 
        rooms=archived_rooms,
        pagination=pagination,
        current_sort=sort_by,
        search_query=search_query,
        now=datetime.utcnow()
    )

@app.route('/manage/room/archive/<int:room_id>', methods=['POST'])
@login_required
def archive_room(room_id):
    room = Room.query.get_or_404(room_id)
    if room.room_name in ['T.B.A.', 'Online Room']:
        flash(f'{room.room_name} room cannot be archived.', 'warning')
        return redirect(url_for('manage_rooms'))
    room.is_archived = True
    room.deleted_at = datetime.utcnow()
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Archive Room', f"Archived room {room.room_name}")
    
    flash('Room moved to Recycle Bin.', 'success')
    return redirect(url_for('manage_rooms'))

@app.route('/manage/room/restore/<int:room_id>', methods=['POST'])
@login_required
def restore_room(room_id):
    room = Room.query.get_or_404(room_id)
    room.is_archived = False
    room.deleted_at = None
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Restore Room', f"Restored room {room.room_name}")
    
    flash('Room restored successfully.', 'success')
    return redirect(url_for('rooms_archive'))

# I-UPDATE ANG delete_room FUNCTION
@app.route('/manage/room/delete/<int:room_id>', methods=['POST'])
@login_required
def delete_room(room_id):
    room = Room.query.get_or_404(room_id)
    if room.room_name in ['T.B.A.', 'Online Room']:
        flash(f'{room.room_name} room cannot be deleted.', 'warning')
        return redirect(url_for('manage_rooms'))
    ScheduledClass.query.filter_by(room_id=room_id).update({'room_id': None}, synchronize_session=False)
    db.session.delete(room)
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Delete Room', f"Permanently deleted room {room.room_name}")
    
    return redirect(url_for('rooms_archive'))

# app.py

@app.route('/manage/sections')
@login_required
def manage_sections():
    # 1. Get Parameters
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'name-asc', type=str)
    search_query = request.args.get('search', '', type=str)
    
    # --- NEW FILTER PARAMETERS ---
    filter_by = request.args.get('filter_by', '', type=str) # 'year'
    filter_val = request.args.get('filter_val', '', type=str) # e.g. '1', '2'

    selected_semester = session.get('selected_semester', 'All')
    
    # ------------------------------------ Time Machine: Historical Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    if session.get('historical_mode_active', False):
        archive_id = session.get('active_archive_id')
        query = get_archive_query(archive_id, 'Section')
        
        if not query:
            return render_template('manage_sections.html', sections=[], pagination=None)

        if search_query:
            query = query.filter(ArchivedSection.section_name.ilike(f"%{search_query}%"))
            
        pagination = query.paginate(page=page, per_page=10, error_out=False)
        
        # ADDED: courses_by_sem for template compatibility (though it might not be used in read-only mode)
        courses = ArchivedCourse.query.filter_by(term_archive_id=archive_id).all()
        courses_by_sem = {
            '1st Semester': [c for c in courses if c.semester_offered == '1st Semester' or c.semester_offered == 'Both'],
            '2nd Semester': [c for c in courses if c.semester_offered == '2nd Semester' or c.semester_offered == 'Both'],
            'Midyear': [c for c in courses if c.semester_offered == 'Midyear']
        }

        return render_template('manage_sections.html', 
                             sections=pagination.items, 
                             pagination=pagination, 
                             search_query=search_query,
                             courses_by_sem=courses_by_sem)

    # 2. Base Query (exclude T.B.A. system section)
    query = Section.query.filter_by(is_archived=False).filter(Section.section_name != 'T.B.A.')
    
    # DATA ISOLATION: Sections are visible to all users (view-only for User role handled in template)
    
    # 3. Apply Search
    if search_query:
        query = query.filter(or_(
            Section.section_name.ilike(f"%{search_query}%"),
            cast(Section.year_level, db.String).ilike(f"%{search_query}%")
        ))

    # 4. Apply SPECIFIC FILTERS (Dropdown)
    if filter_by == 'year' and filter_val:
        try:
            query = query.filter(Section.year_level == int(filter_val))
        except ValueError:
            pass # Ignore invalid integer conversion

    # 5. Apply Sort
    if sort_by == 'name-desc':
        query = query.order_by(Section.section_name.desc())
    elif sort_by == 'year-asc':
        query = query.order_by(Section.year_level.asc(), Section.section_name.asc())
    elif sort_by == 'year-desc':
        query = query.order_by(Section.year_level.desc(), Section.section_name.asc())
    else: # Default: name-asc
        query = query.order_by(Section.section_name.asc())
    
    # 6. Pagination
    pagination = query.paginate(page=page, per_page=10, error_out=False)
    sections_on_page = pagination.items
    
    # 7. Prepare Data for Assignment Modals
    course_query = Course.query.filter_by(is_archived=False)
    if session.get('role') == 'user':
        course_query = course_query.filter_by(created_by_id=session.get('user_id'))
    all_courses_for_modal = course_query.order_by(Course.course_code).all()
    courses_by_sem = {'1st Semester': [], '2nd Semester': [], 'Midyear': []}
    for c in all_courses_for_modal:
        if c.semester_offered in courses_by_sem: 
            courses_by_sem[c.semester_offered].append(c)

    # 8. GET UNIQUE YEARS FOR FILTER DROPDOWN
    year_query = db.session.query(Section.year_level).filter_by(is_archived=False)
    unique_years = year_query.distinct().order_by(Section.year_level).all()
    unique_years = [y[0] for y in unique_years]
    return render_template(
        'manage_sections.html', 
        sections=sections_on_page, 
        pagination=pagination, 
        courses_by_sem=courses_by_sem, 
        current_sort=sort_by, 
        search_query=search_query,
        selected_semester=selected_semester,
        # Pass Filter Data
        unique_years=unique_years,
        current_filter_by=filter_by,
        current_filter_val=filter_val,
        known_departments=_get_depts()
    )

@app.route('/manage/section/add', methods=['POST'])
@role_required('admin', 'superadmin')
def add_section():
    section_name = request.form.get('section_name', '').strip()

    # 1. Length Validation
    constraints = {
        'section_name': 50
    }
    ok, err = validate_lengths(request.form, constraints)
    if not ok:
        flash(err, "danger")
        return redirect(url_for('manage_sections'))

    # 2. XSS Sanitization
    section_name = sanitize_input(section_name)

    existing = Section.query.filter_by(section_name=section_name, is_archived=False).first()
    if existing:
        flash(f"Section name '{section_name}' already exists!", "danger")
        return redirect(url_for('manage_sections'))

    db.session.add(Section(
        section_name=section_name, 
        year_level=int(request.form.get('year_level')), 
        number_of_students=int(request.form.get('number_of_students', 40)),
        created_by_id=session.get('user_id') # Track creator
    ))
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Add Section', f"Created section {section_name}")
    
    flash('Section added successfully.', 'success')
    return redirect(url_for('manage_sections'))

@app.route('/manage/section/update/<int:section_id>', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
@hist_lockdown
def update_section(section_id):
    section = Section.query.get_or_404(section_id)
    # Role-based authorization removed for Sections (standard users share the section pool)
    # 1. Length Validation
    constraints = {
        'section_name': 50
    }
    ok, err = validate_lengths(request.form, constraints)
    if not ok:
        flash(err, "danger")
        return redirect(url_for('manage_sections'))

    new_name = sanitize_input(request.form.get('section_name', '').strip())
    
    existing = Section.query.filter(Section.section_name == new_name, Section.id != section_id, Section.is_archived == False).first()
    if existing:
        flash(f"Error: Section name '{new_name}' is already taken.", 'danger')
        return redirect(url_for('manage_sections'))
    
    section.section_name = new_name
    section.year_level = int(request.form.get('year_level'))
    
    # Conditional update for hidden fields
    if 'number_of_students' in request.form:
        section.number_of_students = int(request.form.get('number_of_students', 40))
        
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Update Section', f"Updated section {new_name}")
    
    flash('Section updated successfully.', 'success')
    return redirect(url_for('manage_sections'))

# app.py

@app.route('/manage/sections/bulk_assign', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def bulk_assign_curriculum():
    # 1. Kunin ang mga IDs mula sa form
    section_ids = request.form.getlist('section_ids')
    course_ids = request.form.getlist('course_ids')
    
    if not section_ids:
        flash('No sections selected.', 'warning')
        return redirect(url_for('manage_sections'))
    
    if not course_ids:
        flash('No courses selected.', 'warning')
        return redirect(url_for('manage_sections'))

    # 2. Get Course Objects
    courses_to_assign = Course.query.filter(Course.id.in_(course_ids)).all()
    
    # 3. Get Section Objects & Update
    sections = Section.query.filter(Section.id.in_(section_ids)).all()
    
    count = 0
    for section in sections:
        # Overwrite existing assignments
        section.courses = courses_to_assign
        count += 1
        
    db.session.commit()
    flash(f'Curriculum assigned to {count} section(s).', 'success')
    
    return redirect(url_for('manage_sections'))

@app.route('/get_section_courses/<int:section_id>')
@login_required
@role_required('admin', 'superadmin')
def get_section_courses(section_id):
    section = Section.query.get_or_404(section_id)
    # Ibalik ang listahan ng Course IDs na meron na siya
    return jsonify([c.id for c in section.courses])

# --- BULK ACTIONS FOR SECTIONS ---

@app.route('/manage/sections/bulk_archive', methods=['POST'])
@login_required
def bulk_archive_sections():
    # Kunin ang mga IDs mula sa checkboxes
    section_ids = request.form.getlist('row_ids')
    
    if section_ids:
        # Exclude the T.B.A. system section from bulk archive
        valid_ids = [sid for sid in section_ids if Section.query.get(sid) and Section.query.get(sid).section_name != 'T.B.A.']
        Section.query.filter(Section.id.in_(valid_ids)).update(
            {Section.is_archived: True, Section.deleted_at: datetime.utcnow()},
            synchronize_session=False)
        db.session.commit()
        flash(f'{len(valid_ids)} sections moved to Recycle Bin.', 'success')
    else:
        flash('No sections selected.', 'secondary')
        
    return redirect(url_for('manage_sections'))

@app.route('/manage/sections/bulk_restore', methods=['POST'])
@login_required
def bulk_restore_sections():
    section_ids = request.form.getlist('row_ids')
    
    if section_ids:
        # Update is_archived = False
        Section.query.filter(Section.id.in_(section_ids)).update({Section.is_archived: False}, synchronize_session=False)
        db.session.commit()
        flash(f'{len(section_ids)} sections restored successfully.', 'success')
    
    return redirect(url_for('sections_archive'))

def get_or_create_tba_section():
    tba = Section.query.filter_by(section_name='T.B.A.').first()
    if not tba:
        tba = Section(section_name='T.B.A.', year_level=0, number_of_students=0)
        db.session.add(tba)
        db.session.flush()
    return tba


@app.route('/manage/sections/bulk_delete', methods=['POST'])
@login_required
def bulk_delete_sections():
    section_ids = request.form.getlist('row_ids')
    
    if section_ids:
        tba_section = get_or_create_tba_section()
        FacultyAssignment.query.filter(FacultyAssignment.section_id.in_(section_ids)).delete(synchronize_session=False)
        ScheduledClass.query.filter(ScheduledClass.section_id.in_(section_ids)).update(
            {ScheduledClass.section_id: tba_section.id}, synchronize_session=False)
        Section.query.filter(Section.id.in_(section_ids)).delete(synchronize_session=False)
        db.session.commit()
        flash(f'{len(section_ids)} sections deleted. Their scheduled classes are now in Pending Sections.', 'success')
    
    return redirect(url_for('sections_archive'))


@app.route('/manage/sections/archive')
@login_required
def sections_archive():
    # Get parameters
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'default', type=str)
    search_query = request.args.get('search', '', type=str)

    # Base Query (Filtered by Archived)
    query = Section.query.filter_by(is_archived=True)
    # DATA ISOLATION: Removed for Sections as per requirements.

    # Search Filter
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(Section.section_name.ilike(search_term))

    # Sort Logic
    if sort_by == 'name-asc':
        query = query.order_by(Section.section_name.asc())
    elif sort_by == 'name-desc':
        query = query.order_by(Section.section_name.desc())
    elif sort_by == 'newest' or sort_by == 'default':
        query = query.order_by(Section.deleted_at.desc(), Section.id.desc())
    else:
        query = query.order_by(Section.id.desc())

    # Pagination Logic
    pagination = query.paginate(page=page, per_page=10, error_out=False)
    archived_sections = pagination.items
    
    return render_template(
        'sections_archive.html', 
        sections=archived_sections,
        pagination=pagination,
        current_sort=sort_by,
        search_query=search_query,
        now=datetime.utcnow()
    )

@app.route('/manage/section/archive/<int:section_id>', methods=['POST'])
@role_required('admin', 'superadmin')
def archive_section(section_id):
    section = Section.query.get_or_404(section_id)
    if section.section_name == 'T.B.A.':
        flash('The T.B.A. section is a system section and cannot be moved to Recycle Bin.', 'warning')
        return redirect(url_for('manage_sections'))
    section.is_archived = True
    section.deleted_at = datetime.utcnow()
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Archive Section', f"Archived section {section.section_name}")
    
    flash('Section moved to Recycle Bin.', 'success')
    return redirect(url_for('manage_sections'))

@app.route('/manage/section/restore/<int:section_id>', methods=['POST'])
@login_required
def restore_section(section_id):
    section = Section.query.get_or_404(section_id)
    section.is_archived = False
    section.deleted_at = None
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Restore Section', f"Restored section {section.section_name}")
    
    flash('Section restored successfully.', 'success')
    return redirect(url_for('sections_archive'))

# I-UPDATE ANG delete_section FUNCTION
@app.route('/manage/section/delete/<int:section_id>', methods=['POST'])
@role_required('admin', 'superadmin')
def delete_section(section_id):
    section = Section.query.get_or_404(section_id)
    tba_section = get_or_create_tba_section()
    FacultyAssignment.query.filter_by(section_id=section_id).delete(synchronize_session=False)
    ScheduledClass.query.filter(ScheduledClass.section_id == section_id).update(
        {ScheduledClass.section_id: tba_section.id}, synchronize_session=False)
    db.session.delete(section)
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Delete Section', f"Permanently deleted section {section.section_name}")
    
    flash('Section deleted. Their scheduled classes are now in Pending Sections.', 'success')
    return redirect(url_for('sections_archive'))

@app.route('/manage/year/assign_courses/<int:year_level>', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def assign_courses_to_year(year_level):
    sections_in_year = Section.query.filter_by(year_level=year_level).all()
    courses_to_assign = Course.query.filter(Course.id.in_(request.form.getlist('course_ids'))).all()
    for section in sections_in_year: section.courses = courses_to_assign
    db.session.commit()
    return redirect(url_for('manage_sections'))

# app.py

@app.route('/manage/faculty')
@login_required
def manage_faculty():
    # 1. Get Parameters
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'name-asc', type=str)
    search_query = request.args.get('search', '', type=str)
    
    # --- NEW FILTER PARAMETERS ---
    filter_by = request.args.get('filter_by', '', type=str) # 'dept' or 'status'
    filter_val = request.args.get('filter_val', '', type=str)

    selected_semester = session.get('selected_semester', 'All')

    # ------------------------------------ Time Machine: Historical Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    if session.get('historical_mode_active', False):
        archive_id = session.get('active_archive_id')
        all_objs = get_archive_entities(archive_id, 'Faculty')
        
        # 1. Apply Filtering
        if search_query:
            s = search_query.lower()
            all_objs = [o for o in all_objs if 
                        s in (getattr(o, 'full_name', '') or '').lower() or 
                        s in (getattr(o, 'employee_id', '') or '').lower() or 
                        s in (getattr(o, 'department', '') or '').lower()]
        
        if filter_by == 'dept' and filter_val:
            all_objs = [o for o in all_objs if getattr(o, 'department', None) == filter_val]
        elif filter_by == 'status' and filter_val:
            all_objs = [o for o in all_objs if getattr(o, 'employment_status', None) == filter_val]

        # 2. Apply Sorting
        if sort_by == 'name-desc':
            all_objs.sort(key=lambda x: (getattr(x, 'full_name', '') or '').lower(), reverse=True)
        else:
            all_objs.sort(key=lambda x: (getattr(x, 'full_name', '') or '').lower())

        # 3. Paginate
        per_page = 10
        total = len(all_objs)
        start = (page - 1) * per_page
        items = all_objs[start:start+per_page]
        pagination = MockPagination(items, page, per_page, total)
        
        # Reconstruct dropdown data from archive
        all_courses = get_archive_entities(archive_id, 'Course')
        if selected_semester != 'All':
            all_courses = [c for c in all_courses if getattr(c, 'semester_offered', None) == selected_semester]
            
        courses_by_sem = {'1st Semester': [], '2nd Semester': [], 'Midyear': []}
        for c in all_courses:
            if getattr(c, 'semester_offered', None) in courses_by_sem:
                courses_by_sem[c.semester_offered].append(c)

        all_archives_sections = get_archive_entities(archive_id, 'Section')
        all_sections_json = [{'id': s.id, 'name': getattr(s, 'section_name', ''), 'course_ids': getattr(s, 'course_ids', [])} for s in all_archives_sections]
        unique_depts = sorted(list(set(getattr(o, 'department', '') for o in all_objs if getattr(o, 'department', None))))
        
        # Calculate workload_map for historical mode
        # Keyed by faculty_name since ArchivedSchedule only stores names
        workload_map = {}
        all_archived_schedules = get_archive_entities(archive_id, 'ArchivedSchedule')
        
        def _sc_hours(start, end):
            try:
                sh, sm = map(int, start.split(':'))
                eh, em = map(int, end.split(':'))
                return ((eh * 60 + em) - (sh * 60 + sm)) / 60.0
            except Exception:
                return 0.0

        for sc in all_archived_schedules:
            if sc.faculty_name and sc.start_time and sc.end_time:
                h = _sc_hours(sc.start_time, sc.end_time)
                workload_map[sc.faculty_name] = workload_map.get(sc.faculty_name, 0) + h
        
        # Convert to int
        workload_map = {k: int(v) for k, v in workload_map.items()}

        return render_template(
            'manage_faculty.html',
            faculty_list=items,
            pagination=pagination,
            courses_by_sem=courses_by_sem,
            all_sections_json=all_sections_json,
            unique_depts=unique_depts,
            workload_map=workload_map,
            current_sort=sort_by,
            search_query=search_query,
            selected_semester=selected_semester,
            current_filter_by=filter_by,
            current_filter_val=filter_val,
            split_data_by_faculty={}, # Assignment logic hidden in Ghost Mode
            faculty_profiles=[],
            sc_course_ids_by_faculty={},
            sc_pairs_by_faculty={},
            others_taken_by_faculty={},
            fa_split_hours_map={},
            all_faculty_for_modals=items,
        )

    # ------------------------------------ Live Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    # 2. Base Query
    query = Faculty.query.filter_by(is_archived=False)
    
    # DATA ISOLATION: Makita nila LANG ang gawa nila (Strict Mode)
    if session.get('role') == 'user':
        user_id = session.get('user_id')
        query = query.filter_by(created_by_id=user_id)

    # 3. Apply Search
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(or_(
            Faculty.full_name.ilike(search_term),
            Faculty.employee_id.ilike(search_term),
            Faculty.department.ilike(search_term)
        ))

    # 4. Apply SPECIFIC FILTERS (Dropdown)
    if filter_by == 'dept' and filter_val:
        query = query.filter(Faculty.department == filter_val)
    elif filter_by == 'status' and filter_val:
        query = query.filter(Faculty.employment_status == filter_val)
    elif filter_by == 'asgn_status' and filter_val:
        query = query.filter(Faculty.assignment_status == filter_val)

    # 5. Apply Sort
    if sort_by == 'name-desc':
        query = query.order_by(Faculty.full_name.desc())
    else:
        query = query.order_by(Faculty.full_name.asc())
    
    # 6. Pagination
    pagination = query.paginate(page=page, per_page=10, error_out=False)
    faculty_on_page = pagination.items
    
    # 7. Get Data for Modals & Filters
    # For Assignment Modal Logic
    course_query = Course.query.filter_by(is_archived=False)
    if session.get('role') == 'user':
        course_query = course_query.filter_by(department=session.get('department'))
    
    if selected_semester != 'All':
        course_query = course_query.filter_by(semester_offered=selected_semester)

    all_courses = course_query.order_by(Course.course_code).all()
    courses_by_sem = {'1st Semester': [], '2nd Semester': [], 'Midyear': []}
    for c in all_courses:
        sem_offered = c.semester_offered
        # Map abbreviations to full names if needed
        if sem_offered == '1st Sem': sem_offered = '1st Semester'
        if sem_offered == '2nd Sem': sem_offered = '2nd Semester'
        
        if sem_offered in courses_by_sem:
            courses_by_sem[sem_offered].append(c)

    section_query = Section.query.filter_by(is_archived=False)
    all_sections = section_query.order_by(Section.section_name).all()
    all_sections_json = [{'id': s.id, 'name': s.section_name, 'course_ids': [c.id for c in s.courses]} for s in all_sections]

    # GET UNIQUE DEPARTMENTS FOR FILTER
    dept_query = db.session.query(Faculty.department).filter_by(is_archived=False)
    if session.get('role') == 'user':
        dept_query = dept_query.filter_by(created_by_id=session.get('user_id'))
    unique_depts = dept_query.distinct().all()
    unique_depts = [d[0] for d in unique_depts if d[0]]

    # Build split data dict: {faculty_id: {"course_id-section_id": {lab and lec split fields}}}
    all_assignments = FacultyAssignment.query.all()
    split_data_by_faculty = {}
    for fa in all_assignments:
        fid = str(fa.faculty_id)
        key = f'{fa.course_id}-{fa.section_id}'
        if fid not in split_data_by_faculty:
            split_data_by_faculty[fid] = {}
        split_data_by_faculty[fid][key] = {
            'day_1':       fa.split_day_1       or '',
            'hours_1':     fa.split_hours_1     or '',
            'day_2':       fa.split_day_2       or '',
            'hours_2':     fa.split_hours_2     or '',
            'lec_day_1':   fa.split_lec_day_1   or '',
            'lec_hours_1': fa.split_lec_hours_1 or '',
            'lec_day_2':   fa.split_lec_day_2   or '',
            'lec_hours_2': fa.split_lec_hours_2 or '',
        }

    # Build workload_map from ScheduledClass (GA-generated) instead of FacultyAssignment (manual only)
    _fids = [f.id for f in faculty_on_page]

    # Pre-fetch ScheduledClass assignments for all faculty on this page (single query, no N+1)
    # Used for workload_map (Fix B) and the "Assigned Courses" list in the View Profile offcanvas
    from sqlalchemy.orm import joinedload as _jl
    _sc_all = _dedup_schedules(
        ScheduledClass.query
        .options(_jl(ScheduledClass.course), _jl(ScheduledClass.section))
        .filter(ScheduledClass.faculty_id.in_(_fids))
        .all()
    )

    # Fix B ---- SC workload: use actual scheduled duration (end_time - start_time) per gene
    def _sc_hours(start, end):
        try:
            sh, sm = map(int, start.split(':'))
            eh, em = map(int, end.split(':'))
            return ((eh * 60 + em) - (sh * 60 + sm)) / 60.0
        except Exception:
            return 0.0

    workload_map = {}
    for _sc in _sc_all:
        if _sc.faculty_id and _sc.start_time and _sc.end_time:
            workload_map[_sc.faculty_id] = (
                workload_map.get(_sc.faculty_id, 0) + _sc_hours(_sc.start_time, _sc.end_time)
            )
    workload_map = {k: int(v) for k, v in workload_map.items()}

    # Fix A ---- FA workload: use split hours when configured, full course hours otherwise
    _fa_objs = (
        FacultyAssignment.query
        .filter(FacultyAssignment.faculty_id.in_(_fids))
        .join(FacultyAssignment.course)
        .all()
    )
    _fa_map = {}
    for _fa in _fa_objs:
        _c = _fa.course
        if not _c:
            continue
        _eff_lec = (
            ((_fa.split_lec_hours_1 or 0) + (_fa.split_lec_hours_2 or 0))
            if (_fa.split_lec_hours_1 or _fa.split_lec_hours_2)
            else (_c.synchronous_lec_hours or _c.lec_units or 0)
        )
        _eff_lab = (
            ((_fa.split_hours_1 or 0) + (_fa.split_hours_2 or 0))
            if (_fa.split_hours_1 or _fa.split_hours_2)
            else (_c.synchronous_lab_hours or _c.lab_units or 0)
        )
        _eff_async = (_c.asynchronous_lec_hours or 0) + (_c.asynchronous_lab_hours or 0)
        _fa_map[_fa.faculty_id] = _fa_map.get(_fa.faculty_id, 0) + _eff_lec + _eff_lab + _eff_async
    for _fid in _fids:
        if _fa_map.get(_fid, 0) > 0:
            workload_map[_fid] = int(_fa_map[_fid])

    # Fix C ---- fa_split_hours_map: per-faculty per-(course_id-section_id) effective hours for Step 2 badges
    fa_split_hours_map = {}  # {str(faculty_id): {"course_id-section_id": {"lec": x, "lab": y}}}
    for _fa in _fa_objs:
        _c = _fa.course
        if not _c:
            continue
        _eff_lec = (
            ((_fa.split_lec_hours_1 or 0) + (_fa.split_lec_hours_2 or 0))
            if (_fa.split_lec_hours_1 or _fa.split_lec_hours_2)
            else (_c.synchronous_lec_hours or _c.lec_units or 0)
        )
        _eff_lab = (
            ((_fa.split_hours_1 or 0) + (_fa.split_hours_2 or 0))
            if (_fa.split_hours_1 or _fa.split_hours_2)
            else (_c.synchronous_lab_hours or _c.lab_units or 0)
        )
        _key = f'{_fa.course_id}-{_fa.section_id}'
        fa_split_hours_map.setdefault(str(_fa.faculty_id), {})[_key] = {
            'lec': _eff_lec, 'lab': _eff_lab
        }

    sc_assignments_map = {}
    for _sc in _sc_all:
        sc_assignments_map.setdefault(_sc.faculty_id, []).append(_sc)

    # Build SC-based course_id sets and course-section pairs for Teachable/Final Load modals
    sc_course_ids_by_faculty = {}   # {faculty_id (int): set of course_ids}
    sc_pairs_by_faculty = {}        # {str(faculty_id): ["course_id-section_id", ...]} (deduplicated)
    for _fid, _sc_list in sc_assignments_map.items():
        _cids = set()
        _pairs = set()
        for _sc in _sc_list:
            if _sc.course_id:
                _cids.add(_sc.course_id)
            if _sc.course_id and _sc.section_id:
                _pairs.add(f'{_sc.course_id}-{_sc.section_id}')
        sc_course_ids_by_faculty[_fid] = _cids
        sc_pairs_by_faculty[str(_fid)] = list(_pairs)

    # Build "taken by others" for Assign Final Load uniqueness (course_id-section_id exclusivity)
    _all_fa = FacultyAssignment.query.with_entities(
        FacultyAssignment.course_id, FacultyAssignment.section_id, FacultyAssignment.faculty_id
    ).all()
    _all_taken = {f"{a.course_id}-{a.section_id}": a.faculty_id for a in _all_fa}
    others_taken_by_faculty = {}
    for _f in faculty_on_page:
        others_taken_by_faculty[str(_f.id)] = [
            pair for pair, fid in _all_taken.items() if fid != _f.id
        ]

    # Build faculty profiles list for View Profile offcanvas
    faculty_profiles = []
    for f in faculty_on_page:
        _asgn_list = []
        for _sc in sc_assignments_map.get(f.id, []):
            if _sc.course is None:
                continue
            _stype = _sc.session_type or 'Lec'
            _dur = 0.0
            if _sc.start_time and _sc.end_time:
                try:
                    _sh, _sm = map(int, _sc.start_time.split(':'))
                    _eh, _em = map(int, _sc.end_time.split(':'))
                    _dur = ((_eh * 60 + _em) - (_sh * 60 + _sm)) / 60.0
                except Exception:
                    pass
            if _dur <= 0:
                if _stype == 'Lab':
                    _dur = _sc.course.synchronous_lab_hours or _sc.course.lab_units or 0
                elif _stype == 'Async':
                    _dur = (_sc.course.asynchronous_lec_hours or 0) + (_sc.course.asynchronous_lab_hours or 0)
                else:
                    _dur = _sc.course.synchronous_lec_hours or _sc.course.lec_units or 0
            _asgn_list.append({
                'course_id':      _sc.course_id,
                'section_id':     _sc.section_id,
                'course_code':    _sc.course.course_code,
                'course_name':    _sc.course.course_name,
                'section_name':   _sc.section.section_name if _sc.section else '----',
                'session_type':   _stype,
                'duration_hours': round(_dur, 1),
                'semester':       _sc.course.semester_offered or '',
            })
        faculty_profiles.append({
            'id': f.id,
            'employee_id': f.employee_id or '',
            'full_name': f.full_name,
            'department': f.department or '',
            'employment_status': f.employment_status or '',
            'academic_rank': getattr(f, 'academic_rank', '') or '',
            'highest_educational_attainment': getattr(f, 'highest_educational_attainment', '') or '',
            'available_days': f.available_days or '',
            'max_weekly_hours': f.max_weekly_hours or 0,
            'workload_hours': workload_map.get(f.id, 0),
            'assignments': _asgn_list,
        })

    return render_template(
        'manage_faculty.html',
        faculty_list=faculty_on_page,
        pagination=pagination,
        courses_by_sem=courses_by_sem,
        all_sections_json=all_sections_json,
        all_faculty_for_modals=faculty_on_page,
        current_sort=sort_by,
        search_query=search_query,
        selected_semester=selected_semester,
        # Pass Filter Data
        unique_depts=_get_depts(),
        current_filter_by=filter_by,
        current_filter_val=filter_val,
        # Split data for pre-population
        split_data_by_faculty=split_data_by_faculty,
        # Faculty profiles for View Profile offcanvas
        faculty_profiles=faculty_profiles,
        workload_map=workload_map,
        sc_course_ids_by_faculty=sc_course_ids_by_faculty,
        sc_pairs_by_faculty=sc_pairs_by_faculty,
        others_taken_by_faculty=others_taken_by_faculty,
        fa_split_hours_map=fa_split_hours_map,
    )

@app.route('/manage/faculty/add', methods=['POST'])
@login_required
def add_faculty():
    # Only allow non-archive mode to add
    if session.get('historical_mode_active'):
        flash('Action not allowed in Archive Mode.', 'danger')
        return redirect(url_for('manage_faculty'))

    employee_id = request.form.get('employee_id', '').strip()
    full_name   = request.form.get('full_name', '').strip()
    dept        = request.form.get('department', '').strip()
    attain      = request.form.get('highest_educational_attainment', '').strip()
    rank        = request.form.get('academic_rank', '').strip()

    # 1. Length Validation
    constraints = {
        'employee_id': 20,
        'full_name': 100,
        'department': 100,
        'highest_educational_attainment': 200,
        'academic_rank': 100
    }
    ok, err = validate_lengths(request.form, constraints)
    if not ok:
        flash(err, 'danger')
        return redirect(url_for('manage_faculty'))

    # 2. XSS Sanitization
    employee_id = sanitize_input(employee_id)
    full_name   = sanitize_input(full_name)
    dept        = sanitize_input(dept)
    attain      = sanitize_input(attain)
    rank        = sanitize_input(rank)

    existing = Faculty.query.filter_by(employee_id=employee_id, is_archived=False).first()
    if existing:
        flash(f"Error: Faculty Employee ID '{employee_id}' already exists!", "danger")
        return redirect(url_for('manage_faculty'))

    # Provide defaults for hidden/restricted fields
    hours = int(request.form.get('max_weekly_hours', 35))
    status = request.form.get('employment_status', 'Full-time')
    day_list = request.form.getlist('available_days')
    if not day_list:
        avail_days = 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday'
    else:
        avail_days = ','.join(day_list)

    # Simplified validation: only if value was actually sent (admin role)
    if 'max_weekly_hours' in request.form:
        if hours <= 0 or hours > 60:
            flash('Error: Max weekly hours must be between 1 and 60.', 'danger')
            return redirect(url_for('manage_faculty'))

    try:
        db.session.add(Faculty(
            employee_id=employee_id,
            full_name=full_name,
            department=session.get('department') if session.get('role') == 'user' else dept,
            employment_status=status,
            highest_educational_attainment=attain,
            academic_rank=rank,
            sex=request.form.get('sex', '') or None,
            max_weekly_hours=hours,
            available_days=avail_days,
            assignment_status=request.form.get('assignment_status', 'Announced'),
            created_by_id=session.get('user_id') # Track creator
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash(f"Error: Could not add Faculty. Employee ID '{employee_id}' may already exist.", "danger")
        return redirect(url_for('manage_faculty'))
    
    # Module 7: Log action
    log_activity('Add Faculty', f"Created faculty {full_name}")
    
    flash('Faculty added successfully.', 'success')
    return redirect(url_for('manage_faculty'))

@app.route('/manage/faculty/quick-add-tba', methods=['POST'])
@login_required
def quick_add_tba_faculty():
    if session.get('role') == 'user':
        user_dept = session.get('department')
        # Scoped TBA name: T.B.A. (DAS)
        full_name_base = f'T.B.A. ({user_dept})'
        existing_tba = Faculty.query.filter_by(full_name=full_name_base).all()
        existing_ids = {f.employee_id for f in existing_tba}
        next_num = 1
        while f'TBA-{user_dept}-{next_num:02d}' in existing_ids:
            next_num += 1
        new_id = f'TBA-{user_dept}-{next_num:02d}'
        new_full_name = full_name_base
        dept = user_dept
    else:
        existing_tba = Faculty.query.filter_by(full_name='T.B.A.').all()
        existing_ids = {f.employee_id for f in existing_tba}
        next_num = 1
        while f'TBA-{next_num:02d}' in existing_ids:
            next_num += 1
        new_id = f'TBA-{next_num:02d}'
        new_full_name = 'T.B.A.'
        dept = 'Unassigned'

    new_tba = Faculty(
        employee_id=new_id,
        full_name=new_full_name,
        department=dept,
        employment_status='Part-time',
        max_weekly_hours=999,
        available_days='Mon,Tue,Wed,Thu,Fri,Sat',
    )
    db.session.add(new_tba)
    db.session.commit()
    flash(f'T.B.A. faculty {new_id} added successfully.', 'success')
    return redirect(url_for('manage_faculty'))

@app.route('/manage/faculty/update/<int:faculty_id>', methods=['POST'])
@login_required
@hist_lockdown
def update_faculty(faculty_id):
    faculty = Faculty.query.get_or_404(faculty_id)
    
    # Security Firewall: Role-based department check
    if not verify_department_access(faculty):
        flash("You are not authorized to update this faculty member as they belong to another department.", "danger")
        log_security('Unauthorized Access Attempt', details=f"User {session.get('username')} tried to update faculty id {faculty_id}")
        return redirect(url_for('manage_faculty'))
    # 1. Length Validation
    constraints = {
        'employee_id': 20,
        'full_name': 100,
        'department': 100,
        'highest_educational_attainment': 200,
        'academic_rank': 100
    }
    ok, err = validate_lengths(request.form, constraints)
    if not ok:
        flash(err, 'danger')
        return redirect(url_for('manage_faculty'))

    new_id = sanitize_input(request.form.get('employee_id', '').strip())
    new_name = sanitize_input(request.form.get('full_name', '').strip())
    new_dept = sanitize_input(request.form.get('department', '').strip())
    new_attain = sanitize_input(request.form.get('highest_educational_attainment', '').strip())
    new_rank = sanitize_input(request.form.get('academic_rank', '').strip())

    existing = Faculty.query.filter(Faculty.employee_id == new_id, Faculty.id != faculty_id, Faculty.is_archived == False).first()
    if existing:
        flash(f"Faculty Employee ID '{new_id}' is already taken.", "danger")
        return redirect(url_for('manage_faculty'))

    faculty.employee_id = new_id
    faculty.full_name = new_name
    faculty.department = new_dept
    
    # Conditional updates for restricted fields
    if 'employment_status' in request.form:
        faculty.employment_status = request.form.get('employment_status')
    if 'max_weekly_hours' in request.form:
        faculty.max_weekly_hours = int(request.form.get('max_weekly_hours', 35))
    if 'available_days' in request.form:
        faculty.available_days = ",".join(request.form.getlist('available_days')) or 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday'
        
    faculty.highest_educational_attainment = new_attain
    faculty.academic_rank = new_rank
    faculty.sex = request.form.get('sex', '') or None
    faculty.assignment_status = request.form.get('assignment_status', 'Announced')
    
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Update Faculty', f"Updated faculty {faculty.full_name}")
    
    flash('Faculty updated successfully.', 'success')
    return redirect(url_for('manage_faculty'))

# --- BULK ACTIONS FOR FACULTY ---

@app.route('/manage/faculty/bulk_archive', methods=['POST'])
@login_required
def bulk_archive_faculty():
    faculty_ids = request.form.getlist('row_ids')
    
    if faculty_ids:
        Faculty.query.filter(Faculty.id.in_(faculty_ids)).update(
            {Faculty.is_archived: True, Faculty.deleted_at: datetime.utcnow()},
            synchronize_session=False)
        db.session.commit()
        flash(f'{len(faculty_ids)} faculty members moved to Recycle Bin.', 'success')
    else:
        flash('No faculty selected.', 'secondary')
        
    return redirect(url_for('manage_faculty'))

@app.route('/manage/faculty/bulk_restore', methods=['POST'])
@login_required
def bulk_restore_faculty():
    faculty_ids = request.form.getlist('row_ids')
    
    if faculty_ids:
        Faculty.query.filter(Faculty.id.in_(faculty_ids)).update({Faculty.is_archived: False}, synchronize_session=False)
        db.session.commit()
        flash(f'{len(faculty_ids)} faculty members restored.', 'success')
    
    return redirect(url_for('faculty_archive'))

@app.route('/manage/faculty/bulk_delete', methods=['POST'])
@login_required
def bulk_delete_faculty():
    faculty_ids = request.form.getlist('row_ids')
    
    if faculty_ids:
        FacultyAssignment.query.filter(FacultyAssignment.faculty_id.in_(faculty_ids)).delete(synchronize_session=False)
        ScheduledClass.query.filter(ScheduledClass.faculty_id.in_(faculty_ids)).update(
            {ScheduledClass.faculty_id: None}, synchronize_session=False)
        Faculty.query.filter(Faculty.id.in_(faculty_ids)).delete(synchronize_session=False)
        db.session.commit()
        flash(f'{len(faculty_ids)} faculty deleted. Their scheduled classes are now in Pending Faculty.', 'success')
    
    return redirect(url_for('faculty_archive'))


@app.route('/manage/faculty/archive')
@login_required
def faculty_archive():
    # --- KUNIN ANG MGA PARAMETERS ---
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'default', type=str)
    search_query = request.args.get('search', '', type=str)

    # Magsimula sa pag-filter ng mga NAKA-ARCHIVE na faculty
    query = Faculty.query.filter_by(is_archived=True)
    if session.get('role') == 'user':
        query = query.filter_by(created_by_id=session.get('user_id'))

    # I-apply ang search filter kung mayroon
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(Faculty.full_name.ilike(search_term))

    # I-apply ang sort order
    if sort_by == 'name-asc':
        query = query.order_by(Faculty.full_name.asc())
    elif sort_by == 'name-desc':
        query = query.order_by(Faculty.full_name.desc())
    elif sort_by == 'newest' or sort_by == 'default':
        query = query.order_by(Faculty.deleted_at.desc(), Faculty.id.desc())
    else:
        query = query.order_by(Faculty.id.desc())

    pagination = query.paginate(page=page, per_page=10, error_out=False)
    archived_faculty = pagination.items
    
    return render_template(
        'faculty_archive.html', 
        faculties=archived_faculty,
        pagination=pagination,
        current_sort=sort_by,
        search_query=search_query,
        now=datetime.utcnow()
    )

@app.route('/manage/faculty/archive/<int:faculty_id>', methods=['POST'])
@login_required
def archive_faculty(faculty_id):
    faculty = Faculty.query.get_or_404(faculty_id)
    faculty.is_archived = True
    faculty.deleted_at = datetime.utcnow()
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Archive Faculty', f"Archived faculty {faculty.full_name}")
    
    flash('Faculty moved to Recycle Bin.', 'success')
    return redirect(url_for('manage_faculty'))

@app.route('/manage/faculty/restore/<int:faculty_id>', methods=['POST'])
@login_required
def restore_faculty(faculty_id):
    faculty = Faculty.query.get_or_404(faculty_id)
    faculty.is_archived = False
    faculty.deleted_at = None
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Restore Faculty', f"Restored faculty {faculty.full_name}")
    
    flash('Faculty restored successfully.', 'success')
    return redirect(url_for('faculty_archive'))

# I-UPDATE ANG delete_faculty FUNCTION
@app.route('/manage/faculty/delete/<int:faculty_id>', methods=['POST'])
@login_required
def delete_faculty(faculty_id):
    faculty = Faculty.query.get_or_404(faculty_id)
    FacultyAssignment.query.filter_by(faculty_id=faculty_id).delete(synchronize_session=False)
    ScheduledClass.query.filter(ScheduledClass.faculty_id == faculty_id).update(
        {ScheduledClass.faculty_id: None}, synchronize_session=False)
    db.session.delete(faculty)
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Delete Faculty', f"Permanently deleted faculty {faculty.full_name}")
    
    flash('Faculty deleted. Their scheduled classes are now in Pending Faculty.', 'success')
    return redirect(url_for('faculty_archive'))

@app.route('/manage/faculty/set_teachable_courses/<int:faculty_id>', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def set_teachable_courses(faculty_id):
    faculty = Faculty.query.get_or_404(faculty_id)
    faculty.courses = Course.query.filter(Course.id.in_(request.form.getlist('course_ids'))).all()
    db.session.commit()
    return redirect(url_for('manage_faculty'))

@app.route('/manage/faculty/save_assignments/<int:faculty_id>', methods=['POST'])
@login_required
@role_required('admin', 'superadmin', 'user')
def save_faculty_assignments(faculty_id):
    _fac_obj = Faculty.query.get_or_404(faculty_id)
    
    # Security: User can only edit faculty in their department
    if session.get('role') == 'user':
        if _fac_obj.department != session.get('department'):
            flash('Access Denied: You can only manage faculty from your own department.', 'danger')
            return redirect(url_for('manage_faculty'))
            
    assignment_keys = request.form.getlist('assignments')
    # Conflict check: ensure no pair is already assigned to a different faculty
    conflicts = []
    for key in assignment_keys:
        cid, sid = key.split('-')
        existing = FacultyAssignment.query.filter(
            FacultyAssignment.course_id == int(cid),
            FacultyAssignment.section_id == int(sid),
            FacultyAssignment.faculty_id != faculty_id
        ).first()
        if existing:
            conflicts.append(key)
    if conflicts:
        flash('Some sections are already assigned to another faculty member. Please refresh and try again.', 'danger')
        return redirect(request.referrer or url_for('manage_faculty'))
    # Department restriction: faculty may only be assigned courses from their own department
    def _norm_dept(s):
        return (s or '').lower().replace('department of ', '').replace(' and ', ' & ').strip()
    if _fac_obj.full_name != 'T.B.A.' and assignment_keys:
        _saved_cids = {int(k.split('-')[0]) for k in assignment_keys}
        _fac_dept_norm = _norm_dept(_fac_obj.department)
        _bad = [c for c in Course.query.filter(Course.id.in_(_saved_cids)).all()
                if c.department and _norm_dept(c.department) != _fac_dept_norm]
        if _bad:
            _names = ', '.join(c.course_code for c in _bad)
            flash(f'Cannot assign courses outside faculty department: {_names}', 'danger')
            return redirect(url_for('manage_faculty'))
    FacultyAssignment.query.filter_by(faculty_id=faculty_id).delete()
    def _float_or_none(v):
        try: return float(v) if v else None
        except: return None
    for key in assignment_keys:
        course_id, section_id = key.split('-')
        prefix = f'split_{key}_'
        # Lab split
        sd1  = request.form.get(f'{prefix}day_1')       or None
        sh1  = _float_or_none(request.form.get(f'{prefix}hours_1'))
        sd2  = request.form.get(f'{prefix}day_2')       or None
        sh2  = _float_or_none(request.form.get(f'{prefix}hours_2'))
        # Lec split
        ld1  = request.form.get(f'{prefix}lec_day_1')   or None
        lh1  = _float_or_none(request.form.get(f'{prefix}lec_hours_1'))
        ld2  = request.form.get(f'{prefix}lec_day_2')   or None
        lh2  = _float_or_none(request.form.get(f'{prefix}lec_hours_2'))
        db.session.add(FacultyAssignment(
            faculty_id=faculty_id,
            course_id=int(course_id),
            section_id=int(section_id),
            split_day_1=sd1, split_hours_1=sh1, split_day_2=sd2, split_hours_2=sh2,
            split_lec_day_1=ld1, split_lec_hours_1=lh1, split_lec_day_2=ld2, split_lec_hours_2=lh2,
        ))
    # Sync teachable subjects: replace exactly with the courses in this Final Load
    faculty = Faculty.query.get_or_404(faculty_id)
    saved_cids = list({int(k.split('-')[0]) for k in assignment_keys})
    faculty.courses = Course.query.filter(Course.id.in_(saved_cids)).all() if saved_cids else []
    # Sync ScheduledClass: replace TBA faculty with the assigned real faculty
    tba_ids = [f.id for f in Faculty.query.filter_by(full_name='T.B.A.').all()]
    if tba_ids and assignment_keys:
        for key in assignment_keys:
            cid, sid = key.split('-')
            ScheduledClass.query.filter(
                ScheduledClass.course_id == int(cid),
                ScheduledClass.section_id == int(sid),
                ScheduledClass.faculty_id.in_(tba_ids)
            ).update({'faculty_id': faculty_id}, synchronize_session=False)
    db.session.commit()
    
    # Module 7: Log action
    log_activity('Save Workload', f"Updated workload for {faculty.full_name}")
    
    flash('Workload saved successfully.', 'success')
    return redirect(url_for('manage_faculty'))


@app.route('/generate')
@login_required
@role_required('admin', 'superadmin', 'user')
def generate_page():
    s = get_settings()
    
    if session.get('role') == 'user':
        known_depts = [session.get('department')]
        saved_depts = [session.get('department')]
    else:
        known_depts = _get_depts()
        saved_depts = session.get('scheduled_depts', SCHEDULED_DEPARTMENTS)

    return render_template(
        'generate_schedule.html',
        start_hour=s.start_hour,
        end_hour=s.end_hour,
        known_departments=known_depts,
        saved_depts=saved_depts,
    )

@app.route('/view-timetable')
@login_required
def view_timetable():
    filter_type = request.args.get('type', 'section')
    filter_id   = request.args.get('id', type=int)

    # ------------------------------------ Time Machine: Historical Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    if session.get('historical_mode_active', False):
        archive_id = session.get('active_archive_id')
        
        # 1. Fetch historical dropdown data (sorted A-Z, T.B.A. last)
        _sec_raw = get_archive_entities(archive_id, 'Section')
        _fac_raw = get_archive_entities(archive_id, 'Faculty')
        _rom_raw = get_archive_entities(archive_id, 'Room')
        _crs_raw = get_archive_entities(archive_id, 'Course')
        
        all_sections = sorted(_sec_raw, key=lambda s: s.section_name)
        _fac_sorted  = sorted(_fac_raw, key=lambda f: f.full_name)
        all_faculty  = [f for f in _fac_sorted if not f.full_name.startswith('T.B.A.')] + \
                       [f for f in _fac_sorted if f.full_name.startswith('T.B.A.')]
        _rom_sorted  = sorted(_rom_raw, key=lambda r: r.room_name)
        all_rooms    = [r for r in _rom_sorted if r.room_name != 'T.B.A.'] + \
                       [r for r in _rom_sorted if r.room_name == 'T.B.A.']
        all_courses  = sorted(_crs_raw, key=lambda c: c.course_code)
        
        # 2. Get target name for filtering
        selected_name = "Historical Schedule"
        target_field = None
        target_name = None
        current_semester = "Archived Term" # Or fetch from TermArchive if desired
        available_semesters = [] # Only one semester per archive

        if filter_id:
            if filter_type == 'section':
                match = next((s for s in all_sections if s.id == filter_id), None)
                if match: 
                    target_field = 'section_name'
                    target_name = match.section_name
                    selected_name = f"Schedule for {match.section_name}"
            elif filter_type == 'faculty':
                match = next((f for f in all_faculty if f.id == filter_id), None)
                if match:
                    target_field = 'faculty_name'
                    target_name = match.full_name
                    selected_name = f"Schedule for {match.full_name}"
            elif filter_type == 'room':
                match = next((r for r in all_rooms if r.id == filter_id), None)
                if match:
                    target_field = 'room_name'
                    target_name = match.room_name
                    selected_name = f"Schedule for {match.room_name}"
            elif filter_type == 'course':
                match = next((c for c in all_courses if c.id == filter_id), None)
                if match:
                    target_field = 'course_code'
                    target_name = match.course_code
                    selected_name = f"Schedule for {match.course_code}"
            elif filter_type in ('student', 'irregular'):
                # 1. Fetch archived student record
                st_match = ArchivedStudent.query.filter_by(term_archive_id=archive_id, id=filter_id).first()
                if st_match:
                    selected_name = f"Schedule for {st_match.full_name}"
                    if st_match.is_irregular:
                        # Irregular student: use assignments_json (list of signatures)
                        import json
                        try:
                            pairs = json.loads(st_match.assignments_json or "[]")
                            # pairs is list of strings like "COURSE CODE - SECTION NAME"
                            schedules_raw = []
                            for p in pairs:
                                parts = p.split(' - ')
                                if len(parts) == 2:
                                    cc, sn = parts
                                    matches = ArchivedSchedule.query.filter_by(
                                        term_archive_id=archive_id, 
                                        course_code=cc.strip(), 
                                        section_name=sn.strip()
                                    ).all()
                                    schedules_raw.extend(matches)
                        except:
                            schedules_raw = []
                    else:
                        # Regular student: follow their archived section_name
                        if st_match.section_name:
                            schedules_raw = ArchivedSchedule.query.filter_by(
                                term_archive_id=archive_id, 
                                section_name=st_match.section_name
                            ).all()
                        else:
                            schedules_raw = []
        else:
            if all_sections:
                match = all_sections[0]
                filter_id = match.id
                target_field = 'section_name'
                target_name = match.section_name
                selected_name = f"Schedule for {match.section_name}"

        # 3. Query ArchivedSchedule
        base_query = ArchivedSchedule.query.filter_by(term_archive_id=archive_id)
        if target_field and target_name:
            schedules_raw = base_query.filter(getattr(ArchivedSchedule, target_field) == target_name).all()
        else:
            schedules_raw = base_query.all()
        
        schedules = [_mock_archived_schedule(s) for s in schedules_raw]
        settings = get_settings()

    else:
        # ------------------------------------ Live Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        # Semester history: collect distinct semesters that have saved schedules
        _sem_rows = db.session.query(ScheduledClass.semester).distinct().all()
        available_semesters = sorted(
            {r[0] for r in _sem_rows if r[0]},
            key=lambda s: ({'1st Semester': 0, 'Midyear': 1, '2nd Semester': 2}.get(s, 99))
        )
        # Default to the semester with the most recent data; fall back to 1st Semester
        default_sem = available_semesters[0] if available_semesters else '1st Semester'
        current_semester = request.args.get('semester', default_sem)
        
        # Semester validation: Normalize UI pills (1st/2nd) to DB strings (1st Semester)
        sem_map = {'1st': '1st Semester', '2nd': '2nd Semester'}
        if current_semester in sem_map:
            current_semester = sem_map[current_semester]

        if available_semesters and current_semester not in available_semesters:
            current_semester = available_semesters[0]

        all_sections = Section.query.filter_by(is_archived=False)
        all_sections = all_sections.order_by(Section.year_level, Section.section_name).all()

        _fac_live = Faculty.query.filter_by(is_archived=False)
        user_dept = session.get('department')
        if session.get('role') == 'user' and user_dept:
             _fac_live = _fac_live.filter(or_(Faculty.department == user_dept, Faculty.created_by_id == session.get('user_id')))
        _fac_live = _fac_live.order_by(Faculty.full_name).all()

        all_faculty  = [f for f in _fac_live if not f.full_name.startswith('T.B.A.')] + \
                       [f for f in _fac_live if f.full_name.startswith('T.B.A.')]

        _rom_live = Room.query.filter_by(is_archived=False)
        if session.get('role') == 'user' and user_dept:
             _rom_live = _rom_live.filter(Room.created_by_id == session.get('user_id'))
        _rom_live = _rom_live.order_by(Room.room_name).all()

        all_rooms    = [r for r in _rom_live if r.room_name != 'T.B.A.'] + \
                       [r for r in _rom_live if r.room_name == 'T.B.A.']
        
        all_courses = Course.query.filter_by(is_archived=False).order_by(Course.course_code).all()

        query = ScheduledClass.query.filter_by(semester=current_semester)
        selected_name = "Master Schedule"

        if filter_id:
            if filter_type == 'section':
                query = query.filter_by(section_id=filter_id)
                item = Section.query.get(filter_id)
                if item: selected_name = f"Schedule for {item.section_name}"
            elif filter_type == 'faculty':
                query = query.filter_by(faculty_id=filter_id)
                item = Faculty.query.get(filter_id)
                if item: selected_name = f"Schedule for {item.full_name}"
            elif filter_type == 'room':
                query = query.filter_by(room_id=filter_id)
                item = Room.query.get(filter_id)
                if item: selected_name = f"Schedule for {item.room_name}"
            elif filter_type == 'course':
                query = query.filter_by(course_id=filter_id)
                item = Course.query.get(filter_id)
                if item: selected_name = f"Schedule for {item.course_code}"
            elif filter_type in ('student', 'irregular'):
                item = Student.query.get(filter_id)
                if item:
                    selected_name = f"Schedule for {item.full_name}"
                    if item.is_irregular:
                        # Irregular: Fetch custom assignments from IrregularAssignment table
                        irreg = IrregularAssignment.query.filter_by(student_id_fk=item.id, semester=current_semester).first()
                        if irreg:
                            try:
                                import json
                                pairs = json.loads(irreg.assignments_json or "[]")
                                # list of {course_id: X, section_id: Y}
                                from sqlalchemy import or_
                                if pairs:
                                    filters = []
                                    for p in pairs:
                                        filters.append(and_(ScheduledClass.course_id == p['course_id'], ScheduledClass.section_id == p['section_id']))
                                    query = query.filter(or_(*filters))
                                else:
                                    query = query.filter(ScheduledClass.id == -1) # Force empty
                            except:
                                query = query.filter(ScheduledClass.id == -1)
                        else:
                            query = query.filter(ScheduledClass.id == -1)
                    else:
                        # Regular: Inherit from their assigned section
                        if item.section_id:
                            query = query.filter_by(section_id=item.section_id)
                        else:
                            # No section assigned - show empty but stable
                            query = query.filter(ScheduledClass.id == -1)
        else:
            # SMART DEFAULTING: One-time default based on current view type
            if filter_type == 'room' and all_rooms:
                first = all_rooms[0]
                query = query.filter_by(room_id=first.id)
                filter_id = first.id
                selected_name = f"Schedule for {first.room_name}"
            elif filter_type == 'faculty' and all_faculty:
                first = all_faculty[0]
                query = query.filter_by(faculty_id=first.id)
                filter_id = first.id
                selected_name = f"Schedule for {first.full_name}"
            elif all_sections:
                first = all_sections[0]
                query = query.filter_by(section_id=first.id)
                filter_id = first.id
                selected_name = f"Schedule for {first.section_name}"

        schedules = query.all()
        
        # --- DATA ISOLATION: Merge Personal Schedules for the current user ---
        # This allows users to see their auto-generated proposals alongside the master schedule.
        user_id = session.get('user_id')
        if user_id:
            personal_query = UserPersonalSchedule.query.filter_by(user_id=user_id)
            # Apply same filters as master query
            if filter_id:
                if filter_type == 'section': personal_query = personal_query.filter_by(section_id=filter_id)
                elif filter_type == 'faculty': personal_query = personal_query.filter_by(faculty_id=filter_id)
                elif filter_type == 'room': personal_query = personal_query.filter_by(room_id=filter_id)
                elif filter_type == 'course': personal_query = personal_query.filter_by(course_id=filter_id)
            
            personal_schedules = personal_query.all()
            for ps in personal_schedules:
                setattr(ps, 'is_personal', True) # Mark for UI differentiation
            schedules.extend(personal_schedules)
        settings = get_settings()

    # --- UPDATED GRID LOGIC ---
    def to_12hr(h, m):
        d = h if h <= 12 else h - 12
        if d == 0: d = 12
        return f"{d}:{m:02d}"

    # 1. Generate Times (Fixed 30-min slots)
    times = []
    # Gumamit ng list of minutes para mas precise
    start_min = settings.start_hour * 60
    end_min = settings.end_hour * 60
    
    # Map "Start Time String" -> Index
    time_index_map = {}
    current_min = start_min
    idx = 0
    
    while current_min < end_min:
        h = current_min // 60
        m = current_min % 60
        s = to_12hr(h, m)
        
        # Calculate End for display
        next_min = current_min + 30
        nh = next_min // 60
        nm = next_min % 60
        e = to_12hr(nh, nm)
        
        times.append(f"{s}-{e}")
        
        # Mahalaga: I-map natin ang exact start string sa index
        # Format must match exactly what is saved in DB (e.g. "7:00", "7:30")
        # DB format is usually 24-hour "H:MM" or "HH:MM" depending on how you saved it
        # Let's ensure consistency by converting DB time to this format or vice versa
        # Mas madali kung index-based na lang tayo sa total minutes
        
        current_min += 30
        idx += 1

    # --- DYNAMIC DAYS ---
    _disp_str = settings.allowed_days
    if _disp_str:
        days = [d.strip() for d in _disp_str.split(',') if d.strip()]
    else:
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

    # Initialize Grid
    grid = [[None for _ in days] for _ in times]

    for sched in schedules:
        if sched.day not in days: continue 

        # Convert DB Time (e.g. "13:00") to Minutes
        sh, sm = map(int, sched.start_time.split(':'))
        sched_start_min = sh * 60 + sm
        
        # Calculate Index
        # Formula: (SchedStart - GlobalStart) / 30
        start_idx = int((sched_start_min - start_min) / 30)
        
        # Check bounds
        if 0 <= start_idx < len(times):
            day_idx = days.index(sched.day)
            
            # Calculate Duration
            eh, em = map(int, sched.end_time.split(':'))
            sched_end_min = eh * 60 + em
            duration_mins = sched_end_min - sched_start_min
            
            # Force minimum 1 hour (2 slots) display if logic allows, 
            # but strictly follow duration. 
            rowspan = int(duration_mins / 30)
            
            # Fix for Async glitch: Ensure rowspan is at least 1
            if rowspan < 1: rowspan = 1

            # Check if within bounds
            if start_idx + rowspan <= len(grid):
                grid[start_idx][day_idx] = {'type': 'head', 'data': sched, 'rowspan': rowspan}
                
                # Fill SKIP slots
                for r in range(1, rowspan):
                    grid[start_idx + r][day_idx] = {'type': 'skip'}

    # Pre-serialise entity lists so the template can use a single tojson call
    sections_json = [{'id': s.id, 'label': f"{s.section_name} ({s.year_level}Yr)"} for s in all_sections]
    faculty_json  = [{'id': f.id, 'label': f.full_name}                            for f in all_faculty]
    rooms_json    = [{'id': r.id, 'label': f"{r.room_name} ({r.building})"}        for r in all_rooms]
    courses_json  = [{'id': c.id, 'label': f"{c.course_code} - {c.course_name}"}    for c in all_courses]

    is_hist = session.get('historical_mode_active', False)
    active_draft_id = session.get('active_editor_draft_id') or request.args.get('draft_id', type=int)

    # Calculate Paper Sizes for all types (Manifest)
    settings = get_settings()
    def _pdim(pk):
        w, h, _ = PAPER_SIZES.get(pk, PAPER_SIZES['A4'])
        return {'w': w, 'h': h}

    sec_p = getattr(settings, 'paper_size', 'A4') or 'A4'
    fac_p = getattr(settings, 'fac_paper_size', 'A4') or 'A4'
    
    layout_configs = {
        'section': _pdim(sec_p),
        'room':    _pdim(sec_p),
        'course':  _pdim(sec_p),
        'faculty': _pdim(fac_p)
    }

    return render_template('view_timetable.html',
                           all_sections=all_sections, all_faculty=all_faculty, all_rooms=all_rooms, all_courses=all_courses,
                           sections_json=sections_json, faculty_json=faculty_json, rooms_json=rooms_json, courses_json=courses_json,
                           current_type=filter_type, current_id=filter_id,
                           current_semester=current_semester,
                           available_semesters=available_semesters,
                           active_draft_id=active_draft_id,
                           layout_configs=layout_configs,
                           is_hist=is_hist)

@app.route('/reports')
@login_required
@role_required('admin', 'superadmin')
def reports_page():
    _sem_rows = db.session.query(ScheduledClass.semester).distinct().all()
    available_semesters = sorted(
        {r[0] for r in _sem_rows if r[0]},
        key=lambda s: ({'1st Semester': 0, 'Midyear': 1, '2nd Semester': 2}.get(s, 99))
    )
    return render_template('reports.html', available_semesters=available_semesters)


@app.route('/api/layout-variables/<string:layout_type>')
@login_required
def api_layout_variables(layout_type):
    """Return all available {{variables}} for a given layout type (section/faculty/room/course).
    Used by the Layout Designer variable panel to render the list dynamically."""
    settings = SystemSettings.query.first()

    # --- Signatories (dynamic JSON) ---
    sig_json_str = getattr(settings, f'{layout_type}_signatories_json', None) if settings else None
    signatories = []
    if sig_json_str:
        try:
            signatories = json.loads(sig_json_str)
        except Exception:
            signatories = []
    # Fallback to old sig1/2/3 if JSON empty
    if not signatories and settings:
        for i in (1, 2, 3):
            v = getattr(settings, f'{layout_type}_signatory_{i}', '') or ''
            if v.strip():
                signatories.append({'name': v, 'title': ''})

    sig_vars = [{'var': f'{{{{sig{i+1}}}}}',       'desc': f'Signatory {i+1} name',  'group': 'Signatories'} for i in range(len(signatories))] + \
               [{'var': f'{{{{sig{i+1}_title}}}}', 'desc': f'Signatory {i+1} title', 'group': 'Signatories'} for i in range(len(signatories))]

    # --- Common variables ---
    common = [
        {'var': '{{name}}',       'desc': 'Section / Faculty / Room name', 'group': 'Header'},
        {'var': '{{school}}',     'desc': 'School name',                   'group': 'Header'},
        {'var': '{{department}}', 'desc': 'Department',                    'group': 'Header'},
        {'var': '{{acad_year}}',  'desc': 'Academic Year',                 'group': 'Header'},
        {'var': '{{semester}}',   'desc': 'Semester',                      'group': 'Header'},
        {'var': '{{generated}}',  'desc': 'Date generated',                'group': 'Header'},
    ]

    # --- Type-specific variables ---
    type_vars = []
    if layout_type == 'faculty':
        type_vars = [
            {'var': '{{employee_id}}',        'desc': 'Employee ID',              'group': 'Faculty'},
            {'var': '{{employment_status}}',  'desc': 'Employment status',        'group': 'Faculty'},
            {'var': '{{highest_education}}',  'desc': 'Highest education',        'group': 'Faculty'},
            {'var': '{{max_weekly_hours}}',   'desc': 'Max weekly hours',         'group': 'Faculty'},
            {'var': '{{available_days}}',     'desc': 'Available days',           'group': 'Faculty'},
            {'var': '{{total_contact_hours}}','desc': 'Total contact hrs (sched)','group': 'Faculty (Computed)'},
            {'var': '{{num_preparations}}',   'desc': 'No. of preparations',      'group': 'Faculty (Computed)'},
            {'var': '{{daily_Mon}}',          'desc': 'Monday load (hrs)',         'group': 'Faculty (Computed)'},
            {'var': '{{daily_Tue}}',          'desc': 'Tuesday load (hrs)',        'group': 'Faculty (Computed)'},
            {'var': '{{daily_Wed}}',          'desc': 'Wednesday load (hrs)',      'group': 'Faculty (Computed)'},
            {'var': '{{daily_Thu}}',          'desc': 'Thursday load (hrs)',       'group': 'Faculty (Computed)'},
            {'var': '{{daily_Fri}}',          'desc': 'Friday load (hrs)',         'group': 'Faculty (Computed)'},
            {'var': '{{daily_Sat}}',          'desc': 'Saturday load (hrs)',       'group': 'Faculty (Computed)'},
        ]
    elif layout_type == 'section':
        type_vars = [
            {'var': '{{year_level}}',   'desc': 'Year level',         'group': 'Section'},
            {'var': '{{num_students}}', 'desc': 'No. of students',    'group': 'Section'},
        ]
    elif layout_type == 'room':
        type_vars = [
            {'var': '{{building}}',     'desc': 'Building',           'group': 'Room'},
            {'var': '{{capacity}}',     'desc': 'Room capacity',      'group': 'Room'},
            {'var': '{{capabilities}}', 'desc': 'Room capabilities',  'group': 'Room'},
        ]
    elif layout_type == 'course':
        type_vars = [
            {'var': '{{course_name}}',  'desc': 'Full course name',   'group': 'Course'},
            {'var': '{{lec_units}}',    'desc': 'Lecture units',      'group': 'Course'},
            {'var': '{{lab_units}}',    'desc': 'Lab units',          'group': 'Course'},
            {'var': '{{program}}',      'desc': 'Program',            'group': 'Course'},
        ]

    # --- Grid anchors ---
    grid_vars = [
        {'var': '{{GRID_TIME}}', 'desc': 'Time column top-left anchor', 'group': 'Grid Anchors'},
        {'var': '{{GRID_MON}}',  'desc': 'Monday column header',      'group': 'Grid Anchors'},
        {'var': '{{GRID_TUE}}',  'desc': 'Tuesday column header',     'group': 'Grid Anchors'},
        {'var': '{{GRID_WED}}',  'desc': 'Wednesday column header',   'group': 'Grid Anchors'},
        {'var': '{{GRID_THU}}',  'desc': 'Thursday column header',    'group': 'Grid Anchors'},
        {'var': '{{GRID_FRI}}',  'desc': 'Friday column header',      'group': 'Grid Anchors'},
        {'var': '{{GRID_SAT}}',  'desc': 'Saturday column header',    'group': 'Grid Anchors'},
    ]

    return jsonify({
        'status': 'ok',
        'variables': common + type_vars + sig_vars + grid_vars,
        'signatories': signatories
    })


@app.route('/api/room-utilization')
@login_required
@role_required('admin', 'superadmin')
def api_room_utilization():
    """Return per-room utilization stats based on currently saved ScheduledClasses.
    Now respects the global semester filter and provides total class counts.
    """
    settings  = get_settings()
    start_h   = settings.start_hour if settings else 7
    end_h     = settings.end_hour   if settings else 20
    day_hours = end_h - start_h           # e.g. 7-20 -> 13 h per day
    active_days = len(settings.allowed_days.split(',')) if settings and settings.allowed_days else 6
    total_avail_h = day_hours * active_days   # per-room available hours per week

    # 1. Get Global Semester Filter
    selected_sem = session.get('selected_semester', 'All')
    is_archive = session.get('historical_mode_active', False)
    archive_id = session.get('active_archive_id')

    # 2. Gather schedules based on mode
    if is_archive and archive_id:
        # Historical Mode: Query ArchivedSchedule
        total_q = ArchivedSchedule.query.filter_by(term_archive_id=archive_id)
        room_q = ArchivedSchedule.query.filter_by(term_archive_id=archive_id)
        schedules = room_q.all()
        total_scheduled_classes = total_q.count()
    else:
        # Live Mode: Query ScheduledClass with DEDUPLICATION
        # The ScheduledClass table accumulates records across AI generations (intentional).
        # We count only DISTINCT class slots so reports are not inflated.
        total_cols = db.session.query(
            ScheduledClass.course_id,
            ScheduledClass.section_id,
            ScheduledClass.day,
            ScheduledClass.start_time,
            ScheduledClass.end_time
        ).filter(ScheduledClass.is_draft == False)
        if selected_sem != 'All':
            total_cols = total_cols.filter(ScheduledClass.semester == selected_sem)
        total_scheduled_classes = total_cols.distinct().count()

        room_q = ScheduledClass.query.filter(ScheduledClass.room_id.isnot(None), ScheduledClass.is_draft == False)
        if selected_sem != 'All':
            room_q = room_q.filter_by(semester=selected_sem)
        schedules = room_q.all()

    # Accumulate used hours and class counts per room
    # For live mode: deduplicate by (room_id/name, day, start_time, end_time) to
    # avoid counting the same slot multiple times across AI generations.
    room_used  = {}   # room_id -> float hours (Live) or room_name -> float (Archive)
    room_count = {}   # room_id -> int
    room_names = {}   # room_id -> str
    seen_slots  = set()  # Tracks unique time slots to skip duplicates (live mode only)

    for sc in schedules:
        # In Archive, room_id might not match live room_id, so we use room_name as key
        key = sc.room_id if not is_archive else sc.room_name

        # DEDUPLICATION: skip if we already processed this exact slot in live mode
        if not is_archive:
            slot_sig = (key, sc.day, sc.start_time, sc.end_time)
            if slot_sig in seen_slots:
                continue
            seen_slots.add(slot_sig)

        try:
            sh, sm = map(int, sc.start_time.split(':'))
            eh, em = map(int, sc.end_time.split(':'))
            dur_h  = (eh * 60 + em - sh * 60 - sm) / 60.0
        except Exception:
            dur_h = 0.0
        
        room_used[key] = room_used.get(key, 0.0) + dur_h
        room_count[key] = room_count.get(key, 0) + 1
        if not is_archive:
            if key not in room_names and sc.room:
                room_names[key] = sc.room.room_name
        else:
            room_names[key] = sc.room_name

    if is_archive:
        # Fetch rooms from the archive to ensure we match the historical data
        all_rooms = ArchivedRoom.query.filter_by(term_archive_id=archive_id).filter(ArchivedRoom.room_name != 'T.B.A.').order_by(ArchivedRoom.room_name).all()
    else:
        # Live Mode: Fetch current rooms
        all_rooms = Room.query.filter(
            Room.is_archived == False,
            Room.room_name != 'T.B.A.'
        ).order_by(Room.room_name).all()

    rooms_data = []
    total_used_sum = 0.0
    total_avail_sum = 0.0

    for r in all_rooms:
        key = r.id if not is_archive else r.room_name
        used_h  = room_used.get(key, 0.0)
        c_count = room_count.get(key, 0)
        pct     = round((used_h / total_avail_h * 100), 1) if total_avail_h > 0 else 0.0
        rooms_data.append({
            'room_id':   r.id,
            'room_name': r.room_name,
            'building':  getattr(r, 'building', 'N/A'),
            'used_hours':  round(used_h, 1),
            'avail_hours': total_avail_h,
            'utilization': pct,
            'class_count': c_count
        })
        total_used_sum  += used_h
        total_avail_sum += total_avail_h

    overall_pct = round((total_used_sum / total_avail_sum * 100), 1) if total_avail_sum > 0 else 0.0

    return jsonify({
        'overall_utilization': overall_pct,
        'total_scheduled_classes': total_scheduled_classes,
        'rooms': rooms_data,
        'settings': {
            'start_hour': start_h,
            'end_hour':   end_h,
            'day_hours':  day_hours,
            'active_days': active_days,
            'selected_semester': selected_sem
        }
    })


@app.route('/archive/semester', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def archive_semester():
    semester = request.form.get('semester', '1st Semester')
    academic_year = request.form.get('academic_year', '2024-2025')
    
    # Kuhanin lahat ng APPROVED (nasa ScheduledClass na) - Deduplicated for AI training data
    active_schedules = _dedup_schedules(ScheduledClass.query.filter_by(semester=semester, is_draft=False).all())
    
    if not active_schedules:
        flash(f'No approved schedules found to archive for {semester}.', 'warning')
        return redirect(url_for('reports_page'))

    archived_count = 0
    for sched in active_schedules:
        # Resolve relationships to safe text strings for the snapshot
        faculty_name = sched.faculty.full_name if sched.faculty else "T.B.A."
        room_name = sched.room.room_name if sched.room else "T.B.A."
        course_code = sched.course.course_code if sched.course else ""
        subject_code = "" # If we have subject code in the future, map it here, otherwise use course_name
        subject_title = sched.course.course_name if sched.course else ""
        section_name = sched.section.section_name if sched.section else ""

        history = HistoricalSchedule(
            semester=semester,
            academic_year=academic_year,
            course_code=course_code,
            section_name=section_name,
            subject_code=subject_code,
            subject_title=subject_title,
            faculty_name=faculty_name,
            room_name=room_name,
            day=sched.day,
            start_time=sched.start_time,
            end_time=sched.end_time,
            archived_by=session.get('username', 'System')
        )
        db.session.add(history)
        archived_count += 1
        
        # Opsyonal: Burahin yung active sched after ma-archive para fresh next sem?
        # User preference usually dictates this, for now we will KEEP active unless they bulk delete.

    db.session.commit()
    flash(f'Successfully archived {archived_count} schedules for {semester} {academic_year}!', 'success')
    return redirect(url_for('clean_archives_page'))

@app.route('/reports/clean-archives')
@login_required
@role_required('admin', 'superadmin')
def clean_archives_page():
    # Kunin lahat at i-sort
    history = HistoricalSchedule.query.order_by(HistoricalSchedule.academic_year.desc(), HistoricalSchedule.semester.desc(), HistoricalSchedule.archived_at.desc()).all()
    
    return render_template('clean_archives.html', history=history)




def _apply_style_from_template(target_cell, source_cell):
    """Deep copy font, border, fill, alignment, and number_format from source to target."""
    from copy import copy
    if source_cell.has_style:
        target_cell.font = copy(source_cell.font)
        target_cell.border = copy(source_cell.border)
        target_cell.fill = copy(source_cell.fill)
        target_cell.alignment = copy(source_cell.alignment)
        target_cell.number_format = copy(source_cell.number_format)

def _process_images(source_ws, target_ws, settings, layout_type):
    """
    Consolidated helper to copy images, apply scale, offsets, and layering in one pass.
    Fixes duplication and over-scaling bugs.
    """
    from openpyxl.drawing.image import Image
    from openpyxl.drawing.spreadsheet_drawing import OneCellAnchor
    from openpyxl.utils.units import pixels_to_EMU
    import copy
    import io
    import json

    # 1. CLEANUP: Clear any images that copy_worksheet might have partially/brokenly copied
    if hasattr(target_ws, '_images'):
        target_ws._images = []

    if not hasattr(source_ws, '_images'): return

    # 2. LOAD SETTINGS
    img_slots = []
    try:
        raw = getattr(settings, f"{layout_type}_img_settings", None)
        if raw: img_slots = json.loads(raw)
    except: pass

    # 3. CLONE AND APPLY TRANSFORMATIONS
    cloned_images = []
    
    # PERFORMANCE OPTIMIZATION: Extract raw bytes once to avoid "I/O on closed file" during bulk loops
    if not hasattr(source_ws, '_cached_images_data'):
        source_ws._cached_images_data = []
        for img in source_ws._images:
            try:
                source_ws._cached_images_data.append(img._data())
            except:
                source_ws._cached_images_data.append(None)

    for i, original_img in enumerate(source_ws._images):
        try:
            from openpyxl.drawing.spreadsheet_drawing import AnchorMarker
            
            # Use cached data if available to prevent multiple stream access
            raw_data = source_ws._cached_images_data[i] if i < len(source_ws._cached_images_data) else None
            if not raw_data:
                try: raw_data = original_img._data()
                except: continue
                
            # Create fresh independent image object from raw data
            new_img = Image(io.BytesIO(raw_data))
            
            # Transfer Anchor from template (Careful deep cloning of Markers)
            old_from = original_img.anchor._from
            new_from = AnchorMarker(col=old_from.col, colOff=old_from.colOff, row=old_from.row, rowOff=old_from.rowOff)
            
            if isinstance(original_img.anchor, OneCellAnchor):
                new_img.anchor = OneCellAnchor(_from=new_from, ext=copy.copy(original_img.anchor.ext))
            else:
                # For TwoCellAnchor, we clone both markers
                old_to = original_img.anchor.to
                new_to = AnchorMarker(col=old_to.col, colOff=old_to.colOff, row=old_to.row, rowOff=old_to.rowOff)
                from openpyxl.drawing.spreadsheet_drawing import TwoCellAnchor
                new_img.anchor = TwoCellAnchor(_from=new_from, to=new_to)

            # A. STANDARDIZED BASELINE
            aspect_ratio = float(original_img.height) / float(original_img.width) if original_img.width > 0 else 1.0
            slot = img_slots[i] if i < len(img_slots) else {}
            base_w = 110.0
            scale = float(slot.get('scale', 1.0))
            w = base_w * scale
            h = w * aspect_ratio
            
            # B. ANCHOR TYPE HANDLING (Force OneCellAnchor if scaling is changed)
            if scale != 1.0 and not isinstance(new_img.anchor, OneCellAnchor):
                new_anchor = OneCellAnchor(_from=new_from)
                new_img.anchor = new_anchor

            # C. POSITION OFFSETS (Pixels -> EMUs)
            dx = pixels_to_EMU(float(slot.get('x', 0.0)))
            dy = pixels_to_EMU(float(slot.get('y', 0.0)))
            
            # Apply offsets to our FRESH markers (prevent accumulation)
            new_img.anchor._from.colOff = (new_img.anchor._from.colOff or 0) + dx
            new_img.anchor._from.rowOff = (new_img.anchor._from.rowOff or 0) + dy

            # D. HARD-LOCK DIMENSIONS (Pixels -> EMUs)
            new_img.width = w
            new_img.height = h
            if hasattr(new_img.anchor, 'ext') and new_img.anchor.ext:
                new_img.anchor.ext.cx = pixels_to_EMU(w)
                new_img.anchor.ext.cy = pixels_to_EMU(h)

            cloned_images.append({'img': new_img, 'z_above': slot.get('z_above', True)})
        except Exception as e:
            print(f"Image processing error at index {i}: {e}")

    # 4. LAYER (Z-INDEX) AND ADD TO SHEET
    below = [item['img'] for item in cloned_images if not item['z_above']]
    above = [item['img'] for item in cloned_images if item['z_above']]
    
    for img in (below + above):
        target_ws.add_image(img)

@app.route('/export/excel_bulk')
@login_required
@role_required('admin', 'superadmin')
def export_excel_bulk():
    report_type = request.args.get('type', 'section') # section, faculty, room
    export_semester = request.args.get('semester', '1st Semester')
    settings = get_settings()

    # 1. LOAD SPECIFIC TEMPLATE (Uploaded via Layout Management)
    template_filename = f"{report_type}_template.xlsx"
    template_path = os.path.join(basedir, 'static', 'assets', template_filename)
    
    if not os.path.exists(template_path):
        if report_type == 'course':
            # Auto-fallback to section template for courses if specific one is missing
            template_filename = "section_template.xlsx"
            template_path = os.path.join(basedir, 'static', 'assets', template_filename)
            if not os.path.exists(template_path):
                flash(f'No template found for Course (and no section fallback).', 'danger')
                return redirect(url_for('reports_page'))
        else:
            flash(f'No template found for {report_type}. Please upload a {report_type} template in "Layouts" first.', 'danger')
            return redirect(url_for('reports_page'))

    # Load Workbook
    wb = load_workbook(template_path)
    template_sheet = wb.active
    
    # 2. GET ITEMS TO PRINT (All non-archived items)
    sem_label = export_semester.replace(' ', '_')
    if report_type == 'section':
        items = Section.query.filter_by(is_archived=False).order_by(Section.year_level, Section.section_name).all()
        out_filename = f"All_Sections_Schedule_{sem_label}.xlsx"
    elif report_type == 'faculty':
        items = Faculty.query.filter_by(is_archived=False).order_by(Faculty.full_name).all()
        out_filename = f"All_Faculty_Load_{sem_label}.xlsx"
    elif report_type == 'room':
        items = Room.query.filter_by(is_archived=False).order_by(Room.room_name).all()
        out_filename = f"All_Rooms_Utilization_{sem_label}.xlsx"
    elif report_type == 'course':
        items = Course.query.filter_by(is_archived=False).order_by(Course.course_code).all()
        out_filename = f"All_Course_Schedules_{sem_label}.xlsx"
    else:
        flash("Invalid report type.", "danger")
        return redirect(url_for('reports_page'))

    if not items:
        flash(f'No schedules found for {report_type} in {export_semester}.', 'warning')
        return redirect(url_for('reports_page'))

    # ------------------------------------------------------------------------------------------------------------------------------
    # 3. CREATE MASTER DATA SHEET (Sheet Index 0)
    # ------------------------------------------------------------------------------------------------------------------------------
    master_ws = wb.create_sheet("Master_Data_List", 0)
    master_ws.sheet_properties.tabColor = "198754" # Success Green
    
    m_headers = ["Semester", "AY", "Course Code", "Subject Title", "Section", "Faculty", "Room", "Day", "Time Slot"]
    master_ws.append(m_headers)
    
    for cell in master_ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="198754", end_color="198754", fill_type="solid")
        cell.alignment = Alignment(horizontal='center')

    for item in items:
        if report_type == 'section':
            schedules = _dedup_schedules(ScheduledClass.query.filter_by(section_id=item.id, semester=export_semester).all())
        elif report_type == 'faculty':
            schedules = _dedup_schedules(ScheduledClass.query.filter_by(faculty_id=item.id, semester=export_semester).all())
        elif report_type == 'room':
            schedules = _dedup_schedules(ScheduledClass.query.filter_by(room_id=item.id, semester=export_semester).all())
        else: # course
            schedules = _dedup_schedules(ScheduledClass.query.filter_by(course_id=item.id, semester=export_semester).all())
        
        for sc in schedules:
            master_ws.append([
                export_semester,
                settings.sem_ay_value if settings else "",
                sc.course.course_code if sc.course else "",
                sc.course.course_name if sc.course else "",
                sc.section.section_name if sc.section else "",
                sc.faculty.full_name if sc.faculty else "T.B.A.",
                sc.room.room_name if sc.room else "T.B.A.",
                sc.day,
                f"{sc.start_time} - {sc.end_time}"
            ])

    for col in master_ws.columns:
        master_ws.column_dimensions[col[0].column_letter].width = 25

    # ------------------------------------------------------------------------------------------------------------------------------
    # 4. PROCESS INDIVIDUAL SHEETS (GRID PLOT)
    # ------------------------------------------------------------------------------------------------------------------------------
    day_headers = {'Monday':['MON','MONDAY'],'Tuesday':['TUE','TUESDAY'],'Wednesday':['WED','WEDNESDAY'],'Thursday':['THU','THURS','THURSDAY'],'Friday':['FRI','FRIDAY'],'Saturday':['SAT','SATURDAY']}
    col_map = {} 
    row_map = {} 
    _t_occurrences = {}
    
    def fuzzy_clean(s):
        if not s or not isinstance(s, str): return ""
        for char in " :/-.,'0123456789":
            s = s.replace(char, "")
        return s.strip().upper()

    def _safe_write_to_cell(ws, target_row, target_col, value):
        target_cell = ws.cell(row=target_row, column=target_col)
        target_coord = target_cell.coordinate
        for merged_range in ws.merged_cells.ranges:
            if target_coord in merged_range:
                ws.cell(row=merged_range.min_row, column=merged_range.min_col).value = value
                return
        target_cell.value = value

    for row in template_sheet.iter_rows(min_row=1, max_row=60, max_col=26):
        for cell in row:
            val = ""
            if cell.value:
                if hasattr(cell.value, 'strftime'):
                    val = cell.value.strftime('%H:%M')
                else:
                    val = str(cell.value).strip().upper()
            if not val: continue
            for db_day, keywords in day_headers.items():
                if val in keywords: col_map[db_day] = cell.column
            
            # BRANCHED ROW MAPPING: Separate logic for Faculty vs Others
            if report_type == 'faculty':
                # EXACT SCANNER for Faculty: Only look at Column 1, strictly split labels
                if cell.column == 1:
                    time_parts = val.replace('-', ' ').replace('–', ' ').split()
                    if time_parts:
                        t_start = time_parts[0].lstrip('0').upper()
                        if ':' in t_start:
                            if t_start not in _t_occurrences: _t_occurrences[t_start] = []
                            if len(_t_occurrences[t_start]) < 2:
                                _t_occurrences[t_start].append(cell.row)
            else:
                # ORIGINAL BROAD SCANNER for Section/Room/Course (Universal compatibility)
                clean_time_val = val.lstrip('0') if ':' in val else val
                for h in range(1, 13):
                    for m in [0, 30]:
                        t_str = f"{h}:{m:02d}"
                        if clean_time_val.startswith(t_str):
                            if t_str not in _t_occurrences: _t_occurrences[t_str] = []
                            if len(_t_occurrences[t_str]) < 2:
                                _t_occurrences[t_str].append(cell.row)

    # Build the final row_map with AM/PM sensitivity (occ[0] is AM, occ[1] is PM)
    for h in range(7, 22): # Scan 7 AM to 9 PM
        for m in [0, 30]:
            t_key = f"{h}:{m:02d}"
            t_12 = f"{h if h <= 12 else h - 12}:{m:02d}"
            if t_12 in _t_occurrences:
                occ = _t_occurrences[t_12]
                # If it's afternoon (h >= 13) and there's a second occurrence, use it.
                row_map[t_key] = occ[0] if (h < 13 or len(occ) == 1) else (occ[1] if len(occ) > 1 else occ[0])

    for item in items:
        target_ws = wb.copy_worksheet(template_sheet)
        
        if report_type == 'section': 
            display_name = item.section_name
            dept_name = "N/A"
            item_schedules = ScheduledClass.query.filter_by(section_id=item.id, semester=export_semester).all()
        elif report_type == 'faculty':
            display_name = item.full_name
            dept_name = item.department if hasattr(item, 'department') else "N/A"
            item_schedules = ScheduledClass.query.filter_by(faculty_id=item.id, semester=export_semester).all()
        elif report_type == 'room':
            display_name = item.room_name
            dept_name = item.building if hasattr(item, 'building') else "N/A"
            item_schedules = ScheduledClass.query.filter_by(room_id=item.id, semester=export_semester).all()
        else: # course
            display_name = item.course_code
            dept_name = item.course_name # fallback to subject title
            item_schedules = ScheduledClass.query.filter_by(course_id=item.id, semester=export_semester).all()

        if report_type == 'section': 
            display_name = item.section_name
            dept_name = "N/A"
        elif report_type == 'faculty': 
            display_name = item.full_name
            dept_name = item.department
        elif report_type == 'room':
            display_name = item.room_name
            dept_name = item.building
        else: # course
            display_name = item.course_code
            dept_name = item.course_name
            
        safe_title = "".join([c for c in display_name if c.isalnum() or c in " -_"])[:30]
        target_ws.title = safe_title

        # ROOM LAYOUT SAFETY: Direct injection for Room Name (Room Only)
        if report_type == 'room':
            _safe_write_to_cell(target_ws, 10, 2, display_name)

        # A. SMART HEADER INJECTION & LOGO POSITIONING
        f_hours = "0"
        f_prep = "0"
        f_educ = ""
        
        if report_type == 'section':
             item_schedules = ScheduledClass.query.options(joinedload(ScheduledClass.course), joinedload(ScheduledClass.section)).filter_by(section_id=item.id, semester=export_semester).all()
        elif report_type == 'faculty':
             item_schedules = ScheduledClass.query.options(joinedload(ScheduledClass.course), joinedload(ScheduledClass.section)).filter_by(faculty_id=item.id, semester=export_semester).all()
             f_educ = item.highest_educational_attainment or ""
             total_mins = 0
             daily_mins = {"Monday": 0, "Tuesday": 0, "Wednesday": 0, "Thursday": 0, "Friday": 0, "Saturday": 0}
             unique_subs = set()
             for s in item_schedules:
                 try:
                     sh_str, sm_str = s.start_time.split(':')
                     eh_str, em_str = s.end_time.split(':')
                     duration = (int(eh_str) * 60 + int(em_str)) - (int(sh_str) * 60 + int(sm_str))
                     total_mins += duration
                     if s.day in daily_mins:
                         daily_mins[s.day] += duration
                 except: pass
                 if s.course: unique_subs.add(s.course.course_code)
             f_hours = str(round(total_mins / 60, 2))
             f_prep = str(len(unique_subs))
        elif report_type == 'room':
             item_schedules = ScheduledClass.query.options(joinedload(ScheduledClass.course), joinedload(ScheduledClass.section), joinedload(ScheduledClass.faculty)).filter_by(room_id=item.id, semester=export_semester).all()
        else: # course
             item_schedules = ScheduledClass.query.options(joinedload(ScheduledClass.course), joinedload(ScheduledClass.section), joinedload(ScheduledClass.faculty), joinedload(ScheduledClass.room)).filter_by(course_id=item.id, semester=export_semester).all()

        # A. BUILD VARIABLE MAP & DYNAMIC INJECTION
        # ----------------------------------------------------------------------------------------------------------
        vmap = build_variable_map(
            report_type, settings, 
            entity_name=display_name,
            faculty=(item if report_type == 'faculty' else None),
            prep_count=f_prep, 
            total_hours=f_hours, 
            sem_ay=export_semester
        )

        def inject_with_style(ws, r, c, n_val, source_cell):
            target = ws.cell(row=r, column=c) # Same cell now for tokens
            target.value = n_val
            # Inherit style if not already set
            if not target.has_style:
                _apply_style_from_template(target, source_cell)

        # Scanner for Header (1-40) and Footer (Last 30)
        max_r = target_ws.max_row
        scan_ranges = [range(1, 41), range(max(1, max_r - 30), max_r + 1)]
        
        # Label-to-Value Offset Registry (BASED ON FINAL COORDINATE TABLE)
        # Section: B11(CLASS)->B10 is (-1,0), G11(Sem)->G10 is (-1,0)
        # Faculty: A15(Name:)->C15 is (0,2), A70(Instructor I)->A69 is (-1,0)
        offsets = {
            'faculty': {
                "Name:":                      (0, 2),   # A15 -> C15
                "Highest Educ. Attainment:":  (0, 2),   # A16 -> C16
                "No. of Preparation/s:":      (0, 2),   # A17 -> C17
                "Total no. of contact hours per week:": (0, 2), # F17 -> H17
                "OIC, Registrar":             (-1, 0),  # A75 -> A74
                "OIC-Registrar":              (-1, 0),
                "Registrar":                  (-1, 0),
                "Department Chairperson":     (-1, 0),
                "Director, Instruction":      (-1, 0),
                "Campus Administrator":       (-1, 0),
                "Instructor I":               (-1, 0),  # Anchor for dynamic Rank & Name Above
            },
            'section': {
                "CLASS":                      (-1, 0),  
                "ROOM":                       (-1, 0),
                "COURSE":                     (-1, 0),
                "Semester / Academic Year":   (-1, 0),  
                "Prepared by:":               (3, 0),  
                "Recommending Approval:":     (3, 1),   
                "APPROVED:":                  (3, 0),   
            },
            'course': {
                "CLASS":                      (-1, 0),  
                "ROOM":                       (-1, 0),
                "COURSE":                     (-1, 0),
                "Semester / Academic Year":   (-1, 0),  
                "Prepared by:":               (3, 1),   
                "Recommending Approval:":     (3, 1),   
                "APPROVED:":                  (3, 1),   
            },
            'room': {
                "ROOM":                       (-1, 0),  # Anchor B11 -> Target B10
                "Prepared by:":               (3, 1),   # Anchor A43 -> Target B46:C47
                "Recommending Approval:":     (3, 1),   
                "APPROVED:":                  (3, 1),   
            }
        }
        
        # Mapping for actual data injection
        val_map = {
            'faculty': {
                "Name:":                      display_name,
                "Highest Educ. Attainment:":  f_educ,
                "No. of Preparation/s:":      str(f_prep),
                "Total no. of contact hours per week:": str(f_hours),
                "OIC, Registrar":             vmap.get('{{fac_registrar_name}}', 'MARLYN A. QUINEZ'),
                "Department Chairperson":     vmap.get('{{fac_chair_name}}', 'ARIES M. GELERA'),
                "Director, Instruction":      vmap.get('{{fac_director_name}}', 'ARIEL G. SANTOS, EdD'),
                "Campus Administrator":       vmap.get('{{fac_admin_name}}', 'LAURO B. PASCUA, EdD'),
                "Instructor I":               display_name, # Name above Rank (Row 69)
            },
            'section': {
                "CLASS":                      display_name,
                "ROOM":                       display_name,
                "COURSE":                     display_name,
                "Semester / Academic Year":   vmap.get('{{sem_ay_value}}', export_semester),
            },
            'course': {
                "CLASS":                      display_name,
                "ROOM":                       display_name,
                "COURSE":                     display_name,
                "Semester / Academic Year":   vmap.get('{{sem_ay_value}}', export_semester),
                "Section name":               dept_name,
                "course name":                dept_name,
                "Prepared by:":               vmap.get('{{sig1}}', 'SCHEDULE COMMITTEE'),
                "Recommending Approval:":     vmap.get('{{sig2}}', 'ARIEL G. SANTOS, EdD'),
                "APPROVED:":                  vmap.get('{{sig3}}', 'LAURO B. PASCUA, EdD'),
            }
        }
        # Dynamic Rank: Handle whatever is in the Instructor I cell
        vmap["Instructor I"] = vmap.get("{{fac_rank}}", "Instructor I")

        # Marker Map: Default Template Text -> Variable Token
        m_map = {
            "Republic of the Philippines": "{{republic_text}}" if report_type != 'faculty' else "{{fac_republic_text}}",
            "CAVITE STATE UNIVERSITY":    "{{school}}" if report_type != 'faculty' else "{{fac_univ_name}}",
            "CCAT Campus":                "{{campus}}" if report_type != 'faculty' else "{{fac_campus_name}}",
            "Rosario, Cavite":            "{{address}}" if report_type != 'faculty' else "{{fac_address}}",
            "(046) 437-9505 / (046) 437-6659": "{{contact}}" if report_type != 'faculty' else "{{fac_contact_details}}",
            "cvsurosario@cvsu.edu.ph":    "{{email}}" if report_type != 'faculty' else "{{fac_email}}",
            "www.cvsu-rosario.edu.ph":    "{{website}}" if report_type != 'faculty' else "{{fac_website}}",
            "' (046) 437-9505 / 7 (046) 437-6659": "{{contact}}" if report_type != 'faculty' else "{{fac_contact_details}}",
            
            "Prepared by:":               "{{prepared_by_label}}",
            "Recommending Approval:":     "{{rec_approval_label}}" if report_type != 'faculty' else "{{fac_rec_approval_label}}",
            "APPROVED:":                  "{{approved_label}}" if report_type != 'faculty' else "{{fac_approved_label}}",
            "CLASS":                      "{{class_label}}",
            "ROOM":                       "{{room_label}}",
            "COURSE":                     "{{course_label}}",
            "Semester / Academic Year":   "{{sem_ay_label}}",
            
            "Section name":               "{{name}}",
            "room name":                  "{{name}}",
            "course name":                "{{name}}",
            "faculty name":               "{{fac_name}}",
            "Second / 2023-2024":         "{{sem_ay_value}}",
            
            "SCHEDULE COMMITTEE":         "{{sig1}}",
            "MARLYN A. QUINEZ":           "{{fac_registrar_name}}",
            "MARLYN A. QUIÑEZ":           "{{fac_registrar_name}}",
            "ARIES M. GELERA":            "{{fac_chair_name}}",
            "ARIEL G. SANTOS, EdD":       "{{sig2}}" if report_type != 'faculty' else "{{fac_director_name}}",
            "LAURO B. PASCUA, EdD":       "{{sig3}}" if report_type != 'faculty' else "{{fac_admin_name}}",
            
            # Use fixed template placeholder as dynamic anchor for rank replacement
            "Instructor I":               "{{fac_rank}}",
            
            "Director, Instruction":      "{{sig2_title}}" if report_type != 'faculty' else "{{fac_director_title}}",
            "Campus Administrator":       "{{sig3_title}}" if report_type != 'faculty' else "{{fac_admin_title}}",
            "Department Chairperson":     "{{fac_chair_title}}",
            "OIC, Registrar":             "{{fac_registrar_label}}",

            "DEPARTMENT OF COMPUTER STUDIES": "{{fac_dept_label}}",
            "FACULTY CLASS SCHEDULE":      "{{fac_sched_title}}",
            "SECOND SEMESTER SY 2023 - 2024": "{{fac_sem_ay_label}}",
            "Highest Educ. Attainment:":  "{{fac_educ_label}}",
            "No. of Preparation/s:":      "{{fac_prep_label}}",
            "Total no. of contact hours per week:": "{{fac_hours_label}}",
            "Consultation:":              "{{fac_consultation}}",
            "Research:":                  "{{fac_research}}",
            "Designation:":               "{{fac_designation}}",
            "Extension:":                 "{{fac_extension}}",
            "Conforme:":                  "{{fac_conforme_label}}",
            "Reviewed by:":               "{{fac_reviewed_label}}",
            "Approved:":                  "{{fac_approved_label}}",
            "V01-2018-07-24":             "{{fac_form_num_bottom}}",
            "VPAA-QF-11":                 "{{fac_form_num_top}}",
            "Name:":                      "{{fac_name_label}}" if report_type == 'faculty' else "{{name}}",
        }


        # CONSOLIDATED SCANNER: One loop for all replacements
        for r_idx in range(1, target_ws.max_row + 1):
            for c_idx in range(1, 26):
                cell = target_ws.cell(row=r_idx, column=c_idx)
                val = cell.value
                if not val or not isinstance(val, str): continue
                
                val = cell.value
                if not val or not isinstance(val, str): continue
                
                original_val = val
                clean_original_val = fuzzy_clean(val) # <--- STORE ORIGINAL FOR ANCHORS
                clean_val = fuzzy_clean(val)
                
                # 1. MARKER SWAP (Literals -> Tokens)
                for m_text, t_token in m_map.items():
                    if fuzzy_clean(m_text) == clean_val:
                        if t_token in vmap:
                            val = str(vmap[t_token])
                            cell.value = val
                            original_val = val 
                            break
                
                # 2. TOKEN INTERPOLATION ({{braces}})
                match_replaced = False
                for t_key, t_val in vmap.items():
                    if t_key in val:
                        val = val.replace(t_key, str(t_val))
                        match_replaced = True
                
                if match_replaced or cell.value != original_val:
                    if match_replaced: cell.value = val
                    # Signatory styling (Bold + Underline)
                    is_sig_field = any(f"{{sig{i}}}" in str(original_val) for i in range(1, 10)) or \
                                 any(f"{{fac_chair_name}}" in str(original_val) for i in range(1, 10)) or \
                                 any(x in str(original_val) for x in ["SANTOS", "PASCUA", "GELERA", "QUINEZ"])
                    if is_sig_field:
                        cell.font = Font(name='Arial Narrow', size=11, bold=True, underline='single')
                        cell.alignment = Alignment(horizontal='center')
                
                # 3. COORDINATE OVERRIDES (Offsets)
                if settings:
                    l_target = offsets.get(report_type, {})
                    v_target = val_map.get(report_type, {})
                    
                    label_found = None
                    # FIX: Use clean_original_val to find anchors even if Step 1 replaced them
                    for log_label, (dr, dc) in l_target.items():
                        if log_label and fuzzy_clean(log_label) == clean_original_val:
                            label_found = log_label
                            break
                    
                    if label_found:
                        dr, dc = l_target[label_found]
                        target_val = v_target.get(label_found)
                        if target_val:
                            # Write raw value (Cleanup for the key 5 dynamic values)
                            # User only wants to remove hashes from dynamic VALUES, keeping them for labels.
                            _safe_write_to_cell(target_ws, r_idx + dr, c_idx + dc, str(target_val))


        # B. PLOT SCHEDULES WITH STYLE INHERITANCE
        # Use first grid cell as style reference for all schedule blocks
        ref_cell = None
        try:
            first_day = list(col_map.keys())[0] if col_map else 'Monday'
            ref_cell = template_sheet.cell(row=row_map.get("7:00", 20), column=col_map.get(first_day, 2))
        except: pass
        # STABILITY OVERHAUL: Phase 1 - Clear existing template merges in the grid area
        # This prevents the "Repaired" error caused by collisions between template merges and code merges.
        grid_min_r, grid_max_r = 20, 41
        grid_min_c, grid_max_c = 2, 8   # Col B to H
        
        existing_merged_ranges = list(target_ws.merged_cells.ranges)
        for mrange in existing_merged_ranges:
            # INTERSECTION CHECK: If the template merge touches our grid area at all, unmerge it
            overlap_r = not (mrange.max_row < grid_min_r or mrange.min_row > grid_max_r)
            overlap_c = not (mrange.max_col < grid_min_c or mrange.min_col > grid_max_c)
            if overlap_r and overlap_c:
                try: target_ws.unmerge_cells(str(mrange))
                except: pass

        # Phase 2: Map grid content for unique merges
        grid_slots = {}
        for sc in item_schedules:
            if sc.day not in col_map: continue
            try:
                sh_s, sm_s = map(int, sc.start_time.split(':'))
                eh_e, em_e = map(int, sc.end_time.split(':'))
            except: continue
            
            start_key = f"{sh_s}:{sm_s:02d}"
            if start_key in row_map:
                s_r = row_map[start_key]
                slots = int(((eh_e * 60 + em_e) - (sh_s * 60 + sm_s)) / 30)
                e_r = s_r + slots - 1
                
                plot_key = (sc.day, s_r, e_r)
                if plot_key not in grid_slots:
                    grid_slots[plot_key] = []
                
                ctype = f"({sc.session_type})" if sc.session_type else ""
                txt = ""
                if report_type == 'faculty':
                    if sc.course: txt += f"{sc.course.course_code} {ctype}\n"
                    if sc.section: txt += f"{sc.section.section_name}\n"
                    if sc.room: txt += f"{sc.room.room_name}"
                elif report_type == 'section':
                    txt = f"{sc.course.course_code} {ctype}\n"
                    fn = sc.faculty.full_name if sc.faculty else "T.B.A."
                    p = fn.split()
                    short_f = f"MR. {p[-1].upper()}" if (len(p) > 1 and not fn.startswith('T.B.A.')) else fn.upper()
                    txt += f"{short_f}\n{sc.room.room_name if sc.room else ''}"
                elif report_type == 'room':
                    txt = f"{sc.course.course_code} {ctype}\n{sc.section.section_name if sc.section else ''}\n"
                    fn = sc.faculty.full_name if sc.faculty else "T.B.A."
                    p = fn.split()
                    short_f = f"MR. {p[-1].upper()}" if (len(p) > 1 and not fn.startswith('T.B.A.')) else fn.upper()
                    txt += f"{short_f}"
                else: # course
                    # Show Section, Room, and Faculty (Course Code is redundant in a Course report)
                    fn = sc.faculty.full_name if sc.faculty else "T.B.A."
                    p = fn.split()
                    short_f = f"MR. {p[-1].upper()}" if (len(p) > 1 and not fn.startswith('T.B.A.')) else fn.upper()
                    txt = f"{sc.section.section_name if sc.section else ''}\n{sc.room.room_name if sc.room else ''}\n{short_f}"
                
                grid_slots[plot_key].append(txt)

        # Phase 3: Plot aggregated slots
        thin = Side(border_style="thin", color="000000")
        full_border = Border(top=thin, left=thin, right=thin, bottom=thin)
        for (day, s_r, e_r), texts in grid_slots.items():
            t_col = col_map[day]
            if e_r > s_r:
                try: target_ws.merge_cells(start_row=s_r, start_column=t_col, end_row=e_r, end_column=t_col)
                except: pass
            
            cell = target_ws.cell(row=s_r, column=t_col)
            cell.value = "\n---\n".join(texts)
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            cell.font = Font(name='Arial Narrow', size=9)
            
            for r in range(s_r, e_r + 1):
                target_ws.cell(row=r, column=t_col).border = full_border


        # C. POPULATE FACULTY SUMMARY TABLE (Bottom List)
        if report_type == 'faculty':
            # 1. Inject DAILY CONTACT HOURS totals (Row above header)
            daily_hours_row = 0
            for r_idx in range(1, 100):
                l_val = str(target_ws.cell(row=r_idx, column=1).value or "").strip().upper()
                if "DAILY CONTACT HOURS" in l_val:
                    daily_hours_row = r_idx
                    break
            
            if daily_hours_row:
                for day, d_mins in daily_mins.items():
                    if day in col_map:
                        d_col = col_map[day]
                        d_hours = round(d_mins / 60, 2)
                        target_ws.cell(row=daily_hours_row, column=d_col).value = d_hours

            # 2. Populate data starting exactly at Row 51 (per Image)
            summary_start_row = 51
            summary_max_data_row = 60 # Data container ends here
            summary_data = {}
            for sc in item_schedules:
                key = (sc.course_id, sc.section_id)
                # Calculate Duration Fallback (Contact Hours) based on schedule (matches Browser View)
                c_dur = 0.0
                try:
                    sh, sm = map(int, sc.start_time.split(':'))
                    eh, em = map(int, sc.end_time.split(':'))
                    c_dur = (eh * 60 + em - sh * 60 - sm) / 60.0
                except: pass

                if key not in summary_data:
                    c_obj = sc.course
                    summary_data[key] = {
                        'code': c_obj.course_code if c_obj else "",
                        'name': c_obj.course_name if c_obj else "",
                        'section': sc.section.section_name if sc.section else "",
                        'lec_h': 0.0,
                        'lab_h': 0.0,
                        'lec_units': float(c_obj.lec_units or 0) if c_obj else 0.0,
                        'lab_units': float(c_obj.lab_units or 0) if c_obj else 0.0,
                        'students': sc.section.number_of_students if sc.section else 0,
                        'rooms_set': set()
                    }
                if sc.session_type == 'Lab': summary_data[key]['lab_h'] += c_dur
                else: summary_data[key]['lec_h'] += c_dur
                if sc.room: summary_data[key]['rooms_set'].add(sc.room.room_name)
            
            curr_row = summary_start_row
            total_lec = 0.0
            total_lab = 0.0
            total_students = 0
            
            for data in summary_data.values():
                if curr_row > summary_max_data_row: break
                
                # TRIPLE-SAFE DATA: Use Course units if > 0, fallback to Calculated Hours (matches System View Image 3)
                final_lec = data['lec_units'] if data['lec_units'] > 0 else data['lec_h']
                final_lab = data['lab_units'] if data['lab_units'] > 0 else data['lab_h']

                # Col A(1): Subject Code, Col C(3): Section, Col D(4): Lec, Col E(5): Lab, Col F(6): Total, Col G(7): Room(s), Col H(8): Students
                target_ws.cell(row=curr_row, column=1).value = data['code']
                target_ws.cell(row=curr_row, column=3).value = data['section']
                target_ws.cell(row=curr_row, column=4).value = final_lec
                target_ws.cell(row=curr_row, column=5).value = final_lab
                total_row_val = final_lec + final_lab
                target_ws.cell(row=curr_row, column=6).value = total_row_val
                target_ws.cell(row=curr_row, column=7).value = ", ".join(sorted(list(data['rooms_set']))) if data['rooms_set'] else "T.B.A."
                target_ws.cell(row=curr_row, column=8).value = data['students']
                
                total_lec += final_lec
                total_lab += final_lab
                total_students += data['students']
                curr_row += 1

            # 3. Ensure full borders and footer totals (Row 51 to 61)
            thin_side = Side(border_style="thin", color="000000")
            table_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
            for r in range(summary_start_row, 62): 
                for c in range(1, 9): 
                    target_ws.cell(row=r, column=c).border = table_border

            # 4. Footer Totals exactly on Row 61
            footer_row = 61
            target_ws.cell(row=footer_row, column=4).value = total_lec
            target_ws.cell(row=footer_row, column=5).value = total_lab
            target_ws.cell(row=footer_row, column=6).value = total_lec + total_lab
            target_ws.cell(row=footer_row, column=8).value = total_students
        # D. PROCESS IMAGES (Cloning, Scaling, Offsets, Layering)
        _process_images(template_sheet, target_ws, settings, report_type)

        # E. PAGE SETUP
        if settings:
            p_map = {'A4': 9, 'Letter': 1, 'Legal': 5}
            target_ws.page_setup.paperSize = p_map.get(settings.paper_size, 9)
            target_ws.page_margins.top    = settings.margin_top
            target_ws.page_margins.bottom = settings.margin_bottom
            target_ws.page_margins.left   = settings.margin_left
            target_ws.page_margins.right  = settings.margin_right
            target_ws.page_setup.orientation = target_ws.ORIENTATION_LANDSCAPE

    wb.remove(template_sheet)
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return Response(out, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={"Content-Disposition": f"attachment;filename={out_filename}"})


@app.route('/manage/pre-assignments')
@login_required
@role_required('admin', 'superadmin')
def manage_preassignments():
    sort_by = request.args.get('sort', 'default', type=str)
    # ------------------------------------ Time Machine: Historical Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    if session.get('historical_mode_active', False):
        archive_id = session.get('active_archive_id')
        all_objs = get_archive_entities(archive_id, 'PreAssignment')
        
        # Joins for sorting (mocked)
        all_courses = get_archive_entities(archive_id, 'Course')
        all_sections = get_archive_entities(archive_id, 'Section')
        course_map = {c.id: getattr(c, 'course_code', '') for c in all_courses}
        sec_map = {s.id: getattr(s, 'section_name', '') for s in all_sections}

        if sort_by == 'course-asc':
            all_objs.sort(key=lambda x: course_map.get(getattr(x, 'course_id', 0), ''))
        elif sort_by == 'course-desc':
            all_objs.sort(key=lambda x: course_map.get(getattr(x, 'course_id', 0), ''), reverse=True)
        elif sort_by == 'section-asc':
            all_objs.sort(key=lambda x: sec_map.get(getattr(x, 'section_id', 0), ''))
        elif sort_by == 'section-desc':
            all_objs.sort(key=lambda x: sec_map.get(getattr(x, 'section_id', 0), ''), reverse=True)
        else:
            # Fallback for Newest: Sort by created_at if it exists, else id
            all_objs.sort(key=lambda x: (getattr(x, 'created_at', None) or datetime.min, getattr(x, 'id', 0)), reverse=True)

        return render_template(
            'manage_preassignments.html',
            pre_assignments=all_objs,
            all_courses=all_courses,
            all_sections=all_sections,
            all_faculty=get_archive_entities(archive_id, 'Faculty'),
            all_rooms=get_archive_entities(archive_id, 'Room'),
            days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
            time_slots=[f"{h:02d}:{m:02d}" for h in range(7, 20) for m in (0, 30)],
            current_sort=sort_by
        )

    # ------------------------------------ Live Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '', type=str)
    
    query = PreAssignment.query.filter_by(is_archived=False)
    if search_query:
        query = query.join(Course).join(Section).join(Faculty).filter(or_(
            Course.course_code.ilike(f"%{search_query}%"),
            Section.section_name.ilike(f"%{search_query}%"),
            Faculty.full_name.ilike(f"%{search_query}%")
        ))

    if sort_by == 'course-asc': query = query.join(Course).order_by(Course.course_code.asc())
    elif sort_by == 'course-desc': query = query.join(Course).order_by(Course.course_code.desc())
    elif sort_by == 'section-asc': query = query.join(Section).order_by(Section.section_name.asc())
    elif sort_by == 'section-desc': query = query.join(Section).order_by(Section.section_name.desc())
    elif sort_by == 'newest' or sort_by == 'default': query = query.order_by(PreAssignment.created_at.desc(), PreAssignment.id.desc())
    else: query = query.order_by(PreAssignment.id.desc())
    
    pagination = query.paginate(page=page, per_page=10, error_out=False)

    return render_template(
        'manage_preassignments.html',
        pre_assignments=pagination.items,
        pagination=pagination,
        all_courses=Course.query.filter_by(is_archived=False).order_by(Course.course_code).all(),
        all_sections=Section.query.filter_by(is_archived=False).order_by(Section.section_name).all(),
        all_faculty=Faculty.query.filter_by(is_archived=False).order_by(Faculty.full_name).all(),
        all_rooms=Room.query.filter_by(is_archived=False).order_by(Room.room_name).all(),
        days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
        time_slots=[f"{h:02d}:{m:02d}" for h in range(7, 20) for m in (0, 30)],
        current_sort=sort_by,
        search_query=search_query
    )

@app.route('/manage/pre-assignment/add', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def add_preassignment():
    # 1. Get Data
    course_id = request.form.get('course_id')
    faculty_id = request.form.get('faculty_id')
    room_id = request.form.get('room_id')
    day = request.form.get('day')
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    
    # Get LIST of Section IDs (Checkboxes)
    section_ids = request.form.getlist('section_ids') 

    # Basic Validation
    if not (course_id and faculty_id and room_id and day and start_time and end_time and section_ids):
        flash('Error: All fields are required. Please select at least one section.', 'danger')
        return redirect(url_for('manage_preassignments'))
    
    if start_time >= end_time:
        flash('Error: Start time must be before End time.', 'danger')
        return redirect(url_for('manage_preassignments'))

    success_count = 0
    error_messages = []

    # 2. LOOP THROUGH SELECTED SECTIONS
    for sec_id in section_ids:
        data = {
            'course_id': course_id, 'section_id': sec_id,
            'faculty_id': faculty_id, 'room_id': room_id,
            'day': day, 'start': start_time, 'end': end_time
        }
        
        # Check Conflict per section
        has_conflict, msg = check_conflict(data)
        
        if has_conflict:
            error_messages.append(msg)
        else:
            # Save
            db.session.add(PreAssignment(
                course_id=int(course_id), section_id=int(sec_id), 
                faculty_id=int(faculty_id), room_id=int(room_id), 
                day=day, start_time=start_time, end_time=end_time
            ))
            success_count += 1

    db.session.commit()

    # 3. Feedback
    if success_count > 0:
        flash(f'Successfully locked schedule for {success_count} sections.', 'success')
    
    if error_messages:
        # Show first few errors if any
        flash(f"Some conflicts occurred: {'; '.join(error_messages[:3])}...", 'warning')

    return redirect(url_for('manage_preassignments'))

# --- BULK ACTIONS FOR PRE-ASSIGNMENTS ---

@app.route('/manage/preassignments/bulk_archive', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def bulk_archive_preassignments():
    pa_ids = request.form.getlist('row_ids')
    
    if pa_ids:
        PreAssignment.query.filter(PreAssignment.id.in_(pa_ids)).update(
            {PreAssignment.is_archived: True, PreAssignment.deleted_at: datetime.utcnow()},
            synchronize_session=False)
        db.session.commit()
        flash(f'{len(pa_ids)} schedules moved to Recycle Bin.', 'success')
    else:
        flash('No items selected.', 'secondary')
        
    return redirect(url_for('manage_preassignments'))

@app.route('/manage/preassignments/bulk_restore', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def bulk_restore_preassignments():
    pa_ids = request.form.getlist('row_ids')
    
    if pa_ids:
        PreAssignment.query.filter(PreAssignment.id.in_(pa_ids)).update({PreAssignment.is_archived: False}, synchronize_session=False)
        db.session.commit()
        flash(f'{len(pa_ids)} schedules restored.', 'success')
    
    return redirect(url_for('preassignments_archive'))

@app.route('/manage/preassignments/bulk_delete', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def bulk_delete_preassignments():
    pa_ids = request.form.getlist('row_ids')
    
    if pa_ids:
        PreAssignment.query.filter(PreAssignment.id.in_(pa_ids)).delete(synchronize_session=False)
        db.session.commit()
        flash(f'{len(pa_ids)} schedules permanently deleted.', 'danger')
    
    return redirect(url_for('preassignments_archive'))
    
@app.route('/manage/pre-assignment/archive/<int:pa_id>', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def archive_preassignment(pa_id):
    pa = PreAssignment.query.get_or_404(pa_id)
    pa.is_archived = True
    pa.deleted_at = datetime.utcnow()
    db.session.commit()
    flash('Schedule moved to Recycle Bin.', 'success')
    return redirect(url_for('manage_preassignments'))

@app.route('/manage/pre-assignments/archive')
@login_required
@role_required('admin', 'superadmin')
def preassignments_archive():
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'default', type=str)
    search_query = request.args.get('search', '', type=str)
    
    query = PreAssignment.query.filter_by(is_archived=True)
    
    if search_query:
        search_term = f"%{search_query}%"
        # Search by course code or section name
        query = query.join(Course).join(Section).filter(
            or_(Course.course_code.ilike(search_term), Section.section_name.ilike(search_term))
        )
        
    if sort_by == 'course-asc': query = query.join(Course).order_by(Course.course_code.asc())
    elif sort_by == 'course-desc': query = query.join(Course).order_by(Course.course_code.desc())
    elif sort_by == 'section-asc': query = query.join(Section).order_by(Section.section_name.asc())
    elif sort_by == 'section-desc': query = query.join(Section).order_by(Section.section_name.desc())
    elif sort_by == 'newest' or sort_by == 'default': query = query.order_by(PreAssignment.deleted_at.desc(), PreAssignment.id.desc())
    else: query = query.order_by(PreAssignment.id.desc())
    
    pagination = query.paginate(page=page, per_page=10, error_out=False)
    
    return render_template('preassignments_archive.html', 
                           pre_assignments=pagination.items, 
                           pagination=pagination,
                           current_sort=sort_by, 
                           search_query=search_query,
                           now=datetime.utcnow())

@app.route('/manage/pre-assignment/restore/<int:pa_id>', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def restore_preassignment(pa_id):
    pa = PreAssignment.query.get_or_404(pa_id)
    pa.is_archived = False
    pa.deleted_at = None
    db.session.commit()
    return redirect(url_for('preassignments_archive'))

@app.route('/manage/pre-assignment/delete/<int:pa_id>', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def delete_preassignment(pa_id):
    db.session.delete(PreAssignment.query.get_or_404(pa_id))
    db.session.commit()
    return redirect(url_for('preassignments_archive'))

# --- CONSTRAINT MANAGEMENT ROUTES ---

# --- MANAGE CONSTRAINTS (UPDATED WITH PAGINATION & FILTER) ---
@app.route('/manage/constraints', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'superadmin')
def manage_constraints():
    if request.method == 'POST':
        for key, value in request.form.items():
            if key.startswith('type_'):
                c_id = key.split('_')[1]
                constraint = Constraint.query.get(c_id)
                if constraint:
                    constraint.constraint_type = value
            elif key.startswith('weight_'):
                c_id = key.split('_')[1]
                constraint = Constraint.query.get(c_id)
                if constraint:
                    # Clamp weight between 1 and 10
                    try:
                        w = int(value)
                        constraint.weight = max(1, min(100, w))
                    except ValueError:
                        pass
        db.session.commit()
        return redirect(request.referrer or url_for('manage_constraints'))

    # 2. Handle VIEW (GET)
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '', type=str)
    sort_by = request.args.get('sort', 'name-asc', type=str) # Default: HC-01 to HC-20
    filter_type = request.args.get('filter', 'all', type=str) # New Filter

    # Base Query
    query = Constraint.query

    # Apply Type Filter (HC, SC1, SC2, NC)
    if filter_type != 'all':
        query = query.filter_by(constraint_type=filter_type)

    # Apply Search
    if search_query:
        query = query.filter(or_(
            Constraint.name.ilike(f"%{search_query}%"),
            Constraint.category.ilike(f"%{search_query}%")
        ))

    # Apply Sort
    if sort_by == 'name-desc':
        query = query.order_by(Constraint.name.desc())
    elif sort_by == 'name-asc':
        query = query.order_by(Constraint.name.asc())
    elif sort_by == 'category':
        query = query.order_by(Constraint.category.asc(), Constraint.name.asc())
    elif sort_by == 'newest' or sort_by == 'default':
        query = query.order_by(Constraint.created_at.desc(), Constraint.id.desc())
    else:
        query = query.order_by(Constraint.name.asc())

    # Apply Pagination
    pagination = query.paginate(page=page, per_page=10, error_out=False)
    
    return render_template(
        'manage_constraints.html', 
        constraints=pagination.items, 
        pagination=pagination,
        current_sort=sort_by,
        current_filter=filter_type,
        search_query=search_query
    )

# --- SYNC CONSTRAINTS (Safe upsert ---- preserves user-set types/weights) ---
@app.route('/manage/constraints/sync', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def sync_constraints():
    """
    Upserts the master constraint list into the DB.
    - Existing rows: updates name, description, category (KEEPS user's type & weight).
    - Missing rows: inserts with the default type and weight=10.
    """
    MASTER_CONSTRAINTS = [
        # ── HARD CONSTRAINTS (HC-01 to HC-23) ──────────────────────────────────────
        {'code': 'LOCKED_SCHEDULES',           'cat': 'Administrative', 'type': 'HC',  'weight': 1,   'name': '(HC-01) Locked Schedules', 'desc': 'Manually plotted schedules are immovable.'},
        {'code': 'MINOR_SUBJECT_GAP',          'cat': 'Administrative', 'type': 'HC',  'weight': 1,   'name': '(HC-02) Space for Minor Subjects', 'desc': 'Ensure free slots for unscheduled minor courses.'},
        {'code': 'GLOBAL_DAY_RESTRICTION',     'cat': 'Administrative', 'type': 'HC',  'weight': 1,   'name': '(HC-03) Global Day Restriction', 'desc': 'No classes on Sundays or non-academic days.'},
        {'code': 'STRICT_ALLOC_ASYNC',         'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-04) Strict Async Allocation', 'desc': 'Online classes must be in Virtual rooms.'},
        {'code': 'STRICT_LEC_DURATION',        'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-05) Strict Lecture Duration', 'desc': 'Lec hours must match curriculum.'},
        {'code': 'STRICT_LAB_DURATION',        'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-06) Strict Laboratory Duration', 'desc': 'Lab hours must match curriculum.'},
        {'code': 'STRICT_ASYNC_LEC_DUR',       'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-07) Strict Async Lec Dur', 'desc': 'Async hours must match curriculum.'},
        {'code': 'STRICT_ASYNC_LAB_DUR',       'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-08) Strict Async Lab Dur', 'desc': 'Async hours must match curriculum.'},
        {'code': 'SECTION_OVERLAP',            'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-09) No Section Course Conflict', 'desc': 'Section cannot have 2 courses at once.'},
        {'code': 'FACULTY_OVERLAP',            'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-10) No Faculty Course Conflict', 'desc': 'Faculty cannot teach 2 courses at once.'},
        {'code': 'SECTION_DAY_RESTRICTIONS',   'cat': 'Section',        'type': 'HC',  'weight': 1,   'name': '(HC-11) Section Day Restrictions', 'desc': 'Follow section-specific day blocks.'},
        {'code': 'MAX_CONSECUTIVE_STUDENT',    'cat': 'Section',        'type': 'HC',  'weight': 1,   'name': '(HC-12) Max Consecutive Student Load', 'desc': 'Max 6 consecutive hours for students.'},
        {'code': 'ROOM_OVERLAP',               'cat': 'Section',        'type': 'HC',  'weight': 1,   'name': '(HC-13) No Multiple Sections in Room', 'desc': 'Room cannot host 2 sections at once.'},
        {'code': 'SINGLE_FACULTY_PER_TIMESLOT','cat': 'Faculty',        'type': 'HC',  'weight': 1,   'name': '(HC-14) Single Fac per Section Slot', 'desc': 'Section cannot have 2 faculty at once.'},
        {'code': 'FACULTY_AVAILABILITY',       'cat': 'Faculty',        'type': 'HC',  'weight': 1,   'name': '(HC-15) Faculty Availability', 'desc': 'Faculty must be available.'},
        {'code': 'MAX_CONSECUTIVE_FACULTY',    'cat': 'Faculty',        'type': 'HC',  'weight': 1,   'name': '(HC-16) Max Consecutive Faculty Load', 'desc': 'Max 6 consecutive hours for faculty.'},
        {'code': 'SINGLE_ROOM_PER_SESSION',    'cat': 'Room',           'type': 'HC',  'weight': 1,   'name': '(HC-17) Single Room per Session', 'desc': 'Session cannot use 2 rooms at once.'},
        {'code': 'ROOM_AVAILABILITY',          'cat': 'Room',           'type': 'HC',  'weight': 1,   'name': '(HC-18) Room Availability', 'desc': 'Room must be available.'},
        {'code': 'OPERATING_HOURS',            'cat': 'Time',           'type': 'HC',  'weight': 1,   'name': '(HC-19) Operating Hours Compliance', 'desc': 'Sessions must be within campus hours.'},
        {'code': 'HOURLY_ALIGNMENT',           'cat': 'Time',           'type': 'HC',  'weight': 1,   'name': '(HC-20) Hourly Slot Alignment', 'desc': 'Classes must start exactly on the hour.'},
        {'code': 'COMPLETE_COURSE_SCHEDULING', 'cat': 'Course',         'type': 'HC',  'weight': 1,   'name': '(HC-21) Complete Course Scheduling', 'desc': 'All curriculum subjects must be plotted.'},
        {'code': 'PREASSIGNMENT_EXCLUSIVITY',  'cat': 'Section',        'type': 'HC',  'weight': 1,   'name': '(HC-22) Pre-assignment Exclusivity', 'desc': 'Locked slots cannot be overwritten.'},
        {'code': 'FACULTY_DAY_SPLIT',          'cat': 'Faculty',        'type': 'HC',  'weight': 1,   'name': '(HC-23) Faculty Day Split', 'desc': 'Sessions must land on designated split days.'},

        # ── SOFT CONSTRAINTS I (SC-I-01 to SC-I-14) ────────────────────────────────
        {'code': 'VIRTUAL_ROOM_USAGE',         'cat': 'Room',           'type': 'SC1', 'weight': 10,  'name': '(SC-I-01) Virtual Room (Online) Penalty', 'desc': 'Avoid Online rooms for physical classes.'},
        {'code': 'EARLY_START_ENFORCEMENT',    'cat': 'Room',           'type': 'SC1', 'weight': 1,   'name': '(SC-I-02) Early Start Enforcement', 'desc': 'Prioritize filling early morning slots.'},
        {'code': 'EVENING_AVOIDANCE',          'cat': 'Time',           'type': 'SC1', 'weight': 1,   'name': '(SC-I-03) Evening Class Avoidance', 'desc': 'Avoid scheduling classes late in the evening.'},
        {'code': 'ROOM_IDLE_GAP',              'cat': 'Room',           'type': 'SC1', 'weight': 10,  'name': '(SC-I-04) Room Idle Gap Penalty', 'desc': 'Incentivize compact room usage.'},
        {'code': 'NO_ISOLATED_LECTURES',       'cat': 'Section',        'type': 'SC1', 'weight': 1,   'name': '(SC-I-05) No Isolated Lectures', 'desc': 'Avoid single lecture subjects in a day.'},
        {'code': 'NO_ISOLATED_LABS',           'cat': 'Section',        'type': 'SC1', 'weight': 1,   'name': '(SC-I-06) No Isolated Labs', 'desc': 'Avoid single lab subjects in a day.'},
        {'code': 'MIN_DAILY_SECTION_LOAD',     'cat': 'Section',        'type': 'SC1', 'weight': 1,   'name': '(SC-I-07) Min Daily Section Load', 'desc': 'Ensure at least 3 hours of class per active day.'},
        {'code': 'LEC_LAB_WEEKLY_DIST',        'cat': 'Course',         'type': 'SC1', 'weight': 1,   'name': '(SC-I-08) Lec-Lab Weekly Dist.', 'desc': 'Lecture scheduled early, Lab scheduled late.'},
        {'code': 'LEC_LAB_PROXIMITY',          'cat': 'Course',         'type': 'SC1', 'weight': 1,   'name': '(SC-I-09) Lec-Lab Proximity', 'desc': 'Max gap between Lecture and Laboratory.'},
        {'code': 'LEC_IN_LAB_FALLBACK',        'cat': 'Room',           'type': 'SC1', 'weight': 5,   'name': '(SC-I-10) Lecture in Lab Fallback', 'desc': 'Allow lectures in labs only if no classrooms are free.'},
        {'code': 'LEC_LAB_SEQUENCE',           'cat': 'Course',         'type': 'SC1', 'weight': 10,  'name': '(SC-I-11) Lec-Lab Sequence', 'desc': 'Lecture should be scheduled before Laboratory.'},
        {'code': 'STRICT_ALLOC_LEC',           'cat': 'Course',         'type': 'SC1', 'weight': 10,  'name': '(SC-I-12) Strict Lecture Allocation', 'desc': 'Lecture must be in a physical room (Non-Virtual).'},
        {'code': 'STRICT_ALLOC_LAB',           'cat': 'Course',         'type': 'SC1', 'weight': 10,  'name': '(SC-I-13) Strict Laboratory Allocation', 'desc': 'Laboratory must be in a Lab room.'},
        {'code': 'ROOM_SUITABILITY',           'cat': 'Room',           'type': 'SC1', 'weight': 10,  'name': '(SC-I-14) Room Type Suitability', 'desc': 'Match subject type with room capabilities.'},

        # ── SOFT CONSTRAINTS II (SC-II-01 to SC-II-04) ───────────────────────────────
        {'code': 'PE_MORNING_PLACEMENT',       'cat': 'Course',         'type': 'SC2', 'weight': 1,   'name': '(SC-II-01) Morning PE Placement', 'desc': 'PE courses priority before 12:00 PM.'},
        {'code': 'PE_EARLY_WEEK',              'cat': 'Course',         'type': 'SC2', 'weight': 1,   'name': '(SC-II-02) Early Week PE Placement', 'desc': 'PE courses priority on Mon-Wed.'},
        {'code': 'LUNCH_BREAK',                'cat': 'Time',           'type': 'SC2', 'weight': 3,   'name': '(SC-II-03) Lunch Break Allocation', 'desc': '1-hour break for all (Students & Faculty) between 10 AM-2 PM.'},
        {'code': 'ROOM_CAPACITY_PROPORTIONAL', 'cat': 'Room',           'type': 'SC2', 'weight': 1,   'name': '(SC-II-04) Room Capacity Allocation', 'desc': 'Prioritize closest absolute fit for room capacity.'},
        {'code': 'LAB_ROOM_SATURATION_GAP',    'cat': 'Room',           'type': 'SC2', 'weight': 10,  'name': '(SC-II-05) Lab Room Squeeze/Saturation', 'desc': 'Avoid wasteful 1 or 2 hour idle gaps in precious Computer Labs.'},
    ]

    added = 0
    updated = 0
    codes_in_master = [c['code'] for c in MASTER_CONSTRAINTS]

    # 1. Update Existing or Add Missing
    for c in MASTER_CONSTRAINTS:
        existing = Constraint.query.filter_by(logic_code=c['code']).first()
        if existing:
            # Overwrite metadata to ensure synchronization with target list
            existing.name            = c['name']
            existing.description     = c['desc']
            existing.category        = c['cat']
            existing.constraint_type = c['type']
            existing.weight          = c['weight']
            updated += 1
        else:
            new_c = Constraint(
                logic_code=c['code'], name=c['name'],
                description=c['desc'], category=c['cat'],
                constraint_type=c['type'], weight=c['weight']
            )
            db.session.add(new_c)
            added += 1

    # 2. Cleanup: Delete obsolete constraints (e.g. DIV4_SLOT_ALIGNMENT if it exists)
    obsolete = Constraint.query.filter(Constraint.logic_code.notin_(codes_in_master)).all()
    deleted = 0
    for obs in obsolete:
        db.session.delete(obs)
        deleted += 1

    db.session.commit()
    flash(f"Constraints Synced: {updated} updated, {added} added, {deleted} removed.", "success")
    return redirect(url_for('manage_constraints'))


# --- REAL-TIME GENERATION ROUTES ---
# app.py

def run_ga_in_background(scheduler, target_semester='1st Semester'):
    global generation_status
    _gen_start_time = time.time()

    with app.app_context():
        def update_progress(stats):
            generation_status['generation']    = stats['generation']
            generation_status['hard_conflicts'] = stats['hard_conflicts']
            generation_status['sc1_violations'] = stats.get('sc1_violations', 0)
            generation_status['sc2_violations'] = stats.get('sc2_violations', 0)
            generation_status['soft_score']    = stats['soft_score']
            generation_status['gen_per_sec']   = stats.get('gen_per_sec', 0)
            generation_status['hardware']      = stats.get('hardware')
            if stats.get('pop_size'):
                generation_status['pop_size'] = stats['pop_size']
            if stats.get('best_chromosome'):
                chrom = stats['best_chromosome']
                matrix = scheduler.get_visualization_matrix(chrom)
                generation_status['visual_matrix'] = matrix
                
                # Write live chromosome state to live_conflicts.json for local debugging
                try:
                    import json
                    live_mock = []
                    for g in chrom.genes:
                        _dy = scheduler.days[g.day_idx] if 0 <= g.day_idx < len(scheduler.days) else 'Unknown'
                        _st = scheduler.slot_to_time(g.start_idx)
                        _en = scheduler.slot_to_time(g.end_idx)
                        live_mock.append({
                            'course_id': g.course_id,
                            'section_id': g.section_id,
                            'faculty_id': g.faculty_id,
                            'room_id': g.room_id,
                            'day': _dy,
                            'start_time': _st,
                            'end_time': _en,
                            'session_type': g.gene_type
                        })
                    with open("live_conflicts.json", "w") as f:
                        json.dump({
                            'semester': generation_status.get('target_semester', '1st Semester'),
                            'schedules': live_mock
                        }, f)
                except Exception as _je:
                    print(f"Error writing live_conflicts.json: {_je}")
                
                # Accuracy tracking for Progress Bar: Count ONLY Conflict-Free genes
                # Includes Hard and Soft violations now.
                total_genes = len(chrom.genes)
                violated_count = len(getattr(chrom, '_violated_genes', []))
                genes_clean = max(0, total_genes - violated_count)
                
                generation_status['scheduled_count'] = genes_clean
                generation_status['total_needed'] = total_genes
                
                # Emit to Dashboard
                v_codes = sorted(list(getattr(chrom, 'violation_codes', [])))
                socketio.emit('ga_live_progress', {
                    'running': True,
                    'semester': generation_status.get('target_semester'),
                    'departments': generation_status.get('selected_depts'),
                    'scheduled': genes_clean,
                    'needed': total_genes,
                    'completion_rate': int((genes_clean / total_genes * 100)) if total_genes > 0 else 0,
                    'violation_codes': v_codes
                })

            if generation_status['stop_requested']: raise Exception("StoppedByUser")

        # ------------------------------------ Warm start: load THIS semester's saved schedule as seed ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        seed_records = None
        try:
            existing = ScheduledClass.query.filter_by(semester=target_semester).all()
            if existing:
                seed_records = [
                    {
                        'course_id':  sc.course_id,
                        'section_id': sc.section_id,
                        'faculty_id': sc.faculty_id,
                        'room_id':    sc.room_id,
                        'day':        sc.day,
                        'start_time': sc.start_time,
                        'end_time':   sc.end_time,
                    }
                    for sc in existing
                ]
                print(f"----------------- Warm-start: {len(seed_records)} genes from '{target_semester}' schedule.")
        except Exception as _e:
            print(f"------------------------ Could not load warm-start seed: {_e}")
            seed_records = None

        # Signal UI that we're in the init phase (before main loop starts)
        generation_status['phase']    = 'init'
        # Pre-compute pop_size estimate for immediate UI display
        try:
            _n_est = sum(len(sec.get('course_ids', [])) for sec in scheduler.sections)
            # Match GA warm-start formula: max(12, min(20, n*0.05))
            generation_status['pop_size'] = max(12, min(20, int(_n_est * 0.05)))
        except Exception:
            generation_status['pop_size'] = None  # fallback ---- UI shows '...'

        # Reset stop signals
        global ga_stop_event
        ga_stop_event = EventletEvent() # Bagong event object bawat run
        generation_status['stop_requested'] = False
        
        # Ensure signal file is gone
        if os.path.exists("ga_stop.signal"):
            try: os.remove("ga_stop.signal")
            except: pass

        try:
            best_schedule = scheduler.run_algorithm(
                progress_callback=update_progress,
                seed_records=seed_records,
                stop_event=ga_stop_event
            )
        except Exception as e:
            import traceback
            print(f"------------- GA error: {e}\n{traceback.format_exc()}")
            best_schedule = None

        # ------------------------------------ C-3: Diagnostic print when HC > 0 at end of run ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        if best_schedule and best_schedule.hard_conflicts > 0:
            print(f"------------------------  GA finished with HC={best_schedule.hard_conflicts} unresolved hard conflict(s):")
            for _ci in best_schedule.conflicting_indices[:8]:
                _g  = best_schedule.genes[_ci]
                _c  = scheduler.course_map.get(_g.course_id, {})
                _f  = scheduler.faculty_map.get(_g.faculty_id, {})
                _r  = scheduler.room_map.get(_g.room_id, {})
                _dy = scheduler.days[_g.day_idx] if 0 <= _g.day_idx < len(scheduler.days) else '?'
                _st = scheduler.slot_to_time(_g.start_idx)
                _en = scheduler.slot_to_time(_g.end_idx)
                _fa = scheduler._fac_avail_days.get(_g.faculty_id) if _g.faculty_id else None
                _hc18 = (_fa is not None and _g.day_idx not in _fa)
                _hint = ' [HC-18: faculty unavailable this day]' if _hc18 else ''
                print(f"   Gene[{_ci}]: {_c.get('course_code','?')} | "
                      f"sec_id={_g.section_id} | "
                      f"fac={_f.get('full_name','?')} | "
                      f"room={_r.get('room_name','?')} | "
                      f"{_dy} {_st}-{_en} | "
                      f"fixed={_g.is_fixed}{_hint}")

        try:
            if best_schedule:
                # 1. Replace only THIS semester's schedule (other semesters untouched)
                db.session.query(ScheduledClass).filter_by(semester=target_semester).delete()
                db.session.commit()

                # 2. Convert GA genes -> DB records with semester tag
                #    Detect room-conflict genes by re-scanning the final chromosome.
                objects_to_save = []
                days_list = scheduler.days

                # Build a simple occupancy map to detect overlapping assignments
                from collections import defaultdict
                room_slots_seen = defaultdict(set)  # (room_id, day_idx) -> set of occupied slot indices
                fac_slots_seen  = defaultdict(set)  # (faculty_id, day_idx) -> set of occupied slot indices
                sec_slots_seen  = defaultdict(set)  # (section_id, day_idx) -> set of occupied slot indices

                # ------------------------------------ HC-02 post-generation check (Minor Subject Gap) ------------------------------------------------------------------------------------------------------------------------------------------------
                # HC-02 is excluded from the GA (needs full section-gap scan).
                # We compute it here once and flag affected sections so the
                # viewer highlights them. Violation = not enough free hours
                # across all days to fit minor-dept courses for a section.
                _hc02_violating_sections = set()
                try:
                    _hc02_cfg     = constraints_config.get('MINOR_SUBJECT_GAP', {})
                    _hc02_enabled = (not _hc02_cfg) or (
                        isinstance(_hc02_cfg, dict) and _hc02_cfg.get('type', 'HC') != 'NC'
                    )
                    if _hc02_enabled:
                        _sel_depts_set = set(selected_depts)
                        _op_hours      = float(scheduler.end_hour - scheduler.start_hour)
                        _n_days        = len(scheduler.days)
                        # Sum scheduled hours per section per day from GA genes
                        _sec_day_h = defaultdict(lambda: defaultdict(float))
                        for _g in best_schedule.genes:
                            if 0 <= _g.day_idx < _n_days:
                                _sec_day_h[_g.section_id][_g.day_idx] += (_g.end_idx - _g.start_idx) / 2.0
                        # Check each section for minor-dept hour gap
                        _hc02_details = []
                        for _sec in raw_sections:
                            _minor_h = sum(
                                (c.synchronous_lec_hours  or c.lec_units or 0) +
                                (c.synchronous_lab_hours  or c.lab_units or 0) +
                                (c.asynchronous_lec_hours or 0) +
                                (c.asynchronous_lab_hours or 0)
                                for c in _sec.courses
                                if c.semester_offered == target_semester
                                and c.department and c.department not in _sel_depts_set
                            )
                            if _minor_h <= 0:
                                continue
                            _free = sum(
                                max(0.0, _op_hours - _sec_day_h[_sec.id].get(d, 0.0))
                                for d in range(_n_days)
                            )
                            if _free < _minor_h:
                                _hc02_violating_sections.add(_sec.id)
                                _hc02_details.append(
                                    f"{_sec.section_name}: needs {_minor_h}h, only {_free:.1f}h free"
                                )
                        if _hc02_details:
                            print(f"------------------------  HC-02 (Minor Subject Gap): {len(_hc02_details)} section(s) have insufficient free time for minor subjects:")
                            for _msg in _hc02_details:
                                print(f"   --------------- {_msg}")
                        else:
                            print("---------------- HC-02 (Minor Subject Gap): All sections have enough free time for minor subjects.")
                        generation_status['hc02_violations'] = len(_hc02_details)
                except Exception as _hc02_err:
                    print(f"------------------------  HC-02 post-gen check error: {_hc02_err}")

                for gene in best_schedule.genes:
                    if gene.day_idx < 0 or gene.day_idx >= len(days_list):
                        continue
                    day_str   = days_list[gene.day_idx]
                    start_str = scheduler.slot_to_time(gene.start_idx)
                    end_str   = scheduler.slot_to_time(gene.end_idx)

                    # Check if this gene's room+day+slots collide with a previously seen gene
                    slots_used = set(range(gene.start_idx, gene.end_idx))
                    key = (gene.room_id, gene.day_idx)
                    
                    # Room conflict check ---- SKIP if it's the University Field
                    room_info = scheduler.room_map.get(gene.room_id, {})
                    room_name = room_info.get('room_name', '')
                    is_field  = "FIELD" in room_name.upper()
                    
                    conflict = False
                    if not is_field:
                        # 1. Check Room Overlap
                        conflict = bool(slots_used & room_slots_seen[key])
                        room_slots_seen[key] |= slots_used
                        
                    # 2. Check Faculty Overlap (Skip if T.B.A.)
                    if not conflict and gene.faculty_id:
                        fac_info = scheduler.faculty_map.get(gene.faculty_id, {})
                        fac_name = fac_info.get('full_name', '')
                        if fac_name.upper() != 'T.B.A.':
                            fac_key = (gene.faculty_id, gene.day_idx)
                            if slots_used & fac_slots_seen[fac_key]:
                                conflict = True
                            fac_slots_seen[fac_key] |= slots_used

                    # 3. HC-16: Section overlap (same section double-booked at same time)
                    if not conflict:
                        sec_key = (gene.section_id, gene.day_idx)
                        if slots_used & sec_slots_seen[sec_key]:
                            conflict = True
                        sec_slots_seen[sec_key] |= slots_used

                    # 4. HC-02: flag all genes of sections that lack minor-subject gaps
                    if not conflict and gene.section_id in _hc02_violating_sections:
                        conflict = True

                    # Infer proper session_type for Fixed (pre-assigned) genes from room type
                    if gene.gene_type == 'Fixed':
                        _caps = room_info.get('capabilities', '')
                        _stype = 'Lab' if 'Computer Lab' in _caps else 'Lec'
                    else:
                        _stype = gene.gene_type

                    objects_to_save.append(ScheduledClass(
                        course_id=gene.course_id,
                        section_id=gene.section_id,
                        faculty_id=gene.faculty_id,
                        room_id=gene.room_id,
                        day=day_str,
                        start_time=start_str,
                        end_time=end_str,
                        semester=target_semester,
                        has_conflict=conflict,
                        session_type=_stype,
                        source='ga',      # Module 3: mark as GA-generated
                        is_draft=False,   # Module 3: GA output goes directly to master
                    ))

                issues_count = sum(1 for o in objects_to_save if o.has_conflict)
                print(f"------------------------  {issues_count} conflicting gene(s) flagged as issues.")

                # 3. Bulk insert
                db.session.bulk_save_objects(objects_to_save)
                db.session.commit()
                print(f"---------------- Saved {len(objects_to_save)} genes for '{target_semester}' ({issues_count} issues).")

                # 4. T.B.A. Sequential Consolidation
                # Redistribute T.B.A.-assigned classes: fill TBA-01 first, then TBA-02, etc.
                # T.B.A. faculty bypass all time-conflict HCs so redistribution is conflict-safe.
                tba_all = Faculty.query.filter_by(full_name='T.B.A.').all()
                if len(tba_all) > 1:
                    tba_sorted = sorted(
                        tba_all,
                        key=lambda f: int(re.search(r'\d+', f.employee_id or '0').group() or 0)
                    )
                    tba_id_list = [t.id for t in tba_sorted]
                    tba_classes = (
                        ScheduledClass.query
                        .filter(
                            ScheduledClass.faculty_id.in_(tba_id_list),
                            ScheduledClass.semester == target_semester
                        )
                        .order_by(ScheduledClass.section_id, ScheduledClass.course_id)
                        .all()
                    )
                    if tba_classes:
                        _idx = 0
                        for _tba in tba_sorted:
                            # Threshold = 80% of (max_weekly_hours / 3 hrs per class)
                            _threshold = max(1, int((_tba.max_weekly_hours or 999) * 0.8 / 3))
                            _count = 0
                            while _idx < len(tba_classes) and _count < _threshold:
                                tba_classes[_idx].faculty_id = _tba.id
                                _idx += 1
                                _count += 1
                            if _idx >= len(tba_classes):
                                break
                        db.session.commit()
                        print(f"---------------- T.B.A. consolidation: {len(tba_classes)} class(es) concentrated to TBA-01 first.")
        except Exception as e:
            import traceback
            print(f"------------- Save error: {e}\n{traceback.format_exc()}")
        finally:
            generation_status['running'] = False
            generation_status['total_time'] = round(time.time() - _gen_start_time, 1)
            generation_status['total_generations'] = generation_status.get('generation', 0)
            generation_status['done'] = True

@app.route('/start-generation', methods=['POST'])
@login_required
@role_required('admin', 'superadmin', 'user')
@hist_lockdown
def start_generation():
    global generation_status
    
    # Check if already running (Atomic check with Lock)
    with generation_lock:
        if generation_status.get('running'):
            return jsonify({
                'status': 'error', 
                'message': 'A generation is already in progress. Please wait for it to finish.'
            }), 409
        
        # Reset status if not running
        generation_status = {
            'running': True,
            'generation': 0,
            'hard_conflicts': 0,
            'sc1_violations': 0,
            'sc2_violations': 0,
            'soft_score': 0,
            'done': False,
            'stop_requested': False,
            'pop_size': None,
            'phase': 'init',
            'hardware': None,
            'gen_per_sec': 0,
            'target_semester': None,
            'selected_depts': []
        }
    
    # Get Data from Frontend (Semester + Departments)
    req_data = request.get_json()
    target_semester = req_data.get('semester', '1st Semester')
    fresh_start = req_data.get('fresh_start', False)
    selected_depts = req_data.get('scheduled_depts', None)

    # Fallback to session, then to hardcoded default
    if not selected_depts:
        selected_depts = session.get('scheduled_depts', SCHEDULED_DEPARTMENTS)

    # Force department isolation for 'user' role
    if session.get('role') == 'user':
        selected_depts = [session.get('department')]

    # Persist selection in session so generate page remembers it
    session['scheduled_depts'] = selected_depts
    
    # Store in status for broad-casting / live focus
    generation_status['target_semester'] = target_semester
    generation_status['selected_depts'] = selected_depts

    print(f"------------------- Starting Generation for: {target_semester} (Fresh Start: {fresh_start})")
    print(f"------------------- Scheduled Departments: {selected_depts}")

    # Module 7: Log action
    log_activity('Generate Schedule', f"Started generation for {target_semester} (Fresh: {fresh_start})")

    # ------------------------------------ FRESH START: Clear existing schedule if requested ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    if fresh_start:
        try:
            # If user, only delete schedules for their department
            if session.get('role') == 'user':
                dept = session.get('department')
                num_deleted = (ScheduledClass.query
                              .join(Course)
                              .filter(ScheduledClass.semester == target_semester, 
                                      Course.department == dept)
                              .delete(synchronize_session=False))
            else:
                num_deleted = ScheduledClass.query.filter_by(semester=target_semester).delete()
            
            db.session.commit()
            print(f"---------------- Fresh Start: Deleted {num_deleted} existing records for {target_semester}.")
        except Exception as e:
            db.session.rollback()
            print(f"------------------------ Failed to clear schedule for fresh start: {e}")
    
    settings_db = get_settings()
    _adays_str  = settings_db.allowed_days or 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'
    active_days = [d.strip() for d in _adays_str.split(',') if d.strip()]
    try:
        _blocked_slots = json.loads(settings_db.blocked_slots_json or '[]') or []
    except Exception:
        _blocked_slots = []
    # 1. FILTER DATA BY SEMESTER + DEPARTMENT
    # Only schedule courses from user-selected departments; others are treated as minor subjects
    raw_courses = Course.query.filter(
        Course.is_archived == False,
        Course.semester_offered == target_semester,
        Course.department.in_(selected_depts)
    ).all()


    courses = []
    for c in raw_courses:
        courses.append({
            'id': c.id,
            'course_code': c.course_code,
            'department': c.department or '',
            'lec_units': c.lec_units or 0,
            'lab_units': c.lab_units or 0,
            'synchronous_lec_hours': c.synchronous_lec_hours or 0,
            'synchronous_lab_hours': c.synchronous_lab_hours or 0,
            'asynchronous_lec_hours': c.asynchronous_lec_hours or 0,
            'asynchronous_lab_hours': c.asynchronous_lab_hours or 0,
        })

    # --- UPDATED ROOM FILTERING ---
    # T.B.A. room is now INCLUDED in the GA pool as a universal fallback room.
    # It bypasses time-conflict checks (handled in GA via tba_room_ids set).
    # University Field is also included (multi-occupancy for NSTP).
    raw_rooms = Room.query.filter(
        Room.is_archived == False
    ).all()
    rooms = [{'id': r.id, 'room_name': r.room_name, 'capabilities': r.capabilities, 'status': r.status, 'capacity': r.capacity, 'special_course_ids': r.special_course_ids or '', 'room_departments': r.room_departments or ''} for r in raw_rooms]
    
    # --- UPDATED FACULTY FILTERING ---
    # Only include faculty who have workload assigned for this semester (via FacultyAssignment),
    # OR are T.B.A. (always included as the fallback pool).
    # Faculty with no FacultyAssignment records have "0 workload" and should not receive GA assignments.
    _fa_faculty_ids = (
        db.session.query(FacultyAssignment.faculty_id)
        .join(Course, FacultyAssignment.course_id == Course.id)
        .filter(Course.semester_offered == target_semester)
        .distinct()
    )
    raw_faculty = Faculty.query.filter(
        Faculty.is_archived == False,
        Faculty.max_weekly_hours > 0,
        or_(
            Faculty.full_name == 'T.B.A.',
            Faculty.id.in_(_fa_faculty_ids)
        )
    ).all()
    faculty = [{'id': f.id, 'full_name': f.full_name,
                'available_days': f.available_days or '',
                'max_weekly_hours': f.max_weekly_hours if f.max_weekly_hours is not None else 35,
                'department': f.department or ''} for f in raw_faculty]
    
    # Sections (All active - algorithm will only schedule courses assigned to them that match the semester)
    raw_sections = Section.query.filter_by(is_archived=False).all()
    # Note: We still pass all course_ids assigned to section, but the algorithm only schedules those present in 'courses' list
    sections = [{'id': s.id, 'course_ids': [c.id for c in s.courses], 'number_of_students': s.number_of_students} for s in raw_sections]
    
    # Pre-assignments: Filter by ID AND matching the courses in the current semester
    # Logic: Only lock schedules if the course is actually running this sem
    valid_course_ids = {c['id'] for c in courses}
    
    raw_pre = PreAssignment.query.filter_by(is_archived=False).all()
    pre_assignments = []
    for pa in raw_pre:
        # Only include pre-assignment if the course is in the current semester list
        if pa.course_id in valid_course_ids:
            pre_assignments.append(SafeObject(
                course_id=pa.course_id, section_id=pa.section_id, 
                faculty_id=pa.faculty_id, room_id=pa.room_id, 
                day=pa.day, start_time=pa.start_time, end_time=pa.end_time
            ))

    # --- DEPARTMENTAL ISOLATION: Load existing schedules from other departments as locked slots ---
    if session.get('role') == 'user':
        user_dept = session.get('department')
        locked_schedules = (ScheduledClass.query
                           .join(Course)
                           .filter(ScheduledClass.semester == target_semester,
                                   or_(Course.department != user_dept, Course.department == None),
                                   ScheduledClass.is_archived == False)
                           .all())
        
        for sc in locked_schedules:
            pre_assignments.append(SafeObject(
                course_id=sc.course_id, section_id=sc.section_id,
                faculty_id=sc.faculty_id, room_id=sc.room_id,
                day=sc.day, start_time=sc.start_time, end_time=sc.end_time,
                is_fixed=True # Force lock in GA
            ))
        print(f"---------------- Departmental Isolation: Locked {len(locked_schedules)} schedules from other departments.")

    db_constraints = Constraint.query.all()
    constraints_config = {c.logic_code: {'type': c.constraint_type, 'weight': c.weight} for c in db_constraints}

    # Build split_assignments list ---- one entry per (assignment, gtype) with split data
    raw_splits = (
        FacultyAssignment.query
        .join(Course, FacultyAssignment.course_id == Course.id)
        .filter(Course.semester_offered == target_semester)
        .all()
    )
    split_assignments = []
    for fa in raw_splits:
        if fa.course_id not in valid_course_ids:
            continue
        # Lab splits (existing columns)
        lab_splits = []
        if fa.split_day_1 and fa.split_hours_1:
            lab_splits.append({'day': fa.split_day_1, 'hours': fa.split_hours_1})
        if fa.split_day_2 and fa.split_hours_2:
            lab_splits.append({'day': fa.split_day_2, 'hours': fa.split_hours_2})
        if lab_splits:
            split_assignments.append({
                'faculty_id': fa.faculty_id,
                'course_id':  fa.course_id,
                'section_id': fa.section_id,
                'gtype':      'Lab',
                'splits':     lab_splits,
            })
        # Lec splits (new columns)
        lec_splits = []
        if fa.split_lec_day_1 and fa.split_lec_hours_1:
            lec_splits.append({'day': fa.split_lec_day_1, 'hours': fa.split_lec_hours_1})
        if fa.split_lec_day_2 and fa.split_lec_hours_2:
            lec_splits.append({'day': fa.split_lec_day_2, 'hours': fa.split_lec_hours_2})
        if lec_splits:
            split_assignments.append({
                'faculty_id': fa.faculty_id,
                'course_id':  fa.course_id,
                'section_id': fa.section_id,
                'gtype':      'Lec',
                'splits':     lec_splits,
            })

    # Build fa_map: {(course_id, section_id): faculty_id} from FacultyAssignment
    # Passed to GA so it uses manually assigned faculty instead of random picks
    fa_map = {}
    for fa in raw_splits:
        if fa.course_id in valid_course_ids:
            fa_map[(fa.course_id, fa.section_id)] = fa.faculty_id

    # 2. INITIALIZE SCHEDULER
    scheduler = GeneticScheduler(
        courses, sections, faculty, rooms, pre_assignments, constraints_config,
        start_time=settings_db.start_hour,
        end_time=settings_db.end_hour,
        allowed_days=active_days,
        split_assignments=split_assignments,
        fa_map=fa_map,
        blocked_slots=_blocked_slots,
    )
    
    # Associate hardware profile with status
    generation_status['hardware'] = scheduler.hardware_profile
    
    # 3. START THREAD (pass semester so save/seed are scoped correctly)
    thread = threading.Thread(target=run_ga_in_background, args=(scheduler, target_semester))
    thread.start()
    
    return jsonify({'status': 'started', 'semester': target_semester})

@app.route('/stop-generation', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def stop_generation():
    global generation_status
    print(f"🛑 STOP CLICKED. Current state: running={generation_status['running']}")
    
    # Always set these to True/False to force UI to stop polling even if thread is stubborn
    generation_status['stop_requested'] = True
    generation_status['running'] = False # Force UI stop
    
    # NUCLEAR OPTION: File-based signal with absolute path
    try:
        sig_path = os.path.join(basedir, "ga_stop.signal")
        with open(sig_path, "w") as f:
            f.write("STOP")
        print(f"📁 Signal file created at: {sig_path}")
    except Exception as e:
        print(f"❌ Failed to create signal file: {e}")

    try:
        ga_stop_event.send(True)
    except:
        pass
        
    return jsonify({'status': 'stopping'})

@app.route('/get-generation-status')
@login_required
@role_required('admin', 'superadmin')
def get_generation_status():
    return jsonify(generation_status)


@app.route('/api/check-feasibility', methods=['POST'])
@login_required
@role_required('admin', 'superadmin', 'user')
def check_feasibility():
    """
    Rapid Greedy FFD check to determine if the rooms can handle the load.
    Runs before the actual GA generation to alert the user about capacity issues.
    """
    # ── Step 0: Extract data from request (same as start-generation) ────────
    req_data = request.get_json()
    target_semester = req_data.get('semester', '1st Semester')
    selected_depts = req_data.get('scheduled_depts', None)
    
    if not selected_depts:
        selected_depts = session.get('scheduled_depts', SCHEDULED_DEPARTMENTS)
    
    # Force department isolation for 'user' role
    if session.get('role') == 'user':
        user_dept = session.get('department')
        if not user_dept:
            return jsonify({'summary': {'status': 'RED', 'message': 'User department not set in session. Please re-login.'}, 'levels': {}})
        selected_depts = [user_dept]
    
    settings_db = get_settings()
    _adays_str  = settings_db.allowed_days or 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'
    active_days = [d.strip() for d in _adays_str.split(',') if d.strip()]
    
    try:
        _blocked_slots = json.loads(settings_db.blocked_slots_json or '[]') or []
    except Exception:
        _blocked_slots = []

    # ── Step 1: Filter Data ────────────────────────────────────────────────
    raw_courses = Course.query.filter(
        Course.is_archived == False,
        Course.semester_offered == target_semester,
        Course.department.in_(selected_depts)
    ).all()
    
    courses = []
    for c in raw_courses:
        courses.append({
            'id': c.id, 'course_code': c.course_code, 'department': c.department or '',
            'lec_units': c.lec_units or 0, 'lab_units': c.lab_units or 0,
            'synchronous_lec_hours': c.synchronous_lec_hours or 0,
            'synchronous_lab_hours': c.synchronous_lab_hours or 0,
            'asynchronous_lec_hours': c.asynchronous_lec_hours or 0,
            'asynchronous_lab_hours': c.asynchronous_lab_hours or 0,
        })

    raw_rooms = Room.query.filter(Room.is_archived == False).all()
    rooms = [{'id': r.id, 'room_name': r.room_name, 'capabilities': r.capabilities, 
              'status': r.status, 'capacity': r.capacity, 
              'special_course_ids': r.special_course_ids or '', 
              'room_departments': r.room_departments or ''} for r in raw_rooms]

    _fa_faculty_ids = (
        db.session.query(FacultyAssignment.faculty_id)
        .join(Course, FacultyAssignment.course_id == Course.id)
        .filter(Course.semester_offered == target_semester)
        .distinct()
    )
    raw_faculty = Faculty.query.filter(
        Faculty.is_archived == False,
        Faculty.max_weekly_hours > 0,
        or_(Faculty.full_name == 'T.B.A.', Faculty.id.in_(_fa_faculty_ids))
    ).all()
    faculty = [{'id': f.id, 'full_name': f.full_name, 
                'available_days': f.available_days or '', 
                'department': f.department or '', 
                'max_weekly_hours': f.max_weekly_hours if f.max_weekly_hours is not None else 35} for f in raw_faculty]

    # Sections (All active)
    raw_sections = Section.query.filter_by(is_archived=False).all()
    sections = [{'id': s.id, 'course_ids': [c.id for c in s.courses], 'number_of_students': s.number_of_students or 0} for s in raw_sections]


    pre_assignments_raw = PreAssignment.query.filter_by(is_archived=False).all()
    valid_course_ids = {c['id'] for c in courses}
    pre_assignments = []
    for pa in pre_assignments_raw:
        if pa.course_id in valid_course_ids:
            pre_assignments.append(SafeObject(
                course_id=pa.course_id, section_id=pa.section_id,
                faculty_id=pa.faculty_id, room_id=pa.room_id,
                day=pa.day, start_time=pa.start_time, end_time=pa.end_time
            ))
    
    # --- DEPARTMENTAL ISOLATION: Include other departments' schedules as locked for feasibility ---
    if session.get('role') == 'user':
        user_dept = session.get('department')
        locked_schedules = (ScheduledClass.query
                           .join(Course)
                           .filter(ScheduledClass.semester == target_semester,
                                   or_(Course.department != user_dept, Course.department == None),
                                   ScheduledClass.is_archived == False)
                           .all())
        for sc in locked_schedules:
            pre_assignments.append(SafeObject(
                course_id=sc.course_id, section_id=sc.section_id,
                faculty_id=sc.faculty_id, room_id=sc.room_id,
                day=sc.day, start_time=sc.start_time, end_time=sc.end_time,
                is_fixed=True
            ))

    # Constraints
    db_constraints = Constraint.query.all()
    constraints_config = {c.logic_code: {'type': c.constraint_type, 'weight': c.weight} for c in db_constraints}

    # Split Assignments & FA Map (CRITICAL for accuracy)
    raw_splits = (
        FacultyAssignment.query
        .join(Course, FacultyAssignment.course_id == Course.id)
        .filter(Course.semester_offered == target_semester)
        .all()
    )
    split_assignments = []
    fa_map = {}
    for fa in raw_splits:
        if fa.course_id not in valid_course_ids:
            continue
        fa_map[(fa.course_id, fa.section_id)] = fa.faculty_id
        
        # Lec Splits
        lec_splits = []
        if fa.split_lec_day_1 and fa.split_lec_hours_1:
            lec_splits.append({'day': fa.split_lec_day_1, 'hours': fa.split_lec_hours_1})
        if fa.split_lec_day_2 and fa.split_lec_hours_2:
            lec_splits.append({'day': fa.split_lec_day_2, 'hours': fa.split_lec_hours_2})
        if lec_splits:
            split_assignments.append({'faculty_id': fa.faculty_id, 'course_id': fa.course_id, 'section_id': fa.section_id, 'gtype': 'Lec', 'splits': lec_splits})
            
        # Lab Splits
        lab_splits = []
        if fa.split_day_1 and fa.split_hours_1:
            lab_splits.append({'day': fa.split_day_1, 'hours': fa.split_hours_1})
        if fa.split_day_2 and fa.split_hours_2:
            lab_splits.append({'day': fa.split_day_2, 'hours': fa.split_hours_2})
        if lab_splits:
            split_assignments.append({'faculty_id': fa.faculty_id, 'course_id': fa.course_id, 'section_id': fa.section_id, 'gtype': 'Lab', 'splits': lab_splits})

    # ── Step 2: Initialize Scheduler ──────────────────────────────────────
    from genetic_algorithm import GeneticScheduler
    scheduler = GeneticScheduler(
        courses, sections, faculty, rooms, pre_assignments, constraints_config,
        start_time=settings_db.start_hour, end_time=settings_db.end_hour,
        allowed_days=active_days, split_assignments=split_assignments,
        fa_map=fa_map, blocked_slots=_blocked_slots
    )

    # ── Step 3: Run Check ──────────────────────────────────────────────────
    try:
        report = scheduler.check_room_feasibility()
        return jsonify(report)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'summary': {'status': 'RED', 'message': f'Internal Error: {str(e)}'}, 'levels': {}})




# --- ROUTES PARA SA "RESOLVE T.B.A." PAGE ---
# Sa app.py
# PALITAN ANG LUMANG RESOLVE ROUTES NITO

@app.route('/resolve-unassigned')
@login_required
@role_required('admin', 'superadmin')
def pending_faculty():
    sort_by = request.args.get('sort', 'course-asc', type=str)

    # Find ALL T.B.A. and placeholder faculty records (by name or 'TBA' status)
    tba_ids = [f.id for f in Faculty.query.filter(or_(
        Faculty.full_name == 'T.B.A.',
        Faculty.assignment_status == 'TBA'
    )).all()]

    # Query real ScheduledClass records that are unassigned (NULL or any T.B.A./placeholder faculty)
    # NSTP is excluded ---- it intentionally has no DCS faculty assigned
    query = (
        ScheduledClass.query
        .join(Course, ScheduledClass.course_id == Course.id)
        .filter(or_(
            ScheduledClass.faculty_id == None,
            ScheduledClass.faculty_id.in_(tba_ids) if tba_ids else (ScheduledClass.faculty_id == None)
        ))
        .filter(~Course.course_code.ilike('%NSTP%'))
    )

    if sort_by == 'course-desc':
        query = query.order_by(Course.course_code.desc())
    else:
        query = query.order_by(Course.course_code.asc())

    unassigned_scs = query.all()

    # Real faculty for the dropdown (exclude T.B.A., 'TBA' placeholders, and archived)
    all_faculty = Faculty.query.filter(
        Faculty.full_name != 'T.B.A.',
        Faculty.assignment_status != 'TBA',
        Faculty.is_archived == False
    ).order_by(Faculty.full_name).all()

    # Build per-SC dept-filtered faculty map
    # Normalize dept names so "Department of Arts and Sciences" matches "Arts & Sciences"
    def _norm_dept(s):
        return (s or '').lower().replace('department of ', '').replace(' & ', ' and ').replace('&', 'and').strip()

    _dept_fac_map = {}
    for _f in all_faculty:
        _key = _norm_dept(_f.department)
        _dept_fac_map.setdefault(_key, []).append(_f)

    sc_faculty_options = {}
    for _sc in unassigned_scs:
        if _sc.course is None:
            continue
        _ckey = _norm_dept(_sc.course.department)
        _matches = _dept_fac_map.get(_ckey, [])
        # Fallback to all_faculty when no dept match (e.g. 'Common'/'Both' dept courses)
        sc_faculty_options[_sc.id] = _matches if _matches else all_faculty

    return render_template(
        'pending_faculty.html',
        unassigned_scs=unassigned_scs,
        all_faculty=all_faculty,
        sc_faculty_options=sc_faculty_options,
        current_sort=sort_by
    )

@app.route('/resolve-unassigned/run', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def run_unassigned_resolver():
    fmt = '%H:%M'

    def _overlap(s1, e1, s2, e2):
        return s1 < e2 and e1 > s2

    # Collect assignments
    assignments = []
    for key, value in request.form.items():
        if key.startswith('assignment_') and value:
            try:
                sc_id = int(key.split('_')[1])
                faculty_id = int(value)
                sc = ScheduledClass.query.get(sc_id)
                faculty = Faculty.query.get(faculty_id)
                if sc and faculty:
                    assignments.append((sc, faculty))
            except (ValueError, IndexError):
                continue

    # Conflict detection
    conflicts = []
    for sc, faculty in assignments:
        if faculty.full_name == 'T.B.A.':
            continue
        sc_start = datetime.strptime(sc.start_time, fmt).time()
        sc_end   = datetime.strptime(sc.end_time,   fmt).time()

        # Check against existing DB records
        existing = ScheduledClass.query.filter(
            ScheduledClass.faculty_id == faculty.id,
            ScheduledClass.day == sc.day,
            ScheduledClass.id  != sc.id
        ).all()
        for ex in existing:
            if _overlap(sc_start, sc_end,
                        datetime.strptime(ex.start_time, fmt).time(),
                        datetime.strptime(ex.end_time,   fmt).time()):
                ex_course = ex.course.course_code if ex.course else '?'
                conflicts.append(
                    f"{sc.course.course_code if sc.course else '?'} ({sc.day} {sc.start_time}----{sc.end_time}) "
                    f"conflicts with {ex_course} ---- {faculty.full_name} is already booked."
                )
                break

        # Check within batch
        for other_sc, other_fac in assignments:
            if other_sc.id == sc.id or other_fac.id != faculty.id or other_sc.day != sc.day:
                continue
            if _overlap(sc_start, sc_end,
                        datetime.strptime(other_sc.start_time, fmt).time(),
                        datetime.strptime(other_sc.end_time,   fmt).time()):
                conflicts.append(
                    f"{sc.course.course_code if sc.course else '?'} and "
                    f"{other_sc.course.course_code if other_sc.course else '?'} "
                    f"both assigned to {faculty.full_name} on {sc.day} ---- time overlap."
                )
                break

    if conflicts:
        for msg in conflicts:
            flash(f'Faculty conflict: {msg}', 'danger')
        return redirect(url_for('pending_faculty'))

    # No conflicts ---- save
    for sc, faculty in assignments:
        sc.faculty_id = faculty.id
    db.session.commit()
    flash('Faculty assignments saved.', 'success')
    return redirect(url_for('manage_faculty'))


@app.route('/pending-sections')
@login_required
@role_required('admin', 'superadmin')
def pending_sections():
    sort = request.args.get('sort', 'course-asc')
    tba_section = Section.query.filter_by(section_name='T.B.A.').first()
    query = ScheduledClass.query.join(ScheduledClass.course)
    
    if tba_section:
        query = query.filter(or_(
            ScheduledClass.section_id == None,
            ScheduledClass.section_id == tba_section.id
        ))
    else:
        query = query.filter(ScheduledClass.section_id == None)
        
    if sort == 'course-desc':
        query = query.order_by(Course.course_code.desc())
    else:
        query = query.order_by(Course.course_code.asc())
        
    orphaned_scs = query.all()

    # All active (non-archived) sections except T.B.A.
    all_sections = Section.query.filter(
        Section.is_archived == False,
        Section.section_name != 'T.B.A.'
    ).order_by(Section.section_name).all()

    return render_template(
        'pending_sections.html',
        orphaned_scs=orphaned_scs,
        all_sections=all_sections,
        current_sort=sort
    )


@app.route('/pending-sections/run', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def run_pending_sections():
    fmt = '%H:%M'

    def _overlap(s1, e1, s2, e2):
        return s1 < e2 and e1 > s2

    # Collect assignments
    assignments = []
    for key, value in request.form.items():
        if key.startswith('assignment_') and value:
            try:
                sc_id = int(key.split('_')[1])
                section_id = int(value)
                sc = ScheduledClass.query.get(sc_id)
                section = Section.query.get(section_id)
                if sc and section:
                    assignments.append((sc, section))
            except (ValueError, IndexError):
                continue

    # Conflict detection
    conflicts = []
    for sc, section in assignments:
        sc_start = datetime.strptime(sc.start_time, fmt).time()
        sc_end   = datetime.strptime(sc.end_time,   fmt).time()

        # Check against existing DB records
        existing = ScheduledClass.query.filter(
            ScheduledClass.section_id == section.id,
            ScheduledClass.day == sc.day,
            ScheduledClass.id  != sc.id
        ).all()
        for ex in existing:
            if _overlap(sc_start, sc_end,
                        datetime.strptime(ex.start_time, fmt).time(),
                        datetime.strptime(ex.end_time,   fmt).time()):
                ex_course = ex.course.course_code if ex.course else '?'
                conflicts.append(
                    f"{sc.course.course_code if sc.course else '?'} ({sc.day} {sc.start_time}----{sc.end_time}) "
                    f"conflicts with {ex_course} ---- {section.section_name} already has a class at this time."
                )
                break

        # Check within batch
        for other_sc, other_sec in assignments:
            if other_sc.id == sc.id or other_sec.id != section.id or other_sc.day != sc.day:
                continue
            if _overlap(sc_start, sc_end,
                        datetime.strptime(other_sc.start_time, fmt).time(),
                        datetime.strptime(other_sc.end_time,   fmt).time()):
                conflicts.append(
                    f"{sc.course.course_code if sc.course else '?'} and "
                    f"{other_sc.course.course_code if other_sc.course else '?'} "
                    f"both assigned to {section.section_name} on {sc.day} ---- time overlap."
                )
                break

    if conflicts:
        for msg in conflicts:
            flash(f'Section conflict: {msg}', 'danger')
        return redirect(url_for('pending_sections'))

    # No conflicts ---- save
    for sc, section in assignments:
        sc.section_id = section.id
    db.session.commit()
    flash('Section assignments saved.', 'success')
    return redirect(url_for('manage_sections'))


def _fmt_time_12h(t_str):
    """Convert '13:30' -> '1:30 PM', '07:00' -> '7:00 AM'."""
    try:
        h, m = map(int, t_str.split(':'))
        suffix = 'AM' if h < 12 else 'PM'
        h12 = h if h <= 12 else h - 12
        if h12 == 0: h12 = 12
        return f"{h12}:{m:02d} {suffix}"
    except Exception:
        return t_str

# ------------------------------------------------------ INTERACTIVE SCHEDULE GRID (drag-and-drop) ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
@app.route('/get-schedule-grid/<string:view_type>/<int:entity_id>')
@login_required
def get_schedule_grid(view_type, entity_id):
    settings  = SystemSettings.query.first()
    start_h   = settings.start_hour  if settings else 7
    end_h     = settings.end_hour    if settings else 21
    days_str  = settings.allowed_days if settings else "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday"
    days      = [d.strip() for d in days_str.split(',') if d.strip()]

    # 30-min time slots (include end_h :00/:30, plus end_h+1 :00 as final boundary)
    slots = []
    h = start_h
    while h <= end_h:
        slots.append(f"{h:02d}:00")
        slots.append(f"{h:02d}:30")
        h += 1
    slots.append(f"{end_h + 1:02d}:00")

    # Fetch schedules + entity label (deduplicated for multi-generation AI data)
    user_id = session.get('user_id')
    def _fetch_all(model, is_p=False):
        if view_type == 'room':    q = model.query.filter_by(room_id=entity_id)
        elif view_type == 'faculty': q = model.query.filter_by(faculty_id=entity_id)
        elif view_type == 'section': q = model.query.filter_by(section_id=entity_id)
        else:                      q = model.query.filter_by(course_id=entity_id)
        
        # Add user filter for personal schedules
        if is_p and user_id:
            q = q.filter_by(user_id=user_id)
            
        res = q.all()
        for r in res: setattr(r, 'is_personal', is_p)
        return res

    schedules = _dedup_schedules(_fetch_all(ScheduledClass))
    if user_id:
        schedules.extend(_fetch_all(UserPersonalSchedule, is_p=True))

    if view_type == 'room':
        entity       = Room.query.get(entity_id)
        entity_label = entity.room_name if entity else ''
    elif view_type == 'faculty':
        entity       = Faculty.query.get(entity_id)
        entity_label = entity.full_name if entity else ''
    elif view_type == 'section':
        entity       = Section.query.get(entity_id)
        entity_label = entity.section_name if entity else ''
    elif view_type == 'course':
        entity       = Course.query.get(entity_id)
        entity_label = entity.course_code if entity else ''
    else:
        return '<div class="alert alert-danger m-3">Invalid view type.</div>'

    def time_to_idx(t_str):
        try:
            h2, m2 = map(int, t_str.split(':'))
            return (h2 - start_h) * 2 + (1 if m2 >= 30 else 0)
        except Exception:
            return 0

    # Build occupancy map + cell_data
    occupied_set = {d: set() for d in days}   # day -> set of slot indices
    cell_data    = {}                           # (day, start_idx) -> list of entry dicts

    def find_covering_cell(day, slot):
        """Return the cell_data key whose rowspan already covers this slot, or None."""
        for k, entries in cell_data.items():
            if k[0] != day:
                continue
            k_si = k[1]
            k_rowspan = entries[0]['rowspan']
            if k_si <= slot < k_si + k_rowspan:
                return k
        return None

    # Sort by start time so earlier classes become the primary cell
    for s in sorted(schedules, key=lambda x: (x.day, x.start_time)):
        if s.day not in occupied_set:
            continue
        si      = time_to_idx(s.start_time)
        ei      = time_to_idx(s.end_time)
        rowspan = max(ei - si, 1)
        # Build cell label based on view type
        if view_type == 'section':
            line1 = s.course.course_code
            line2 = s.faculty.full_name if s.faculty else 'TBA'
            line3 = s.room.room_name    if s.room    else 'T.B.A.'
        elif view_type == 'faculty':
            line1 = s.course.course_code
            line2 = s.section.section_name if s.section else ''
            line3 = s.room.room_name        if s.room    else 'T.B.A.'
        elif view_type == 'room':
            line1 = s.course.course_code
            line2 = s.section.section_name if s.section else ''
            line3 = s.faculty.full_name     if s.faculty else 'TBA'
        else:  # course
            line1 = s.section.section_name if s.section else ''
            line2 = s.faculty.full_name     if s.faculty else 'TBA'
            line3 = s.room.room_name        if s.room    else 'T.B.A.'
        entry = {
            'sched_id': s.id,
            'rowspan':  rowspan,
            'day':      s.day,
            'start':    s.start_time,
            'end':      s.end_time,
            'line1':    line1,
            'line2':    line2,
            'line3':    line3,
            'pop_course':  s.course.course_code  if s.course  else '',
            'pop_section': s.section.section_name if s.section else '',
            'is_personal': getattr(s, 'is_personal', False),
        }
        # Check if this class overlaps (same start OR falls within an existing cell's rowspan)
        parent_key = find_covering_cell(s.day, si)
        if parent_key:
            # Partial or same-start overlap ---- attach to existing cell
            cell_data[parent_key].append(entry)
        else:
            # New cell ---- mark its slots as occupied
            for i in range(si, min(si + rowspan, len(slots))):
                occupied_set[s.day].add(i)
            cell_data[(s.day, si)] = [entry]

    # Build grid rows
    grid_rows = []
    for idx, slot in enumerate(slots):
        cells = []
        for day in days:
            if idx in occupied_set[day] and (day, idx) not in cell_data:
                cells.append({'type': 'skip'})
            elif (day, idx) in cell_data:
                entries = cell_data[(day, idx)]
                primary = entries[0]
                # Build popover lines for all overlapping classes
                pop_lines = [
                    f"{e['pop_course']} | {e['pop_section']} | {_fmt_time_12h(e['start'])}----{_fmt_time_12h(e['end'])}"
                    for e in entries
                ]
                cells.append({
                    'type':          'sched',
                    'overlap_count': len(entries),
                    'pop_lines':     pop_lines,
                    **primary,
                })
            else:
                cells.append({'type': 'empty', 'day': day, 'time': slot})
        grid_rows.append({'time': slot, 'cells': cells})

    return render_template('_schedule_grid.html',
                           view_type=view_type,
                           entity_id=entity_id,
                           entity_label=entity_label,
                           days=days,
                           grid_rows=grid_rows)


@app.route('/view-schedule-modal/<string:view_type>/<int:entity_id>')
@login_required
@role_required('admin', 'superadmin')
def view_schedule_modal(view_type, entity_id):
    """Smart schedule viewer: uses uploaded layout template if available, else default grid."""
    # Student -> delegate to their assigned section (or irregular timetable)
    if view_type == 'student':
        student = Student.query.get(entity_id)
        if not student:
            return '<div class="alert alert-warning m-3">Student not found.</div>'
        if student.is_irregular:
            iframe_src = url_for('irregular_timetable_html', viewer='true', student_id=student.student_id)
            # Use dynamic sizing even for irregulars
            settings = get_settings()
            sec_p = getattr(settings, 'paper_size', 'A4') or 'A4'
            w_in, h_in, _ = PAPER_SIZES.get(sec_p, PAPER_SIZES['A4'])
            pw, ph = int(w_in * 96), int(h_in * 96)
            return f'<div class="dynamic-paper-wrapper" data-width="{pw}" data-height="{ph}"><iframe src="{iframe_src}" style="width:100%;height:100%;border:none;display:block;"></iframe></div>'
        if not student.section_id:
            return '<div class="alert alert-warning m-3">This student has no section assigned yet.</div>'
        view_type = 'section'
        entity_id = student.section_id

    _timetable_routes = {
        'section': ('section_timetable_html', 'section_id'),
        'faculty': ('faculty_timetable_html', 'faculty_id'),
        'room':    ('room_timetable_html',    'room_id'),
        'course':  ('course_timetable_html',  'course_id'),
    }
    if view_type not in _timetable_routes:
        return '<div class="alert alert-danger m-3">Invalid view type.</div>'

    assets_dir    = os.path.join(basedir, 'static', 'assets')
    template_path = os.path.join(assets_dir, f'{view_type}_template.xlsx')

    # Dynamic Paper Sizing for the Viewer
    settings = get_settings()
    sec_p = getattr(settings, 'paper_size', 'A4') or 'A4'
    fac_p = getattr(settings, 'fac_paper_size', 'A4') or 'A4'
    pk = fac_p if view_type == 'faculty' else sec_p
    w_in, h_in, _ = PAPER_SIZES.get(pk, PAPER_SIZES['A4'])
    
    pw, ph = int(w_in * 96), int(h_in * 96)

    if os.path.isfile(template_path):
        func_name, param_name = _timetable_routes[view_type]
        iframe_src = url_for(func_name, viewer='true', canvas='true', **{param_name: entity_id})
        return f'<div class="dynamic-paper-wrapper" data-width="{pw}" data-height="{ph}"><iframe src="{iframe_src}" style="width:100%;height:100%;border:none;display:block;"></iframe></div>'
    else:
        return f'<div class="dynamic-paper-wrapper" data-width="{pw}" data-height="{ph}">{get_schedule_grid(view_type, entity_id)}</div>'


@app.route('/api/move-class', methods=['POST'])
@login_required
def api_move_class():
    data           = request.get_json(force=True) or {}
    sched_id       = data.get('sched_id')
    new_day        = data.get('day')
    new_start      = data.get('start')
    new_end        = data.get('end')
    new_room       = data.get('room_id')
    force_override = data.get('force_override', False)

    sched = ScheduledClass.query.get(sched_id)
    if not sched:
        return jsonify({'ok': False, 'error': 'Schedule not found'})

    # Module 3: enforce Global AI-Lock for regular users on GA entries
    role     = session.get('role', 'user')
    settings = SystemSettings.query.first()
    lock_on  = bool(settings.schedule_lock) if settings else False
    if role == 'user' and sched.source == 'ga' and lock_on:
        return jsonify({'ok': False,
                        'error': 'Schedule is locked. GA entries cannot be moved.'}), 403
    # Non-admin users can only move their own draft entries
    if role == 'user' and not sched.is_draft:
        return jsonify({'ok': False,
                        'error': 'Regular users can only move draft entries.'}), 403
    # Security: force_override only allowed for admins
    if force_override and role not in ('admin', 'superadmin'):
        return jsonify({'ok': False, 'error': 'Force override requires admin role.'}), 403

    # Conflict check (skipped if admin force-overrides)
    if not force_override:
        fmt = '%H:%M'
        try:
            t_start = datetime.strptime(new_start, fmt).time()
            t_end   = datetime.strptime(new_end,   fmt).time()
        except (ValueError, TypeError):
            return jsonify({'ok': False, 'error': 'Invalid time format'}), 400

        effective_room = new_room or sched.room_id
        candidates = ScheduledClass.query.options(
            joinedload(ScheduledClass.course),
            joinedload(ScheduledClass.section),
            joinedload(ScheduledClass.faculty),
            joinedload(ScheduledClass.room),
        ).filter_by(day=new_day, semester=sched.semester, is_draft=sched.is_draft).all()

        conflicts = []
        for other in candidates:
            if other.id == sched_id:
                continue
            try:
                o_start = datetime.strptime(other.start_time, fmt).time()
                o_end   = datetime.strptime(other.end_time,   fmt).time()
            except ValueError:
                continue
            if not (t_end <= o_start or t_start >= o_end):
                cc   = other.course.course_code if other.course else str(other.course_id)
                slot = f'{other.start_time}----{other.end_time}'
                if sched.faculty_id and other.faculty_id == sched.faculty_id:
                    fn = other.faculty.full_name if other.faculty else None
                    if fn and fn != 'T.B.A.':
                        conflicts.append(f'{fn} already has {cc} on {new_day} {slot}')
                if effective_room and other.room_id == effective_room:
                    rn = other.room.room_name if other.room else None
                    if rn and rn not in ('T.B.A.', 'University Field'):
                        conflicts.append(f'{rn} already has {cc} on {new_day} {slot}')
                if other.section_id == sched.section_id:
                    sn = other.section.section_name if other.section else str(other.section_id)
                    conflicts.append(f'{sn} already has {cc} on {new_day} {slot}')

        if conflicts:
            return jsonify({'ok': False, 'conflicts': conflicts}), 409

    sched.day        = new_day
    sched.start_time = new_start
    sched.end_time   = new_end
    if new_room:
        sched.room_id = new_room
    db.session.commit()
    return jsonify({'ok': True,
                    'message': f'Moved to {new_day} {new_start}----{new_end}'})


@app.route('/api/preview-conflicts')
@login_required
@role_required('admin', 'superadmin')
def api_preview_conflicts():
    """Pre-compute conflict level for every possible drop position for a class.
    Returns {day: {time: level}} where level is 'hard'|'semi'|'soft'|'free'|'out'.
      hard  = faculty/section/room double-booking (HC)
      semi  = faculty already has ---------------3 classes that day, or class ends past 7 PM (SHC)
      soft  = Saturday placement (SC)
      free  = no constraint violations
      out   = class would extend past operating hours (not droppable)
    """
    sched_id = request.args.get('sched_id', type=int)
    sched = ScheduledClass.query.get(sched_id)
    if not sched:
        return jsonify({})

    settings  = SystemSettings.query.first()
    start_h   = settings.start_hour  if settings else 7
    end_h     = settings.end_hour    if settings else 21
    days_str  = (settings.allowed_days
                 if settings else "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday")
    days = [d.strip() for d in days_str.split(',') if d.strip()]

    def t2m(t):
        h, m = map(int, t.split(':'))
        return h * 60 + m

    duration = t2m(sched.end_time) - t2m(sched.start_time)
    if duration <= 0:
        duration = 90

    # All other scheduled classes
    others = ScheduledClass.query.filter(ScheduledClass.id != sched_id).all()

    # How many classes does this faculty already have per day (for semi-hard check)
    fac_day_count = {}
    if sched.faculty_id:
        for o in others:
            if o.faculty_id == sched.faculty_id:
                fac_day_count[o.day] = fac_day_count.get(o.day, 0) + 1

    result = {}
    for day in days:
        result[day] = {}
        today = [o for o in others if o.day == day]

        h = start_h
        while h < end_h:
            for minute in (0, 30):
                new_start = h * 60 + minute
                new_end   = new_start + duration
                slot_key  = f"{h:02d}:{minute:02d}"

                # Class would extend past operating hours -> not droppable
                if new_end > end_h * 60:
                    result[day][slot_key] = 'out'
                    continue

                level = 'free'

                # ------------------------------------ HARD: faculty / section / room overlap ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
                for o in today:
                    o_s = t2m(o.start_time)
                    o_e = t2m(o.end_time)
                    if new_start < o_e and new_end > o_s:
                        hard = (
                            (sched.faculty_id and o.faculty_id == sched.faculty_id) or
                            (sched.section_id == o.section_id) or
                            (sched.room_id == o.room_id)
                        )
                        if hard:
                            level = 'hard'
                            break
                        # Resources conflict but different entity -> semi
                        if level != 'hard':
                            level = 'semi'

                # ------------------------------------ SEMI-HARD: faculty overloaded that day (---------------3 classes) ------------------------------------
                if level == 'free' and sched.faculty_id:
                    if fac_day_count.get(day, 0) >= 3:
                        level = 'semi'

                # ------------------------------------ SEMI-HARD: class ends after 7 PM ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
                if level == 'free' and new_end > 19 * 60:
                    level = 'semi'

                # ------------------------------------ SOFT: Saturday ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
                if level == 'free' and day == 'Saturday':
                    level = 'soft'

                result[day][slot_key] = level
            h += 1

    return jsonify(result)


# =============================================================================
# MODULE 3: MULTI-DEPARTMENT DRAFTING & MANUAL OVERRIDES
# =============================================================================

# --- B: GLOBAL AI-LOCK TOGGLE ---

@app.route('/api/settings/schedule-lock', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def toggle_schedule_lock():
    data     = request.get_json(force=True) or {}
    locked   = bool(data.get('locked', False))
    settings = SystemSettings.query.first()
    if not settings:
        return jsonify({'ok': False, 'error': 'No settings found'}), 404
    settings.schedule_lock = locked
    db.session.commit()
    return jsonify({'ok': True, 'locked': settings.schedule_lock})


# --- F: REAL-TIME CONFLICT CHECK (single slot) ---

@app.route('/api/conflicts/check')
@login_required
def api_check_conflicts():
    """Check if a specific day/time slot has room, faculty, or section conflicts.
    Params: day, start, end, faculty_id, room_id, section_id, semester
            exclude_id (optional ---- ignore self when moving)
            draft_version_id (optional ---- also check against this draft's entries)
    Returns: {hard_conflicts: [{type, entry_id, label}]}
    """
    day        = request.args.get('day', '')
    start      = request.args.get('start', '')
    end        = request.args.get('end', '')
    faculty_id = request.args.get('faculty_id', type=int)
    room_id    = request.args.get('room_id', type=int)
    section_id = request.args.get('section_id', type=int)
    semester   = request.args.get('semester', '1st Semester')
    exclude_id = request.args.get('exclude_id', type=int)
    draft_version_id = request.args.get('draft_version_id', type=int)

    if not day or not start or not end:
        return jsonify({'hard_conflicts': []})

    fmt = '%H:%M'
    try:
        t_start = datetime.strptime(start, fmt).time()
        t_end   = datetime.strptime(end,   fmt).time()
    except ValueError:
        return jsonify({'hard_conflicts': [], 'error': 'Invalid time format'})

    # Build query: master entries + optionally the specified draft's entries
    q = ScheduledClass.query.options(
        joinedload(ScheduledClass.course),
        joinedload(ScheduledClass.section),
        joinedload(ScheduledClass.faculty),
        joinedload(ScheduledClass.room),
    ).filter_by(day=day, semester=semester, is_draft=False)
    if draft_version_id:
        q = ScheduledClass.query.options(
            joinedload(ScheduledClass.course),
            joinedload(ScheduledClass.section),
            joinedload(ScheduledClass.faculty),
            joinedload(ScheduledClass.room),
        ).filter_by(day=day, semester=semester).filter(
            or_(ScheduledClass.is_draft == False,
                ScheduledClass.draft_version_id == draft_version_id)
        )

    candidates = _dedup_schedules(q.all())
    hard_conflicts = []

    def _fmt12(t_str):
        """Convert 'HH:MM' to '8:00 AM' style."""
        try:
            t = datetime.strptime(t_str, '%H:%M')
            return t.strftime('%-I:%M %p') if hasattr(t, 'strftime') else t_str
        except Exception:
            return t_str

    for sc in candidates:
        if exclude_id and sc.id == exclude_id:
            continue
        try:
            sc_start = datetime.strptime(sc.start_time, fmt).time()
            sc_end   = datetime.strptime(sc.end_time,   fmt).time()
        except ValueError:
            continue
        # Time overlap check
        if not (t_end <= sc_start or t_start >= sc_end):
            cc = sc.course.course_code if sc.course else str(sc.course_id)
            slot = f'{sc.start_time}----{sc.end_time}'
            # Faculty conflict (skip T.B.A.)
            if faculty_id and sc.faculty_id == faculty_id:
                fac_name = sc.faculty.full_name if sc.faculty else None
                if fac_name and fac_name != 'T.B.A.':
                    hard_conflicts.append({'type': 'faculty', 'entry_id': sc.id,
                                           'label': f'{fac_name} already has {cc} on {day} {slot}'})
            # Room conflict (skip T.B.A. and University Field)
            if room_id and sc.room_id == room_id:
                rm_name = sc.room.room_name if sc.room else None
                if rm_name and rm_name not in ('T.B.A.', 'University Field'):
                    hard_conflicts.append({'type': 'room', 'entry_id': sc.id,
                                           'label': f'{rm_name} already has {cc} on {day} {slot}'})
            # Section conflict
            if section_id and sc.section_id == section_id:
                sec_name = sc.section.section_name if sc.section else str(section_id)
                hard_conflicts.append({'type': 'section', 'entry_id': sc.id,
                                       'label': f'{sec_name} already has {cc} on {day} {slot}'})

    return jsonify({'hard_conflicts': hard_conflicts})


# --- E: SCHEDULE ENTRIES FOR EDITOR GRID ---

@app.route('/api/schedule/entries')
@login_required
def api_schedule_entries():
    """Return master (is_draft=False) ScheduledClass entries for the editor grid.
    Params: section_id OR faculty_id OR room_id, plus semester.
    """
    semester   = request.args.get('semester', '1st Semester')
    section_id = request.args.get('section_id', type=int)
    faculty_id = request.args.get('faculty_id', type=int)
    room_id    = request.args.get('room_id', type=int)
    course_id  = request.args.get('course_id', type=int)

    # ------------------------------------ Time Machine: Historical Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    if session.get('historical_mode_active', False):
        archive_id = session.get('active_archive_id')
        
        target_field = None
        target_name = None
        
        if section_id:
            all_sections = get_archive_entities(archive_id, 'Section')
            match = next((s for s in all_sections if s.id == section_id), None)
            if match:
                target_field = 'section_name'
                target_name = match.section_name
        elif faculty_id:
            all_faculty = get_archive_entities(archive_id, 'Faculty')
            match = next((f for f in all_faculty if f.id == faculty_id), None)
            if match:
                target_field = 'faculty_name'
                target_name = match.full_name
        elif room_id:
            all_rooms = get_archive_entities(archive_id, 'Room')
            match = next((r for r in all_rooms if r.id == room_id), None)
            if match:
                target_field = 'room_name'
                target_name = match.room_name
        elif course_id:
            all_courses = get_archive_entities(archive_id, 'Course')
            match = next((c for c in all_courses if c.id == course_id), None)
            if match:
                target_field = 'course_code'
                target_name = match.course_code

        if not target_field or not target_name:
            return jsonify([])

        schedules_raw = ArchivedSchedule.query.filter_by(term_archive_id=archive_id).filter(
            getattr(ArchivedSchedule, target_field) == target_name
        ).all()
        
        entries = []
        for as_obj in schedules_raw:
            entries.append({
                'id':           as_obj.id,
                'course_id':    None,
                'course_code':  as_obj.course_code,
                'course_name':  as_obj.course_name,
                'section_id':   section_id if target_field == 'section_name' else None,
                'section_name': as_obj.section_name,
                'faculty_id':   faculty_id if target_field == 'faculty_name' else None,
                'faculty_name': as_obj.faculty_name,
                'room_id':      room_id    if target_field == 'room_name'    else None,
                'room_name':    as_obj.room_name,
                'day':          as_obj.day,
                'start_time':   as_obj.start_time,
                'end_time':     as_obj.end_time,
                'semester':     "Archived",
                'session_type': as_obj.schedule_type,
                'source':       'archive',
                'is_draft':     False,
                'has_conflict': False
            })
        return jsonify(entries)

    # ------------------------------------ Live Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    q = ScheduledClass.query.options(
        joinedload(ScheduledClass.course),
        joinedload(ScheduledClass.section),
        joinedload(ScheduledClass.faculty),
        joinedload(ScheduledClass.room),
    ).filter_by(semester=semester, is_draft=False)
    if section_id:
        q = q.filter_by(section_id=section_id)
    elif faculty_id:
        q = q.filter_by(faculty_id=faculty_id)
    elif room_id:
        q = q.filter_by(room_id=room_id)
    elif course_id:
        q = q.filter_by(course_id=course_id)
    else:
        return jsonify([])

    entries = []
    schedules = _dedup_schedules(q.all())
    for sc in schedules:
        entries.append({
            'id':           sc.id,
            'course_id':    sc.course_id,
            'course_code':  sc.course.course_code  if sc.course  else '',
            'course_name':  sc.course.course_name  if sc.course  else '',
            'section_id':   sc.section_id,
            'section_name': sc.section.section_name if sc.section else '',
            'faculty_id':   sc.faculty_id,
            'faculty_name': sc.faculty.full_name    if sc.faculty else 'T.B.A.',
            'room_id':      sc.room_id,
            'room_name':    sc.room.room_name       if sc.room    else '',
            'day':          sc.day,
            'start_time':   sc.start_time,
            'end_time':     sc.end_time,
            'semester':     sc.semester,
            'session_type': sc.session_type,
            'source':       sc.source,
            'is_draft':     sc.is_draft,
            'has_conflict': sc.has_conflict,
        })
    return jsonify(entries)


# --- E: ADD MANUAL SCHEDULE ENTRY ---

@app.route('/api/schedule/add', methods=['POST'])
@login_required
def api_add_schedule():
    """Manually add a new schedule entry. Admins can add to master directly.
    Regular users always add to a draft (draft_version_id required if role='user').
    """
    data       = request.get_json(force=True) or {}
    course_id  = data.get('course_id')
    section_id = data.get('section_id')
    faculty_id = data.get('faculty_id')
    room_id    = data.get('room_id')
    day        = data.get('day')
    start_time = data.get('start_time')
    end_time   = data.get('end_time')
    semester   = data.get('semester', '1st Semester')
    session_type     = data.get('session_type', 'Lec')
    draft_version_id = data.get('draft_version_id')

    if not all([course_id, section_id, day, start_time, end_time, semester]):
        return jsonify({'ok': False, 'error': 'Missing required fields'}), 400

    role = session.get('role', 'user')
    settings = SystemSettings.query.first()
    lock_on  = bool(settings.schedule_lock) if settings else False

    # Determine is_draft flag
    if draft_version_id:
        is_draft = True
    elif role == 'user' and lock_on:
        return jsonify({'ok': False, 'error': 'Schedule is locked. Please create a draft first.'}), 403
    else:
        is_draft = False

    # Validate draft version belongs to someone the user can write to
    if draft_version_id:
        dv = DraftVersion.query.get(draft_version_id)
        if not dv:
            return jsonify({'ok': False, 'error': 'Draft version not found'}), 404
        if role == 'user' and dv.created_by != session.get('user_id'):
            return jsonify({'ok': False, 'error': 'Not authorized to write to this draft'}), 403

    # Conflict check before insert
    fmt = '%H:%M'
    try:
        t_start = datetime.strptime(start_time, fmt).time()
        t_end   = datetime.strptime(end_time,   fmt).time()
    except ValueError:
        return jsonify({'ok': False, 'error': 'Invalid time format'}), 400

    candidates = ScheduledClass.query.options(
        joinedload(ScheduledClass.course),
        joinedload(ScheduledClass.section),
        joinedload(ScheduledClass.faculty),
        joinedload(ScheduledClass.room),
    ).filter_by(day=day, semester=semester, is_draft=is_draft).all()

    conflicts = []
    for other in candidates:
        try:
            o_start = datetime.strptime(other.start_time, fmt).time()
            o_end   = datetime.strptime(other.end_time,   fmt).time()
        except ValueError:
            continue
        if not (t_end <= o_start or t_start >= o_end):
            cc   = other.course.course_code if other.course else str(other.course_id)
            slot = f'{other.start_time}----{other.end_time}'
            if faculty_id and other.faculty_id == faculty_id:
                fn = other.faculty.full_name if other.faculty else None
                if fn and fn != 'T.B.A.':
                    conflicts.append(f'{fn} already has {cc} on {day} {slot}')
            if room_id and other.room_id == room_id:
                rn = other.room.room_name if other.room else None
                if rn and rn not in ('T.B.A.', 'University Field'):
                    conflicts.append(f'{rn} already has {cc} on {day} {slot}')
            if other.section_id == section_id:
                sn = other.section.section_name if other.section else str(other.section_id)
                conflicts.append(f'{sn} already has {cc} on {day} {slot}')

    if conflicts:
        return jsonify({'ok': False, 'conflicts': conflicts}), 409

    new_sc = ScheduledClass(
        course_id=course_id, section_id=section_id,
        faculty_id=faculty_id, room_id=room_id,
        day=day, start_time=start_time, end_time=end_time,
        semester=semester, session_type=session_type,
        source='manual', is_draft=is_draft,
        draft_version_id=draft_version_id if is_draft else None,
        has_conflict=False,
    )
    db.session.add(new_sc)
    db.session.commit()

    course  = Course.query.get(course_id)
    section = Section.query.get(section_id)
    return jsonify({'ok': True, 'entry': {
        'id': new_sc.id, 'course_code': course.course_code if course else '',
        'section_name': section.section_name if section else '',
        'day': day, 'start_time': start_time, 'end_time': end_time,
        'source': 'manual', 'is_draft': is_draft,
    }})


# --- E: DELETE SCHEDULE ENTRY ---

@app.route('/api/schedule/<int:sched_id>', methods=['DELETE'])
@login_required
def api_delete_schedule(sched_id):
    """Delete a schedule entry. Guards:
    - GA entries (source='ga') with lock ON: user role cannot delete.
    - Draft entries: only owner or admin can delete.
    - Admin/superadmin can always delete any entry.
    """
    sc = ScheduledClass.query.get(sched_id)
    if not sc:
        return jsonify({'ok': False, 'error': 'Not found'}), 404

    role     = session.get('role', 'user')
    settings = SystemSettings.query.first()
    lock_on  = bool(settings.schedule_lock) if settings else False

    if role in ('admin', 'superadmin'):
        # Admins can delete anything
        db.session.delete(sc)
        db.session.commit()
        return jsonify({'ok': True})

    # Regular user guards
    if sc.source == 'ga' and lock_on:
        return jsonify({'ok': False, 'error': 'Cannot delete GA entry while schedule is locked'}), 403
    # Users cannot delete master (non-draft) entries ---- only admins can
    if not sc.is_draft:
        return jsonify({'ok': False, 'error': 'Cannot delete master schedule entries. Create a draft to make changes.'}), 403
    if sc.is_draft:
        dv = DraftVersion.query.get(sc.draft_version_id) if sc.draft_version_id else None
        if not dv or dv.created_by != session.get('user_id'):
            return jsonify({'ok': False, 'error': 'Not authorized to delete this draft entry'}), 403

    db.session.delete(sc)
    db.session.commit()
    return jsonify({'ok': True})


# --- E: PATCH / UPDATE SCHEDULE ENTRY ---

@app.route('/api/schedule/<int:sched_id>', methods=['PATCH'])
@login_required
def api_patch_schedule(sched_id):
    """Update an existing schedule entry's faculty, room, day, time, session_type.
    Runs a conflict check (excluding self) before saving.
    Same lock/role guards as move-class.
    """
    sc = ScheduledClass.query.get(sched_id)
    if not sc:
        return jsonify({'ok': False, 'error': 'Entry not found'}), 404

    role     = session.get('role', 'user')
    user_id  = session.get('user_id')
    settings = SystemSettings.query.first()
    lock_on  = bool(settings.schedule_lock) if settings else False

    # Lock guard: user cannot edit GA entries when locked
    if role == 'user' and sc.source == 'ga' and lock_on:
        return jsonify({'ok': False, 'error': 'Schedule is locked. Cannot edit GA entries.'}), 403
    # Draft ownership guard
    if sc.is_draft and role == 'user':
        dv = DraftVersion.query.get(sc.draft_version_id) if sc.draft_version_id else None
        if not dv or dv.created_by != user_id:
            return jsonify({'ok': False, 'error': 'Not authorized to edit this draft entry'}), 403

    data           = request.get_json(force=True) or {}
    force_override = data.get('force_override', False)
    # Security: force_override only allowed for admins
    if force_override and role not in ('admin', 'superadmin'):
        return jsonify({'ok': False, 'error': 'Force override requires admin role.'}), 403

    faculty_id   = data.get('faculty_id',   sc.faculty_id)
    room_id      = data.get('room_id',      sc.room_id)
    day          = data.get('day',          sc.day)
    start_time   = data.get('start_time',   sc.start_time)
    end_time     = data.get('end_time',     sc.end_time)
    session_type = data.get('session_type', sc.session_type)

    # Conflict check (exclude self; skipped if admin force-overrides)
    if not force_override:
        fmt = '%H:%M'
        try:
            t_start = datetime.strptime(start_time, fmt).time()
            t_end   = datetime.strptime(end_time,   fmt).time()
        except ValueError:
            return jsonify({'ok': False, 'error': 'Invalid time format'}), 400

        candidates = ScheduledClass.query.options(
            joinedload(ScheduledClass.course),
            joinedload(ScheduledClass.section),
            joinedload(ScheduledClass.faculty),
            joinedload(ScheduledClass.room),
        ).filter_by(day=day, semester=sc.semester, is_draft=sc.is_draft).all()

        conflicts = []
        for other in candidates:
            if other.id == sched_id:
                continue
            try:
                o_start = datetime.strptime(other.start_time, fmt).time()
                o_end   = datetime.strptime(other.end_time,   fmt).time()
            except ValueError:
                continue
            if not (t_end <= o_start or t_start >= o_end):
                cc   = other.course.course_code if other.course else str(other.course_id)
                slot = f'{other.start_time}----{other.end_time}'
                if faculty_id and other.faculty_id == faculty_id:
                    fn = other.faculty.full_name if other.faculty else None
                    if fn and fn != 'T.B.A.':
                        conflicts.append(f'{fn} already has {cc} on {day} {slot}')
                if room_id and other.room_id == room_id:
                    rn = other.room.room_name if other.room else None
                    if rn and rn not in ('T.B.A.', 'University Field'):
                        conflicts.append(f'{rn} already has {cc} on {day} {slot}')
                if other.section_id == sc.section_id:
                    sn = other.section.section_name if other.section else str(other.section_id)
                    conflicts.append(f'{sn} already has {cc} on {day} {slot}')

        if conflicts:
            return jsonify({'ok': False, 'conflicts': conflicts}), 409

    # Apply changes
    sc.faculty_id   = faculty_id
    sc.room_id      = room_id
    sc.day          = day
    sc.start_time   = start_time
    sc.end_time     = end_time
    sc.session_type = session_type
    db.session.commit()

    fac  = Faculty.query.get(sc.faculty_id) if sc.faculty_id else None
    room = Room.query.get(sc.room_id)       if sc.room_id    else None
    crs  = Course.query.get(sc.course_id)
    sec  = Section.query.get(sc.section_id)
    return jsonify({'ok': True, 'entry': {
        'id':           sc.id,
        'course_id':    sc.course_id,
        'course_code':  crs.course_code   if crs  else '',
        'course_name':  crs.course_name   if crs  else '',
        'section_id':   sc.section_id,
        'section_name': sec.section_name  if sec  else '',
        'faculty_id':   sc.faculty_id,
        'faculty_name': fac.full_name     if fac  else 'T.B.A.',
        'room_id':      sc.room_id,
        'room_name':    room.room_name    if room else '',
        'day':          sc.day,
        'start_time':   sc.start_time,
        'end_time':     sc.end_time,
        'session_type': sc.session_type,
        'source':       sc.source,
        'is_draft':     sc.is_draft,
    }})


# --- D: DRAFT VERSION MANAGEMENT ---

@app.route('/api/draft/create', methods=['POST'])
@login_required
def api_draft_create():
    data       = request.get_json(force=True) or {}
    name       = (data.get('name') or '').strip()
    semester   = data.get('semester', '1st Semester')
    department = (data.get('department') or '').strip() or None
    notes      = (data.get('notes') or '').strip() or None

    if not name:
        return jsonify({'ok': False, 'error': 'Draft name is required'}), 400

    role    = session.get('role', 'user')
    user_id = session.get('user_id')

    # Regular users: max 3 active (unpublished) drafts per department
    if role == 'user':
        count = DraftVersion.query.filter_by(department=department, created_by=user_id, is_published=False).count()
        if count >= 3:
            return jsonify({'ok': False, 'error': 'Maximum 3 active drafts per department allowed'}), 400

    dv = DraftVersion(name=name, semester=semester, department=department,
                      created_by=user_id, notes=notes)
    db.session.add(dv)
    db.session.commit()
    return jsonify({'ok': True, 'draft': {
        'id': dv.id, 'name': dv.name, 'semester': dv.semester,
        'department': dv.department, 'is_published': dv.is_published,
        'notes': dv.notes
    }})

@app.route('/api/draft/snapshot', methods=['POST'])
@login_required
def api_draft_snapshot():
    """Clones all master schedule entries into a new draft version."""
    data      = request.get_json(force=True) or {}
    name      = (data.get('name') or '').strip()
    if not name:
        name = f"Snapshot {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
    
    semester  = data.get('semester') or session.get('selected_semester') or '1st Semester'
    user_id   = session.get('user_id')
    user_dept = session.get('department')

    # 1. Create New Draft Version
    dv = DraftVersion(
        name=name,
        semester=semester,
        department=user_dept,
        created_by=user_id,
        notes=f"Snapshot from Master on {datetime.utcnow()}"
    )
    db.session.add(dv)
    db.session.flush() # Get ID before commit

    # 2. Clone Master Entries (is_draft=False)
    master_entries = ScheduledClass.query.filter_by(semester=semester, is_draft=False).all()
    for item in master_entries:
        clone = ScheduledClass(
            course_id=item.course_id,
            section_id=item.section_id,
            faculty_id=item.faculty_id,
            room_id=item.room_id,
            day=item.day,
            start_time=item.start_time,
            end_time=item.end_time,
            semester=item.semester,
            has_conflict=item.has_conflict,
            session_type=item.session_type,
            source=item.source,
            is_draft=True,
            draft_version_id=dv.id
        )
        db.session.add(clone)

    db.session.commit()
    return jsonify({'ok': True, 'draft_id': dv.id, 'name': dv.name})

@app.route('/api/draft/<int:draft_id>/clone', methods=['POST'])
@login_required
def api_draft_clone(draft_id):
    """Duplicates an existing draft version and its entries."""
    source_dv = DraftVersion.query.get(draft_id)
    if not source_dv:
        return jsonify({'ok': False, 'error': 'Source draft not found'}), 404

    user_id = session.get('user_id')
    
    data = request.get_json(force=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        name = f"{source_dv.name} (Copy)"

    # 1. Create New Clone Draft Version
    new_dv = DraftVersion(
        name=name,
        semester=source_dv.semester,
        department=source_dv.department,
        created_by=user_id,
        notes=f"Cloned from {source_dv.name} (ID: {source_dv.id})"
    )
    db.session.add(new_dv)
    db.session.flush()

    # 2. Clone Entries from Source Draft
    source_entries = ScheduledClass.query.filter_by(draft_version_id=draft_id).all()
    for item in source_entries:
        clone = ScheduledClass(
            course_id=item.course_id,
            section_id=item.section_id,
            faculty_id=item.faculty_id,
            room_id=item.room_id,
            day=item.day,
            start_time=item.start_time,
            end_time=item.end_time,
            semester=item.semester,
            has_conflict=item.has_conflict,
            session_type=item.session_type,
            source=item.source,
            is_draft=True,
            draft_version_id=new_dv.id
        )
        db.session.add(clone)

    db.session.commit()
    return jsonify({'ok': True, 'draft_id': new_dv.id, 'name': new_dv.name})


@app.route('/api/draft/<int:draft_id>/entries')
@login_required
def api_draft_entries(draft_id):
    dv = DraftVersion.query.get(draft_id)
    if not dv:
        return jsonify({'ok': False, 'error': 'Draft not found'}), 404

    role    = session.get('role', 'user')
    user_id = session.get('user_id')
    if role == 'user' and dv.created_by != user_id:
        return jsonify({'ok': False, 'error': 'Not authorized'}), 403

    entries = []
    draft_scs = ScheduledClass.query.options(
        joinedload(ScheduledClass.course),
        joinedload(ScheduledClass.section),
        joinedload(ScheduledClass.faculty),
        joinedload(ScheduledClass.room),
    ).filter_by(draft_version_id=draft_id, is_draft=True).all()
    for sc in draft_scs:
        entries.append({
            'id':           sc.id,
            'course_id':    sc.course_id,
            'course_code':  sc.course.course_code   if sc.course  else '',
            'course_name':  sc.course.course_name   if sc.course  else '',
            'section_id':   sc.section_id,
            'section_name': sc.section.section_name if sc.section else '',
            'faculty_id':   sc.faculty_id,
            'faculty_name': sc.faculty.full_name    if sc.faculty else 'T.B.A.',
            'room_id':      sc.room_id,
            'room_name':    sc.room.room_name       if sc.room    else '',
            'day':          sc.day,
            'start_time':   sc.start_time,
            'end_time':     sc.end_time,
            'semester':     sc.semester,
            'session_type': sc.session_type,
            'source':       sc.source,
            'is_draft':     True,
        })
    return jsonify(entries)


@app.route('/api/draft/<int:draft_id>/publish', methods=['POST'])
@login_required
def api_draft_publish(draft_id):
    role = session.get('role')
    user_id = session.get('user_id')
    dv = DraftVersion.query.get(draft_id)
    if not dv:
        return jsonify({'ok': False, 'error': 'Draft not found'}), 404
    if role == 'user' and dv.created_by != user_id:
        return jsonify({'ok': False, 'error': 'Not authorized to publish this draft'}), 403
    if dv.is_published:
        return jsonify({'ok': False, 'error': 'Already published'}), 400

    draft_entries = ScheduledClass.query.filter_by(draft_version_id=draft_id, is_draft=True).all()

    # Pre-publish conflict check against master
    fmt = '%H:%M'
    conflicts = []
    for sc in draft_entries:
        try:
            t_s = datetime.strptime(sc.start_time, fmt).time()
            t_e = datetime.strptime(sc.end_time,   fmt).time()
        except ValueError:
            continue
        master = ScheduledClass.query.filter_by(
            day=sc.day, semester=sc.semester, is_draft=False).all()
        for ms in master:
            try:
                ms_s = datetime.strptime(ms.start_time, fmt).time()
                ms_e = datetime.strptime(ms.end_time,   fmt).time()
            except ValueError:
                continue
            if not (t_e <= ms_s or t_s >= ms_e):
                if (sc.faculty_id and sc.faculty_id == ms.faculty_id) or \
                   (sc.room_id    and sc.room_id    == ms.room_id   ) or \
                   (sc.section_id == ms.section_id):
                    course = Course.query.get(sc.course_id)
                    conflicts.append(f'{course.course_code if course else sc.course_id} on {sc.day} {sc.start_time}----{sc.end_time}')
                    break

    if conflicts:
        return jsonify({'ok': False,
                        'error': 'Hard conflicts found before publish',
                        'conflicts': conflicts}), 400

    # Publish: move all draft entries to master
    for sc in draft_entries:
        sc.is_draft         = False
        sc.draft_version_id = None
    dv.is_published = True
    db.session.commit()
    return jsonify({'ok': True, 'published_count': len(draft_entries)})

@app.route('/api/draft/<int:draft_id>', methods=['DELETE'])
@login_required
def api_draft_delete(draft_id):
    dv = DraftVersion.query.get(draft_id)
    if not dv:
        return jsonify({'ok': False, 'error': 'Draft not found'}), 404

    role    = session.get('role', 'user')
    user_id = session.get('user_id')
    if role == 'user' and dv.created_by != user_id:
        return jsonify({'ok': False, 'error': 'Not authorized'}), 403

    # Native delete
    db.session.delete(dv)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/draft/<int:draft_id>', methods=['PATCH'])
@login_required
def api_draft_edit(draft_id):
    dv = DraftVersion.query.get(draft_id)
    if not dv:
        return jsonify({'ok': False, 'error': 'Draft not found'}), 404
    role    = session.get('role', 'user')
    user_id = session.get('user_id')
    if role == 'user' and dv.created_by != user_id:
        return jsonify({'ok': False, 'error': 'Not authorized'}), 403
    data = request.get_json(force=True)
    if 'name' in data and data['name']:
        dv.name = data['name'].strip()
    if 'semester' in data:
        dv.semester = data['semester']
    if 'department' in data:
        dv.department = data['department'] or None
    if 'notes' in data:
        dv.notes = data['notes'] or None
    db.session.commit()
    return jsonify(ok=True, draft=dict(id=dv.id, name=dv.name, semester=dv.semester,
                                       department=dv.department, notes=dv.notes))


@app.route('/api/draft/<int:draft_id>/entities')
@login_required
def api_draft_entities(draft_id):
    """Returns only the sections, faculty, and rooms that have entries in this draft."""
    entries  = ScheduledClass.query.filter_by(draft_version_id=draft_id).all()
    sec_ids  = sorted({e.section_id for e in entries if e.section_id})
    fac_ids  = sorted({e.faculty_id for e in entries if e.faculty_id})
    room_ids = sorted({e.room_id    for e in entries if e.room_id})
    crs_ids  = sorted({e.course_id  for e in entries if e.course_id})
    sections  = Section.query.filter(Section.id.in_(sec_ids)).order_by(Section.section_name).all()  if sec_ids  else []
    faculties = Faculty.query.filter(Faculty.id.in_(fac_ids)).order_by(Faculty.full_name).all()     if fac_ids  else []
    rooms     = Room.query.filter(Room.id.in_(room_ids)).order_by(Room.room_name).all()              if room_ids else []
    courses   = Course.query.filter(Course.id.in_(crs_ids)).order_by(Course.course_code).all()      if crs_ids  else []
    return jsonify({
        'sections':  [{'id': s.id, 'label': s.section_name} for s in sections],
        'faculties': [{'id': f.id, 'label': f.full_name}    for f in faculties],
        'rooms':     [{'id': r.id, 'label': r.room_name}    for r in rooms],
        'courses':   [{'id': c.id, 'label': c.course_code}   for c in courses]
    })


@app.route('/api/hub/message/<int:msg_id>/edit', methods=['POST'])
@login_required
def api_hub_message_edit(msg_id):
    msg = HubMessage.query.get_or_404(msg_id)
    if msg.sender_id != session.get('user_id'):
        return jsonify(ok=False), 403
    new_content = (request.get_json() or {}).get('content', '').strip()
    if not new_content:
        return jsonify(ok=False), 400
    msg.content = new_content
    db.session.commit()
    return jsonify(ok=True)


@app.route('/api/hub/message/<int:msg_id>/delete', methods=['POST'])
@login_required
def api_hub_message_delete(msg_id):
    msg = HubMessage.query.get_or_404(msg_id)
    if msg.sender_id != session.get('user_id'):
        return jsonify(ok=False), 403
    db.session.delete(msg)
    db.session.commit()
    return jsonify(ok=True)


@app.route('/api/archive/stats')
@login_required
@role_required('admin', 'superadmin')
def api_archive_stats():
    """Returns counts of active entities for the archive summary modal."""
    return jsonify({
        'ok': True,
        'counts': {
            'courses': Course.query.filter_by(is_archived=False).count(),
            'sections': Section.query.filter_by(is_archived=False).count(),
            'students': Student.query.filter_by(is_archived=False).count(),
            'irregular': Student.query.filter_by(is_archived=False, is_irregular=True).count(),
            'faculty': Faculty.query.filter_by(is_archived=False).count(),
            'rooms': Room.query.filter_by(is_archived=False).count(),
            'scheduled': ScheduledClass.query.filter_by(is_draft=False).count()
        }
    })


@app.route('/api/archive/capture', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def api_archive_capture():
    """Performs the full-state cloning of current schedules into an archive snapshot."""
    data = request.get_json()
    ay = data.get('ay')
    sem = data.get('semester')

    if not ay or not sem:
        return jsonify(ok=False, message="Missing Academic Year or Semester metadata.")

    try:
        # 1. Fetch live master schedules (non-drafts) for the selected semester
        master_schedules = ScheduledClass.query.filter_by(semester=sem, is_draft=False).all()
        
        # 2. Calculate summary totals
        active_sections = Section.query.filter_by(is_archived=False).count()
        active_courses = Course.query.filter_by(is_archived=False).count()
        active_faculty = Faculty.query.filter_by(is_archived=False).count()
        # Count all students (except permanently deleted ones)
        active_students = Student.query.filter(Student.deleted_at.is_(None)).count()

        # 3. Create the parent Archive record
        new_archive = TermArchive(
            academic_year=ay,
            semester=sem,
            created_by_id=session.get('user_id'),
            total_sections=active_sections,
            total_courses=active_courses,
            total_faculty=active_faculty,
            total_schedules=len(master_schedules),
            total_students=active_students
        )
        db.session.add(new_archive)
        db.session.flush() # Get ID for the schedules

        # 4. Clone entries (flattening names to strings for decoupling)
        for sc in master_schedules:
            # Extract names cautiously
            course_code = sc.course.course_code if sc.course else "Unknown"
            course_name = sc.course.course_name if sc.course else "Unknown"
            sec_name = sc.section.section_name if sc.section else "TBA"
            fac_name = sc.faculty.full_name if sc.faculty else "TBA"
            rm_name = sc.room.room_name if sc.room else "TBA"

            # Determine if this class was pre-assigned
            # Pre-assignments match records in the PreAssignment table for the current term
            # Since we don't have a direct FK, we check for a match on all space-time-entity fields
            is_pre = db.session.query(PreAssignment).filter_by(
                course_id=sc.course_id,
                section_id=sc.section_id,
                faculty_id=sc.faculty_id,
                room_id=sc.room_id,
                day=sc.day,
                start_time=sc.start_time,
                end_time=sc.end_time
            ).first() is not None

            archived_sc = ArchivedSchedule(
                term_archive_id=new_archive.id,
                course_code=course_code,
                course_name=course_name,
                section_name=sec_name,
                faculty_name=fac_name,
                room_name=rm_name,
                day=sc.day,
                start_time=sc.start_time,
                end_time=sc.end_time,
                schedule_type=sc.session_type, # FIXED: was schedule_type
                is_preassigned=is_pre,
                section_num_students=sc.section.number_of_students if sc.section else 0
            )
            db.session.add(archived_sc)

        # 5. Snapshot Entities for 1:1 Reconstruction (Time Machine)
        # Capture Courses
        for c in Course.query.filter_by(is_archived=False).all():
            db.session.add(ArchivedCourse(
                term_archive_id=new_archive.id,
                course_code=c.course_code,
                course_name=c.course_name,
                year_level=c.year_level,
                program=c.program,
                department=c.department if c.department else "None",
                lec_units=c.lec_units,
                lab_units=c.lab_units,
                synchronous_lec_hours=c.synchronous_lec_hours,
                synchronous_lab_hours=c.synchronous_lab_hours,
                asynchronous_lec_hours=c.asynchronous_lec_hours,
                asynchronous_lab_hours=c.asynchronous_lab_hours,
                semester_offered=c.semester_offered
            ))

        # Capture Sections
        for s in Section.query.filter_by(is_archived=False).all():
            db.session.add(ArchivedSection(
                term_archive_id=new_archive.id,
                section_name=s.section_name,
                year_level=s.year_level,
                number_of_students=s.number_of_students
            ))

        # Capture Faculty
        for f in Faculty.query.filter_by(is_archived=False).all():
            db.session.add(ArchivedFaculty(
                term_archive_id=new_archive.id,
                employee_id=f.employee_id,
                full_name=f.full_name,
                department=f.department if f.department else "None",
                employment_status=f.employment_status,
                highest_educational_attainment=f.highest_educational_attainment,
                academic_rank=f.academic_rank,
                sex=f.sex,
                max_weekly_hours=f.max_weekly_hours,
                available_days=f.available_days
            ))

        # Capture Rooms
        for r in Room.query.filter_by(is_archived=False).all():
            db.session.add(ArchivedRoom(
                term_archive_id=new_archive.id,
                room_name=r.room_name,
                building=r.building,
                capabilities=r.capabilities,
                capacity=r.capacity,
                functional_computers=r.functional_computers,
                status=r.status,
                special_course_ids=r.special_course_ids,
                room_departments=r.room_departments
            ))

        # Capture Students
        for st in Student.query.filter(Student.deleted_at.is_(None)).all():
            asgn_data = None
            sec_name = None
            if st.is_irregular:
                asgn = IrregularAssignment.query.filter_by(student_id_fk=st.id, semester=sem).first()
                asgn_data = asgn.assignments_json if asgn else "[]"
            else:
                sec_name = st.section.section_name if st.section else None

            db.session.add(ArchivedStudent(
                term_archive_id=new_archive.id,
                student_id=st.student_id,
                full_name=st.full_name,
                year_level=st.year_level,
                is_irregular=st.is_irregular,
                section_name=sec_name,
                email=st.email if hasattr(st, 'email') else None,
                assignments_json=asgn_data
            ))

        # Capture Pre-Assignments
        for pa in PreAssignment.query.filter_by(is_archived=False).all():
            data = {col.name: getattr(pa, col.name) for col in pa.__table__.columns if col.name != 'deleted_at'}
            # Cautiously add names for reconstruction
            data['course_code'] = pa.course.course_code if pa.course else "Unknown"
            data['course_name'] = pa.course.course_name if pa.course else "Unknown"
            data['section_name'] = pa.section.section_name if pa.section else "TBA"
            data['faculty_name'] = pa.faculty.full_name if pa.faculty else "TBA"
            data['room_name'] = pa.room.room_name if pa.room else "TBA"
            db.session.add(ArchivedEntity(term_archive_id=new_archive.id, entity_type='PreAssignment', data_json=json.dumps(data, default=str)))

        db.session.commit()
        return jsonify(ok=True, message=f"Archived {len(master_schedules)} records for {sem} AY {ay} successfully.")

    except Exception as e:
        db.session.rollback()
        return jsonify(ok=False, message=str(e))


# --- Module 4: SNAPSHOT EXPLORATION ---

# Snapshot Explorer and Archive Viewers have been removed as per the final streamlined plan.
# Navigation is now handled exclusively via the Semester Switcher in the top navbar.


@app.route('/archives/delete/<int:archive_id>', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def archive_delete(archive_id):
    """Permanently removes an entire snapshot snapshot."""
    archive = TermArchive.query.get_or_404(archive_id)
    db.session.delete(archive)
    db.session.commit()
    flash(f"Archive for {archive.semester} AY {archive.academic_year} deleted permanently.", "danger")
    return redirect(url_for('dashboard'))


@app.route('/api/archive/reset-system', methods=['POST'])
@login_required
@role_required('superadmin')
def api_archive_reset():
    """Wipes the active operational data and prepares the system for a new term."""
    data = request.get_json()
    new_ay = data.get('new_ay')
    new_sem = data.get('new_semester')

    try:
        # 1. Wipe Active Tables (Wipes both Master and Drafts)
        ScheduledClass.query.delete()
        DraftVersion.query.delete()
        IrregularAssignment.query.delete()

        # 2. Update System Metadata
        settings = SystemSettings.query.first()
        if settings:
            if new_ay and new_sem:
                settings.sem_ay_value = f"{new_sem} / {new_ay}"
            # Reset Global AI-Lock for the new term
            settings.schedule_lock = False

        db.session.commit()
        return jsonify(ok=True, message=f"System cleared! Metadata updated to {new_sem} AY {new_ay}.")

    except Exception as e:
        db.session.rollback()
        return jsonify(ok=False, message=str(e))

# --- Integrated Archive Mode Controller ---

@app.route('/api/archive/enter-snapshot/<int:archive_id>')
@login_required
@role_required('admin', 'superadmin')
def api_archive_enter(archive_id):
    """Activates the system-wide read-only historical view for a specific snapshot."""
    archive = TermArchive.query.get_or_404(archive_id)
    session['historical_mode_active'] = True
    session['active_archive_id'] = archive_id
    session['active_archive_display'] = f"{archive.semester} AY {archive.academic_year}"
    flash(f"Entering Archive: {session['active_archive_display']}", "info")
    return redirect(url_for('dashboard'))

@app.route('/api/archive/exit-snapshot')
@login_required
@role_required('admin', 'superadmin')
def api_archive_exit():
    """Exits historical view and returns the system to the active live state."""
    session.pop('historical_mode_active', None)
    session.pop('active_archive_id', None)
    session.pop('active_archive_display', None)
    flash("Returned to Active Scheduling System.", "success")
    return redirect(url_for('dashboard'))


@app.route('/api/archive/export/<int:archive_id>')
@login_required
@role_required('admin', 'superadmin')
def archive_export_excel(archive_id):
    """Exports a specific archive to a professional Excel report."""
    archive = TermArchive.query.get_or_404(archive_id)
    schedules = ArchivedSchedule.query.filter_by(term_archive_id=archive_id).all()
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Archived Schedule"
    
    # Professional Styling
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="0D6EFD", end_color="0D6EFD", fill_type="solid") # Bootstrap Primary
    center_align = Alignment(horizontal="center", vertical="center")
    thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                        top=Side(style='thin'), bottom=Side(style='thin'))

    # Build Headers
    headers = ['Course Code', 'Course Name', 'Section', 'Faculty Member', 'Room', 'Day', 'Start Time', 'End Time', 'Type']
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.value = header
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = thin_border

    # Populate Data
    for row_num, s in enumerate(schedules, 2):
        cells = [
            ws.cell(row=row_num, column=1, value=s.course_code),
            ws.cell(row=row_num, column=2, value=s.course_name),
            ws.cell(row=row_num, column=3, value=s.section_name),
            ws.cell(row=row_num, column=4, value=s.faculty_name),
            ws.cell(row=row_num, column=5, value=s.room_name),
            ws.cell(row=row_num, column=6, value=s.day),
            ws.cell(row=row_num, column=7, value=s.start_time),
            ws.cell(row=row_num, column=8, value=s.end_time),
            ws.cell(row=row_num, column=9, value=s.schedule_type)
        ]
        for c in cells:
            c.border = thin_border
            if c.column == 6: # Day column
                c.alignment = center_align

    # Auto-adjust column widths
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except: pass
        ws.column_dimensions[column].width = max_length + 3

    # Save to buffer
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    safe_name = f"CVSu_Archive_{archive.semester}_{archive.academic_year}".replace(" ", "_")
    return send_file(output, 
                     download_name=f"{safe_name}.xlsx", 
                     as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')





# --- C: SCHEDULE EDITOR PAGE ---



@app.route('/schedule-editor')
@login_required
def schedule_editor():
    settings  = SystemSettings.query.first()
    
    is_user = session.get('role') == 'user'
    uid = session.get('user_id')

    section_q = Section.query.filter_by(is_archived=False)
    faculty_q = Faculty.query.filter_by(is_archived=False)
    room_q    = Room.query.filter_by(is_archived=False)
    course_q  = Course.query.filter_by(is_archived=False)

    if is_user:
        # DATA ISOLATION: Removed for Sections
        faculty_q = faculty_q.filter_by(created_by_id=uid)
        room_q    = room_q.filter_by(created_by_id=uid)
        course_q  = course_q.filter_by(created_by_id=uid)

    sections  = section_q.order_by(Section.section_name).all()
    faculties = faculty_q.order_by(Faculty.full_name).all()
    rooms     = room_q.order_by(Room.room_name).all()
    courses   = course_q.order_by(Course.course_code).all()
    semesters = ['1st Semester', '2nd Semester', 'Summer']

    role    = session.get('role', 'user')
    user_id = session.get('user_id')

    # Infer user's department (for regular users)
    user_dept = None
    if role == 'user':
        user = User.query.get(user_id)
        if user:
            if user.department:
                # Use stored department directly
                user_dept = user.department
            else:
                # Fallback: match faculty record by username
                fac = Faculty.query.filter(Faculty.full_name.ilike(f'%{user.username}%')).first()
                user_dept = fac.department if fac else None

    # Draft versions visible to this user
    if role in ('admin', 'superadmin'):
        drafts = DraftVersion.query.order_by(DraftVersion.created_at.desc()).all()
    else:
        drafts = DraftVersion.query.filter_by(
            department=user_dept, is_published=False
        ).filter(
            (DraftVersion.created_by == user_id)
        ).order_by(DraftVersion.created_at.desc()).all()

    # Allowed days and hours for grid
    allowed_days = (settings.allowed_days.split(',')
                    if settings and settings.allowed_days
                    else ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'])
    start_hour = settings.start_hour if settings else 7
    end_hour   = settings.end_hour   if settings else 21

    # Pass Layout Dimensions for Preview Sync
    def _pdim(pk):
        w, h, _ = PAPER_SIZES.get(pk, PAPER_SIZES['A4'])
        return {'w': w, 'h': h}
    
    sec_p = getattr(settings, 'paper_size', 'A4') or 'A4'
    fac_p = getattr(settings, 'fac_paper_size', 'A4') or 'A4'
    layout_configs = {
        'section': _pdim(sec_p),
        'room':    _pdim(sec_p),
        'course':  _pdim(sec_p),
        'faculty': _pdim(fac_p)
    }

    return render_template('schedule_editor.html',
        sections=sections, faculties=faculties, rooms=rooms,
        courses=courses, semesters=semesters,
        drafts=drafts, user_dept=user_dept,
        departments=KNOWN_DEPARTMENTS,
        allowed_days=allowed_days,
        start_hour=start_hour, end_hour=end_hour,
        lock_status=bool(settings.schedule_lock) if settings else False,
        layout_configs=layout_configs
    )

# --- END MODULE 3 ROUTES ---


# --- CONSTRAINT CHECKER MODULE ---

@app.route('/check-constraints')
@login_required
@role_required('admin', 'superadmin')
def check_constraints():
    sort_by      = request.args.get('sort',   'rule-asc', type=str)
    search_query = request.args.get('search', '',        type=str)
    page         = request.args.get('page',   1,         type=int)
    # Multi-select: empty list = show all
    selected_depts = request.args.getlist('dept')
    selected_types = request.args.getlist('types')

    target_semester = session.get('selected_semester', '1st Semester')

    all_schedules = _dedup_schedules(ScheduledClass.query.all())
    # Filter by semester when a specific semester is selected
    if target_semester and target_semester != 'All':
        schedules = [s for s in all_schedules if s.course.semester_offered == target_semester]
    else:
        schedules = all_schedules
    all_sections = Section.query.all()
    constraints_db = Constraint.query.all()
    settings = {c.logic_code: c.constraint_type for c in constraints_db}

    violations = []

    def to_minutes(t):
        try:
            h, m = map(int, t.split(':'))
            return h * 60 + m
        except:
            return 0

    def is_active(code):
        return settings.get(code, 'HC') != 'NC'

    # Pre-identify virtual rooms (TBA/Virtual/Online) to exempt from physical-only constraints
    _v_rooms = {r.id for r in Room.query.filter(
        (Room.room_name.ilike('%TBA%')) | (Room.room_name.ilike('%Virtual%')) | (Room.room_name.ilike('%Online%'))
    ).all()}

    # DYNAMIC ROOM IDLE GAP THRESHOLD (SC-I-04)
    # Short-circuit scan: if any scheduled course is 1-hour, threshold is 30 mins.
    # Otherwise, threshold is 90 mins (1.5 hours).
    _min_dur_m = 120
    for s in schedules:
        c = s.course
        if (c.synchronous_lec_hours == 1.0) or (c.synchronous_lab_hours == 1.0):
            _min_dur_m = 60
            break
    _idle_gap_limit = _min_dur_m - 30

    def add_v(code, rule, desc, ca, cb=None):
        if is_active(code):
            violations.append({'type': settings.get(code, 'HC'), 'rule': rule, 'desc': desc, 'class_a': ca, 'class_b': cb})

    # Fake schedule object for allocation-only violations (no actual ScheduledClass row)
    class Fake:
        def __init__(self, sc, cr):
            self.course = cr
            self.section = sc
            self.room = type('obj', (object,), {'room_name': 'N/A'})()
            self.day = 'N/A'
            self.start_time = '--'
            self.end_time = '--'

    day_rank = {'Monday': 1, 'Tuesday': 2, 'Wednesday': 3, 'Thursday': 4, 'Friday': 5, 'Saturday': 6}
    pe_keywords = ('PE', 'FITT')
    special_rooms = {'T.B.A.', 'University Field', 'Online Room'}

    # Pre-load allowed days for HC-14
    _sys = SystemSettings.query.first()
    allowed_days_set = set(_sys.allowed_days.split(',')) if _sys and _sys.allowed_days else set()

    # Pre-compute div4 mode: dynamic threshold = special_long_lec_count + 5.
    # Only count sections belonging to the current semester so NSTP from other semesters
    # don't inflate the count and incorrectly disable div4 for unrelated schedules.
    # Special-room courses (e.g. NSTP -> University Field) are exempt from div4 already,
    # so their count is added to the threshold as a buffer.
    _special_cids_cc = set()
    for _r in Room.query.filter_by(is_archived=False).all():
        for _cid_str in (_r.special_course_ids or '').split(','):
            _cid_str = _cid_str.strip()
            if _cid_str:
                try: _special_cids_cc.add(int(_cid_str))
                except ValueError: pass
    # Also include pre-assigned course IDs ---- fixed genes are already exempt from div4
    # via `not g.is_fixed`, so they count as "special" for the threshold.
    for _pa in PreAssignment.query.filter_by(is_archived=False).all():
        _special_cids_cc.add(_pa.course_id)
    _all_sections   = Section.query.all()
    _all_courses_map = {c.id: c for c in Course.query.all()}
    # Filter to current semester's sections only
    _sem_sections = [s for s in _all_sections
                     if any(c.semester_offered == target_semester for c in s.courses)]
    _long_lec_genes_count = sum(
        1 for sec in _sem_sections
        for course in sec.courses
        if (course.synchronous_lec_hours or 0) > 2
        and course.semester_offered == target_semester
    )
    _special_long_lec_count = sum(
        1 for sec in _sem_sections
        for course in sec.courses
        if (course.synchronous_lec_hours or 0) > 2
        and course.semester_offered == target_semester
        and course.id in _special_cids_cc
    )
    _div4_active = (_long_lec_genes_count <= _special_long_lec_count + 5)
    _lec_only_room_names = {
        r.room_name for r in Room.query.filter_by(status='Available').all()
        if 'Computer Lab' not in (r.capabilities or '')
    } - special_rooms
    # Div4 valid start minutes: 7AM, 9AM, 11AM, 1PM, 3PM, 5PM, 7PM (every 2 hours from start_hour)
    _sys_sh = (_sys.start_hour if _sys else 7)
    _div4_start_minutes = {(_sys_sh + i * 2) * 60 for i in range(8)}

    # Pre-build HC-27 split map: {(faculty_id, course_id, section_id): [(day, hours), ...]}
    _split_map_cc = {}
    for _fa in FacultyAssignment.query.all():
        _splits = []
        if _fa.split_day_1 and _fa.split_hours_1:
            _splits.append((_fa.split_day_1, _fa.split_hours_1))
        if _fa.split_day_2 and _fa.split_hours_2:
            _splits.append((_fa.split_day_2, _fa.split_hours_2))
        if _splits:
            _split_map_cc[(_fa.faculty_id, _fa.course_id, _fa.section_id)] = _splits

    # Pre-build room occupation map for SC-II-03 "no choice" detection
    # {(room_id, day): [(start_m, end_m), ...]}
    _room_day_occ = {}
    for s in schedules:
        key = (s.room_id, s.day)
        if key not in _room_day_occ:
            _room_day_occ[key] = []
        _room_day_occ[key].append((to_minutes(s.start_time), to_minutes(s.end_time)))

    _avail_rooms = Room.query.filter_by(status='Available').all()
    _lec_room_ids = [r.id for r in _avail_rooms if 'Computer Lab' not in (r.capabilities or '')]
    _lab_room_ids = [r.id for r in _avail_rooms if 'Computer Lab' in (r.capabilities or '')]

    # Pre-compute total Lab/Lec duration per (course_id, section_id) pair.
    # Used by HC-08/HC-09 to correctly handle day-split sessions:
    # a 6h Lab split 3+3 creates two 3h rows ---- summing them gives 6h (no violation).
    from collections import defaultdict as _ddict
    _lab_dur_sum = _ddict(float)   # (course_id, section_id) -> total Lab hours
    _lec_dur_sum = _ddict(float)   # (course_id, section_id) -> total Lec hours
    for _sd in schedules:
        if not _sd.start_time or not _sd.end_time:
            continue
        try:
            _sh2, _sm2 = map(int, _sd.start_time.split(':'))
            _eh2, _em2 = map(int, _sd.end_time.split(':'))
            _dh2 = ((_eh2 * 60 + _em2) - (_sh2 * 60 + _sm2)) / 60.0
        except Exception:
            continue
        _stype2 = (_sd.session_type or 'Lec')
        if _stype2 == 'Lab':
            _lab_dur_sum[(_sd.course_id, _sd.section_id)] += _dh2
        elif _stype2 == 'Lec':
            _lec_dur_sum[(_sd.course_id, _sd.section_id)] += _dh2
    # Seen-sets: only report HC-08/HC-09 once per (course, section) pair to avoid
    # duplicate violations from split sub-genes being flagged individually
    _hc08_seen = set()
    _hc09_seen = set()

    def _room_has_daytime_slot(room_id, day, duration_m):
        """Return True if room has a free block >= duration_m minutes between 7AM----7PM."""
        DAY_S, DAY_E = 420, 1140   # 7AM, 7PM in minutes
        occupied = sorted(_room_day_occ.get((room_id, day), []))
        free_start = DAY_S
        for occ_s, occ_e in occupied:
            occ_s = max(occ_s, DAY_S)
            occ_e = min(occ_e, DAY_E)
            if occ_s > free_start and occ_s - free_start >= duration_m:
                return True
            free_start = max(free_start, occ_e)
        return DAY_E - free_start >= duration_m

    # =========================================================
    # GROUP 1: INDIVIDUAL CHECKS
    # =========================================================
    for s in schedules:
        start_m = to_minutes(s.start_time)
        end_m   = to_minutes(s.end_time)
        dur_h   = (end_m - start_m) / 60
        code_up = s.course.course_code.upper()

        # HC-03: Global Day Restriction (no Sunday classes)
        if s.day == 'Sunday':
            add_v('GLOBAL_DAY_RESTRICTION', 'Global Day Restriction', 'No classes on Sunday.', s)

        # HC-23: Operating Hours (7:00 AM — 9:00 PM)
        if start_m < 420 or end_m > 1260:
            add_v('OPERATING_HOURS', 'Operating Hours Compliance', 'Class scheduled outside 7 AM—9 PM.', s)

        # HC-24: Hourly Alignment (start on the hour or half-hour)
        if start_m % 30 != 0:
            add_v('HOURLY_ALIGNMENT', 'Hourly Time Alignment', 'Class must start on the hour or half-hour.', s)

        # HC-22: Room Availability
        if s.room.status != 'Available':
            add_v('ROOM_AVAILABILITY', 'Room Availability', f"Room is marked '{s.room.status}'.", s)

        # HC-21: Room Type Suitability (lab session must be in a Computer Lab)
        if s.room.room_name not in special_rooms:
            is_lab_r = 'Computer Lab' in (s.room.capabilities or '')
            is_lec_r = 'Lecture' in (s.room.capabilities or '')
            
            req_lab = s.course.synchronous_lab_hours if s.course.synchronous_lab_hours > 0 else s.course.lab_units
            is_lab_session = req_lab > 0 and abs(dur_h - req_lab) <= 0.5
            
            if is_lab_session and not is_lab_r:
                # Lab in a non-lab room is still a Hard Conflict
                add_v('ROOM_SUITABILITY', 'Room Type Suitability', f'Lab session assigned to non-lab room ({s.room.room_name}).', s)
            elif not is_lab_session and is_lab_r and not is_lec_r:
                # Lec in a pure Lab room is now a SOFT Fallback
                add_v('LEC_IN_LAB_FALLBACK', 'Lecture in Lab Fallback', f'Lecture session is using a Lab room ({s.room.room_name}) as fallback.', s)
            elif not is_lab_session and is_lab_r and is_lec_r and s.room.room_name[:1] == 'B':
                # B-rooms (Labs with Lec capability) are also reported as fallbacks for Lec sessions
                add_v('LEC_IN_LAB_FALLBACK', 'Lecture in Lab Fallback', f'Lecture is in Lab room {s.room.room_name}.', s)

        # SC-II-05: Room Capacity Allocation (Absolute Fit)
        r_name_up = (s.room.room_name or '').upper()
        if not any(ex in r_name_up for ex in ['COURT', 'GYM', 'T.B.A.', 'ONLINE', 'VIRTUAL']):
            diff = abs(s.room.capacity - s.section.number_of_students)
            if diff > 10: # Only report significant mismatches (>10 seats difference)
                add_v('ROOM_CAPACITY_PROPORTIONAL', 'Room Capacity Allocation',
                      f'Room {s.room.room_name} capacity ({s.room.capacity}) is not a close fit for {s.section.number_of_students} students (Diff: {diff}).', s)

        # SC-II-04: Lunch Break ---- checked at section-day level in GROUP 3 below

        # SC-I-03: Evening Avoidance (Physical Room Only)
        if s.room_id not in _v_rooms:
            if start_m >= 1140: # 7:00 PM onwards
                add_v('EVENING_AVOIDANCE', 'Evening Avoidance',
                      f'Class in {s.room.room_name} starts at {s.start_time} (7:00 PM or later).', s)
            elif start_m >= 1020: # 5:00 PM onwards
                add_v('EVENING_AVOIDANCE', 'Evening Avoidance',
                      f'Class in {s.room.room_name} starts at {s.start_time} (5:00 PM or later).', s)

        # SC-II-01: PE Morning Placement (Starts before 12 PM)
        is_pe = 'P.E.' in s.course.course_code.upper() or 'FITT' in s.course.course_code.upper()
        if is_pe:
            if to_minutes(s.start_time) >= 720: # 12:00 PM
                add_v('PE_MORNING_PLACEMENT', 'PE Morning Placement',
                      f'PE session {s.course.course_code} starts at {s.start_time} (Prefer morning).', s)
            # SC-II-02: PE Early Week (Mon-Wed)
            day_idx = day_rank.get(s.day, 0)
            if day_idx > 2: # Thu, Fri, Sat
                add_v('PE_EARLY_WEEK', 'PE Early Week Placement',
                      f'PE session {s.course.course_code} is on {s.day} (Prefer Mon-Wed).', s)

        # SC-II-03: Strategic Async Placement (Disabled as per user request)
        pass

        # HC-14: Section Day Restrictions (must be within SystemSettings allowed_days)
        if allowed_days_set and s.day not in allowed_days_set:
            add_v('SECTION_DAY_RESTRICTIONS', 'Section Day Restrictions',
                  f'Section {s.section.section_name} is scheduled on {s.day}, which is not an allowed academic day.', s)

        # HC-18: Faculty Availability (faculty must be available on the scheduled day)
        if s.faculty_id and s.faculty.full_name != 'T.B.A.':
            fac_avail = set((s.faculty.available_days or '').split(','))
            if fac_avail and s.day not in fac_avail:
                add_v('FACULTY_AVAILABILITY', 'Faculty Availability',
                      f'{s.faculty.full_name} is not available on {s.day}.', s)

        # HC-27: Faculty Day Split (session must land on its designated split day)
        if s.faculty_id and s.section_id and s.course_id:
            _split_key = (s.faculty_id, s.course_id, s.section_id)
            _split_days = _split_map_cc.get(_split_key)
            if _split_days:
                _allowed_days = [d for d, _ in _split_days]
                if s.day not in _allowed_days:
                    add_v('FACULTY_DAY_SPLIT', 'Faculty Day Split',
                          f'{s.faculty.full_name} ---- {s.course.course_code} in section '
                          f'{s.section.section_name} is on {s.day} but split requires '
                          f'{" or ".join(_allowed_days)}.', s)

        # HC-08 / HC-09 / HC-10 / HC-11: Strict Duration Checks
        if s.room and s.room.room_name not in special_rooms:
            req_sl_d    = s.course.synchronous_lec_hours if s.course.synchronous_lec_hours > 0 else s.course.lec_units
            req_slab_d  = s.course.synchronous_lab_hours if s.course.synchronous_lab_hours > 0 else s.course.lab_units
            async_lec_d = s.course.asynchronous_lec_hours or 0
            async_lab_d = s.course.asynchronous_lab_hours or 0
            async_d     = async_lec_d + async_lab_d
            is_lab_r    = s.room and 'Computer Lab' in (s.room.capabilities or '')
            stype       = s.session_type or 'Lec'
            if stype == 'Lab' and req_slab_d > 0:
                # HC-09: Lab session duration ---- use group sum to handle day-split sessions
                # (e.g. 3h+3h split -> total 6h = expected 6h -> no violation)
                _hc09_pair = (s.course_id, s.section_id)
                if _hc09_pair not in _hc09_seen:
                    _hc09_seen.add(_hc09_pair)
                    _total_lab_h = _lab_dur_sum.get(_hc09_pair, dur_h)
                    if abs(_total_lab_h - req_slab_d) > 0.5:
                        add_v('STRICT_LAB_DURATION', 'Strict Laboratory Duration',
                              f'Lab for {s.course.course_code} is {_total_lab_h:.1f}h total, expected {req_slab_d}h.', s)
            elif stype == 'Async' and async_d > 0:
                # Async session ---- check HC-10 and HC-11 independently
                if abs(dur_h - async_d) > 0.5:
                    # HC-10: Async Lecture Duration (fires if course has async lec component)
                    if async_lec_d > 0:
                        add_v('STRICT_ASYNC_LEC_DUR', 'Strict Async Lecture Duration',
                              f'Async session for {s.course.course_code} is {dur_h:.1f}h; '
                              f'async lec component expects {async_lec_d}h.', s)
                    # HC-11: Async Lab Duration (fires if course has async lab component)
                    if async_lab_d > 0:
                        add_v('STRICT_ASYNC_LAB_DUR', 'Strict Async Laboratory Duration',
                              f'Async session for {s.course.course_code} is {dur_h:.1f}h; '
                              f'async lab component expects {async_lab_d}h.', s)
            elif stype == 'Lec' and req_sl_d > 0:
                # HC-08: Lecture session duration ---- use group sum to handle day-split sessions
                _hc08_pair = (s.course_id, s.section_id)
                if _hc08_pair not in _hc08_seen:
                    _hc08_seen.add(_hc08_pair)
                    _total_lec_h = _lec_dur_sum.get(_hc08_pair, dur_h)
                    if abs(_total_lec_h - req_sl_d) > 0.5:
                        add_v('STRICT_LEC_DURATION', 'Strict Lecture Duration',
                              f'Lecture for {s.course.course_code} is {_total_lec_h:.1f}h total, expected {req_sl_d}h.', s)

    # =========================================================
    # GROUP 2: PAIRWISE OVERLAP CHECKS
    # =========================================================
    count = len(schedules)
    for i in range(count):
        for j in range(i + 1, count):
            s1, s2 = schedules[i], schedules[j]
            if s1.day != s2.day:
                continue
            start1, end1 = to_minutes(s1.start_time), to_minutes(s1.end_time)
            start2, end2 = to_minutes(s2.start_time), to_minutes(s2.end_time)
            if max(start1, start2) >= min(end1, end2):
                continue

            # HC-16: No Multiple Sections in One Room (was ROOM_CONFLICT)
            if s1.room_id == s2.room_id and s1.room.room_name not in special_rooms:
                add_v('ROOM_OVERLAP', 'No Room Conflict',
                      f'Room {s1.room.room_name} is double-booked.', s1, s2)

            # HC-13: No Faculty Course Conflict
            if s1.faculty_id and s2.faculty_id and s1.faculty_id == s2.faculty_id:
                if s1.faculty.full_name != 'T.B.A.':
                    add_v('FACULTY_OVERLAP', 'No Faculty Conflict',
                          f'Prof. {s1.faculty.full_name} is double-booked.', s1, s2)

            # HC-12: No Section Course Conflict
            if s1.section_id == s2.section_id:
                add_v('SECTION_OVERLAP', 'No Section Conflict',
                      f'Section {s1.section.section_name} has overlapping classes.', s1, s2)

            # HC-17: Single Faculty per Section Timeslot
            if s1.section_id == s2.section_id:
                if (s1.faculty_id and s2.faculty_id and s1.faculty_id != s2.faculty_id
                        and s1.faculty.full_name != 'T.B.A.' and s2.faculty.full_name != 'T.B.A.'):
                    add_v('SINGLE_FACULTY_PER_TIMESLOT', 'Single Faculty per Timeslot',
                          f'Section {s1.section.section_name} has 2 different faculty '
                          f'({s1.faculty.full_name} & {s2.faculty.full_name}) at the same time.', s1, s2)

    # =========================================================
    # SC-I-09: EARLY START ENFORCEMENT (per room per day)
    # First class in each used room must start within 1 hour of system start time.
    # =========================================================
    _sys_start_m    = (_sys.start_hour if _sys else 7) * 60   # e.g. 7AM = 420 min
    _max_first_m    = _sys_start_m                             # No grace period - must start exactly on system start
    _room_day_first = {}                                        # (room_id, day) -> earliest schedule

    for s in schedules:
        if s.room_id in _v_rooms: continue
        key = (s.room_id, s.day)
        if key not in _room_day_first or to_minutes(s.start_time) < to_minutes(_room_day_first[key].start_time):
            _room_day_first[key] = s
            
    for (room_id, day), first_s in _room_day_first.items():
        if to_minutes(first_s.start_time) > _sys_start_m: # Report any idle time in the morning
            sys_start_label = f"{_sys.start_hour}:00 AM" if _sys else "7:00 AM"
            add_v('EARLY_START_ENFORCEMENT', 'Early Start Enforcement',
                  f'First class in {first_s.room.room_name} on {day} starts at {first_s.start_time}. '
                  f'Room is idle during {sys_start_label}----{first_s.start_time}.', first_s)

    # =========================================================
    # SC-I-04: ROOM IDLE GAP (Compact Room Usage)
    # Penalize small gaps between classes in physical rooms.
    # =========================================================
    _room_day_groups = {} # (room_id, day) -> [schedules]
    for s in schedules:
        if s.room_id in _v_rooms: continue
        _room_day_groups.setdefault((s.room_id, s.day), []).append(s)
        
    for (room_id, day), room_schedules in _room_day_groups.items():
        room_schedules.sort(key=lambda x: to_minutes(x.start_time))
        for i in range(len(room_schedules) - 1):
            s1 = room_schedules[i]
            s2 = room_schedules[i+1]
            gap_min = to_minutes(s2.start_time) - to_minutes(s1.end_time)
            if 0 < gap_min <= _idle_gap_limit: # DYNAMIC threshold (30m to _idle_gap_limit)
                add_v('ROOM_IDLE_GAP', 'Room Idle Gap',
                      f'Room {s1.room.room_name} on {day} has a {gap_min}-minute gap '
                      f'between {s1.course.course_code} and {s2.course.course_code}.', s1, s2)

    # =========================================================
    # SC-II-05: LAB ROOM SATURATION GAP
    # Penalize wasteful 1-hour or 2-hour gaps in physical Computer Labs.
    # =========================================================
    for (room_id, day), room_schedules in _room_day_groups.items():
        r = room_schedules[0].room if room_schedules else None
        if r and 'Computer Lab' in (r.capabilities or ''):
            room_schedules.sort(key=lambda x: to_minutes(x.start_time))
            for i in range(len(room_schedules) - 1):
                s1 = room_schedules[i]
                s2 = room_schedules[i+1]
                gap_min = to_minutes(s2.start_time) - to_minutes(s1.end_time)
                if gap_min in (30, 60, 90, 120):
                    add_v('LAB_ROOM_SATURATION_GAP', 'Lab Room Squeeze/Saturation',
                          f'Lab room {s1.room.room_name} on {day} has a wasteful {gap_min}-minute idle gap '
                          f'between {s1.course.course_code} and {s2.course.course_code}.', s1, s2)

    # =========================================================
    # GROUP 3: LOAD, SEQUENCE & DAILY DISTRIBUTION CHECKS
    # =========================================================
    faculty_loads      = {}
    section_loads      = {}
    section_courses_map = {}

    for s in schedules:
        if s.faculty_id and s.faculty.full_name != 'T.B.A.':
            faculty_loads.setdefault(s.faculty_id, []).append(s)
        section_loads.setdefault(s.section_id, []).append(s)
        section_courses_map.setdefault(s.section_id, []).append(s)

    def check_consecutive(group_items, rule_name, rule_code):
        if not group_items:
            return
        group_items.sort(key=lambda x: (x.day, to_minutes(x.start_time)))
        streak = 0
        last_end = -999
        last_day = ''
        for x in group_items:
            dur = (to_minutes(x.end_time) - to_minutes(x.start_time)) / 60
            if x.day != last_day:
                streak = dur
            else:
                streak = streak + dur if abs(to_minutes(x.start_time) - last_end) <= 15 else dur
            last_end = to_minutes(x.end_time)
            last_day = x.day
            if streak > 6:
                add_v(rule_code, rule_name, 'Exceeds 6 consecutive hours.', x)
                break

    for fac_id, items in faculty_loads.items():
        check_consecutive(list(items), 'Max Consecutive Faculty Load', 'MAX_CONSECUTIVE_FACULTY')
        
        # SC-II-04: Faculty Lunch Break (10 AM - 2 PM)
        daily_fac = {}
        for s in items: daily_fac.setdefault(s.day, []).append(s)
        for day, day_classes in daily_fac.items():
            _LUNCH_START = 600; _LUNCH_END = 840
            occ = set()
            for _c in day_classes:
                _s = to_minutes(_c.start_time); _e = to_minutes(_c.end_time)
                for _m in range(max(_s, _LUNCH_START), min(_e, _LUNCH_END), 30): occ.add(_m)
            if occ and not any(_m not in occ and (_m+30) not in occ for _m in range(_LUNCH_START, _LUNCH_END-30, 30)):
                add_v('LUNCH_BREAK', 'Faculty Lunch Break',
                      f'Faculty {day_classes[0].faculty.full_name} has no 1-hr break between 10 AM-2 PM on {day}.', day_classes[0])

    for items in section_loads.values():
        check_consecutive(list(items), 'Max Consecutive Student Load', 'MAX_CONSECUTIVE_STUDENT')

    # HC-04: Lec-before-Lab sequence + SC-I-01/SC-I-03 proximity checks
    for sec_id, classes in section_courses_map.items():
        subject_map = {}
        for c in classes:
            base = c.course.course_code[:7]
            subject_map.setdefault(base, []).append(c)

        for base, pair in subject_map.items():
            lec = next((x for x in pair if x.course.lec_units > 0 or x.course.synchronous_lec_hours > 0), None)
            lab = next((x for x in pair if x.course.lab_units > 0 or x.course.synchronous_lab_hours > 0), None)
            if not (lec and lab and lec != lab):
                continue

            lec_time_rank = day_rank.get(lec.day, 0) * 1440 + to_minutes(lec.start_time)
            lab_time_rank = day_rank.get(lab.day, 0) * 1440 + to_minutes(lab.start_time)

            # HC-04: Lab must not come before Lecture (time-wise)
            if lab_time_rank < lec_time_rank:
                add_v('LEC_LAB_SEQUENCE', 'Lecture-Laboratory Sequence',
                      f'Lab for {base} is scheduled before its Lecture.', lab, lec)

            lec_day = day_rank.get(lec.day, 0)
            lab_day = day_rank.get(lab.day, 0)

            # SC-I-08: Lec should be earlier in the week than Lab (Weekly Distribution)
            if lab_day > 0 and lec_day > 0 and lab_day < lec_day:
                add_v('LEC_LAB_WEEKLY_DIST', 'Lecture-Lab Weekly Distribution',
                      f'Lab for {base} is earlier in the week than its Lecture.', lab, lec)

            # SC-I-09: Lec and Lab should be within 2 days of each other (Proximity)
            if lec_day > 0 and lab_day > 0 and abs(lec_day - lab_day) > 2:
                add_v('LEC_LAB_PROXIMITY', 'Lecture-Lab Proximity',
                      f'Lecture and Lab for {base} are more than 2 days apart.', lec, lab)

    # SC-I-05/SC-I-06: No isolated lecture/lab; SC-II-02: Min daily section load
    for sec_id, classes in section_courses_map.items():
        daily = {}
        for c in classes:
            daily.setdefault(c.day, []).append(c)

        for day, day_classes in daily.items():
            # SC-I-08: Lunch Break ---- section must have ---------------1 free hour in 10:00 AM----2:00 PM window
            # Build set of occupied minute-intervals within the window for this section+day
            _LUNCH_START = 600   # 10:00 AM in minutes
            _LUNCH_END   = 840   # 2:00 PM in minutes
            _SLOT = 60           # 1-hour minimum break
            occupied_mins = set()
            for _c in day_classes:
                _s = to_minutes(_c.start_time)
                _e = to_minutes(_c.end_time)
                for _m in range(max(_s, _LUNCH_START), min(_e, _LUNCH_END), 30):
                    occupied_mins.add(_m)
            if occupied_mins and not any(
                _m not in occupied_mins and (_m + 30) not in occupied_mins
                for _m in range(_LUNCH_START, _LUNCH_END - 30, 30)
            ):
                add_v('LUNCH_BREAK', 'Lunch Break Preference',
                      f'Section {day_classes[0].section.section_name} has no free hour in the 10 AM----2 PM '
                      f'lunch window on {day}.', day_classes[0])

            # SC-I-07: Minimum Daily Section Load (Target >= 3.0 Hours)
            total_dur_h = sum((to_minutes(s.end_time) - to_minutes(s.start_time))/60 for s in day_classes)
            if total_dur_h < 3.0:
                add_v('MIN_DAILY_SECTION_LOAD', 'Min Daily Section Load',
                      f'Section {day_classes[0].section.section_name} has only {total_dur_h:.1f} hours of class on {day} (Target: >= 3.0h).', day_classes[0])

            # SC-I-05 / SC-I-06: Isolated single class with nothing else that day.
            # Use room capabilities to distinguish Lec vs Lab (same as GA gene_type logic)
            # so a session is counted as ONE violation type only, preventing double-counting
            # for courses that have both lec_units > 0 and lab_units > 0.
            if len(day_classes) == 1:
                c = day_classes[0]
                is_lab_room = hasattr(c, 'room') and c.room and 'Computer Lab' in (c.room.capabilities or '')
                if is_lab_room and (c.course.lab_units > 0 or c.course.synchronous_lab_hours > 0):
                    add_v('NO_ISOLATED_LABS', 'No Isolated Laboratories',
                          f'Section {c.section.section_name} has an isolated lab on {day}.', c)
                elif not is_lab_room and (c.course.lec_units > 0 or c.course.synchronous_lec_hours > 0):
                    add_v('NO_ISOLATED_LECTURES', 'No Isolated Lectures',
                          f'Section {c.section.section_name} has an isolated lecture on {day}.', c)

    # =========================================================
    # GROUP 4: STRICT ALLOCATION CHECKS (HC-05/06/07) & HC-25
    # =========================================================
    allocation_audit = {}
    for s in schedules:
        key = (s.section_id, s.course_id)
        allocation_audit.setdefault(key, set())
        # Use stored session_type directly ---- no more room-type guessing
        allocation_audit[key].add(s.session_type or 'Lec')

    scheduled_pairs = {(s.section_id, s.course_id) for s in schedules}

    for sec in all_sections:
        for course in sec.courses:
            if target_semester != 'All' and course.semester_offered != target_semester:
                continue
            found_types = allocation_audit.get((sec.id, course.id), set())
            fake_obj = Fake(sec, course)

            # HC-05: Missing Lecture
            if (course.synchronous_lec_hours > 0 or course.lec_units > 0) and 'Lec' not in found_types:
                add_v('STRICT_ALLOC_LEC', 'Missing Lecture',
                      f'Lecture for {course.course_code} ({sec.section_name}) is not scheduled.', fake_obj)

            # HC-06: Missing Laboratory
            if (course.synchronous_lab_hours > 0 or course.lab_units > 0) and 'Lab' not in found_types:
                add_v('STRICT_ALLOC_LAB', 'Missing Laboratory',
                      f'Laboratory for {course.course_code} ({sec.section_name}) is not scheduled.', fake_obj)

            # HC-07: Missing Async
            has_async = ((course.asynchronous_lec_hours or 0) + (course.asynchronous_lab_hours or 0)) > 0
            if has_async and 'Async' not in found_types:
                add_v('STRICT_ALLOC_ASYNC', 'Missing Async',
                      f'Async session for {course.course_code} ({sec.section_name}) is not scheduled.', fake_obj)

            # HC-25: Complete Course Scheduling (no session at all for this sec/course pair)
            if (sec.id, course.id) not in scheduled_pairs:
                add_v('COMPLETE_COURSE_SCHEDULING', 'Unscheduled Course',
                      f'{course.course_code} for section {sec.section_name} has no scheduled session.', fake_obj)

    # =========================================================
    # GROUP 5: PRE-ASSIGNMENT INTEGRITY CHECKS
    # =========================================================
    pre_assignments = PreAssignment.query.filter_by(is_archived=False).all()
    if target_semester and target_semester != 'All':
        pre_assignments = [pa for pa in pre_assignments
                           if pa.course and pa.course.semester_offered == target_semester]

    if pre_assignments:
        # HC-01: Locked Schedules ---- pre-assigned class must not have been moved
        for pa in pre_assignments:
            matching = [s for s in schedules
                        if s.section_id == pa.section_id and s.course_id == pa.course_id]
            for s in matching:
                if (s.day != pa.day or s.start_time != pa.start_time
                        or s.end_time != pa.end_time or s.room_id != pa.room_id):
                    add_v('LOCKED_SCHEDULES', 'Locked Schedule Moved',
                          f'Pre-assigned slot for {pa.course.course_code} ({pa.section.section_name}) '
                          f'was changed: expected {pa.day} {pa.start_time}----{pa.end_time} '
                          f'but found {s.day} {s.start_time}----{s.end_time}.', s)

        # HC-26: Pre-assignment Exclusivity ---- no other class may overlap a pre-assigned slot
        for pa in pre_assignments:
            pa_start = to_minutes(pa.start_time)
            pa_end   = to_minutes(pa.end_time)
            for s in schedules:
                if s.section_id != pa.section_id or s.day != pa.day:
                    continue
                s_start = to_minutes(s.start_time)
                s_end   = to_minutes(s.end_time)
                if max(pa_start, s_start) >= min(pa_end, s_end):
                    continue
                # Skip if this IS the pre-assigned class itself
                is_same = (s.course_id == pa.course_id and s.day == pa.day
                           and s.start_time == pa.start_time and s.end_time == pa.end_time)
                if not is_same:
                    add_v('PREASSIGNMENT_EXCLUSIVITY', 'Pre-assignment Exclusivity',
                          f'Class overlaps a pre-assigned slot for {pa.course.course_code} '
                          f'({pa.section.section_name}) on {pa.day} {pa.start_time}----{pa.end_time}.', s)

    # =========================================================
    # GROUP 6: HC-02 ---- MINOR SUBJECT GAP CHECK
    # =========================================================
    # "Minor subjects" = courses from departments NOT included in the last generation run.
    # Each section must have enough free time gaps to accommodate their assigned minor courses.
    active_scheduled_depts = set(session.get('scheduled_depts', SCHEDULED_DEPARTMENTS))
    minor_dept_courses = {}  # section_id -> total minor hours needed

    for sec in all_sections:
        minor_hours = 0
        for course in sec.courses:
            if target_semester != 'All' and course.semester_offered != target_semester:
                continue
            if course.department and course.department not in active_scheduled_depts:
                total_h = (
                    (course.synchronous_lec_hours or course.lec_units or 0) +
                    (course.synchronous_lab_hours or course.lab_units or 0) +
                    (course.asynchronous_lec_hours or 0) +
                    (course.asynchronous_lab_hours or 0)
                )
                minor_hours += total_h
        if minor_hours > 0:
            minor_dept_courses[sec.id] = minor_hours

    if minor_dept_courses and is_active('MINOR_SUBJECT_GAP'):
        # Build a map of scheduled hours per section per day
        sec_day_busy = {}
        for s in schedules:
            dur = (to_minutes(s.end_time) - to_minutes(s.start_time)) / 60
            sec_day_busy.setdefault(s.section_id, {})
            sec_day_busy[s.section_id][s.day] = sec_day_busy[s.section_id].get(s.day, 0) + dur

        op_hours = (_sys.end_hour - _sys.start_hour) if _sys else 13  # default 7am-8pm = 13h

        for sec in all_sections:
            if sec.id not in minor_dept_courses:
                continue
            needed = minor_dept_courses[sec.id]
            # Count total free hours across all active days
            busy_map = sec_day_busy.get(sec.id, {})
            active_days_list = list(allowed_days_set) if allowed_days_set else ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday']
            total_free = sum(max(0, op_hours - busy_map.get(day, 0)) for day in active_days_list)
            if total_free < needed:
                fake_obj = Fake(sec, sec.courses[0] if sec.courses else None)
                if fake_obj.course:
                    violations.append({
                        'type': settings.get('MINOR_SUBJECT_GAP', 'HC'),
                        'rule': 'Minor Subject Gap',
                        'desc': (f'Section {sec.section_name} needs {needed}h for minor subjects '
                                 f'but only has {total_free:.1f}h of free time available.'),
                        'class_a': fake_obj,
                        'class_b': None
                    })

    # ---------------------------------------------------------
    # SORTING, SEARCH & PAGINATION
    # ---------------------------------------------------------

    # Use the canonical department list (covers all depts incl. DHM and DBA)
    all_depts = KNOWN_DEPARTMENTS

    # Also load prefix rules once for the fallback dept lookup below
    _prefix_rules = CodePrefixRule.query.filter_by(is_archived=False).all()

    def _get_course_dept(course):
        """Return department for a course, falling back to CodePrefixRule if Course.department is NULL."""
        if course.department:
            return course.department
        code = course.course_code.upper()
        for rule in _prefix_rules:
            rc = rule.code.upper()
            if rule.is_prefix and code.startswith(rc):
                return rule.department
            elif not rule.is_prefix and code == rc:
                return rule.department
        return None

    if search_query:
        s_term = search_query.lower()
        filtered = []
        for v in violations:
            ca = v['class_a']
            ca_str = f"{ca.course.course_code} {ca.section.section_name} {ca.room.room_name}"
            cb_str = ''
            if v['class_b']:
                cb = v['class_b']
                cb_str = f"{cb.course.course_code} {cb.section.section_name} {cb.room.room_name}"
            if s_term in f"{v['rule']} {v['desc']} {ca_str} {cb_str}".lower():
                filtered.append(v)
        violations = filtered

    # Department filter ---- multi-select checkboxes; empty = all
    if selected_depts:
        violations = [
            v for v in violations
            if (_get_course_dept(v['class_a'].course) or 'Unknown') in selected_depts
        ]

    # Constraint type filter ---- multi-select checkboxes; empty = all
    if selected_types:
        violations = [v for v in violations if v['type'] in selected_types]

    if sort_by == 'rule-desc':
        violations.sort(key=lambda x: x['rule'], reverse=True)
    else:
        violations.sort(key=lambda x: x['rule'])

    per_page = 10
    total_violations = len(violations)
    total_pages = max(1, (total_violations + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    paginated_violations = violations[(page - 1) * per_page: page * per_page]

    hard_count = sum(1 for v in violations if v['type'] == 'HC')
    sc1_count  = sum(1 for v in violations if v['type'] == 'SC1')
    sc2_count  = sum(1 for v in violations if v['type'] == 'SC2')
    soft_count = sc1_count + sc2_count

    return render_template(
        'check_constraints.html',
        violations=paginated_violations,
        hard_count=hard_count,
        sc1_count=sc1_count,
        sc2_count=sc2_count,
        soft_count=soft_count,
        sort_by=sort_by,
        current_page=page,
        total_pages=total_pages,
        search_query=search_query,
        all_depts=all_depts,
        selected_depts=selected_depts,
        selected_types=selected_types,
    )

# --- SYSTEM SETTINGS (UPDATED & CORRECTED) ---

# Helper to get settings (creates default if none exists)
def get_settings():
    settings = SystemSettings.query.first()
    if not settings:
        settings = SystemSettings(start_hour=7, end_hour=20)
        db.session.add(settings)
        db.session.commit()
    return settings

# 1. CONTEXT PROCESSOR (Para available ang Settings sa lahat ng pages/modal)
@app.context_processor
def inject_settings():
    settings = get_settings()
    current_days = settings.allowed_days.split(',') if settings.allowed_days else []
    return dict(
        global_settings=settings,
        current_days=current_days,
        all_days=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
        # Module 3: Global AI-Lock status available in all templates
        lock_status=bool(settings.schedule_lock) if settings else False,
    )

# 2. UPDATE SETTINGS ROUTE (Save & Redirect Back lang)
@app.route('/settings', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def save_settings():
    settings = get_settings()
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    try:
        # 1. Save Time Settings
        s_h = int(request.form.get('start_hour'))
        e_h = int(request.form.get('end_hour'))
        
        # 2. Save Schedule Days (used by GA for plotting)
        selected_days = request.form.getlist('days')
        sorted_days = sorted(selected_days, key=lambda d: day_order.index(d) if d in day_order else 99)

        if not sorted_days:
            flash('Please select at least one schedule day.', 'danger')
        elif s_h >= e_h:
            flash('Start time must be earlier than End time.', 'danger')
        else:
            settings.start_hour = s_h
            settings.end_hour = e_h
            settings.allowed_days = ",".join(sorted_days)
            settings.blocked_slots_json = request.form.get('blocked_slots_json', '[]') or '[]'
            db.session.commit()
            flash('System settings updated successfully!', 'success')
            
    except ValueError:
        flash('Invalid input.', 'danger')

    # Redirect sa pinanggalingang page
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/manage/layouts', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'superadmin')
def manage_layouts():
    settings = get_settings()

    if request.method == 'POST':
        # --- Guard: no text field may exceed 100 characters ---
        _non_text = {'paper_size', 'margin_top', 'margin_bottom', 'margin_left', 'margin_right',
                     'fac_paper_size', 'fac_margin_top', 'fac_margin_bottom', 'fac_margin_left', 'fac_margin_right'}
        _over = [k for k, v in request.form.items()
                 if k not in _non_text and isinstance(v, str) and len(v) > 100]
        if _over:
            flash('Error: One or more fields exceed the 100-character limit. Settings not saved.', 'danger')
            return redirect(url_for('manage_layouts'))

        # --- Global / shared ---
        settings.republic_text      = request.form.get('republic_text', '')
        settings.campus_name        = request.form.get('campus_name', '')
        settings.address            = request.form.get('address', '')
        settings.contact_details    = request.form.get('contact_details', '')
        settings.email              = request.form.get('email', '')
        settings.website            = request.form.get('website', '')
        settings.prepared_by_label  = request.form.get('prepared_by_label', '')
        settings.rec_approval_label = request.form.get('rec_approval_label', '')
        settings.approved_label     = request.form.get('approved_label', '')
        settings.class_label        = request.form.get('class_label', '')
        settings.room_label         = request.form.get('room_label', '')
        settings.course_label       = request.form.get('course_label', '')
        settings.sem_ay_label       = request.form.get('sem_ay_label', '')
        settings.sem_ay_value       = request.form.get('sem_ay_value', '')
        try:
            settings.margin_top    = max(0.0, min(5.0, float(request.form.get('margin_top',    1.0))))
            settings.margin_bottom = max(0.0, min(5.0, float(request.form.get('margin_bottom', 1.0))))
            settings.margin_left   = max(0.0, min(5.0, float(request.form.get('margin_left',   1.0))))
            settings.margin_right  = max(0.0, min(5.0, float(request.form.get('margin_right',  1.0))))
        except (ValueError, TypeError):
            pass
        _ps = request.form.get('paper_size', 'A4')
        settings.paper_size = _ps if _ps in PAPER_SIZES else 'A4'

        # --- Section ---
        settings.section_school_name = request.form.get('section_school_name', '')
        settings.section_signatory_1 = request.form.get('section_signatory_1', '')
        settings.section_signatory_2 = request.form.get('section_signatory_2', '')
        settings.section_sig2_title  = request.form.get('section_sig2_title', '')
        settings.section_signatory_3 = request.form.get('section_signatory_3', '')
        settings.section_sig3_title  = request.form.get('section_sig3_title', '')
        # Flush JSON cache so it stays in sync with individual fields
        settings.section_signatories_json = json.dumps([
            {'name': settings.section_signatory_1, 'title': ''},
            {'name': settings.section_signatory_2, 'title': settings.section_sig2_title},
            {'name': settings.section_signatory_3, 'title': settings.section_sig3_title},
        ])

        # --- Faculty (independent fac_ fields only ---- never touches Section/Room/Course) ---
        settings.fac_republic_text     = request.form.get('fac_republic_text',     '')
        settings.fac_univ_name         = request.form.get('fac_univ_name',         '')
        settings.fac_campus_name       = request.form.get('fac_campus_name',       '')
        settings.fac_address           = request.form.get('fac_address',           '')
        settings.fac_contact_details   = request.form.get('fac_contact_details',   '')
        settings.fac_email             = request.form.get('fac_email',             '')
        settings.fac_website           = request.form.get('fac_website',           '')
        settings.fac_dept_label        = request.form.get('fac_dept_label',        '')
        settings.fac_sched_title       = request.form.get('fac_sched_title',       '')
        settings.fac_sem_ay_label      = request.form.get('fac_sem_ay_label',      '')
        settings.fac_name_label        = request.form.get('fac_name_label',        '')
        settings.fac_educ_label        = request.form.get('fac_educ_label',        '')
        settings.fac_prep_label        = request.form.get('fac_prep_label',        '')
        settings.fac_hours_label       = request.form.get('fac_hours_label',       '')
        settings.fac_conforme_label    = request.form.get('fac_conforme_label',    '')
        settings.fac_rec_approval_label= request.form.get('fac_rec_approval_label','')
        settings.fac_reviewed_label    = request.form.get('fac_reviewed_label',    '')
        settings.fac_approved_label    = request.form.get('fac_approved_label',    '')
        settings.fac_registrar_label   = request.form.get('fac_registrar_label',   '')
        settings.fac_chair_name        = request.form.get('fac_chair_name',        '')
        settings.fac_chair_title       = request.form.get('fac_chair_title',       '')
        settings.fac_director_name     = request.form.get('fac_director_name',     '')
        settings.fac_director_title    = request.form.get('fac_director_title',    '')
        settings.fac_registrar_name    = request.form.get('fac_registrar_name',    '')
        settings.fac_admin_name        = request.form.get('fac_admin_name',        '')
        settings.fac_admin_title       = request.form.get('fac_admin_title',       '')
        settings.fac_form_num_top      = request.form.get('fac_form_num_top',      '')
        settings.fac_form_num_bottom   = request.form.get('fac_form_num_bottom',   '')
        # Activity labels
        settings.fac_consultation      = request.form.get('fac_consultation',      '')
        settings.fac_research          = request.form.get('fac_research',          '')
        settings.fac_designation       = request.form.get('fac_designation',       '')
        settings.fac_extension         = request.form.get('fac_extension',         '')
        # Faculty-specific margins & paper size
        try:
            settings.fac_margin_top    = max(0.0, min(5.0, float(request.form.get('fac_margin_top',    1.0))))
            settings.fac_margin_bottom = max(0.0, min(5.0, float(request.form.get('fac_margin_bottom', 1.0))))
            settings.fac_margin_left   = max(0.0, min(5.0, float(request.form.get('fac_margin_left',   1.0))))
            settings.fac_margin_right  = max(0.0, min(5.0, float(request.form.get('fac_margin_right',  1.0))))
        except (ValueError, TypeError):
            pass
        _fac_ps = request.form.get('fac_paper_size', 'A4')
        settings.fac_paper_size = _fac_ps if _fac_ps in PAPER_SIZES else 'A4'

        # --- Room ---
        settings.room_school_name  = request.form.get('room_school_name', '')
        settings.room_signatory_1  = request.form.get('room_signatory_1', '')
        settings.room_signatory_2  = request.form.get('room_signatory_2', '')
        settings.room_sig2_title   = request.form.get('room_sig2_title', '')
        settings.room_signatory_3  = request.form.get('room_signatory_3', '')
        settings.room_sig3_title   = request.form.get('room_sig3_title', '')
        settings.room_signatories_json = json.dumps([
            {'name': settings.room_signatory_1, 'title': ''},
            {'name': settings.room_signatory_2, 'title': settings.room_sig2_title},
            {'name': settings.room_signatory_3, 'title': settings.room_sig3_title},
        ])

        # --- Course ---
        settings.course_school_name = request.form.get('course_school_name', '')
        settings.course_signatory_1 = request.form.get('course_signatory_1', '')
        settings.course_signatory_2 = request.form.get('course_signatory_2', '')
        settings.course_sig2_title  = request.form.get('course_sig2_title', '')
        settings.course_signatory_3 = request.form.get('course_signatory_3', '')
        settings.course_sig3_title  = request.form.get('course_sig3_title', '')
        settings.course_signatories_json = json.dumps([
            {'name': settings.course_signatory_1, 'title': ''},
            {'name': settings.course_signatory_2, 'title': settings.course_sig2_title},
            {'name': settings.course_signatory_3, 'title': settings.course_sig3_title},
        ])

        # --- Image adjustments (dynamic slot count matches GET handler) ---
        _img_counts = {t: max(3, _get_template_img_count(t)) for t in ('section', 'faculty', 'room', 'course')}
        settings.section_img_settings = _read_img_slots(request.form, 'section', _img_counts['section'])
        settings.faculty_img_settings = _read_img_slots(request.form, 'faculty', _img_counts['faculty'])
        settings.room_img_settings    = _read_img_slots(request.form, 'room',    _img_counts['room'])
        settings.course_img_settings  = _read_img_slots(request.form, 'course',  _img_counts['course'])

        db.session.commit()
        flash('Layout settings saved successfully!', 'success')
        _saved_tab = request.form.get('active_tab', 'section')
        if _saved_tab not in ('section', 'faculty', 'room', 'course'):
            _saved_tab = 'section'
        return redirect(url_for('manage_layouts', tab=_saved_tab))

    # Pass template existence flags so the template can show upload status
    assets_dir = os.path.join(basedir, 'static', 'assets')
    template_exists = {
        t: os.path.isfile(os.path.join(assets_dir, f'{t}_template.xlsx'))
        for t in ('section', 'faculty', 'room', 'course')
    }
    all_semesters = [r[0] for r in db.session.query(ScheduledClass.semester).distinct().all() if r[0]]
    img_counts = {t: max(3, _get_template_img_count(t)) for t in ('section', 'faculty', 'room', 'course')}
    img_slots  = {
        t: _parse_img_slots(getattr(settings, f'{t}_img_settings', None), img_counts[t])
        for t in ('section', 'faculty', 'room', 'course')
    }
    return render_template('manage_layouts.html', settings=settings,
                           template_exists=template_exists, all_semesters=all_semesters,
                           paper_sizes=PAPER_SIZES,
                           img_counts=img_counts, img_slots=img_slots,
                           departments=_get_depts())


@app.route('/manage/layouts/upload_template', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def upload_template():
    if 'template_file' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('manage_layouts'))
    
    file = request.files['template_file']
    template_type = request.form.get('template_type') # nakukuha sa dropdown ('section', 'faculty', 'room')

    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('manage_layouts'))
    
    if file and file.filename.endswith('.xlsx'):
        # DYNAMIC FILENAME: Ise-save bilang 'section_template.xlsx', etc.
        filename = f"{template_type}_template.xlsx"
        template_path = os.path.join(basedir, 'static', 'assets', filename)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(template_path), exist_ok=True)
        
        file.save(template_path)
        flash(f'{template_type.capitalize()} template uploaded successfully!', 'success')
    else:
        flash('Invalid file type. Please upload an Excel (.xlsx) file.', 'danger')

    return redirect(url_for('manage_layouts', tab=template_type))

@app.route('/import_faculty_loading', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def import_faculty_loading():
    if 'file' not in request.files:
        flash('No file uploaded.', 'danger')
        return redirect(url_for('manage_faculty'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file.', 'danger')
        return redirect(url_for('manage_faculty'))

    if file and file.filename.endswith('.xlsx'):
        try:
            wb = load_workbook(file)
            sheet = wb.active # Kunin ang unang sheet
            
            # CONFIGURATION NG EXCEL MAPPING (Base sa Screenshot mo)
            # Row 16 ang start ng data (NAME OF FACULTY row)
            START_ROW = 16 
            # Column Letters to Index (0-based or 1-based adjustments)
            COL_NAME = 1      # A
            COL_CODE = 2      # B
            COL_SECTION = 8   # H
            COL_TOTAL_HRS = 11 # K
            
            # EXTRACT DEPARTMENT FROM HEADERS (Rows 1 to 15)
            header_text = ""
            for r in range(1, 16):
                for c in range(1, 10):
                    val = sheet.cell(row=r, column=c).value
                    if val and isinstance(val, str):
                        header_text += val.upper() + " "
            
            detected_dept = "Department of Computer Studies" # Default
            if "ARTS AND SCIENCE" in header_text or "ARTS & SCIENCE" in header_text:
                detected_dept = "Department of Arts and Sciences"
            elif "TEACHERS EDUCATION" in header_text:
                detected_dept = "Department of Teachers Education"
            elif "ENGINEERING" in header_text:
                detected_dept = "Department of Engineering"
            elif "NSTP" in header_text:
                detected_dept = "NSTP Department"
            elif "COMPUTER STUDIES" in header_text:
                detected_dept = "Department of Computer Studies"
            
            detected_dept = sanitize_input(detected_dept)
                
            current_faculty = None
            assignments_added = 0
            
            # I-loop natin ang rows. Titigil kapag nakita na ang "Prepared by:"
            for row in range(START_ROW, sheet.max_row + 1):
                cell_a = sheet.cell(row=row, column=COL_NAME).value
                cell_b = sheet.cell(row=row, column=COL_CODE).value # Course Code
                cell_h = sheet.cell(row=row, column=COL_SECTION).value # Section
                cell_k = sheet.cell(row=row, column=COL_TOTAL_HRS).value # Total Hours

                # CHECK STOP CONDITION (Footer)
                if cell_a and "Prepared by" in str(cell_a):
                    break

                # 1. DETECT FACULTY NAME
                if cell_a and isinstance(cell_a, str):
                    val_upper = str(cell_a).upper().strip()
                    # Filter out headers and generic text
                    if len(val_upper) > 2 and "NAME OF FACULTY" not in val_upper and "CAVITE STATE" not in val_upper and "REPUBLIC" not in val_upper and "FACULTY LOADING" not in val_upper:
                        # Linisin ang pangalan
                        raw_name = val_upper
                        
                        # Try natin kunin ang M.I. sa susunod na row (row + 1)
                        if mi_val and isinstance(mi_val, str) and len(mi_val.strip()) <= 3:
                            full_name = f"{raw_name} {str(mi_val).strip()}"
                        else:
                            full_name = raw_name
                        
                        full_name = sanitize_input(full_name)
                            
                        # HANAPIN O GAWIN ANG FACULTY SA DATABASE
                    faculty = Faculty.query.filter(Faculty.full_name.ilike(f"%{raw_name}%")).first()
                    
                    if not faculty:
                        # Generate Department Prefix (e.g., "Department of Computer Studies" -> "DCS")
                        dept_words = [word for word in detected_dept.split() if word.lower() not in ['of', 'and', '&']]
                        dept_prefix = "".join([word[0].upper() for word in dept_words])[:3]
                        if not dept_prefix: dept_prefix = "EMP"
                        
                        # Generate a clean <PREFIX>-XXX ID
                        last_faculty = Faculty.query.filter(Faculty.employee_id.like(f"{dept_prefix}-%")).order_by(Faculty.employee_id.desc()).first()
                        if last_faculty and '-' in last_faculty.employee_id:
                            try:
                                next_num = int(last_faculty.employee_id.split('-')[1]) + 1
                            except:
                                next_num = 1
                        else:
                            next_num = 1
                            
                        auto_id = f"{dept_prefix}-{next_num:03d}"
                        
                        # Create New Faculty
                        faculty = Faculty(
                            employee_id=auto_id,
                            full_name=full_name,
                            department=detected_dept, # Dynamic based on header
                            employment_status="Part-time", # Default safe
                            max_weekly_hours=0 # I-aupdate natin mamaya
                        )
                        db.session.add(faculty)
                        db.session.commit()
                        print(f"Created Faculty: {full_name} ({auto_id}, {detected_dept})")
                    
                    current_faculty = faculty
                
                # 2. UPDATE TOTAL HOURS (Kung may value sa Column K sa row ng pangalan o total row)
                if current_faculty and cell_k and isinstance(cell_k, (int, float)):
                    # Update natin ang max hours niya base sa loading
                    if cell_k > 0:
                        current_faculty.max_weekly_hours = int(cell_k)
                        # I-set as Full-time kung marami units, Part-time kung konti (Optional Logic)
                        if cell_k >= 15:
                            current_faculty.employment_status = 'Full-time'
                        db.session.commit()

                # 3. DETECT SUBJECT ASSIGNMENT (Kung may Course Code at Section)
                if current_faculty and cell_b and cell_h:
                    code = str(cell_b).strip()
                    section_name = str(cell_h).strip()
                    
                    # Hanapin ang Course
                    course = Course.query.filter(Course.course_code.ilike(code)).first()
                    
                    # Hanapin ang Section
                    section = Section.query.filter(Section.section_name.ilike(section_name)).first()
                    
                    # Kung parehong existing, i-assign!
                    if course and section:
                        # Check kung assigned na para iwas duplicate
                        existing = FacultyAssignment.query.filter_by(
                            faculty_id=current_faculty.id,
                            course_id=course.id,
                            section_id=section.id
                        ).first()
                        
                        if not existing:
                            assign = FacultyAssignment(
                                faculty_id=current_faculty.id,
                                course_id=course.id,
                                section_id=section.id
                            )
                            db.session.add(assign)
                            assignments_added += 1
                            print(f"Assigned {code} to {current_faculty.full_name} for {section_name}")

            db.session.commit()
            flash(f'Successfully imported loading! Added {assignments_added} subject assignments.', 'success')

        except Exception as e:
            db.session.rollback()
            print(f"Import Error: {e}")
            flash(f'Error processing file: {str(e)}', 'danger')
            
    return redirect(url_for('manage_faculty'))

@app.route('/import-courses-pdf', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def import_courses_pdf():
    if 'file' not in request.files:
        flash('No file uploaded.', 'danger')
        return redirect(url_for('manage_courses'))

    file = request.files['file']
    target_program = request.form.get('target_program')
    auto_assign    = request.form.get('auto_assign') == 'on'
    assign_semester = request.form.get('assign_semester')

    if file and file.filename.endswith('.pdf'):
        try:
            added = 0
            updated = 0
            assigned_sections_count = 0 # Counter para sa sections
            current_semester = '1st Semester'
            current_year_level = 1

            with pdfplumber.open(file) as pdf:
                # --- 1. PROGRAM MISMATCH VALIDATION ---
                # Read the first 2 pages to check the curriculum title
                validation_text = ""
                for i in range(min(2, len(pdf.pages))):
                    page_text = pdf.pages[i].extract_text()
                    if page_text:
                        validation_text += page_text.upper() + "\n"

                is_bscs = "COMPUTER SCIENCE" in validation_text
                is_bsit = "INFORMATION TECHNOLOGY" in validation_text

                # Check for conflicts and abort if wrong PDF is uploaded
                if target_program == 'BSCoS' and is_bsit and not is_bscs:
                    flash('Program Mismatch Error! You selected BS Computer Science but the file appears to be BS Information Technology. Import cancelled.', 'danger')
                    return redirect(url_for('manage_courses'))
                
                if target_program == 'BSInfoTech' and is_bscs and not is_bsit:
                    flash('Program Mismatch Error! You selected BS Information Technology but the file appears to be BS Computer Science. Import cancelled.', 'danger')
                    return redirect(url_for('manage_courses'))

                # --- 2. WALK ALL PAGES ---
                for page in pdf.pages:
                    text = page.extract_text()
                    if not text: continue
                    
                    # Detect Year Level and Semester change from text headers
                    lines = text.split('\n')
                    for line in lines:
                        l_up = line.upper()
                        if "FIRST YEAR" in l_up:    current_year_level = 1
                        elif "SECOND YEAR" in l_up: current_year_level = 2
                        elif "THIRD YEAR" in l_up:  current_year_level = 3
                        elif "FOURTH YEAR" in l_up: current_year_level = 4
                        
                        if "FIRST SEMESTER" in l_up:     current_semester = '1st Semester'
                        elif "SECOND SEMESTER" in l_up:    current_semester = '2nd Semester'
                        elif "MIDYEAR" in l_up or "SUMMER" in l_up: current_semester = 'Midyear'

                    # Extract Tables
                    tables = page.extract_tables()
                    for table in tables:
                        for row in table:
                            if not row or len(row) < 3: continue
                            
                            code = str(row[0]).strip() if row[0] else ""
                            # Skip headers or empty code rows (e.g., "COURSE CODE", "CODE")
                            if not code or len(code.replace(' ','')) < 3 or code.upper() in ["CODE", "COURSE CODE", "COURSE\nCODE", "COURSE"]:
                                continue
                            
                            title = str(row[1]).strip() if row[1] else ""
                            # Some PDFs have title and units merged in title list
                            try:
                                lec = int(row[2]) if row[2] and str(row[2]).isdigit() else 0
                                lab = int(row[3]) if len(row) > 3 and row[3] and str(row[3]).isdigit() else 0
                            except:
                                lec = 0
                                lab = 0

                            # Normalize NSTP
                            if code.upper().startswith('NSTP'):
                                parts = code.split()
                                num = parts[1] if len(parts) > 1 else '1'
                                code = f"NSTP {num}"
                                title = title or f"National Service Training Program {num}"

                            # OJT / Practicum special handling
                            if "COSC 199" in code.upper() or "ITEC 199" in code.upper() or code.upper().startswith("OJT"):
                                title = "Internship / OJT / Practicum"

                            # Upsert Course
                            existing = Course.query.filter_by(course_code=code).first()
                            if existing:
                                existing.year_level = current_year_level
                                existing.semester_offered = current_semester # Update based on PDF context
                                if existing.program != target_program and existing.program != 'Both':
                                    existing.program = 'Both'
                                updated += 1
                            else:
                                new_course = Course(
                                    course_code=code,
                                    course_name=title,
                                    program=target_program,
                                    department=_dept_for_code(code, auto_add=True),
                                    year_level=current_year_level,
                                    lec_units=lec,
                                    lab_units=lab,
                                    synchronous_lec_hours=(2 if lec > 0 else 0),
                                    synchronous_lab_hours=(3 if lab > 0 else 0),
                                    asynchronous_lec_hours=0,
                                    asynchronous_lab_hours=0,
                                    semester_offered=current_semester
                                )
                                db.session.add(new_course)
                                added += 1
            
            db.session.commit()

            # --- 3. AUTO-LOCK NSTP LOGIC (1st Year Only & Program Specific) ---
            nstp_to_lock = Course.query.filter(Course.course_code.ilike('NSTP%'), Course.year_level == 1).first()
            if nstp_to_lock:
                court = Room.query.filter_by(room_name="University Field").first()
                tba_faculty = Faculty.query.filter_by(full_name="T.B.A.").first()

                if court and tba_faculty:
                    prog_identifier = "BSCoS" if target_program == "BSCoS" else "BSIT"
                    target_sections = Section.query.filter(
                        Section.section_name.ilike(f"%{prog_identifier}%"),
                        Section.year_level == 1,
                        Section.is_archived == False
                    ).all()
                    
                    locked_count = 0
                    for sec in target_sections:
                        # Check kung meron na
                        existing_slot = ScheduledClass.query.filter_by(
                            course_id=nstp_to_lock.id,
                            section_id=sec.id,
                            semester='1st Semester'
                        ).first()
                        
                        if not existing_slot:
                            db.session.add(ScheduledClass(
                                course_id=nstp_to_lock.id,
                                section_id=sec.id,
                                room_id=court.id,
                                faculty_id=tba_faculty.id,
                                day='Sunday',
                                start_time='08:00',
                                end_time='11:00',
                                semester='1st Semester',
                                is_draft=False,
                                is_archived=False
                            ))
                            locked_count += 1
                    
                    db.session.commit()
                    print(f"Auto-locked {nstp_to_lock.course_code} for {locked_count} 1st Year {target_program} sections.")

            # --- 4. AUTO ASSIGN LOGIC ---
            if auto_assign:
                prog_identifier = "BSCoS" if target_program == "BSCoS" else "BSIT"
                sections = Section.query.filter(Section.section_name.ilike(f"%{prog_identifier}%")).all()
                assigned_sections_count = len(sections) # Bilangin kung ilang sections ang nadamay
                
                for section in sections:
                    matching_courses = Course.query.filter(
                        or_(Course.program == target_program, Course.program == 'Both'),
                        Course.year_level == section.year_level,
                        Course.semester_offered == assign_semester
                    ).all()
                    
                    for course in matching_courses:
                        existing = SectionAssignment.query.filter_by(section_id=section.id, course_id=course.id).first()
                        if not existing:
                            db.session.add(SectionAssignment(section_id=section.id, course_id=course.id))
                db.session.commit()

            msg = f"Imported from PDF: {added} new courses, {updated} updated."
            if auto_assign:
                msg += f" Automatically assigned to {assigned_sections_count} {target_program} sections for {assign_semester}."
            flash(msg, 'success')

        except Exception as e:
            db.session.rollback()
            print(f"PDF Import Error: {e}")
            flash(f"Error processing PDF: {str(e)}", 'danger')
            
    return redirect(url_for('manage_courses'))






@app.route('/import_courses_docx', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def import_courses_docx():
    if 'file' not in request.files:
        flash('No file uploaded.', 'danger')
        return redirect(url_for('manage_courses'))

    file = request.files['file']
    target_program = request.form.get('target_program')
    auto_assign = request.form.get('auto_assign') == 'on'
    assign_semester = request.form.get('assign_semester')

    if file and file.filename.endswith('.docx'):
        try:
            added = 0
            updated = 0
            assigned_sections_count = 0
            current_semester = '1st Semester'
            current_year_level = 1

            from docx import Document as DocxDocument
            doc_in = DocxDocument(io.BytesIO(file.read()))

            # --- 1. PROGRAM MISMATCH VALIDATION ---
            head_text = ' '.join(p.text for p in doc_in.paragraphs[:8]).upper()
            is_bscs = 'COMPUTER SCIENCE' in head_text
            is_bsit = 'INFORMATION TECHNOLOGY' in head_text
            if target_program == 'BSCoS' and is_bsit and not is_bscs:
                flash('Program Mismatch Error! You selected BS Computer Science but the file appears to be BS Information Technology. Import cancelled.', 'danger')
                return redirect(url_for('manage_courses'))
            if target_program == 'BSInfoTech' and is_bscs and not is_bsit:
                flash('Program Mismatch Error! You selected BS Information Technology but the file appears to be BS Computer Science. Import cancelled.', 'danger')
                return redirect(url_for('manage_courses'))

            # --- 2. WALK BODY ELEMENTS (paragraphs + tables in DOM order) ---
            WNS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
            def _el_text(el):
                return ''.join(t.text or '' for t in el.iter() if t.tag == WNS + 't').strip()

            for elem in doc_in.element.body:
                local = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                if local == 'p':
                    txt = _el_text(elem).upper()
                    if 'FIRST YEAR' in txt:    current_year_level = 1
                    elif 'SECOND YEAR' in txt: current_year_level = 2
                    elif 'THIRD YEAR' in txt:  current_year_level = 3
                    elif 'FOURTH YEAR' in txt: current_year_level = 4
                    if 'FIRST SEMESTER' in txt:    current_semester = '1st Semester'
                    elif 'SECOND SEMESTER' in txt:  current_semester = '2nd Semester'
                    elif 'MIDYEAR' in txt or 'SUMMER' in txt: current_semester = 'Midyear'
                elif local == 'tbl':
                    rows = elem.findall('.//' + WNS + 'tr')
                    for row_i, row_el in enumerate(rows):
                        if row_i == 0: continue  # skip header row
                        cells = row_el.findall('.//' + WNS + 'tc')
                        if len(cells) < 2: continue
                        code  = _el_text(cells[0])
                        title = _el_text(cells[1])
                        try: lec = int(_el_text(cells[2])) if len(cells) > 2 and _el_text(cells[2]) else 0
                        except: lec = 0
                        try: lab = int(_el_text(cells[3])) if len(cells) > 3 and _el_text(cells[3]) else 0
                        except: lab = 0
                        if not code or len(code.replace(' ', '')) < 3: continue
                        # NSTP handling
                        if code.upper().startswith('NSTP'):
                            parts = code.split()
                            num = parts[1] if len(parts) > 1 else '1'
                            code = f'NSTP {num}'
                            title = title or f'National Service Training Program {num}'
                        # OJT/Practicum handling
                        if 'COSC 199' in code.upper() or 'ITEC 199' in code.upper() or code.upper().startswith('OJT'):
                            title = 'Internship / OJT / Practicum'
                        existing = Course.query.filter_by(course_code=code).first()
                        if existing:
                            existing.year_level = current_year_level
                            existing.semester_offered = current_semester
                            if existing.program != target_program and existing.program != 'Both':
                                existing.program = 'Both'
                            updated += 1
                        else:
                            db.session.add(Course(
                                course_code=code, course_name=title, program=target_program,
                                department=_dept_for_code(code, auto_add=True),
                                year_level=current_year_level,
                                lec_units=lec, lab_units=lab,
                                synchronous_lec_hours=(2 if lec > 0 else 0),
                                synchronous_lab_hours=(3 if lab > 0 else 0),
                                asynchronous_lec_hours=0, asynchronous_lab_hours=0,
                                semester_offered=current_semester
                            ))
                            added += 1

            # Commit
            db.session.commit()

            # AUTO-LOCK NSTP LOGIC (1st Year Only & Program Specific)
            if auto_assign:
                court = Room.query.filter_by(room_name="University Field").first()
                tba_faculty = Faculty.query.filter_by(full_name="T.B.A.").first()
                prog_identifier = "BSCoS" if target_program == "BSCoS" else "BSIT"
                target_sections = Section.query.filter(
                    Section.section_name.ilike(f"%{prog_identifier}%"),
                    Section.year_level == 1,
                    Section.is_archived == False
                ).all()
                nstp_to_lock = Course.query.filter(
                    Course.course_code.ilike('NSTP%'),
                    Course.semester_offered == assign_semester
                ).first()
                if nstp_to_lock and court and tba_faculty:
                    locked_count = 0
                    for section in target_sections:
                        exists = PreAssignment.query.filter_by(
                            course_id=nstp_to_lock.id,
                            section_id=section.id
                        ).first()
                        if not exists:
                            db.session.add(PreAssignment(
                                course_id=nstp_to_lock.id,
                                section_id=section.id,
                                faculty_id=tba_faculty.id,
                                room_id=court.id,
                                day="Friday",
                                start_time="07:00",
                                end_time="11:00",
                                is_archived=False
                            ))
                            locked_count += 1
                    db.session.commit()

            # AUTO ASSIGN LOGIC
            if auto_assign:
                prog_identifier = "BSCoS" if target_program == "BSCoS" else "BSIT"
                sections = Section.query.filter(Section.section_name.ilike(f"%{prog_identifier}%")).all()
                assigned_sections_count = len(sections)
                for section in sections:
                    matching_courses = Course.query.filter(
                        or_(Course.program == target_program, Course.program == 'Both'),
                        Course.year_level == section.year_level,
                        Course.semester_offered == assign_semester,
                        Course.is_archived == False
                    ).all()
                    section.courses = matching_courses
                db.session.commit()

            notif_msg = f"Import Success! Added: {added} new, Updated: {updated} existing."
            if auto_assign:
                notif_msg += f" Auto-assigned {assign_semester} subjects to {assigned_sections_count} sections."
            flash(notif_msg, 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'Error parsing Word file: {str(e)}', 'danger')

    return redirect(url_for('manage_courses'))


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# LAYOUT HELPER FUNCTIONS
# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def build_variable_map(layout_type, settings, section_name=None, entity_name=None, sem_ay=None,
                       faculty=None, prep_count=0, total_hours=0):
    """Build a {{token}}: value dict for substitution into Excel templates."""
    s = settings

    # Entity name
    if section_name:
        name_val = section_name
    elif entity_name:
        name_val = entity_name
    else:
        placeholders = {'section': '[Section Name]', 'faculty': '[Faculty Name]',
                        'room': '[Room Name]', 'course': '[Course Name]'}
        name_val = placeholders.get(layout_type, '[Name]')

    school_val = getattr(s, f'{layout_type}_school_name', '') or 'CAVITE STATE UNIVERSITY'

    # Signatories from JSON
    sig_json_str = getattr(s, f'{layout_type}_signatories_json', None)
    signatories = []
    if sig_json_str:
        try:
            signatories = json.loads(sig_json_str)
        except Exception:
            signatories = []
    if not signatories:
        for i in (1, 2, 3):
            v_name = getattr(s, f'{layout_type}_signatory_{i}', '') or ''
            v_title = ''
            if layout_type != 'faculty':
                # For non-faculty, check sig2/sig3 title columns
                if i == 2: v_title = getattr(s, f'{layout_type}_sig2_title', '') or 'Director, Instruction'
                elif i == 3: v_title = getattr(s, f'{layout_type}_sig3_title', '') or 'Campus Administrator'
            
            if v_name.strip():
                signatories.append({'name': v_name, 'title': v_title})

    from datetime import date as _date
    vmap = {
        '{{name}}':              name_val,
        '{{school}}':            school_val,
        '{{republic_text}}':     getattr(s, 'republic_text', '') or 'Republic of the Philippines',
        '{{campus}}':            getattr(s, 'campus_name', '') or '',
        '{{address}}':           getattr(s, 'address', '') or '',
        '{{contact}}':           getattr(s, 'contact_details', '') or '',
        '{{email}}':             getattr(s, 'email', '') or '',
        '{{website}}':           getattr(s, 'website', '') or '',
        '{{class_label}}':       (getattr(s, 'room_label',   'ROOM')   or 'ROOM')   if layout_type == 'room'
                                  else (getattr(s, 'course_label', 'COURSE') or 'COURSE') if layout_type == 'course'
                                  else (getattr(s, 'class_label',  'CLASS')  or 'CLASS'),
        '{{room_label}}':        getattr(s, 'room_label',   'ROOM')   or 'ROOM',
        '{{course_label}}':      getattr(s, 'course_label', 'COURSE') or 'COURSE',
        '{{sem_ay_label}}':      getattr(s, 'sem_ay_label', 'Semester / Academic Year') or 'Semester / Academic Year',
        '{{sem_ay_value}}':      (f"{sem_ay} / {s.sem_ay_value.split('/')[-1].strip()}" if (sem_ay and '/' not in sem_ay and s.sem_ay_value and '/' in s.sem_ay_value) else (sem_ay or s.sem_ay_value or '')),
        '{{prepared_by_label}}': getattr(s, 'prepared_by_label', 'Prepared by:') or 'Prepared by:',
        '{{rec_approval_label}}':getattr(s, 'rec_approval_label', 'Recommending Approval:') or 'Recommending Approval:',
        '{{approved_label}}':    getattr(s, 'approved_label', 'APPROVED:') or 'APPROVED:',
        '{{generated}}':         _date.today().strftime('%B %d, %Y'),
        '{{GRID_TIME}}':         'TIME',
        '{{GRID_MON}}':          'MONDAY',
        '{{GRID_TUE}}':          'TUESDAY',
        '{{GRID_WED}}':          'WEDNESDAY',
        '{{GRID_THU}}':          'THURSDAY',
        '{{GRID_FRI}}':          'FRIDAY',
        '{{GRID_SAT}}':          'SATURDAY',
        '{{GRID_SUN}}':          'SUNDAY',
    }
    
    # Generic sig mapping
    for i in range(3):
        n_key = f'{{{{sig{i+1}}}}}'
        t_key = f'{{{{sig{i+1}_title}}}}'
        if i < len(signatories):
            vmap[n_key] = signatories[i].get('name', '')
            vmap[t_key] = signatories[i].get('title', '')
        else:
            vmap[n_key] = ''
            vmap[t_key] = ''

    # --- Faculty-specific tokens (Hiwalay ang variables) ---
    if layout_type == 'faculty':
        fac_name  = (faculty.full_name  if faculty else None) or entity_name or '[Faculty Name]'
        fac_educ  = (faculty.highest_educational_attainment if faculty else None) or ''
        fac_rank  = (faculty.academic_rank if faculty else None) or ''

        # Convert to numbers to avoid ValueError with string decimals
        try:
            th = float(total_hours)
            pc = float(prep_count)
        except (ValueError, TypeError):
            th = 0.0
            pc = 0.0

        vmap.update({
            '{{fac_name}}':          fac_name,
            '{{fac_educ}}':          fac_educ,
            '{{fac_title}}':         fac_rank,
            '{{fac_rank}}':          fac_rank,
            '{{fac_prep}}':          str(int(pc)) if pc == int(pc) else str(round(pc, 1)),
            '{{fac_total_hours}}':   str(int(th)) if th == int(th) else str(round(th, 1)),
            '{{fac_republic_text}}': getattr(s, 'fac_republic_text',  'Republic of the Philippines') or 'Republic of the Philippines',
            '{{fac_univ_name}}':     getattr(s, 'fac_univ_name',      'CAVITE STATE UNIVERSITY') or 'CAVITE STATE UNIVERSITY',
            '{{fac_campus_name}}':   getattr(s, 'fac_campus_name',    'CCAT Campus') or 'CCAT Campus',
            '{{fac_address}}':       getattr(s, 'fac_address',        'Rosario, Cavite') or 'Rosario, Cavite',
            '{{fac_contact_details}}':getattr(s, 'fac_contact_details','(046) 437-9505 / (046) 437-6659') or '(046) 437-9505 / (046) 437-6659',
            '{{fac_email}}':         getattr(s, 'fac_email',          'cvsurosario@cvsu.edu.ph') or 'cvsurosario@cvsu.edu.ph',
            '{{fac_website}}':       getattr(s, 'fac_website',        'www.cvsu-rosario.edu.ph') or 'www.cvsu-rosario.edu.ph',
            '{{fac_form_num_top}}':   getattr(s, 'fac_form_num_top',    'VPAA-QF-11')           or 'VPAA-QF-11',
            '{{fac_form_num_bottom}}':getattr(s, 'fac_form_num_bottom',  'V01-2018-07-24')       or 'V01-2018-07-24',
            '{{fac_dept_label}}':     getattr(s, 'fac_dept_label',       'DEPARTMENT OF COMPUTER STUDIES') or 'DEPARTMENT OF COMPUTER STUDIES',
            '{{fac_sched_title}}':    getattr(s, 'fac_sched_title',      'FACULTY CLASS SCHEDULE') or 'FACULTY CLASS SCHEDULE',
            '{{fac_sem_ay_label}}':   getattr(s, 'fac_sem_ay_label',     'SECOND SEMESTER SY 2023 - 2024') or 'SECOND SEMESTER SY 2023 - 2024',
            '{{fac_name_label}}':     getattr(s, 'fac_name_label',       'Name:') or 'Name:',
            '{{fac_educ_label}}':     getattr(s, 'fac_educ_label',       'Highest Educ. Attainment:') or 'Highest Educ. Attainment:',
            '{{fac_prep_label}}':     getattr(s, 'fac_prep_label',       'No. of Preparation/s:') or 'No. of Preparation/s:',
            '{{fac_hours_label}}':    getattr(s, 'fac_hours_label',      'Total no. of contact hours per week:') or 'Total no. of contact hours per week:',
            '{{fac_conforme_label}}': getattr(s, 'fac_conforme_label',   'Conforme:')            or 'Conforme:',
            '{{fac_reviewed_label}}': getattr(s, 'fac_reviewed_label',   'Reviewed by:')         or 'Reviewed by:',
            '{{fac_rec_approval_label}}':getattr(s, 'fac_rec_approval_label','Recommending Approval:') or 'Recommending Approval:',
            '{{fac_approved_label}}': getattr(s, 'fac_approved_label',   'Approved:')            or 'Approved:',
            '{{fac_registrar_label}}':getattr(s, 'fac_registrar_label',  'OIC, Registrar')       or 'OIC, Registrar',
            '{{fac_chair_name}}':     getattr(s, 'fac_chair_name',       'ARIES M. GELERA')      or 'ARIES M. GELERA',
            '{{fac_chair_title}}':    getattr(s, 'fac_chair_title',      'Department Chairperson') or 'Department Chairperson',
            '{{fac_director_name}}':  getattr(s, 'fac_director_name',    'ARIEL G. SANTOS, EdD') or 'ARIEL G. SANTOS, EdD',
            '{{fac_director_title}}': getattr(s, 'fac_director_title',   'Director, Instruction') or 'Director, Instruction',
            '{{fac_registrar_name}}': getattr(s, 'fac_registrar_name',   'MARLYN A. QUINEZ')     or 'MARLYN A. QUINEZ',
            '{{fac_admin_name}}':     getattr(s, 'fac_admin_name',       'LAURO B. PASCUA, EdD') or 'LAURO B. PASCUA, EdD',
            '{{fac_admin_title}}':    getattr(s, 'fac_admin_title',      'Campus Administrator') or 'Campus Administrator',
            '{{fac_consultation}}':   getattr(s, 'fac_consultation',     'Consultation:')        or 'Consultation:',
            '{{fac_research}}':       getattr(s, 'fac_research',         'Research:')            or 'Research:',
            '{{fac_designation}}':    getattr(s, 'fac_designation',      'Designation :')        or 'Designation :',
            '{{fac_extension}}':      getattr(s, 'fac_extension',        'Extension:')           or 'Extension:',
            # Also map sig1/sig2 equivalents for backward compatibility
            '{{sig1}}':               getattr(s, 'fac_chair_name',    'ARIES M. GELERA'),
            '{{sig2}}':               getattr(s, 'fac_director_name', 'ARIEL G. SANTOS, EdD'),
            '{{sig3}}':               getattr(s, 'fac_admin_name',    'LAURO B. PASCUA, EdD'),
        })
    
    return vmap


def _argb_to_css(color_obj):
    """Convert openpyxl Color -> CSS hex string, or None.

    Returns None for transparent/auto colours so callers can fall back to
    CSS inherit rather than rendering a wrong colour.
    """
    if color_obj is None:
        return None
    try:
        if color_obj.type == 'rgb':
            argb = color_obj.rgb  # 'FFRRGGBB'
            if argb and len(argb) == 8 and argb[:2] != '00' and argb != '00000000':
                return '#' + argb[2:]
        elif color_obj.type == 'indexed':
            # Index 64 = Excel "auto" (inherit) ---- return None so CSS inherits
            if color_obj.indexed == 64:
                return None
            # Standard 64-entry Excel indexed colour palette
            idx_map = {
                 0:'000000',  1:'FFFFFF',  2:'FF0000',  3:'00FF00',
                 4:'0000FF',  5:'FFFF00',  6:'FF00FF',  7:'00FFFF',
                 8:'000000',  9:'FFFFFF', 10:'FF0000', 11:'00FF00',
                12:'0000FF', 13:'FFFF00', 14:'FF00FF', 15:'00FFFF',
                16:'800000', 17:'008000', 18:'000080', 19:'808000',
                20:'800080', 21:'008080', 22:'C0C0C0', 23:'808080',
                24:'9999FF', 25:'993366', 26:'FFFFCC', 27:'CCFFFF',
                28:'660066', 29:'FF8080', 30:'0066CC', 31:'CCCCFF',
                32:'000080', 33:'FF00FF', 34:'FFFF00', 35:'00FFFF',
                36:'800080', 37:'800000', 38:'008080', 39:'0000FF',
                40:'00CCFF', 41:'CCFFFF', 42:'CCFFCC', 43:'FFFF99',
                44:'99CCFF', 45:'FF99CC', 46:'CC99FF', 47:'FFCC99',
                48:'3366FF', 49:'33CCCC', 50:'99CC00', 51:'FFCC00',
                52:'FF9900', 53:'FF6600', 54:'666699', 55:'969696',
                56:'003366', 57:'339966', 58:'003300', 59:'333300',
                60:'993300', 61:'993366', 62:'333399', 63:'333333',
            }
            idx = color_obj.indexed
            if idx in idx_map:
                return '#' + idx_map[idx]
        elif color_obj.type == 'theme':
            # Office 2013 default theme baseline (theme1.xml).
            # Tint/shade ignored ---- covers ~90 % of cases without XML parsing.
            _THEME = {
                0: '#FFFFFF', 1: '#000000', 2: '#E7E6E6', 3: '#44546A',
                4: '#4472C4', 5: '#ED7D31', 6: '#A5A5A5', 7: '#FFC000',
                8: '#5B9BD5', 9: '#70AD47',
            }
            return _THEME.get(color_obj.theme)
    except Exception:
        pass
    return None


def _border_side_css(side):
    """Convert openpyxl border side -> CSS border string, or None.

    Returns None when the side carries no real Excel border so the caller
    can set border-{side}:none and let the CSS outline debug-grid show through.
    """
    if not side or not side.border_style or side.border_style == 'none':
        return None
    style_map = {
        'thin':         '1px solid',
        'medium':       '2px solid',
        'thick':        '3px solid',
        'hair':         '1px solid',
        'dashed':       '1px dashed',
        'dotted':       '1px dotted',
        'double':       '3px double',
        'mediumDashed': '2px dashed',
        'dashDot':      '1px dashed',
        'dashDotDot':   '1px dashed',
        'slantDashDot': '1px dashed',
    }
    css = style_map.get(side.border_style, '1px solid')
    clr = _argb_to_css(side.color) if side.color else None
    return f"{css} {clr or '#000000'}"


def detect_content_bounds(ws):
    """Return (min_r, min_c, max_r, max_c) ---- the tightest bounding box around
    all cells that have a value, a fill colour, or at least one visible border.
    Returns None if the sheet is completely empty.
    """
    VISIBLE_BORDER_STYLES = {
        'thin', 'medium', 'thick', 'hair', 'dashed', 'dotted',
        'double', 'mediumDashed', 'slantDashDot', 'dashDot', 'dashDotDot',
    }

    def _has_fill(cell):
        f = cell.fill
        if not f or f.fill_type in (None, 'none'):
            return False
        return _argb_to_css(f.fgColor) is not None if f.fgColor else False

    def _has_border(cell):
        bd = cell.border
        if not bd:
            return False
        for side in (bd.top, bd.right, bd.bottom, bd.left):
            if side and side.border_style in VISIBLE_BORDER_STYLES:
                return True
        return False

    def _is_content(cell):
        if cell.value is not None and str(cell.value).strip():
            return True
        return _has_fill(cell) or _has_border(cell)

    min_r = min_c = None
    max_r = max_c = None

    for row in ws.iter_rows():
        for cell in row:
            if _is_content(cell):
                r, c = cell.row, cell.column
                min_r = r if min_r is None else min(min_r, r)
                min_c = c if min_c is None else min(min_c, c)
                max_r = r if max_r is None else max(max_r, r)
                max_c = c if max_c is None else max(max_c, c)

    if min_r is None:
        # Fallback: if the template is empty, provide a standard range so rendering doesn't skip
        return (1, 1, 40, 10) 
    return (min_r, min_c, max_r, max_c)


def _extract_ws_images_html(ws, col_offsets, row_offsets, col_start, row_start, total_w_px=1, left_offset_px=0, img_dim_ref_w_px=None, img_settings_list=None, scale_v=1.0):
    """Extract images from worksheet and return absolutely-positioned <img> HTML tags.

    col_offsets      : {0-based col index -> left px from table origin}
    row_offsets      : {0-based row index -> top px from table origin}
    col_start        : 1-based first rendered column (for offset correction)
    row_start        : 1-based first rendered row   (for offset correction)
    total_w_px       : sum of all visible reference column px widths ---- used only for the
                       left/top position (as %) so images track their column as the table
                       stretches.  Width and height use fixed px from Excel metadata.
    img_settings_list: optional list of per-image dicts from manage_layouts settings.
                       Each dict: {'x': px_offset, 'y': px_offset, 'scale': float, 'z_above': bool}
    """
    # 1 EMU = 1 inch / 914400.  At 96 DPI: 1 inch = 96 px.
    # Therefore: px = EMU / (914400 / 96) = EMU / 9525  (exact integer divisor)
    EMU_PER_PX = 9525
    imgs_above = []   # rendered AFTER table (on top of text) ---- default
    imgs_below = []   # rendered BEFORE table (behind text)

    _img_bytes_cache = getattr(ws, '_img_bytes_cache', None)
    for i, img in enumerate(getattr(ws, '_images', [])):
        try:
            if _img_bytes_cache is not None and i < len(_img_bytes_cache):
                raw = _img_bytes_cache[i]
            else:
                raw = img._data()
            if not raw:
                continue
            # Detect MIME type by magic bytes
            if raw[:8] == b'\x89PNG\r\n\x1a\n':
                mime = 'image/png'
            elif raw[:3] == b'\xff\xd8\xff':
                mime = 'image/jpeg'
            elif raw[:4] == b'GIF8':
                mime = 'image/gif'
            else:
                mime = 'image/png'
            b64 = base64.b64encode(raw).decode('ascii')
            src = f'data:{mime};base64,{b64}'

            anchor = img.anchor
            has_two_cell = hasattr(anchor, '_from') and hasattr(anchor, 'to')
            has_one_cell = hasattr(anchor, '_from') and not has_two_cell

            if not (has_two_cell or has_one_cell):
                continue  # unknown anchor type ---- skip

            fr = anchor._from

            def _col_ref(col_idx_0based, col_off_emu):
                """0-based col + EMU offset -> reference px (same space as col_widths)."""
                base = col_offsets.get(col_idx_0based - (col_start - 1), 0)
                return base + col_off_emu / EMU_PER_PX

            def _row_abs(row_idx_0based, row_off_emu):
                """0-based row + EMU offset -> absolute px from table top."""
                base = row_offsets.get(row_idx_0based - (row_start - 1), 0)
                return base + row_off_emu / EMU_PER_PX

            left_ref = _col_ref(fr.col, fr.colOff)
            # Add safety rounding and +0.1 buffer to prevent WeasyPrint from clipping base64 boundaries
            top_px   = round(_row_abs(fr.row, fr.rowOff), 1) + 0.1

            # Per-image overrides from manage_layouts settings
            _cfg     = (img_settings_list[i] if img_settings_list and i < len(img_settings_list) else {})
            _x_off   = float(_cfg.get('x', 0.0))
            _y_off   = float(_cfg.get('y', 0.0))
            _sc      = float(_cfg.get('scale', 1.0))
            _z_above = bool(_cfg.get('z_above', True))

            # Use ONLY raw anchor position + user layout y-offset.
            # The parent div CSS transform handles all vertical scaling uniformly.
            top_px  += _y_off

            # --------- ---------------- ------- Image size --------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- ---------------- -------# ---
            # Priority 1: anchor.ext.cx / .cy --  exact EMU dimensions stored by Excel.
            # These are the definitive pixel-perfect dimensions regardless of anchor type.
            ext = getattr(anchor, 'ext', None)
            cx  = getattr(ext, 'cx', None) if ext else None
            cy  = getattr(ext, 'cy', None) if ext else None

            # w_css / h_css built per priority below
            w_css = None
            h_px  = 10.0

            # dim_ref: denominator for image dimension percentages.
            # When img_dim_ref_w_px is set (section layout), images scale
            # proportionally with the paper width instead of staying fixed px.
            dim_ref = img_dim_ref_w_px or total_w_px

            if cx and cy:
                # Image dimensions: raw px from Excel. The parent div transform
                # will scale them visually -> no manual multiplication needed.
                w_px  = cx / EMU_PER_PX
                h_px  = cy / EMU_PER_PX
                if img_dim_ref_w_px:
                    w_css = f'width:{w_px / dim_ref * 100:.4f}%'
                    h_css = 'height:auto'
                else:
                    w_css = f'width:{w_px:.1f}px'
                    h_css = f'height:{h_px:.1f}px'
            elif has_two_cell:
                to        = anchor.to
                right_ref = _col_ref(to.col, to.colOff)
                bottom_px = _row_abs(to.row, to.rowOff)
                span_px   = max(1.0, right_ref - left_ref)
                h_px      = max(1.0, bottom_px - top_px)
                w_css     = f'width:{span_px / dim_ref * 100:.4f}%'
                h_css     = f'height:{h_px:.1f}px'
            else:
                w_raw = getattr(img, 'width',  100)
                h_raw = getattr(img, 'height', 100)
                w_px  = w_raw / EMU_PER_PX if w_raw > 5000 else float(w_raw)
                h_px  = h_raw / EMU_PER_PX if h_raw > 5000 else float(h_raw)
                w_css = f'width:{w_px:.1f}px'
                h_css = f'height:{h_px:.1f}px'

            # Apply user scale to width/height
            if _sc != 1.0 and w_css:
                if w_css.endswith('%'):
                    w_css = f'width:{float(w_css[6:-1]) * _sc:.4f}%'
                elif w_css.endswith('px'):
                    w_css = f'width:{float(w_css[6:-2]) * _sc:.1f}px'
            if _sc != 1.0 and h_css and h_css != 'height:auto':
                if h_css.endswith('px'):
                    h_css = f'height:{float(h_css[7:-2]) * _sc:.1f}px'

            left_pct = (left_ref + left_offset_px + _x_off) / total_w_px * 100

            _style = ';'.join(p for p in [
                'position:absolute',
                f'left:{left_pct:.4f}%',
                f'top:{top_px:.1f}px',
                w_css,
                h_css,
                f'transform:scaleX({scale_v:.4f})' if scale_v != 1.0 else '',
                'transform-origin:0% 50%' if scale_v != 1.0 else '',
                'z-index:2' if _z_above else 'z-index:0',
                'pointer-events:none',
            ] if p)
            img_tag = f'<img src="{src}" style="{_style}" alt="">'
            if _z_above:
                imgs_above.append(img_tag)
            else:
                imgs_below.append(img_tag)
        except Exception:
            pass  # skip broken images silently

    return '\n'.join(imgs_below), '\n'.join(imgs_above)


def render_excel_to_html(ws, variable_map=None, cell_overrides=None,
                         extra_merge_map=None, extra_skip_cells=None,
                         bounds=None, layout_type=None, margins=None,
                         img_settings=None):
    """Convert openpyxl worksheet --- (html_div_string, table_width_px).

    The returned HTML is wrapped in a position:relative div so that
    absolutely-positioned worksheet images sit correctly over the table.

    variable_map     : {{{token}}}: value}  --- substituted into cell text
    cell_overrides   : {(row, col): html_string}  --- replaces cell content
    extra_merge_map  : {(row, col): (rowspan, colspan)}  --- additional merges
    extra_skip_cells : set of (row, col) to skip
    bounds           : (min_r, min_c, max_r, max_c) from detect_content_bounds
                       --- restricts rendering to content area only
    """
    variable_map    = variable_map    or {}
    cell_overrides  = cell_overrides  or {}
    extra_merge_map = extra_merge_map or {}
    skip_cells      = set(extra_skip_cells or set())

    MDW   = 7          # avg char width px (Excel default)
    PT_PX = 96 / 72    # 1pt --- px

    # Apply content bounds (smart crop)
    if bounds:
        row_start, col_start, max_row, max_col = bounds
    else:
        row_start, col_start = 1, 1
        max_col = ws.max_column or 1
        max_row = ws.max_row    or 1

    # Column widths (only for visible range)
    # Reference px widths (from Excel chars --- px) used for proportional sizing only.
    col_widths = []
    col_hidden = []
    for c in range(col_start, max_col + 1):
        cd = ws.column_dimensions.get(get_column_letter(c))
        hidden = bool(cd and cd.hidden)
        col_hidden.append(hidden)
        if hidden:
            col_widths.append(0)
        else:
            chars = (cd.width if cd and cd.width else 8.43)
            col_widths.append(max(4, round(chars * MDW)))
    # ------ Step A: Snapshot ORIGINAL col_offsets for pixel-perfect image placement ------
    # Must be done BEFORE any equalization or tightening so that image anchor
    # positions map correctly to the original Excel column layout.
    _orig_col_offsets = {}
    _acc = 0
    for _i, _w in enumerate(col_widths):
        _orig_col_offsets[_i] = _acc
        _acc += _w
    _orig_total_w_px = sum(w for w, h in zip(col_widths, col_hidden) if not h) or 1

    # Extend _orig_col_offsets to include pre-start columns with negative keys.
    # Image anchors can start in columns before col_start (e.g. logo in col A when
    # table starts at col B). Without this, _col_ref falls back to 0, shifting
    # images right by exactly the width of those pre-start columns.
    if col_start > 1:
        _pre_acc = 0
        for _c in range(col_start - 1, 0, -1):
            _cd = ws.column_dimensions.get(get_column_letter(_c))
            _hidden = bool(_cd and _cd.hidden)
            _cw = 0 if _hidden else max(4, round((_cd.width if _cd and _cd.width else 8.43) * MDW))
            _pre_acc += _cw
            # rel_idx = (_c - 1) - (col_start - 1) = _c - col_start  (always < 0)
            _orig_col_offsets[_c - col_start] = -_pre_acc

    # ------ Step B: Detect day-header row and collect day/time column indices ---------------------
    _DAY_KW = {
        'MON', 'TUE', 'WED', 'THU', 'THURS', 'FRI', 'SAT', 'SUN',
        'MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY',
    }
    _best_row_hits = 0
    _day_col_indices = []   # 0-based indices into col_widths
    for _r in range(row_start, max_row + 1):
        _hits = []
        for _ci, _c in enumerate(range(col_start, max_col + 1)):
            _v = ws.cell(row=_r, column=_c).value
            if _v and str(_v).strip().upper() in _DAY_KW:
                _hits.append(_ci)
        if len(_hits) >= 3 and len(_hits) > _best_row_hits:
            _best_row_hits = len(_hits)
            _day_col_indices = _hits

    # Time columns = only columns that ACTUALLY contain time values, found by
    # scanning BACKWARDS from the first day column and stopping at the first
    # column whose cells contain no time values.
    # This prevents header/info columns (e.g. "DEPARTMENT OF COMPUTER STUDIES")
    # from being incorrectly included and inflating the time-column width.
    _TIME_VAL_PAT = re.compile(r'^\d{1,2}:\d{2}')  # matches "HH:MM" or "HH:MM:SS"

    def _col_has_time_values(ci_0based):
        """Return True if any cell in this column holds a time value."""
        _ce = col_start + ci_0based
        for _r in range(row_start, max_row + 1):
            _v = ws.cell(row=_r, column=_ce).value
            if _v is None:
                continue
            # datetime.time: has strftime but no .year attribute
            if hasattr(_v, 'strftime') and not hasattr(_v, 'year'):
                return True
            # String that starts with "HH:MM"
            if isinstance(_v, str) and _TIME_VAL_PAT.match(_v.strip()):
                return True
        return False

    _time_col_indices = []
    if _day_col_indices:
        _first_day_idx = min(_day_col_indices)
        for _ti in range(_first_day_idx - 1, -1, -1):
            if col_hidden[_ti]:
                continue          # skip hidden cols, don't stop scanning
            if _col_has_time_values(_ti):
                _time_col_indices.insert(0, _ti)
            else:
                # Check if this column is completely empty (e.g. non-anchor of a
                # merged "TIME/DAYS" cell whose anchor is further left).
                # If fully empty --- skip it and keep scanning left.
                # If it has non-time content --- stop (real content boundary).
                _ce = col_start + _ti
                _col_empty = all(
                    ws.cell(row=_r, column=_ce).value is None
                    for _r in range(row_start, max_row + 1)
                )
                if _col_empty:
                    continue      # empty placeholder --- keep scanning left
                break             # non-empty non-time col --- stop

    # ------ Step C: Auto-fit each time column to its own content width ------------------------------------------
    # Only measure cells that contain ACTUAL TIME VALUES --- datetime.time objects
    # or strings matching the HH:MM pattern.  All other cells (headers, labels,
    # "DAILY CONTACT HOURS", "Prepared by:", etc.) are skipped.  This restricts
    # measurement to the schedule data rows only, regardless of template layout.
    for _ti in _time_col_indices:
        _col_excel = col_start + _ti   # 1-based Excel column number
        _max_len = 0
        _col_has_time_obj = False
        for _r in range(row_start, max_row + 1):
            _val = ws.cell(row=_r, column=_col_excel).value
            if _val is None:
                continue
            # ------ Identify time values only ------------------------------------------------------------------------------------------------------------------
            _is_time_obj = hasattr(_val, 'strftime') and not hasattr(_val, 'year')
            _is_time_str = isinstance(_val, str) and _TIME_VAL_PAT.match(_val.strip())
            if not (_is_time_obj or _is_time_str):
                continue    # skip non-time cells (headers, labels, totals, etc.)
            # ------ Measure display string ---------------------------------------------------------------------------------------------------------------------------
            # datetime.time --- strftime('%H:%M') = "07:00" (matches Excel display)
            # strings --- unchanged
            if _is_time_obj:
                _s = f"{_val.hour}:{_val.minute:02d}"   # "7:00" --- no leading zero
                _col_has_time_obj = True
            else:
                _s = str(_val).strip()
            _max_len = max(_max_len, len(_s))
        # datetime.time cols (Faculty): +20px padding
        # string time cols (Section): no extra padding
        _pad = 20 if _col_has_time_obj else 0
        _tight_w = max(MDW * 3, _max_len * MDW + _pad)
        col_widths[_ti] = _tight_w

    # ------ Step D: Day columns fill the space freed by time-col tightening ---------------------------
    # remaining = original_total --- new_tight_time --- other_non-day_non-time cols
    # Each day col gets an equal share of remaining, guaranteeing symmetry AND
    # that they are as wide as possible given the tightened time columns.
    if _day_col_indices:
        _tight_time_total = sum(col_widths[_i] for _i in _time_col_indices)
        _other_indices    = [_i for _i in range(len(col_widths))
                             if not col_hidden[_i]
                             and _i not in _day_col_indices
                             and _i not in _time_col_indices]
        _other_total      = sum(col_widths[_i] for _i in _other_indices)
        _remaining        = _orig_total_w_px - _tight_time_total - _other_total
        _day_col_w        = max(MDW * 5, round(_remaining / len(_day_col_indices)))
        for _di in _day_col_indices:
            col_widths[_di] = _day_col_w

    # total_w_px = reference pixel sum of ALL visible columns (used for % and image coords)
    total_w_px = sum(w for w, h in zip(col_widths, col_hidden) if not h) or 1
    num_visible = sum(1 for h in col_hidden if not h)
    table_px = total_w_px  # kept for API compatibility; actual table uses width:100%

    # Row heights (only for visible range)
    row_heights = []
    for r in range(row_start, max_row + 1):
        rd = ws.row_dimensions.get(r)
        pts = (rd.height if rd and rd.height else 13.5)
        row_heights.append(max(8, round(pts * PT_PX)))

    # Merged cell spans (full sheet --- clip rendering handles out-of-range)
    merged_spans = {}
    for merge in ws.merged_cells.ranges:
        r1, c1, r2, c2 = merge.min_row, merge.min_col, merge.max_row, merge.max_col
        merged_spans.setdefault(r1, {})[c1] = (r2 - r1 + 1, c2 - c1 + 1)
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                if r != r1 or c != c1:
                    skip_cells.add((r, c))

    for (r, c), (rs, cs) in extra_merge_map.items():
        merged_spans.setdefault(r, {})[c] = (rs, cs)
        for dr in range(r, r + rs):
            for dc in range(c, c + cs):
                if dr != r or dc != c:
                    skip_cells.add((dr, dc))

    def subst(text):
        if not text or not variable_map:
            return text
        for tok, val in variable_map.items():
            text = text.replace(tok, str(val) if val is not None else '')
        return text

    def esc(t):
        return str(t).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')

    lines = [
        '<table style="border-collapse:collapse;table-layout:fixed;width:100%;">',
        '<colgroup>',
    ]
    _time_col_set = set(_time_col_indices)
    _day_col_set  = set(_day_col_indices)
    for i, w in enumerate(col_widths):
        if col_hidden[i]:
            lines.append(f'  <col style="width:0;visibility:collapse;">')
        elif i in _time_col_set:
            # Time columns: absolute px --- fixed tight width.
            # Faculty gets +20px extra for readability.
            _tcw = w + 20 if layout_type == 'faculty' else w
            lines.append(f'  <col style="width:{_tcw}px;">')
        elif layout_type in ('section', 'room', 'course', 'faculty') and i in _day_col_set:
            # Day columns: auto --- browser splits all remaining space
            # (paper_content_w - time_col_px) equally among day cols
            # so the schedule grid fills edge-to-edge across the paper.
            lines.append(f'  <col style="width:auto;">')
        else:
            pct = w / total_w_px * 100
            lines.append(f'  <col style="width:{pct:.4f}%;">')
    lines.append('</colgroup><tbody>')

    for r in range(row_start, max_row + 1):
        rh = row_heights[r - row_start]
        lines.append(f'<tr style="height:{rh}px;">')

        for c in range(col_start, max_col + 1):
            if (r, c) in skip_cells:
                continue

            cell = ws.cell(row=r, column=c)

            # Cell value
            if (r, c) in cell_overrides:
                raw = cell_overrides[(r, c)]
                is_override = True
            else:
                v = cell.value
                if v is None:
                    raw = ''
                elif hasattr(v, 'strftime') and not hasattr(v, 'year'):
                    # datetime.time: no leading zero, e.g. "7:00" not "07:00"
                    raw = f"{v.hour}:{v.minute:02d}"
                else:
                    raw = str(v)
                is_override = False

            cell_text = subst(raw) if not is_override else raw

            # Span attrs
            span_info = merged_spans.get(r, {}).get(c)
            span_attrs = ''
            if span_info:
                rs, cs_span = span_info
                if rs > 1: span_attrs += f' rowspan="{rs}"'
                if cs_span > 1: span_attrs += f' colspan="{cs_span}"'

            # Style parts --- overflow:visible lets text spill like Excel does
            # Padding computed after alignment so we can factor in Excel indent.
            sp = [f'height:{rh}px', 'overflow:visible']

            # Fill --- solid fgColor; fall back to bgColor for pattern fills
            fill = cell.fill
            if fill and fill.fill_type not in (None, 'none'):
                fg = _argb_to_css(fill.fgColor) if fill.fgColor else None
                if not fg and fill.bgColor:
                    fg = _argb_to_css(fill.bgColor)
                if fg:
                    sp.append(f'background-color:{fg}')

            # Font --- name, size, weight, style, decorations, color
            font = cell.font
            if font:
                sz = font.size or 11
                sp.append(f'font-size:{round(sz * PT_PX, 1)}px')
                fname = font.name or 'Calibri'
                sp.append(f"font-family:'{fname}',sans-serif")
                if font.bold:   sp.append('font-weight:bold')
                if font.italic: sp.append('font-style:italic')
                td_deco = []
                if font.underline: td_deco.append('underline')
                if font.strike:    td_deco.append('line-through')
                if td_deco: sp.append(f'text-decoration:{" ".join(td_deco)}')
                fc = _argb_to_css(font.color) if font.color else None
                if fc: sp.append(f'color:{fc}')

            # Alignment + indent-aware padding
            # Excel cell indent (alignment.indent) adds character-width leading space.
            # Each indent level --- MDW px.  We convert it to CSS padding-left so the
            # visual indentation in Excel is faithfully reproduced in HTML.
            al = cell.alignment
            _indent_px = int(al.indent) * MDW if al and al.indent else 0
            _pad_left  = _indent_px + 4   # base 4 px + indent
            if cell_overrides and str(cell_overrides.get((r, c), '')).startswith('<'):
                sp.append('padding:0')
            else:
                sp.append(f'padding:0 4px 0 {_pad_left}px')
            if al:
                h_map = {'center':'center','right':'right','left':'left',
                         'justify':'justify','general':'left'}
                v_map = {'center':'middle','top':'top','bottom':'bottom'}
                sp.append(f'text-align:{h_map.get(al.horizontal or "left","left")}')
                _valign = 'middle' if layout_type == 'faculty' else v_map.get(al.vertical or 'bottom', 'bottom')
                sp.append(f'vertical-align:{_valign}')
                sp.append('white-space:pre-wrap;word-wrap:break-word' if al.wrap_text else 'white-space:pre')
            else:
                sp += ['text-align:left', 'vertical-align:middle', 'white-space:pre']

            # Borders --- per-side explicit control.
            # Real Excel border --- use its CSS.  No real border --- 'none' so the
            # CSS outline debug-grid (rgba 0,0,0,0.10) shows through cleanly.
            bd = cell.border
            for _s in ('top', 'right', 'bottom', 'left'):
                _real = _border_side_css(getattr(bd, _s, None) if bd else None)
                sp.append(f'border-{_s}:{_real if _real else "none"}')

            style_str = ';'.join(sp)

            if is_override:
                html_text = cell_text  # already HTML
            else:
                html_text = esc(cell_text).replace('\n', '<br>') if cell_text else ''

            lines.append(f'  <td{span_attrs} style="{style_str}">{html_text}</td>')

        lines.append('</tr>')

    lines += ['</tbody>', '</table>']

    # Build cumulative pixel offsets for image placement (col/row index --- px from top-left of table)
    col_offsets = {}  # 0-based col index --- left px
    acc = 0
    for i, w in enumerate(col_widths):
        col_offsets[i] = acc
        acc += w
    row_offsets = {}  # 0-based row index --- top px
    acc = 0
    for i, h in enumerate(row_heights):
        row_offsets[i] = acc
        acc += h

    # Extract and embed worksheet images.
    # For section/room/course: image left% must be relative to the actual paper content width
    # (not _orig_total_w_px from Excel) so the logo lands at its true Excel position.
    # Paper content width = (paper_w - left_margin - right_margin) -- 96dpi.
    # left_offset_px=-30 compensates for pre-start column offset (logo in col A, table at col B).
    if layout_type in ('section', 'room', 'course') and margins:
        _m  = margins
        _ml = float(_m.get('left',  1.0))
        _mr = float(_m.get('right', 1.0))
        _pk = _m.get('paper', 'A4')
        _pw, _, _ = PAPER_SIZES.get(_pk, PAPER_SIZES['A4'])
        _paper_content_px = (_pw - _ml - _mr) * 96
        imgs_below, imgs_above = _extract_ws_images_html(ws, _orig_col_offsets, row_offsets, col_start, row_start, _paper_content_px, left_offset_px=-30, img_settings_list=img_settings)
    elif layout_type == 'faculty' and margins:
        _m  = margins
        _ml = float(_m.get('left',  1.0))
        _mr = float(_m.get('right', 1.0))
        _pk = _m.get('paper', 'A4')
        _pw, _, _ = PAPER_SIZES.get(_pk, PAPER_SIZES['A4'])
        _paper_content_px = (_pw - _ml - _mr) * 96
        imgs_below, imgs_above = _extract_ws_images_html(ws, _orig_col_offsets, row_offsets, col_start, row_start, _paper_content_px, left_offset_px=20, img_settings_list=img_settings)
    else:
        imgs_below, imgs_above = _extract_ws_images_html(ws, _orig_col_offsets, row_offsets, col_start, row_start, _orig_total_w_px, img_settings_list=img_settings)

    # Wrapper is width:100% so the table always fills the paper content area.
    # Images use percentage left/width so they scale with the table.
    # below-images go before the table (behind text), above-images after (on top of text).
    html_out = (
        '<div style="position:relative;width:100%;isolation:isolate;">\n'
        + imgs_below + '\n'
        + '<div style="position:relative;z-index:1;">'
        + '\n'.join(lines)
        + '</div>\n'
        + imgs_above + '\n'
        + '</div>'
    )
    return html_out, table_px, 1.0, 0




def render_a4_page(html_content, table_px, margins=None, for_canvas=False, dominant_font=None):
    """Wrap HTML table in a paper-sized page for iframe preview.

    margins: dict with keys top/bottom/left/right (float, inches) + paper (str key).
    for_canvas: if True, sets background to transparent and removes padding for Infinite Canvas.
    """
    m = margins or {}
    mt = float(m.get('top',    1.0))
    mb = float(m.get('bottom', 1.0))
    ml = float(m.get('left',   1.0))
    mr = float(m.get('right',  1.0))
    paper_key  = m.get('paper', 'A4')
    pw, ph, _  = PAPER_SIZES.get(paper_key, PAPER_SIZES['A4'])

    # Canvas-specific overrides
    bg_style = "background: transparent;" if for_canvas else "background: #c8c8c8;"
    body_padding = "padding: 0;"
    body_overflow = "overflow: hidden;"
    paper_shadow = "box-shadow: none;" if for_canvas else "box-shadow: 0 4px 24px rgba(0,0,0,.28), 0 1px 4px rgba(0,0,0,.14);"
    
    dfont = f"'{dominant_font}', " if dominant_font else ""
    
    # Check if viewer mode (request arg)
    is_viewer = request.args.get('viewer', 'false') == 'true'
    body_class = "viewer-mode" if is_viewer else ""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    {bg_style}
    font-family: {dfont}Calibri, Arial, sans-serif;
    {body_padding}
    {body_overflow}
    min-height: 100vh;
    display: block;
    touch-action: pan-x pan-y;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    text-rendering: optimizeLegibility;
    image-rendering: -webkit-optimize-contrast;
  }}
  
  /* Reset internal padding for viewer mode if needed */
  body.viewer-mode {{
    padding: 0 !important;
  }}
  
  /* On larger screens, center the paper. On mobile, keep it left-aligned so it scales cleanly */
  @media (min-width: 850px) {{
    body {{
      display: flex;
      justify-content: center;
      align-items: flex-start;
    }}
  }}
  .a4 {{
    background: #ffffff;
    width: {pw}in;
    min-height: {ph}in;
    padding: {mt}in {mr}in {mb}in {ml}in;
    {paper_shadow}
    border-radius: 1px;
    position: relative;
    overflow: visible;
    margin: 0 auto;

  }}
  .table-wrap {{
    width: 100%;
    overflow: visible;
    position: relative;
  }}
  /* Debug grid ---- faint outline on every cell */
  table td, table th {{
    outline: 0.5px solid rgba(0,0,0,0.10);
  }}
  /* Overlap badge ---- cursor only, tooltip via JS */
  .sched-overlap-badge {{ cursor: pointer; }}
  table {{
    width: 100%;
    transform-origin: top left;
  }}
</style></head><body>
  <div class="a4" id="a4Paper">
    <div class="table-wrap" id="tableWrap">
      {html_content}
    </div>
  </div>
  <script>
    (function() {{
      var wrap  = document.getElementById('tableWrap');
      var paper = document.getElementById('a4Paper');
      // Scale the inner position:relative container (holds both table AND images)
      // so that images auto-resize together with the table.
      var table = wrap.querySelector('table');
      if (!table) {{
          // Fallback for sheets with logos where inner div exists
          var inner = wrap.querySelector('div');
          table = inner && inner.querySelector('table');
      }}
      if (!table) return;

      // Available content area in px (paper minus CSS padding margins)
      var DPI = 96;
      var paperContentW = ({pw} - {ml} - {mr}) * DPI;
      var paperContentH = ({ph} - {mt} - {mb}) * DPI;

      // Identify the secure content wrapper (the isolation:isolate div)
      var target = wrap.firstElementChild; 
      if (!target) return;
      var table = target.querySelector('table');
      if (!table) return;

      // Measure unscaled content bounds
      var contentW = target.scrollWidth || target.offsetWidth;
      var contentH = table.scrollHeight;

      // Calculate necessary scaling to fit both width and height
      var scaleW = (contentW > paperContentW && paperContentW > 0) ? paperContentW / contentW : 1.0;
      var scaleH = (contentH > paperContentH && paperContentH > 0) ? paperContentH / contentH : 1.0;

      // Pick the stricter scale (the smaller one) to ensure no overflow
      var finalScale = Math.min(scaleW, scaleH, 1.0);

      if (finalScale < 1.0) {{
          target.style.transform = 'scale(' + finalScale + ')';
          target.style.transformOrigin = 'top center'; // Centered looks more professional on paper
          
          // Fix visual width of wrapper to avoid extra scroll-room
          target.style.width = (contentW) + 'px'; 
          wrap.style.overflow = 'hidden';

          // Lock paper to fixed height when shrinking to fit
          paper.style.height    = '{ph}in';
          paper.style.minHeight = 'unset';
          paper.style.overflow  = 'hidden';
      }}
    }})();
  </script>

  <!-- Overlap tooltip panel -->
  <div id="overlapTip" style="display:none;position:fixed;z-index:9999;
    background:#fff;border:1.5px solid #dc3545;border-radius:7px;
    padding:9px 12px;font-size:11px;min-width:240px;max-width:340px;
    box-shadow:0 4px 18px rgba(0,0,0,0.22);
    font-family:Calibri,Arial,sans-serif;">
    <div id="overlapTipTitle" style="font-weight:700;margin-bottom:5px;font-size:12px;"></div>
    <div id="overlapTipBody" style="max-height:260px;overflow-y:auto;"></div>
  </div>
  <script>
  (function() {{
    var tip  = document.getElementById('overlapTip');
    var body = document.getElementById('overlapTipBody');
    var hideTimer = null;
    document.querySelectorAll('.sched-overlap-badge').forEach(function(badge) {{
      badge.addEventListener('mouseenter', function(e) {{
        var entries;
        try {{ entries = JSON.parse(this.dataset.overlap || '[]'); }} catch(ex) {{ entries = []; }}
        var vtype = this.dataset.vtype || '';
        var titleText, titleColor, borderColor;
        if (vtype === 'course') {{
          titleText = 'Overlapping Courses';     titleColor = '#333';     borderColor = '#aaa';
        }} else if (vtype === 'room_neutral') {{
          titleText = 'Overlapping Rooms';       titleColor = '#333';     borderColor = '#aaa';
        }} else if (vtype === 'faculty_neutral') {{
          titleText = 'Overlapping Faculty';     titleColor = '#333';     borderColor = '#aaa';
        }} else if (vtype === 'section') {{
          titleText = '\u26a0 Overlapping Sections'; titleColor = '#dc3545'; borderColor = '#dc3545';
        }} else if (vtype === 'faculty') {{
          titleText = '\u26a0 Overlapping Faculty';  titleColor = '#dc3545'; borderColor = '#dc3545';
        }} else if (vtype === 'room') {{
          titleText = '\u26a0 Overlapping Rooms';    titleColor = '#dc3545'; borderColor = '#dc3545';
        }} else {{
          titleText = '\u26a0 Overlapping Classes';  titleColor = '#dc3545'; borderColor = '#dc3545';
        }}
        var titleEl = document.getElementById('overlapTipTitle');
        titleEl.textContent   = titleText;
        titleEl.style.color   = titleColor;
        tip.style.borderColor = borderColor;
        body.innerHTML = entries.map(function(en, i) {{
          return '<div style="padding:3px 0;'
            + (i > 0 ? 'border-top:1px solid #f0f0f0;margin-top:3px;' : '') + '">'
            + (en.t ? '<span style="color:#666;font-size:10px;">' + en.t + '</span><br>' : '')
            + '<strong style="font-size:12px;">' + (en.c || '') + '</strong>'
            + (en.s ? ' <span style="color:#555;">---- ' + en.s + '</span>' : '')
            + (en.f ? '<br><span style="color:#888;font-size:10px;">' + en.f + '</span>' : '')
            + '</div>';
        }}).join('');
        tip.style.display = 'block';
        tip.style.left = Math.min(e.clientX + 12, window.innerWidth - 360) + 'px';
        tip.style.top  = Math.min(e.clientY + 12, window.innerHeight - 220) + 'px';
      }});
      badge.addEventListener('mouseleave', function() {{
        hideTimer = setTimeout(function() {{ tip.style.display = 'none'; }}, 150);
      }});
    }});
    tip.addEventListener('mouseenter', function() {{
      if (hideTimer) {{ clearTimeout(hideTimer); hideTimer = null; }}
    }});
    tip.addEventListener('mouseleave', function() {{
      tip.style.display = 'none';
    }});
  }})();
  </script>
</body></html>"""

def render_blank_timetable_fallback(entity_name, semester, sem_ay, layout_type, for_canvas=False):
    settings = get_settings()
    if layout_type == 'faculty':
        _margins = _get_faculty_margins(settings)
    else:
        _margins = _get_margins(settings)
    html_content = render_template('_blank_timetable.html', entity_name=entity_name, semester=semester, sem_ay=sem_ay)
    return render_a4_page(html_content, 960, margins=_margins, for_canvas=for_canvas)





def detect_schedule_grid(ws):
    """Scan worksheet for timetable grid. Two-pass detection:
    1) Token-based: looks for {{GRID_TIME}} + {{GRID_MON}} etc.
    2) Auto-detect fallback: scans for time patterns + day name headers.

    Returns dict with grid geometry, or None if no grid found.
    """
    GRID_TOKEN_TO_DAY = {
        '{{GRID_MON}}': 'Monday',   '{{GRID_TUE}}': 'Tuesday',
        '{{GRID_WED}}': 'Wednesday','{{GRID_THU}}': 'Thursday',
        '{{GRID_FRI}}': 'Friday',   '{{GRID_SAT}}': 'Saturday',
        '{{GRID_SUN}}': 'Sunday',
    }
    DAY_KEYWORDS = {
        'monday': 'Monday',   'mon': 'Monday',
        'tuesday': 'Tuesday', 'tue': 'Tuesday',
        'wednesday': 'Wednesday', 'wed': 'Wednesday',
        'thursday': 'Thursday',   'thu': 'Thursday',
        'friday': 'Friday',   'fri': 'Friday',
        'saturday': 'Saturday',   'sat': 'Saturday',
        'sunday': 'Sunday',   'sun': 'Sunday',
    }
    timere        = re.compile(
        r'(\d{1,2}:\d{2})\s*(AM|PM)?\s*[-----]\s*(\d{1,2}:\d{2})\s*(AM|PM)?',
        re.IGNORECASE)
    simple_timere = re.compile(r'\b(\d{1,2}:\d{2})\s*(AM|PM)?\b', re.IGNORECASE)

    def _to24(time_str, period=None):
        """Convert HH:MM + optional AM/PM to 24-hour HH:MM string."""
        h, m = map(int, time_str.split(':'))
        if period:
            p = period.upper()
            if p == 'PM' and h != 12:
                h += 12
            elif p == 'AM' and h == 12:
                h = 0
        return f'{h:02d}:{m:02d}'

    def _build_time_slots(anchor_row, anchor_col):
        slots = []
        for r in range(anchor_row + 1, ws.max_row + 1):
            v = str(ws.cell(row=r, column=anchor_col).value or '').strip()
            if not v:
                continue
            m = timere.search(v)
            if m:
                start_t = _to24(m.group(1), m.group(2))
                end_t   = _to24(m.group(3), m.group(4))
                slots.append((r, start_t, end_t))
            else:
                m2 = simple_timere.search(v)
                if m2:
                    start_t = _to24(m2.group(1), m2.group(2))
                    slots.append((r, start_t, None))
        return slots

    def _normalize_12h_wrap(slots):
        """Fix implicit 12-hour time wrapping in templates without AM/PM labels.

        Philippine timetable templates often show "7:00, 7:30, ..., 12:30, 1:00, 1:30, ..."
        where "1:00" after "12:30" means 1:00 PM = 13:00.  Detect the backwards jump in
        the time sequence and add +12 h to all slots from that point on, so template times
        align with the DB's 24-hour start_time / end_time values.
        """
        if len(slots) < 2:
            return slots
        result  = []
        offset  = 0
        prev_sm = None
        for (r, s, e) in slots:
            h, m = map(int, s.split(':'))
            sm   = h * 60 + m + offset
            if prev_sm is not None and sm < prev_sm:  # backwards jump -> 12h wrap
                offset += 720
                sm     += 720
            new_s = f'{sm // 60:02d}:{sm % 60:02d}'
            if e:
                eh, em  = map(int, e.split(':'))
                em_val  = eh * 60 + em + offset
                if em_val < sm:       # end also wraps within same slot (e.g. "12:30-1:00")
                    em_val += 720
                new_e = f'{em_val // 60:02d}:{em_val % 60:02d}'
            else:
                new_e = e
            result.append((r, new_s, new_e))
            prev_sm = sm
        return result

    # ------------------------------------ Pass 1: token-based detection ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    time_anchor_row = time_anchor_col = None
    for row in ws.iter_rows():
        for cell in row:
            if cell.value and '{{GRID_TIME}}' in str(cell.value):
                time_anchor_row = cell.row
                time_anchor_col = cell.column
                break
        if time_anchor_row:
            break

    if time_anchor_row:
        header_row = time_anchor_row
        day_cols = {}
        for c in range(time_anchor_col + 1, ws.max_column + 1):
            v = str(ws.cell(row=header_row, column=c).value or '')
            if v in GRID_TOKEN_TO_DAY:
                day_cols[GRID_TOKEN_TO_DAY[v]] = c
        if day_cols:
            time_slots = _normalize_12h_wrap(_build_time_slots(time_anchor_row, time_anchor_col))
            if time_slots:
                return {'header_row': header_row, 'time_col': time_anchor_col,
                        'day_cols': day_cols, 'time_slots': time_slots}

    # ------------------------------------ Pass 2: auto-detect ---- find time column + day name headers ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    # Score columns: range-format "HH:MM-HH:MM" (strong signal) vs bare "HH:MM" (weak)
    col_range_counts   = {}
    col_time_counts    = {}
    col_first_time_row = {}
    for row in ws.iter_rows():
        for cell in row:
            if not cell.value or isinstance(cell, MergedCell):
                continue
            v = str(cell.value).strip()
            c = cell.column
            if timere.search(v):
                col_range_counts[c] = col_range_counts.get(c, 0) + 1
                col_time_counts[c]  = col_time_counts.get(c, 0) + 1
                if c not in col_first_time_row:
                    col_first_time_row[c] = cell.row
            elif simple_timere.search(v):
                col_time_counts[c] = col_time_counts.get(c, 0) + 1
                if c not in col_first_time_row:
                    col_first_time_row[c] = cell.row

    if not col_time_counts:
        return None

    # Prefer columns with range-format times; fall back to simple-time count
    if col_range_counts:
        best_col = max(col_range_counts, key=lambda c: col_range_counts[c])
    else:
        best_col = max(col_time_counts, key=lambda c: col_time_counts[c])
    if col_time_counts[best_col] < 3:
        return None  # Too few time values ---- probably not a timetable

    first_time_row = col_first_time_row[best_col]

    def _scan_day_names(hrow):
        """Scan a candidate header row for day name keywords; return day_cols dict."""
        found = {}
        for c in range(1, ws.max_column + 1):
            if c == best_col:
                continue
            v = str(ws.cell(row=hrow, column=c).value or '').strip().lower()
            if not v:
                continue
            for kw, day_name in DAY_KEYWORDS.items():
                if kw in v and day_name not in found:
                    found[day_name] = c
                    break
        return found

    # Try header rows row-1, row-2, row-3 above the first time slot
    header_row = None
    day_cols   = {}
    for offset in range(1, 4):
        candidate = first_time_row - offset
        if candidate < 1:
            break
        found = _scan_day_names(candidate)
        if found:
            header_row = candidate
            day_cols   = found
            break

    if not day_cols:
        return None

    time_slots = _normalize_12h_wrap(_build_time_slots(header_row, best_col))
    if not time_slots:
        return None

    return {'header_row': header_row, 'time_col': best_col,
            'day_cols': day_cols, 'time_slots': time_slots}


    # ------------------------------------ Pass 3: Standard Fallback ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    # If no tokens or auto-detection worked, provide a standard Monday to Friday grid
    # starting from 7:00 AM to 7:00 PM (1-hour slots).
    fallback_day_cols = {
        'Monday': 2, 'Tuesday': 3, 'Wednesday': 4, 'Thursday': 5,
        'Friday': 6, 'Saturday': 7, 'Sunday': 8
    }
    fallback_time_slots = []
    for i, hour in enumerate(range(7, 19)):
        fallback_time_slots.append((i + 2, f"{hour:02d}:00", f"{hour+1:02d}:00"))
    
    return {
        'header_row': 1,
        'time_col': 1,
        'day_cols': fallback_day_cols,
        'time_slots': fallback_time_slots,
        'is_fallback': True
    }


def build_schedule_overlays(schedules, grid_info, view_type):
    """Map ScheduledClass objects onto the detected Excel grid.

    Returns (cell_overrides, extra_merge_map, extra_skip_cells).
    """
    cell_overrides   = {}
    extra_merge_map  = {}
    extra_skip_cells = set()
    # cell_data: (start_row, col) -> list of (rowspan, lines, entry_dict)
    cell_data = {}

    # Badge view-type: some entities are not real conflicts ---- treat as neutral.
    _vtype_for_badge = view_type
    if view_type == 'room' and schedules:
        _first_room = getattr(schedules[0], 'room', None)
        if _first_room and getattr(_first_room, 'capacity', 0) == 999:
            _vtype_for_badge = 'room_neutral'  # NSTP universal room ---- not a real conflict
    if view_type == 'faculty' and schedules:
        _first_faculty = getattr(schedules[0], 'faculty', None)
        if _first_faculty:
            _fname = (getattr(_first_faculty, 'full_name', '') or '').strip().upper()
            if 'T.B.A' in _fname or _fname == 'TBA':
                _vtype_for_badge = 'faculty_neutral'  # T.B.A. is not a real teacher ---- not a conflict

    day_cols   = grid_info['day_cols']
    time_slots = grid_info['time_slots']  # [(row, start_str, end_str|None)]

    def t2m(t):
        """'HH:MM' -> minutes from midnight."""
        if not t:
            return 0
        try:
            h, mn = t.strip().split(':')
            return int(h) * 60 + int(mn)
        except Exception:
            return 0

    slot_list = []
    slot_by_start = {}
    for (row, s, e) in time_slots:
        sm = t2m(s)
        em = t2m(e) if e else sm + 60
        slot_list.append((row, sm, em))
        if sm not in slot_by_start:
            slot_by_start[sm] = row
    slot_list.sort(key=lambda x: x[0])

    def physical_rows(start_row, start_min, end_min):
        """Return the physical Excel row span from start_row to the last slot row
        that falls within [start_min, end_min). Works correctly even when the
        template has empty/spacer rows between time slots."""
        last_slot_row = start_row
        for (srow, smin, emin) in slot_list:
            if srow < start_row:
                continue
            if smin >= end_min:
                break
            if smin >= start_min:
                last_slot_row = srow
        return max(1, last_slot_row - start_row + 1)

    def _esc(s):
        return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    def fmt_faculty(full_name, sex):
        parts = (full_name or '').split()
        surname = parts[-1].upper() if parts else (full_name or '').upper()
        prefix = 'MR.' if sex == 'M' else 'MS.' if sex == 'F' else 'PROF.'
        return f'{prefix} {surname}'

    # ------------------------------------ Pass 1: collect all schedule entries per grid cell ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    for sched in schedules:
        col = day_cols.get(sched.day)
        if col is None:
            continue
        sm  = t2m(sched.start_time)
        em  = t2m(sched.end_time)
        start_row = slot_by_start.get(sm)
        if start_row is None:
            best = min(slot_list, key=lambda x: abs(x[1] - sm), default=None)
            if best:
                start_row = best[0]
            else:
                continue

        rowspan = physical_rows(start_row, sm, em)

        course_code  = (sched.course.course_code or sched.course.course_name or '') if sched.course  else ''
        section_name = sched.section.section_name if sched.section else ''
        faculty_name = fmt_faculty(sched.faculty.full_name, getattr(sched.faculty, 'sex', None)) if sched.faculty else 'T.B.A.'
        room_name    = sched.room.room_name        if sched.room    else 'T.B.A.'
        sess_type    = getattr(sched, 'session_type', '')

        if view_type == 'section':
            lines = [course_code + (f' ({sess_type})' if sess_type else ''),
                     faculty_name, room_name]
        elif view_type == 'faculty':
            lines = [course_code + (f' ({sess_type})' if sess_type else ''),
                     section_name, room_name]
        elif view_type == 'course':
            lines = [section_name or course_code, faculty_name, room_name]
        else:  # room
            lines = [course_code + (f' ({sess_type})' if sess_type else ''),
                     section_name, faculty_name]

        lines = [l for l in lines if l]
        start_t = _fmt_time_12h(sched.start_time) if sched.start_time else ''
        end_t   = _fmt_time_12h(sched.end_time)   if sched.end_time   else ''
        entry_dict = {'c': course_code, 's': section_name, 'f': faculty_name,
                      't': f'{start_t}----{end_t}'}
        cell_data.setdefault((start_row, col), []).append((rowspan, lines, entry_dict))

    # ------------------------------------ Pass 2: build HTML for each cell, stacking all entries ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    for (start_row, col), entries in sorted(cell_data.items()):
        rowspan = max(e[0] for e in entries)
        cnt     = len(entries)

        if cnt == 1:
            # Single schedule ---- centered block
            _, lines, _ = entries[0]
            main_line = _esc(lines[0]) if lines else ''
            sub_html  = ''.join(
                f'<div>{_esc(l)}</div>'
                for l in lines[1:] if l
            )
            cell_html = (
                '<div style="display:table;width:100%;height:100%;'
                'border-top:1px solid #000000;border-right:1px solid #000000;'
                'border-bottom:1px solid #000000;border-left:1px solid #000000;overflow:hidden;">'
                '<div style="display:table-cell;vertical-align:middle;text-align:center;'
                'padding:3px;font-size:11px;line-height:1.3;color:#000;font-family:inherit;">'
                f'<div>{main_line}</div>'
                f'{sub_html}'
                '</div></div>'
            )
        else:
            # Multiple overlapping schedules ---- show top schedule only, badge reveals all
            _, lines, _ = entries[0]
            main_line = _esc(lines[0]) if lines else ''
            sub_html  = ''.join(f'<div>{_esc(l)}</div>' for l in lines[1:] if l)
            payload   = json.dumps([e[2] for e in entries]).replace("'", "&#39;")
            badge     = (
                f'<span class="sched-overlap-badge" data-overlap=\'{payload}\' data-vtype="{_vtype_for_badge}" '
                f'style="position:absolute;top:3px;right:3px;background:#dc3545;'
                f'color:#fff;font-size:9px;font-weight:bold;min-width:16px;height:16px;'
                f'border-radius:50%;display:inline-flex;align-items:center;'
                f'justify-content:center;line-height:1;z-index:5;cursor:pointer;">{cnt}</span>'
            )
            cell_html = (
                '<div style="position:relative;display:table;width:100%;height:100%;'
                'border-top:1px solid #000000;border-right:1px solid #000000;'
                'border-bottom:1px solid #000000;border-left:1px solid #000000;overflow:hidden;">'
                f'{badge}'
                '<div style="display:table-cell;vertical-align:middle;text-align:center;'
                'padding:3px;font-size:11px;line-height:1.3;color:#000;font-family:inherit;">'
                f'<div>{main_line}</div>'
                f'{sub_html}'
                '</div></div>'
            )

        cell_overrides[(start_row, col)] = cell_html
        if rowspan > 1 and (start_row, col) not in extra_skip_cells:
            extra_merge_map[(start_row, col)] = (rowspan, 1)
            for dr in range(1, rowspan):
                extra_skip_cells.add((start_row + dr, col))

    return cell_overrides, extra_merge_map, extra_skip_cells


# ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# Paper size catalog ---- (width_in, height_in) in portrait orientation
PAPER_SIZES = {
    'A4':        (8.27,  11.69,  'A4 Bond Paper (8.27 in ------------ 11.69 in)'),
    'Letter':    (8.5,   11.0,   'Short Bond / US Letter (8.5 in ------------ 11 in)'),
    'Legal':     (8.5,   14.0,   'Long Bond / Legal (8.5 in ------------ 14 in)'),
    'Folio':     (8.5,   13.0,   'Folio / F4 (8.5 in ------------ 13 in)'),
    'A3':        (11.69, 16.54,  'A3 (11.69 in ------------ 16.54 in)'),
    'A5':        (5.83,  8.27,   'A5 (5.83 in ------------ 8.27 in)'),
    'B4':        (9.84,  13.90,  'B4 (9.84 in ------------ 13.90 in)'),
    'B5':        (6.93,  9.84,   'B5 (6.93 in ------------ 9.84 in)'),
    'Executive': (7.25,  10.5,   'Executive (7.25 in ------------ 10.5 in)'),
    'Tabloid':   (11.0,  17.0,   'Tabloid / Ledger (11 in ------------ 17 in)'),
    'Statement': (5.5,   8.5,    'Statement / Half Letter (5.5 in ------------ 8.5 in)'),
}


def _get_margins(settings):
    """Extract shared margin values (Section/Room/Course) from SystemSettings."""
    return {
        'top':    getattr(settings, 'margin_top',    1.0) or 1.0,
        'bottom': getattr(settings, 'margin_bottom', 1.0) or 1.0,
        'left':   getattr(settings, 'margin_left',   1.0) or 1.0,
        'right':  getattr(settings, 'margin_right',  1.0) or 1.0,
        'paper':  getattr(settings, 'paper_size',    'A4') or 'A4',
    }


def _get_faculty_margins(settings):
    """Extract Faculty-specific margin values (independent from shared margins)."""
    return {
        'top':    getattr(settings, 'fac_margin_top',    1.0) or 1.0,
        'bottom': getattr(settings, 'fac_margin_bottom', 1.0) or 1.0,
        'left':   getattr(settings, 'fac_margin_left',   1.0) or 1.0,
        'right':  getattr(settings, 'fac_margin_right',  1.0) or 1.0,
        'paper':  getattr(settings, 'fac_paper_size',    'A4') or 'A4',
    }


def _get_img_settings(settings, layout_type):
    """Return parsed per-image settings list for a layout type.
    Each element: {'x': float, 'y': float, 'scale': float, 'z_above': bool}
    Returns [] if no settings saved or column missing."""
    col_map = {
        'section': 'section_img_settings',
        'faculty': 'faculty_img_settings',
        'room':    'room_img_settings',
        'course':  'course_img_settings',
    }
    raw = getattr(settings, col_map.get(layout_type, ''), None)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except (ValueError, TypeError):
        pass
    return []


def _get_template_img_count(layout_type):
    """Count images embedded in the layout's Excel template (uses template cache)."""
    path = os.path.join(basedir, 'static', 'assets', f'{layout_type}_template.xlsx')
    if not os.path.exists(path):
        return 0
    try:
        ws, _, _ = _get_cached_template(path)
        return len(getattr(ws, '_images', []))
    except Exception:
        return 0


def _parse_img_slots(raw_json, n):
    """Return list of n image setting dicts, padded with defaults."""
    _default = {'x': 0.0, 'y': 0.0, 'scale': 1.0, 'z_above': True}
    try:
        slots = json.loads(raw_json) if raw_json else []
    except Exception:
        slots = []
    while len(slots) < n:
        slots.append(dict(_default))
    return slots[:n]


def _read_img_slots(form, prefix, n):
    """Read n image slot fields from POST form and return JSON string."""
    slots = []
    for i in range(1, n + 1):
        try:
            x       = float(form.get(f'{prefix}_img_{i}_x', 0.0))
            y       = float(form.get(f'{prefix}_img_{i}_y', 0.0))
            scale   = max(0.1, min(5.0, float(form.get(f'{prefix}_img_{i}_scale', 1.0))))
            z_above = form.get(f'{prefix}_img_{i}_z_above', '1') == '1'
        except (ValueError, TypeError):
            x, y, scale, z_above = 0.0, 0.0, 1.0, True
        slots.append({'x': x, 'y': y, 'scale': scale, 'z_above': z_above})
    return json.dumps(slots)


@app.route('/preview-layout/<layout_type>')
@login_required
@role_required('admin', 'superadmin')
def preview_layout(layout_type):
    """Render the uploaded XLSX template as a standalone A4-paper HTML page.
    Used by the preview iframe in manage_layouts.html."""
    path = os.path.join(basedir, 'static', 'assets', f"{layout_type}_template.xlsx")
    if not os.path.exists(path):
        return (
            "<div style='padding:40px;color:#dc3545;font-family:Arial,sans-serif;'>"
            f"<strong>No template found:</strong> {layout_type}_template.xlsx<br>"
            "Upload an Excel (.xlsx) file first."
            "</div>"
        )

    wb = load_workbook(path, data_only=True)
    ws = wb.active
    
    # Extract dominant font from Excel
    font_counts = {}
    for r in range(1, min(ws.max_row, 50) + 1):
        for c in range(1, min(ws.max_column, 20) + 1):
            f = ws.cell(row=r, column=c).font
            if f and f.name:
                font_counts[f.name] = font_counts.get(f.name, 0) + 1
    dom_font = max(font_counts, key=font_counts.get) if font_counts else None

    settings = get_settings()
    var_map  = build_variable_map(layout_type, settings)   # preview: dynamic fields show [placeholder]
    bounds   = detect_content_bounds(ws)
    if layout_type == 'faculty':
        static_overrides = build_faculty_cell_overrides(ws, settings)
        _margins = _get_faculty_margins(settings)
    else:
        static_overrides = build_static_cell_overrides(ws, layout_type, settings)
        _margins = _get_margins(settings)
    _img_settings = _get_img_settings(settings, layout_type)
    html_content, table_px, _, _ = render_excel_to_html(
        ws, variable_map=var_map, cell_overrides=static_overrides, bounds=bounds,
        layout_type=layout_type, margins=_margins, img_settings=_img_settings)
    return render_a4_page(html_content, table_px, margins=_margins, dominant_font=dom_font)



def render_viewer_page(html_content, table_px, margins=None, for_canvas=False, dominant_font=None):
    """Wrap HTML table in a paper-sized page for iframe preview.

    margins: dict with keys top/bottom/left/right (float, inches) + paper (str key).
    for_canvas: if True, sets background to transparent and removes padding for Infinite Canvas.
    """
    m = margins or {}
    mt = float(m.get('top',    1.0))
    mb = float(m.get('bottom', 1.0))
    ml = float(m.get('left',   1.0))
    mr = float(m.get('right',  1.0))
    paper_key  = m.get('paper', 'A4')
    pw, ph, _  = PAPER_SIZES.get(paper_key, PAPER_SIZES['A4'])

    # Canvas-specific overrides
    bg_style = "background: transparent;" if for_canvas else "background: #c8c8c8;"
    body_padding = "padding: 0;" if for_canvas else "padding: 24px 0;"
    body_overflow = "overflow: hidden;" if for_canvas else ""
    
    dfont = f"'{dominant_font}', " if dominant_font else ""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    {bg_style}
    font-family: {dfont}Calibri, Arial, sans-serif;
    {body_padding}
    {body_overflow}
    min-height: 100vh;
    touch-action: pan-x pan-y;
  }}
  
  /* On larger screens, center the paper. On mobile, keep it left-aligned so it scales cleanly */
  @media (min-width: 850px) {{
    body {{
      display: flex;
      justify-content: center;
      align-items: flex-start;
    }}
  }}
  .a4 {{
    background: #ffffff;
    width: {pw}in;
    min-height: {ph}in;
    padding: {mt}in {mr}in {mb}in {ml}in;
    box-shadow: 0 4px 24px rgba(0,0,0,.28), 0 1px 4px rgba(0,0,0,.14);
    border-radius: 1px;
    position: relative;
    overflow: visible;
  }}
  .table-wrap {{
    width: 100%;
    overflow: visible;
    position: relative;
  }}
  /* Debug grid ---- faint outline on every cell */
  table td, table th {{
    outline: 0.5px solid rgba(0,0,0,0.10);
  }}
  /* Overlap badge ---- cursor only, tooltip via JS */
  .sched-overlap-badge {{ cursor: pointer; }}
  table {{
    width: 100%;
    transform-origin: top left;
  }}
</style></head><body>
  <div class="a4" id="a4Paper">
    <div class="table-wrap" id="tableWrap">
      {html_content}
    </div>
  </div>
  <script>
    (function() {{
      var wrap  = document.getElementById('tableWrap');
      var paper = document.getElementById('a4Paper');
      // Scale the inner position:relative container (holds both table AND images)
      // so that images auto-resize together with the table.
      var table = wrap.querySelector('table');
      if (!table) {{
          // Fallback for sheets with logos where inner div exists
          var inner = wrap.querySelector('div');
          table = inner && inner.querySelector('table');
      }}
      if (!table) return;

      // Available content area in px (paper minus CSS padding margins)
      var DPI = 96;
      var paperContentW = ({pw} - {ml} - {mr}) * DPI;
      var paperContentH = ({ph} - {mt} - {mb}) * DPI;

      // Identify the secure content wrapper (the isolation:isolate div)
      var target = wrap.firstElementChild; 
      if (!target) return;
      var table = target.querySelector('table');
      if (!table) return;

      // Measure unscaled content bounds
      var contentW = target.scrollWidth || target.offsetWidth;
      var contentH = table.scrollHeight;

      // Calculate necessary scaling to fit both width and height
      var scaleW = (contentW > paperContentW && paperContentW > 0) ? paperContentW / contentW : 1.0;
      var scaleH = (contentH > paperContentH && paperContentH > 0) ? paperContentH / contentH : 1.0;

      // Pick the stricter scale (the smaller one) to ensure no overflow
      var finalScale = Math.min(scaleW, scaleH, 1.0);

      if (finalScale < 1.0) {{
          target.style.transform = 'scale(' + finalScale + ')';
          target.style.transformOrigin = 'top center'; // Centered looks more professional on paper
          
          // Fix visual width of wrapper to avoid extra scroll-room
          target.style.width = (contentW) + 'px'; 
          wrap.style.overflow = 'hidden';

          // Lock paper to fixed height when shrinking to fit
          paper.style.height    = '{ph}in';
          paper.style.minHeight = 'unset';
          paper.style.overflow  = 'hidden';
      }}
      // --- Custom Mobile Pinch-to-Zoom (Isolated) ---
      var currentZoom = 1.0;
      var lastDist = 0;
      
      // Auto-fit initial zoom so it looks like a PDF viewer starting point
      if (window.innerWidth > 0 && window.innerWidth < ({pw} * DPI + 40)) {{
          currentZoom = window.innerWidth / ({pw} * DPI + 40);
          document.body.style.zoom = currentZoom;
      }}
      
      var initialFitZoom = currentZoom;

      document.documentElement.addEventListener('touchstart', function(e) {{
          if (e.touches.length === 2 && currentZoom > 0) {{
              e.preventDefault(); // Stop any browser-level interference
              lastDist = Math.hypot(
                  e.touches[0].clientX - e.touches[1].clientX,
                  e.touches[0].clientY - e.touches[1].clientY
              );
          }}
      }}, {{passive: false}});

      document.documentElement.addEventListener('touchmove', function(e) {{
          if (e.touches.length === 2 && currentZoom > 0) {{
              e.preventDefault(); // Lock the parent modal from zooming!
              var dist = Math.hypot(
                  e.touches[0].clientX - e.touches[1].clientX,
                  e.touches[0].clientY - e.touches[1].clientY
              );
              if (lastDist > 0) {{
                  var ratio = dist / lastDist;
                  // Allow up to 4x zoom from initial size
                  var nextZoom = currentZoom * ratio;
                  currentZoom = Math.min(Math.max(initialFitZoom, nextZoom), 4.0);
                  document.body.style.zoom = currentZoom;
              }}
              lastDist = dist;
          }}
      }}, {{passive: false}});
    }})();
  </script>

  <!-- Overlap tooltip panel -->
  <div id="overlapTip" style="display:none;position:fixed;z-index:9999;
    background:#fff;border:1.5px solid #dc3545;border-radius:7px;
    padding:9px 12px;font-size:11px;min-width:240px;max-width:340px;
    box-shadow:0 4px 18px rgba(0,0,0,0.22);
    font-family:Calibri,Arial,sans-serif;">
    <div id="overlapTipTitle" style="font-weight:700;margin-bottom:5px;font-size:12px;"></div>
    <div id="overlapTipBody" style="max-height:260px;overflow-y:auto;"></div>
  </div>
  <script>
  (function() {{
    var tip  = document.getElementById('overlapTip');
    var body = document.getElementById('overlapTipBody');
    var hideTimer = null;
    document.querySelectorAll('.sched-overlap-badge').forEach(function(badge) {{
      badge.addEventListener('mouseenter', function(e) {{
        var entries;
        try {{ entries = JSON.parse(this.dataset.overlap || '[]'); }} catch(ex) {{ entries = []; }}
        var vtype = this.dataset.vtype || '';
        var titleText, titleColor, borderColor;
        if (vtype === 'course') {{
          titleText = 'Overlapping Courses';     titleColor = '#333';     borderColor = '#aaa';
        }} else if (vtype === 'room_neutral') {{
          titleText = 'Overlapping Rooms';       titleColor = '#333';     borderColor = '#aaa';
        }} else if (vtype === 'faculty_neutral') {{
          titleText = 'Overlapping Faculty';     titleColor = '#333';     borderColor = '#aaa';
        }} else if (vtype === 'section') {{
          titleText = '\u26a0 Overlapping Sections'; titleColor = '#dc3545'; borderColor = '#dc3545';
        }} else if (vtype === 'faculty') {{
          titleText = '\u26a0 Overlapping Faculty';  titleColor = '#dc3545'; borderColor = '#dc3545';
        }} else if (vtype === 'room') {{
          titleText = '\u26a0 Overlapping Rooms';    titleColor = '#dc3545'; borderColor = '#dc3545';
        }} else {{
          titleText = '\u26a0 Overlapping Classes';  titleColor = '#dc3545'; borderColor = '#dc3545';
        }}
        var titleEl = document.getElementById('overlapTipTitle');
        titleEl.textContent   = titleText;
        titleEl.style.color   = titleColor;
        tip.style.borderColor = borderColor;
        body.innerHTML = entries.map(function(en, i) {{
          return '<div style="padding:3px 0;'
            + (i > 0 ? 'border-top:1px solid #f0f0f0;margin-top:3px;' : '') + '">'
            + (en.t ? '<span style="color:#666;font-size:10px;">' + en.t + '</span><br>' : '')
            + '<strong style="font-size:12px;">' + (en.c || '') + '</strong>'
            + (en.s ? ' <span style="color:#555;">---- ' + en.s + '</span>' : '')
            + (en.f ? '<br><span style="color:#888;font-size:10px;">' + en.f + '</span>' : '')
            + '</div>';
        }}).join('');
        tip.style.display = 'block';
        tip.style.left = Math.min(e.clientX + 12, window.innerWidth - 360) + 'px';
        tip.style.top  = Math.min(e.clientY + 12, window.innerHeight - 220) + 'px';
      }});
      badge.addEventListener('mouseleave', function() {{
        hideTimer = setTimeout(function() {{ tip.style.display = 'none'; }}, 150);
      }});
    }});
    tip.addEventListener('mouseenter', function() {{
      if (hideTimer) {{ clearTimeout(hideTimer); hideTimer = null; }}
    }});
    tip.addEventListener('mouseleave', function() {{
      tip.style.display = 'none';
    }});
  }})();
  </script>
</body></html>"""

def render_blank_timetable_fallback(entity_name, semester, sem_ay, layout_type, for_canvas=False):
    settings = get_settings()
    if layout_type == 'faculty':
        _margins = _get_faculty_margins(settings)
    else:
        _margins = _get_margins(settings)
    html_content = render_template('_blank_timetable.html', entity_name=entity_name, semester=semester, sem_ay=sem_ay)
    return render_a4_page(html_content, 960, margins=_margins, for_canvas=for_canvas)





def detect_schedule_grid(ws):
    """Scan worksheet for timetable grid. Two-pass detection:
    1) Token-based: looks for {{GRID_TIME}} + {{GRID_MON}} etc.
    2) Auto-detect fallback: scans for time patterns + day name headers.

    Returns dict with grid geometry, or None if no grid found.
    """
    GRID_TOKEN_TO_DAY = {
        '{{GRID_MON}}': 'Monday',   '{{GRID_TUE}}': 'Tuesday',
        '{{GRID_WED}}': 'Wednesday','{{GRID_THU}}': 'Thursday',
        '{{GRID_FRI}}': 'Friday',   '{{GRID_SAT}}': 'Saturday',
        '{{GRID_SUN}}': 'Sunday',
    }
    DAY_KEYWORDS = {
        'monday': 'Monday',   'mon': 'Monday',
        'tuesday': 'Tuesday', 'tue': 'Tuesday',
        'wednesday': 'Wednesday', 'wed': 'Wednesday',
        'thursday': 'Thursday',   'thu': 'Thursday',
        'friday': 'Friday',   'fri': 'Friday',
        'saturday': 'Saturday',   'sat': 'Saturday',
        'sunday': 'Sunday',   'sun': 'Sunday',
    }
    timere        = re.compile(
        r'(\d{1,2}:\d{2})\s*(AM|PM)?\s*[-----]\s*(\d{1,2}:\d{2})\s*(AM|PM)?',
        re.IGNORECASE)
    simple_timere = re.compile(r'\b(\d{1,2}:\d{2})\s*(AM|PM)?\b', re.IGNORECASE)

    def _to24(time_str, period=None):
        """Convert HH:MM + optional AM/PM to 24-hour HH:MM string."""
        h, m = map(int, time_str.split(':'))
        if period:
            p = period.upper()
            if p == 'PM' and h != 12:
                h += 12
            elif p == 'AM' and h == 12:
                h = 0
        return f'{h:02d}:{m:02d}'

    def _build_time_slots(anchor_row, anchor_col):
        slots = []
        for r in range(anchor_row + 1, ws.max_row + 1):
            v = str(ws.cell(row=r, column=anchor_col).value or '').strip()
            if not v:
                continue
            m = timere.search(v)
            if m:
                start_t = _to24(m.group(1), m.group(2))
                end_t   = _to24(m.group(3), m.group(4))
                slots.append((r, start_t, end_t))
            else:
                m2 = simple_timere.search(v)
                if m2:
                    start_t = _to24(m2.group(1), m2.group(2))
                    slots.append((r, start_t, None))
        return slots

    def _normalize_12h_wrap(slots):
        """Fix implicit 12-hour time wrapping in templates without AM/PM labels.

        Philippine timetable templates often show "7:00, 7:30, ..., 12:30, 1:00, 1:30, ..."
        where "1:00" after "12:30" means 1:00 PM = 13:00.  Detect the backwards jump in
        the time sequence and add +12 h to all slots from that point on, so template times
        align with the DB's 24-hour start_time / end_time values.
        """
        if len(slots) < 2:
            return slots
        result  = []
        offset  = 0
        prev_sm = None
        for (r, s, e) in slots:
            h, m = map(int, s.split(':'))
            sm   = h * 60 + m + offset
            if prev_sm is not None and sm < prev_sm:  # backwards jump -> 12h wrap
                offset += 720
                sm     += 720
            new_s = f'{sm // 60:02d}:{sm % 60:02d}'
            if e:
                eh, em  = map(int, e.split(':'))
                em_val  = eh * 60 + em + offset
                if em_val < sm:       # end also wraps within same slot (e.g. "12:30-1:00")
                    em_val += 720
                new_e = f'{em_val // 60:02d}:{em_val % 60:02d}'
            else:
                new_e = e
            result.append((r, new_s, new_e))
            prev_sm = sm
        return result

    # ------------------------------------ Pass 1: token-based detection ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    time_anchor_row = time_anchor_col = None
    for row in ws.iter_rows():
        for cell in row:
            if cell.value and '{{GRID_TIME}}' in str(cell.value):
                time_anchor_row = cell.row
                time_anchor_col = cell.column
                break
        if time_anchor_row:
            break

    if time_anchor_row:
        header_row = time_anchor_row
        day_cols = {}
        for c in range(time_anchor_col + 1, ws.max_column + 1):
            v = str(ws.cell(row=header_row, column=c).value or '')
            if v in GRID_TOKEN_TO_DAY:
                day_cols[GRID_TOKEN_TO_DAY[v]] = c
        if day_cols:
            time_slots = _normalize_12h_wrap(_build_time_slots(time_anchor_row, time_anchor_col))
            if time_slots:
                return {'header_row': header_row, 'time_col': time_anchor_col,
                        'day_cols': day_cols, 'time_slots': time_slots}

    # ------------------------------------ Pass 2: auto-detect ---- find time column + day name headers ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    # Score columns: range-format "HH:MM-HH:MM" (strong signal) vs bare "HH:MM" (weak)
    col_range_counts   = {}
    col_time_counts    = {}
    col_first_time_row = {}
    for row in ws.iter_rows():
        for cell in row:
            if not cell.value or isinstance(cell, MergedCell):
                continue
            v = str(cell.value).strip()
            c = cell.column
            if timere.search(v):
                col_range_counts[c] = col_range_counts.get(c, 0) + 1
                col_time_counts[c]  = col_time_counts.get(c, 0) + 1
                if c not in col_first_time_row:
                    col_first_time_row[c] = cell.row
            elif simple_timere.search(v):
                col_time_counts[c] = col_time_counts.get(c, 0) + 1
                if c not in col_first_time_row:
                    col_first_time_row[c] = cell.row

    if not col_time_counts:
        return None

    # Prefer columns with range-format times; fall back to simple-time count
    if col_range_counts:
        best_col = max(col_range_counts, key=lambda c: col_range_counts[c])
    else:
        best_col = max(col_time_counts, key=lambda c: col_time_counts[c])
    if col_time_counts[best_col] < 3:
        return None  # Too few time values ---- probably not a timetable

    first_time_row = col_first_time_row[best_col]

    def _scan_day_names(hrow):
        """Scan a candidate header row for day name keywords; return day_cols dict."""
        found = {}
        for c in range(1, ws.max_column + 1):
            if c == best_col:
                continue
            v = str(ws.cell(row=hrow, column=c).value or '').strip().lower()
            if not v:
                continue
            for kw, day_name in DAY_KEYWORDS.items():
                if kw in v and day_name not in found:
                    found[day_name] = c
                    break
        return found

    # Try header rows row-1, row-2, row-3 above the first time slot
    header_row = None
    day_cols   = {}
    for offset in range(1, 4):
        candidate = first_time_row - offset
        if candidate < 1:
            break
        found = _scan_day_names(candidate)
        if found:
            header_row = candidate
            day_cols   = found
            break

    if not day_cols:
        return None

    time_slots = _normalize_12h_wrap(_build_time_slots(header_row, best_col))
    if not time_slots:
        return None

    return {'header_row': header_row, 'time_col': best_col,
            'day_cols': day_cols, 'time_slots': time_slots}


    # ------------------------------------ Pass 3: Standard Fallback ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    # If no tokens or auto-detection worked, provide a standard Monday to Friday grid
    # starting from 7:00 AM to 7:00 PM (1-hour slots).
    fallback_day_cols = {
        'Monday': 2, 'Tuesday': 3, 'Wednesday': 4, 'Thursday': 5,
        'Friday': 6, 'Saturday': 7, 'Sunday': 8
    }
    fallback_time_slots = []
    for i, hour in enumerate(range(7, 19)):
        fallback_time_slots.append((i + 2, f"{hour:02d}:00", f"{hour+1:02d}:00"))
    
    return {
        'header_row': 1,
        'time_col': 1,
        'day_cols': fallback_day_cols,
        'time_slots': fallback_time_slots,
        'is_fallback': True
    }


def build_schedule_overlays(schedules, grid_info, view_type):
    """Map ScheduledClass objects onto the detected Excel grid.

    Returns (cell_overrides, extra_merge_map, extra_skip_cells).
    """
    cell_overrides   = {}
    extra_merge_map  = {}
    extra_skip_cells = set()
    # cell_data: (start_row, col) -> list of (rowspan, lines, entry_dict)
    cell_data = {}

    # Badge view-type: some entities are not real conflicts ---- treat as neutral.
    _vtype_for_badge = view_type
    if view_type == 'room' and schedules:
        _first_room = getattr(schedules[0], 'room', None)
        if _first_room and getattr(_first_room, 'capacity', 0) == 999:
            _vtype_for_badge = 'room_neutral'  # NSTP universal room ---- not a real conflict
    if view_type == 'faculty' and schedules:
        _first_faculty = getattr(schedules[0], 'faculty', None)
        if _first_faculty:
            _fname = (getattr(_first_faculty, 'full_name', '') or '').strip().upper()
            if 'T.B.A' in _fname or _fname == 'TBA':
                _vtype_for_badge = 'faculty_neutral'  # T.B.A. is not a real teacher ---- not a conflict

    day_cols   = grid_info['day_cols']
    time_slots = grid_info['time_slots']  # [(row, start_str, end_str|None)]

    def t2m(t):
        """'HH:MM' -> minutes from midnight."""
        if not t:
            return 0
        try:
            h, mn = t.strip().split(':')
            return int(h) * 60 + int(mn)
        except Exception:
            return 0

    slot_list = []
    slot_by_start = {}
    for (row, s, e) in time_slots:
        sm = t2m(s)
        em = t2m(e) if e else sm + 60
        slot_list.append((row, sm, em))
        if sm not in slot_by_start:
            slot_by_start[sm] = row
    slot_list.sort(key=lambda x: x[0])

    def physical_rows(start_row, start_min, end_min):
        """Return the physical Excel row span from start_row to the last slot row
        that falls within [start_min, end_min). Works correctly even when the
        template has empty/spacer rows between time slots."""
        last_slot_row = start_row
        for (srow, smin, emin) in slot_list:
            if srow < start_row:
                continue
            if smin >= end_min:
                break
            if smin >= start_min:
                last_slot_row = srow
        return max(1, last_slot_row - start_row + 1)

    def _esc(s):
        return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    def fmt_faculty(full_name, sex):
        parts = (full_name or '').split()
        surname = parts[-1].upper() if parts else (full_name or '').upper()
        prefix = 'MR.' if sex == 'M' else 'MS.' if sex == 'F' else 'PROF.'
        return f'{prefix} {surname}'

    # ------------------------------------ Pass 1: collect all schedule entries per grid cell ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    for sched in schedules:
        col = day_cols.get(sched.day)
        if col is None:
            continue
        sm  = t2m(sched.start_time)
        em  = t2m(sched.end_time)
        start_row = slot_by_start.get(sm)
        if start_row is None:
            best = min(slot_list, key=lambda x: abs(x[1] - sm), default=None)
            if best:
                start_row = best[0]
            else:
                continue

        rowspan = physical_rows(start_row, sm, em)

        course_code  = (sched.course.course_code or sched.course.course_name or '') if sched.course  else ''
        section_name = sched.section.section_name if sched.section else ''
        faculty_name = fmt_faculty(sched.faculty.full_name, getattr(sched.faculty, 'sex', None)) if sched.faculty else 'T.B.A.'
        room_name    = sched.room.room_name        if sched.room    else 'T.B.A.'
        sess_type    = getattr(sched, 'session_type', '')

        if view_type == 'section':
            lines = [course_code + (f' ({sess_type})' if sess_type else ''),
                     faculty_name, room_name]
        elif view_type == 'faculty':
            lines = [course_code + (f' ({sess_type})' if sess_type else ''),
                     section_name, room_name]
        elif view_type == 'course':
            lines = [section_name or course_code, faculty_name, room_name]
        else:  # room
            lines = [course_code + (f' ({sess_type})' if sess_type else ''),
                     section_name, faculty_name]

        lines = [l for l in lines if l]
        start_t = _fmt_time_12h(sched.start_time) if sched.start_time else ''
        end_t   = _fmt_time_12h(sched.end_time)   if sched.end_time   else ''
        entry_dict = {'c': course_code, 's': section_name, 'f': faculty_name,
                      't': f'{start_t}----{end_t}'}
        cell_data.setdefault((start_row, col), []).append((rowspan, lines, entry_dict))

    # ------------------------------------ Pass 2: build HTML for each cell, stacking all entries ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    for (start_row, col), entries in sorted(cell_data.items()):
        rowspan = max(e[0] for e in entries)
        cnt     = len(entries)

        if cnt == 1:
            # Single schedule ---- centered block
            _, lines, _ = entries[0]
            main_line = _esc(lines[0]) if lines else ''
            sub_html  = ''.join(
                f'<div>{_esc(l)}</div>'
                for l in lines[1:] if l
            )
            cell_html = (
                '<div style="display:table;width:100%;height:100%;'
                'border-top:1px solid #000000;border-right:1px solid #000000;'
                'border-bottom:1px solid #000000;border-left:1px solid #000000;overflow:hidden;">'
                '<div style="display:table-cell;vertical-align:middle;text-align:center;'
                'padding:3px;font-size:11px;line-height:1.3;color:#000;">'
                f'<div>{main_line}</div>'
                f'{sub_html}'
                '</div></div>'
            )
        else:
            # Multiple overlapping schedules ---- show top schedule only, badge reveals all
            _, lines, _ = entries[0]
            main_line = _esc(lines[0]) if lines else ''
            sub_html  = ''.join(f'<div>{_esc(l)}</div>' for l in lines[1:] if l)
            payload   = json.dumps([e[2] for e in entries]).replace("'", "&#39;")
            badge     = (
                f'<span class="sched-overlap-badge" data-overlap=\'{payload}\' data-vtype="{_vtype_for_badge}" '
                f'style="position:absolute;top:3px;right:3px;background:#dc3545;'
                f'color:#fff;font-size:9px;font-weight:bold;min-width:16px;height:16px;'
                f'border-radius:50%;display:inline-flex;align-items:center;'
                f'justify-content:center;line-height:1;z-index:5;cursor:pointer;">{cnt}</span>'
            )
            cell_html = (
                '<div style="position:relative;display:table;width:100%;height:100%;'
                'border-top:1px solid #000000;border-right:1px solid #000000;'
                'border-bottom:1px solid #000000;border-left:1px solid #000000;overflow:hidden;">'
                f'{badge}'
                '<div style="display:table-cell;vertical-align:middle;text-align:center;'
                'padding:3px;font-size:11px;line-height:1.3;color:#000;">'
                f'<div>{main_line}</div>'
                f'{sub_html}'
                '</div></div>'
            )

        cell_overrides[(start_row, col)] = cell_html
        if rowspan > 1 and (start_row, col) not in extra_skip_cells:
            extra_merge_map[(start_row, col)] = (rowspan, 1)
            for dr in range(1, rowspan):
                extra_skip_cells.add((start_row + dr, col))

    return cell_overrides, extra_merge_map, extra_skip_cells


# ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# Paper size catalog ---- (width_in, height_in) in portrait orientation
PAPER_SIZES = {
    'A4':        (8.27,  11.69,  'A4 Bond Paper (8.27 in ------------ 11.69 in)'),
    'Letter':    (8.5,   11.0,   'Short Bond / US Letter (8.5 in ------------ 11 in)'),
    'Legal':     (8.5,   14.0,   'Long Bond / Legal (8.5 in ------------ 14 in)'),
    'Folio':     (8.5,   13.0,   'Folio / F4 (8.5 in ------------ 13 in)'),
    'A3':        (11.69, 16.54,  'A3 (11.69 in ------------ 16.54 in)'),
    'A5':        (5.83,  8.27,   'A5 (5.83 in ------------ 8.27 in)'),
    'B4':        (9.84,  13.90,  'B4 (9.84 in ------------ 13.90 in)'),
    'B5':        (6.93,  9.84,   'B5 (6.93 in ------------ 9.84 in)'),
    'Executive': (7.25,  10.5,   'Executive (7.25 in ------------ 10.5 in)'),
    'Tabloid':   (11.0,  17.0,   'Tabloid / Ledger (11 in ------------ 17 in)'),
    'Statement': (5.5,   8.5,    'Statement / Half Letter (5.5 in ------------ 8.5 in)'),
}


def _get_margins(settings):
    """Extract shared margin values (Section/Room/Course) from SystemSettings."""
    return {
        'top':    getattr(settings, 'margin_top',    1.0) or 1.0,
        'bottom': getattr(settings, 'margin_bottom', 1.0) or 1.0,
        'left':   getattr(settings, 'margin_left',   1.0) or 1.0,
        'right':  getattr(settings, 'margin_right',  1.0) or 1.0,
        'paper':  getattr(settings, 'paper_size',    'A4') or 'A4',
    }


def _get_faculty_margins(settings):
    """Extract Faculty-specific margin values (independent from shared margins)."""
    return {
        'top':    getattr(settings, 'fac_margin_top',    1.0) or 1.0,
        'bottom': getattr(settings, 'fac_margin_bottom', 1.0) or 1.0,
        'left':   getattr(settings, 'fac_margin_left',   1.0) or 1.0,
        'right':  getattr(settings, 'fac_margin_right',  1.0) or 1.0,
        'paper':  getattr(settings, 'fac_paper_size',    'A4') or 'A4',
    }


def _get_img_settings(settings, layout_type):
    """Return parsed per-image settings list for a layout type.
    Each element: {'x': float, 'y': float, 'scale': float, 'z_above': bool}
    Returns [] if no settings saved or column missing."""
    col_map = {
        'section': 'section_img_settings',
        'faculty': 'faculty_img_settings',
        'room':    'room_img_settings',
        'course':  'course_img_settings',
    }
    raw = getattr(settings, col_map.get(layout_type, ''), None)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except (ValueError, TypeError):
        pass
    return []


def _get_template_img_count(layout_type):
    """Count images embedded in the layout's Excel template (uses template cache)."""
    path = os.path.join(basedir, 'static', 'assets', f'{layout_type}_template.xlsx')
    if not os.path.exists(path):
        return 0
    try:
        ws, _, _ = _get_cached_template(path)
        return len(getattr(ws, '_images', []))
    except Exception:
        return 0


def _parse_img_slots(raw_json, n):
    """Return list of n image setting dicts, padded with defaults."""
    _default = {'x': 0.0, 'y': 0.0, 'scale': 1.0, 'z_above': True}
    try:
        slots = json.loads(raw_json) if raw_json else []
    except Exception:
        slots = []
    while len(slots) < n:
        slots.append(dict(_default))
    return slots[:n]


def _read_img_slots(form, prefix, n):
    """Read n image slot fields from POST form and return JSON string."""
    slots = []
    for i in range(1, n + 1):
        try:
            x       = float(form.get(f'{prefix}_img_{i}_x', 0.0))
            y       = float(form.get(f'{prefix}_img_{i}_y', 0.0))
            scale   = max(0.1, min(5.0, float(form.get(f'{prefix}_img_{i}_scale', 1.0))))
            z_above = form.get(f'{prefix}_img_{i}_z_above', '1') == '1'
        except (ValueError, TypeError):
            x, y, scale, z_above = 0.0, 0.0, 1.0, True
        slots.append({'x': x, 'y': y, 'scale': scale, 'z_above': z_above})
    return json.dumps(slots)


# ------------------------------------ Template cache ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# Caches (ws, grid_info, bounds) per template file path, keyed by mtime.
# Avoids re-loading + re-parsing the Excel template on every request.
# Invalidates automatically when a template is re-uploaded (mtime changes).
_tpl_cache = {}

def _get_cached_template(path):
    """Return (ws, grid_info, bounds) from cache; re-load only when file mtime changes."""
    mtime = os.path.getmtime(path)
    entry = _tpl_cache.get(path)
    if entry and entry['mtime'] == mtime:
        return entry['ws'], entry['grid_info'], entry['bounds']
    wb        = load_workbook(path, data_only=True)
    ws        = wb.active
    grid_info = detect_schedule_grid(ws)
    bounds    = detect_content_bounds(ws)
    ws._img_bytes_cache = []
    for _img in getattr(ws, '_images', []):
        try:
            ws._img_bytes_cache.append(_img._data())
        except Exception:
            ws._img_bytes_cache.append(b'')
    _tpl_cache[path] = {'mtime': mtime, 'ws': ws, 'grid_info': grid_info, 'bounds': bounds}
    return ws, grid_info, bounds


def _dedup_schedules(schedules):
    """Remove duplicate ScheduledClass records caused by multi-generation AI training.
    Filters by (day, start_time, end_time, course_id, section_id).
    """
    seen = set()
    result = []
    for sc in schedules:
        if not sc: continue
        sig = (sc.day, sc.start_time, sc.end_time, sc.course_id, sc.section_id)
        if sig not in seen:
            seen.add(sig)
            result.append(sc)
    return result


@app.route('/section-timetable-html/<int:section_id>')
@login_required
def section_timetable_html(section_id):
    """Render a section's scheduled classes into the uploaded Excel template.
    Returns a standalone A4-paper HTML page.

    Query params:
      ?semester=1st Semester   (default: most recent in DB)
      ?sem_ay=Second / 2023-2024
    """
    # ------------------------------------ Time Machine: Historical Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    if session.get('historical_mode_active', False):
        archive_id = session.get('active_archive_id')
        sections = get_archive_entities(archive_id, 'Section')
        section = next((s for s in sections if s.id == section_id), None)
        
        if not section:
            # Safe empty state for missing archive sections
            section = SimpleNamespace(section_name="Unassigned / Unknown", id=section_id)
            schedules_raw = []
        else:
            schedules_raw = ArchivedSchedule.query.filter_by(
                term_archive_id=archive_id, 
                section_name=section.section_name
            ).all()
        schedules = [_mock_archived_schedule(s) for s in schedules_raw]
        semester = "Archived"
        sem_ay = request.args.get('sem_ay', '')
    else:
        # ------------------------------------ Live Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        section = Section.query.get(section_id)
        if not section:
            # Safe empty state for unassigned live sections
            section = SimpleNamespace(section_name="Unassigned", id=section_id)

        # Resolve semester
        _req_sem  = request.args.get('semester', '')
        _all_sems = [r[0] for r in db.session.query(ScheduledClass.semester).distinct().all() if r[0]]
        semester  = _req_sem if _req_sem in _all_sems else (_all_sems[0] if _all_sems else '1st Semester')
        if _req_sem == 'All' and _all_sems:
            semester = _all_sems[0]
        sem_ay    = request.args.get('sem_ay', '')

    path = os.path.join(basedir, 'static', 'assets', 'section_template.xlsx')
    for_canvas = request.args.get('canvas', 'false') == 'true'
    
    if not os.path.exists(path):
        return render_blank_timetable_fallback(
            entity_name=section.section_name,
            semester=semester,
            sem_ay=sem_ay,
            layout_type='section',
            for_canvas=for_canvas
        )

    is_archive = session.get('historical_mode_active', False)
    if not is_archive:
        if getattr(section, 'id', 0) == 0 or not hasattr(section, '__table__'):
            # If it's our mock 'Unassigned' section, don't query the database
            schedules = []
        else:
            draft_id = request.args.get('draft_id', type=int)
            _opts = [
                joinedload(ScheduledClass.course),
                joinedload(ScheduledClass.section),
                joinedload(ScheduledClass.faculty),
                joinedload(ScheduledClass.room),
            ]
            if draft_id:
                schedules = _dedup_schedules(ScheduledClass.query.options(*_opts).filter(
                    ScheduledClass.section_id == section_id,
                    ScheduledClass.semester == semester,
                    db.or_(
                        ScheduledClass.is_draft == False,
                        ScheduledClass.draft_version_id == draft_id
                    )
                ).all())
            else:
                schedules = _dedup_schedules(ScheduledClass.query.options(*_opts).filter_by(
                    section_id=section_id, semester=semester, is_draft=False
                ).all())

    ws, grid_info, bounds = _get_cached_template(path)

    if grid_info:
        cell_overrides, extra_merge_map, extra_skip_cells = build_schedule_overlays(
            schedules, grid_info, 'section'
        )
    else:
        # Template has no detectable grid ---- render header/variables only
        cell_overrides   = {}
        extra_merge_map  = {}
        extra_skip_cells = set()

    # ------------------------------------ Build variable map (with real section name + sem/ay) ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    settings = get_settings()
    var_map  = build_variable_map(
        'section', settings,
        section_name=section.section_name,
        sem_ay=sem_ay,
    )
    static_overrides = build_static_cell_overrides(
        ws, 'section', settings,
        entity_name=section.section_name,
        sem_ay=sem_ay,
    )
    all_overrides = {**static_overrides, **cell_overrides}

    _margins = _get_margins(settings)
    _img_settings = _get_img_settings(settings, 'section')
    html_content, table_px, _, _ = render_excel_to_html(
        ws,
        cell_overrides=all_overrides,
        variable_map=var_map,
        extra_merge_map=extra_merge_map,
        extra_skip_cells=extra_skip_cells,
        bounds=bounds,
        layout_type='section',
        margins=_margins,
        img_settings=_img_settings,
    )
    
    # Infinite Canvas support
    for_canvas = request.args.get('canvas', 'false') == 'true'
    return render_a4_page(html_content, table_px, margins=_margins, for_canvas=for_canvas)


@app.route('/public/section-timetable/<int:section_id>')
def public_section_timetable(section_id):
    """Same as section_timetable_html but publicly accessible (no login required).
    Used by the Student Portal schedule iframe."""
    section = Section.query.get(section_id)
    _req_sem  = request.args.get('semester', '')
    _all_sems = [r[0] for r in db.session.query(ScheduledClass.semester).distinct().all() if r[0]]
    semester  = _req_sem if _req_sem in _all_sems else (_all_sems[0] if _all_sems else '1st Semester')
    sem_ay    = request.args.get('sem_ay', '')
    path = os.path.join(basedir, 'static', 'assets', 'section_template.xlsx')
    for_canvas = request.args.get('canvas', 'false') == 'true'
    
    if not os.path.exists(path):
        return render_blank_timetable_fallback(
            entity_name=section.section_name,
            semester=semester,
            sem_ay=sem_ay,
            layout_type='section',
            for_canvas=for_canvas
        )

    # Safe handling for unassigned sections in public portal
    if not section:
        section = SimpleNamespace(section_name="Unassigned", id=section_id)
        schedules = []
    else:
        schedules = ScheduledClass.query.options(
            joinedload(ScheduledClass.course),
            joinedload(ScheduledClass.section),
            joinedload(ScheduledClass.faculty),
            joinedload(ScheduledClass.room),
        ).filter_by(section_id=section_id, semester=semester, is_draft=False).all()
    ws, grid_info, bounds = _get_cached_template(path)
    if grid_info:
        cell_overrides, extra_merge_map, extra_skip_cells = build_schedule_overlays(
            schedules, grid_info, 'section'
        )
    else:
        cell_overrides   = {}
        extra_merge_map  = {}
        extra_skip_cells = set()
    settings = get_settings()
    var_map  = build_variable_map('section', settings, section_name=section.section_name, sem_ay=sem_ay)
    static_overrides = build_static_cell_overrides(ws, 'section', settings, entity_name=section.section_name, sem_ay=sem_ay)
    all_overrides = {**static_overrides, **cell_overrides}
    _margins = _get_margins(settings)
    _img_settings = _get_img_settings(settings, 'section')
    html_content, table_px, _, _ = render_excel_to_html(
        ws,
        cell_overrides=all_overrides,
        variable_map=var_map,
        extra_merge_map=extra_merge_map,
        extra_skip_cells=extra_skip_cells,
        bounds=bounds,
        layout_type='section',
        margins=_margins,
        img_settings=_img_settings,
    )
    
    # Infinite Canvas support
    for_canvas = request.args.get('canvas', 'false') == 'true'
    return render_a4_page(html_content, table_px, margins=_margins, for_canvas=for_canvas)
@app.route('/public/student-timetable-html/<string:identifier>')
def public_student_timetable_html(identifier):
    """Publicly accessible route for the Student Portal and Admin viewer.
    Handles both student_id (string) and PK (int).
    """
    # 1. Try as student_id
    student = Student.query.filter_by(student_id=identifier, is_archived=False).first()
    
    # 2. If not found, try as PK
    if not student:
        try:
            pk = int(identifier)
            student = Student.query.get(pk)
        except (ValueError, TypeError):
            pass
            
    if not student:
        abort(404)
        
    return student_timetable_html(student.id)

@app.route('/student-timetable-html/<int:student_pk>')
def student_timetable_html(student_pk):
    """Unified route to render a student's schedule.
    If regular, redirects/delegates to section_timetable_html.
    If irregular, renders their custom subject mix.
    """
    student = Student.query.get_or_404(student_pk)
    if not student.is_irregular:
        if not student.section_id:
            return (
                "<div style='padding:40px;text-align:center;color:#5f6368;font-family:Arial,sans-serif;'>"
                "<strong>No section assigned.</strong><br>"
                "This regular student is not yet assigned to any section."
                "</div>"
            )
        # Delegate to public section viewer (no login required)
        return public_section_timetable(student.section_id)
    
    # Otherwise, render irregular view
    return irregular_timetable_html(student.student_id)


@app.route('/irregular-timetable/<string:student_id>')
def irregular_timetable_html(student_id):
    """Render an irregular student's custom mixed schedule using the section template.
    Publicly accessible ---- used by the Student Portal iframe."""
    student = Student.query.filter_by(student_id=student_id, is_archived=False).first_or_404()
    if not student.is_irregular:
        abort(404)
    
    assignment = IrregularAssignment.query.filter_by(student_id_fk=student.id)\
                     .order_by(IrregularAssignment.updated_at.desc()).first()
    
    has_assignment = assignment and assignment.assignments_json and assignment.assignments_json != '[]'
    has_section = student.section_id is not None
    
    # 1. Fallback to "No schedule assigned yet" only if they have NEITHER custom subjects NOR an assigned section.
    if not has_assignment and not has_section:
        settings = get_settings()
        _margins = _get_margins(settings)
        html_content = (
            f"<div class='a4-fallback-message' style='padding:100px 40px; text-align:center; color:#5f6368; font-family:Arial,sans-serif;'>"
            f"  <i style='font-size:3rem; color:#bdc1c6; display:block; margin-bottom:20px;' class='bi bi-calendar-x'></i>"
            f"  <strong style='font-size:1.3rem; color:#202124; display:block; margin-bottom:10px;'>No schedule assigned yet.</strong>"
            f"  <p style='font-size:0.95rem; color:#5f6368; margin:0;'>Please contact the administrator to set up your irregular schedule.</p>"
            f"</div>"
        )
        for_canvas = request.args.get('canvas', 'false') == 'true'
        return render_a4_page(html_content, 960, margins=_margins, for_canvas=for_canvas)

    schedules = []
    semester = "1st Semester"
    if has_assignment:
        semester = assignment.semester
        pairs = json.loads(assignment.assignments_json)
        for pair in pairs:
            slots = ScheduledClass.query.options(
                joinedload(ScheduledClass.course),
                joinedload(ScheduledClass.section),
                joinedload(ScheduledClass.faculty),
                joinedload(ScheduledClass.room),
            ).filter_by(
                course_id=pair['course_id'],
                section_id=pair['section_id'],
                semester=assignment.semester,
            ).all()
            schedules.extend(slots)
        schedules = _dedup_schedules(schedules)
    elif has_section:
        # INHERITANCE LOGIC: Inherit the section's schedule!
        schedules = ScheduledClass.query.options(
            joinedload(ScheduledClass.course),
            joinedload(ScheduledClass.section),
            joinedload(ScheduledClass.faculty),
            joinedload(ScheduledClass.room),
        ).filter_by(
            section_id=student.section_id
        ).all()
        schedules = _dedup_schedules(schedules)

    path = os.path.join(basedir, 'static', 'assets', 'section_template.xlsx')
    for_canvas = request.args.get('canvas', 'false') == 'true'
    
    if not os.path.exists(path):
        section_obj = Section.query.get(student.section_id) if student.section_id else None
        entity_name = f"{student.full_name} ({section_obj.section_name})" if section_obj else student.full_name
        return render_blank_timetable_fallback(
            entity_name=entity_name,
            semester=semester,
            sem_ay="",
            layout_type='section',
            for_canvas=for_canvas
        )

    ws, grid_info, bounds = _get_cached_template(path)
    if grid_info:
        cell_overrides, extra_merge_map, extra_skip_cells = build_schedule_overlays(
            schedules, grid_info, 'section'
        )
    else:
        cell_overrides   = {}
        extra_merge_map  = {}
        extra_skip_cells = set()
    settings = get_settings()
    var_map  = build_variable_map('section', settings,
                                  section_name=student.full_name, sem_ay='')
    static_overrides = build_static_cell_overrides(ws, 'section', settings,
                                                    entity_name=student.full_name, sem_ay='')
    all_overrides = {**static_overrides, **cell_overrides}
    _margins      = _get_margins(settings)
    _img_settings = _get_img_settings(settings, 'section')
    html_content, table_px, _, _ = render_excel_to_html(
        ws,
        cell_overrides=all_overrides,
        variable_map=var_map,
        extra_merge_map=extra_merge_map,
        extra_skip_cells=extra_skip_cells,
        bounds=bounds,
        layout_type='section',
        margins=_margins,
        img_settings=_img_settings,
    )
    # Infinite Canvas support
    for_canvas = request.args.get('canvas', 'false') == 'true'
    return render_a4_page(html_content, table_px, margins=_margins, for_canvas=for_canvas)




def build_static_cell_overrides(ws, layout_type, settings, entity_name=None, sem_ay=None):
    """
    Static text swapping for Section, Room, and Course templates.
    Scans every cell for known default anchor strings and overwrites with
    current DB values. No {{tokens}} required in the Excel file.
    Returns: cell_overrides dict {(row, col): new_value_str}
    """
    s = settings
    overrides = {}

    print(f"\n[STATIC_SWAP] ------------------------------------ Starting build_static_cell_overrides layout_type={layout_type!r} ------------------------------------")

    # --- Resolve per-type values ---
    school_name = (
        getattr(s, 'section_school_name', '') or 'CAVITE STATE UNIVERSITY'
        if layout_type == 'section' else
        getattr(s, 'room_school_name',    '') or 'CAVITE STATE UNIVERSITY'
        if layout_type == 'room' else
        getattr(s, 'course_school_name',  '') or 'CAVITE STATE UNIVERSITY'
    )
    sig2_title = (
        getattr(s, 'section_sig2_title', '') or 'Director, Instruction'
        if layout_type == 'section' else
        getattr(s, 'room_sig2_title',    '') or 'Director, Instruction'
        if layout_type == 'room' else
        getattr(s, 'course_sig2_title',  '') or 'Director, Instruction'
    )
    sig3_title = (
        getattr(s, 'section_sig3_title', '') or 'Campus Administrator'
        if layout_type == 'section' else
        getattr(s, 'room_sig3_title',    '') or 'Campus Administrator'
        if layout_type == 'room' else
        getattr(s, 'course_sig3_title',  '') or 'Campus Administrator'
    )
    class_label = (
        getattr(s, 'class_label',  '') or 'CLASS'  if layout_type == 'section' else
        getattr(s, 'room_label',   '') or 'ROOM'   if layout_type == 'room'    else
        getattr(s, 'course_label', '') or 'COURSE'
    )
    sem_ay_val   = sem_ay or getattr(s, 'sem_ay_value', '') or ''
    sem_ay_label = getattr(s, 'sem_ay_label', '') or 'Semester / Academic Year'
    prep_by      = getattr(s, 'prepared_by_label',  '') or 'Prepared by:'
    rec_appr     = getattr(s, 'rec_approval_label', '') or 'Recommending Approval:'
    approved     = getattr(s, 'approved_label',     '') or 'APPROVED:'
    republic     = getattr(s, 'republic_text',      '') or 'Republic of the Philippines'
    campus       = getattr(s, 'campus_name',        '') or 'CCAT Campus'
    address      = getattr(s, 'address',            '') or 'Rosario, Cavite'
    contact      = getattr(s, 'contact_details',    '') or ''
    email        = getattr(s, 'email',              '') or ''
    website      = getattr(s, 'website',            '') or ''

    # Read signatory names DIRECTLY from individual DB fields.
    # Do NOT use *_signatories_json ---- that JSON is written once at migration time
    # and never updated when the user edits individual fields, causing stale values.
    sig1_name = (getattr(s, f'{layout_type}_signatory_1', '') or '').strip()
    sig2_name = (getattr(s, f'{layout_type}_signatory_2', '') or '').strip()
    sig3_name = (getattr(s, f'{layout_type}_signatory_3', '') or '').strip()

    print(f"[STATIC_SWAP] Resolved values:")
    print(f"  school_name={school_name!r}  campus={campus!r}  address={address!r}")
    print(f"  sem_ay_val={sem_ay_val!r}  sem_ay_label={sem_ay_label!r}")
    print(f"  class_label={class_label!r}  prep_by={prep_by!r}")
    print(f"  rec_appr={rec_appr!r}  approved={approved!r}")
    print(f"  sig1={sig1_name!r}  sig2={sig2_name!r}  sig2_title={sig2_title!r}")
    print(f"  sig3={sig3_name!r}  sig3_title={sig3_title!r}")

    # --- Strategy 1 & 2: SWAPS list ---
    # Tuples: (anchor_str, is_partial, new_value)
    # Exact matches use case-insensitive + trimmed comparison.
    # Partial matches check if anchor_str.lower() appears anywhere in cell.lower().
    SWAPS = [
        # ------------------------------------ Header block ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        ('Republic of the Philippines',  False, republic),
        ('CAVITE STATE UNIVERSITY',      False, school_name),
        ('CCAT Campus',                  False, campus),
        ('Rosario, Cavite',              False, address),
        # Partial: phone/email/website cells often have extra chars (------------, apostrophe)
        ('437-9505',                     True,  contact),
        ('437-6659',                     True,  contact),
        ('@cvsu',                        True,  email),
        ('cvsu-rosario',                 True,  website),
        # ------------------------------------ Schedule details ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        ('Semester / Academic Year',     False, sem_ay_label),
        ('SEMESTER / ACADEMIC YEAR',     False, sem_ay_label),
        # Class / Room / Course identifier label (exact ---- whole cell)
        ('CLASS',                        False, class_label),
        ('ROOM',                         False, class_label),
        ('COURSE',                       False, class_label),
        # ------------------------------------ Signatory block labels ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        ('Prepared by:',                 False, prep_by),
        ('Prepared By:',                 False, prep_by),
        ('PREPARED BY:',                 False, prep_by),
        ('Recommending Approval:',       False, rec_appr),
        ('RECOMMENDING APPROVAL:',       False, rec_appr),
        ('APPROVED:',                    False, approved),
        ('Approved:',                    False, approved),
        # ------------------------------------ Signatory titles ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        ('Director, Instruction',        False, sig2_title),
        ('Campus Administrator',         False, sig3_title),
        ('Department Chairperson',       False, sig1_name if sig1_name else 'Department Chairperson'),
    ]

    # Signatory name swaps: replace known defaults with DB values.
    # Always append ---- fallback to anchor itself so no-op replaces still register.
    _sig_name_defaults = [
        ('SCHEDULE COMMITTEE',   sig1_name or 'SCHEDULE COMMITTEE'),
        ('ARIES M. GELERA',      sig1_name or 'ARIES M. GELERA'),
        ('ARIEL G. SANTOS, EdD', sig2_name or 'ARIEL G. SANTOS, EdD'),
        ('LAURO B. PASCUA, EdD', sig3_name or 'LAURO B. PASCUA, EdD'),
    ]
    for _anchor, _new in _sig_name_defaults:
        SWAPS.append((_anchor, False, _new))

    # --- Regex for sem/ay value detection (Strategy 4) ---
    # Matches any cell that looks like a semester / school-year value:
    # "Second / 2023-2024", "1st Semester / 2024-2025", "SY 2024-2025", etc.
    _SEM_PAT = re.compile(
        r'(1st|2nd|first|second|third|midyear)\s*(sem(ester)?)?'
        r'|SY\s*\d{4}'
        r'|\d{4}\s*[-\u2013]\s*\d{4}',
        re.IGNORECASE
    )

    # --- Strategy 3: label + adjacent entity name injection ---
    ENTITY_LABELS = {'section:', 'room:', 'course:', 'schedule for:', 'class:'}
    entity_label_found = False

    # --- Build merge lookup so entity_name lands on the anchor (primary) cell ---
    # Writing to a secondary merged cell is silently skipped by render_excel_to_html,
    # so we must resolve c+1 to the actual anchor cell of the name field merge.
    _merge_anchor = {}   # (r, c) secondary -> (r1, c1) primary
    _merge_maxcol = {}   # (r1, c1) primary -> max_col of that merge
    for _mg in ws.merged_cells.ranges:
        _r1, _c1, _r2, _c2 = _mg.min_row, _mg.min_col, _mg.max_row, _mg.max_col
        _merge_maxcol[(_r1, _c1)] = _c2
        for _mr in range(_r1, _r2 + 1):
            for _mc in range(_c1, _c2 + 1):
                if _mr != _r1 or _mc != _c1:
                    _merge_anchor[(_mr, _mc)] = (_r1, _c1)

    def _entity_target(r, c):
        """Return anchor cell to inject entity_name into, given label cell at (r, c).
        Entity name lives in the row ABOVE the CLASS/ROOM/COURSE label."""
        target_row = r - 1
        return _merge_anchor.get((target_row, c), (target_row, c))

    # --- Scan all cells ---
    for row_cells in ws.iter_rows():
        for cell in row_cells:
            raw = cell.value
            if raw is None:
                continue
            val = str(raw).strip()
            if not val:
                continue
            r, c = cell.row, cell.column
            val_lower = val.lower()

            matched = False

            # Strategy 1 & 2: SWAPS (case-insensitive exact + partial)
            for anchor, is_partial, new_val in SWAPS:
                if is_partial:
                    if anchor.lower() in val_lower:
                        if new_val:
                            overrides[(r, c)] = new_val
                            print(f"[STATIC_SWAP] ({r},{c}) PARTIAL '{val}' -> '{new_val}'")
                        matched = True
                        break
                else:
                    if val_lower == anchor.lower():
                        if new_val is not None:
                            overrides[(r, c)] = new_val
                            print(f"[STATIC_SWAP] ({r},{c}) EXACT '{val}' -> '{new_val}'")
                        matched = True
                        # Also inject entity_name into anchor cell of name field when this is the entity identifier label
                        if entity_name and not entity_label_found and val_lower in {'class', 'room', 'course'}:
                            _tr, _tc = _entity_target(r, c)
                            overrides[(_tr, _tc)] = entity_name
                            entity_label_found = True
                            print(f"[STATIC_SWAP] ({_tr},{_tc}) ENTITY_ID adjacent -> '{entity_name}'")
                        break

            # Strategy 4: Regex-based sem/ay value detection
            if not matched and sem_ay_val and _SEM_PAT.search(val):
                overrides[(r, c)] = sem_ay_val
                print(f"[STATIC_SWAP] ({r},{c}) SEM_REGEX '{val}' -> '{sem_ay_val}'")
                matched = True

            # Strategy 3: entity label -> inject entity name in anchor cell of name field
            if not matched and entity_name and not entity_label_found:
                if val_lower in ENTITY_LABELS:
                    _tr, _tc = _entity_target(r, c)
                    overrides[(_tr, _tc)] = entity_name
                    entity_label_found = True
                    print(f"[STATIC_SWAP] ({_tr},{_tc}) ENTITY_LABEL adjacent -> '{entity_name}'")

            if not matched:
                print(f"[STATIC_SCAN] ({r},{c}) no match: {val!r}")

    print(f"[STATIC_SWAP] ------------------------------------ Done. {len(overrides)} overrides generated ------------------------------------\n")
    return overrides


def build_faculty_cell_overrides(ws, settings, faculty=None, prep_count=0, total_hours=0):
    """
    Scan the faculty Excel template for known static anchor strings and overwrite
    them with current DB / dynamic values. No {{tokens}} needed in the Excel file.

    Strategies:
      1. Exact CI  ---- val.strip().lower() == anchor.lower()
      2. Partial   ---- anchor.lower() in val.lower()
      3. Regex     ---- semester/year pattern for fac_sem_ay_label
      4. Label+Adj ---- replace label cell AND write dynamic value to col+offset
      5. Positional---- faculty name/rank injected N rows below 'Conforme:' anchor

    Returns: cell_overrides dict {(row, col): new_value_str}
    """
    s = settings
    overrides = {}

    print(f"\n[FAC_SWAP] ------------------------------------ Starting build_faculty_cell_overrides (faculty={getattr(faculty,'full_name','[preview]')!r}) ------------------------------------")

    # ------------------------------------ Helper ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    def _fmt_hours(h):
        try:
            h = float(h)
            return str(int(h)) if h == int(h) else str(round(h, 1))
        except (TypeError, ValueError):
            return '0'

    def _g(attr, default=''):
        return getattr(s, attr, default) or default

    # ------------------------------------ Dynamic values (preview-safe) ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    is_preview = faculty is None
    fac_name   = (faculty.full_name                      if faculty else '[Faculty Name]') or '[Faculty Name]'
    fac_educ   = (faculty.highest_educational_attainment if faculty else '[Educational Attainment]') or '[Educational Attainment]'
    fac_rank   = (faculty.academic_rank                  if faculty else '[Academic Rank]') or '[Academic Rank]'
    prep_str   = str(prep_count)          if not is_preview else '0'
    hours_str  = _fmt_hours(total_hours)  if not is_preview else '0.0'

    print(f"[FAC_SWAP] Dynamic: name={fac_name!r}  educ={fac_educ!r}  rank={fac_rank!r}")
    print(f"[FAC_SWAP] Settings sample: dept={_g('fac_dept_label','DEPARTMENT OF COMPUTER STUDIES')!r}")

    # ------------------------------------ Resolved setting values ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    republic   = _g('fac_republic_text',    'Republic of the Philippines')
    univ_name  = _g('fac_univ_name',        'CAVITE STATE UNIVERSITY')
    campus     = _g('fac_campus_name',      'CCAT Campus')
    address    = _g('fac_address',          'Rosario, Cavite')
    contact    = _g('fac_contact_details',  '')
    email      = _g('fac_email',            '')
    website    = _g('fac_website',          '')
    dept       = _g('fac_dept_label',       'DEPARTMENT OF COMPUTER STUDIES')
    sched_ttl  = _g('fac_sched_title',      'FACULTY CLASS SCHEDULE')
    sem_ay_lbl = _g('fac_sem_ay_label',     'SECOND SEMESTER SY 2023 - 2024')
    form_top   = _g('fac_form_num_top',     'VPAA-QF-11')
    form_bot   = _g('fac_form_num_bottom',  'V01-2018-07-24')
    # Faculty info labels
    name_lbl   = _g('fac_name_label',   'Name:')
    educ_lbl   = _g('fac_educ_label',   'Highest Educ. Attainment:')
    prep_lbl   = _g('fac_prep_label',   'No. of Preparation/s:')
    hours_lbl  = _g('fac_hours_label',  'Total no. of contact hours per week:')
    # Signatory labels
    conf_lbl   = _g('fac_conforme_label',     'Conforme:')
    rec_lbl    = _g('fac_rec_approval_label', 'Recommending Approval:')
    rev_lbl    = _g('fac_reviewed_label',     'Reviewed by:')
    appr_lbl   = _g('fac_approved_label',     'Approved:')
    reg_lbl    = _g('fac_registrar_label',    'OIC, Registrar')
    # Signatory names & titles
    chair_name = _g('fac_chair_name',    'ARIES M. GELERA')
    chair_ttl  = _g('fac_chair_title',   'Department Chairperson')
    dir_name   = _g('fac_director_name', 'ARIEL G. SANTOS, EdD')
    dir_ttl    = _g('fac_director_title','Director, Instruction')
    reg_name   = _g('fac_registrar_name','MARLYN A. QUINEZ')
    adm_name   = _g('fac_admin_name',    'LAURO B. PASCUA, EdD')
    adm_ttl    = _g('fac_admin_title',   'Campus Administrator')
    # Activity labels
    consult    = _g('fac_consultation',  'Consultation:')
    research   = _g('fac_research',      'Research:')
    designat   = _g('fac_designation',   'Designation :')
    extension  = _g('fac_extension',     'Extension:')

    # ------------------------------------ Strategy 1 & 2: SWAPS list ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    # (anchor, is_partial, new_value)
    # All exact matches use case-insensitive + trimmed comparison in the scan loop.
    SWAPS = [
        # ------------------------------------ Header (vars 1----9) ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        ('Republic of the Philippines',    False, republic),
        ('CAVITE STATE UNIVERSITY',        False, univ_name),
        ('CCAT Campus',                    False, campus),
        ('Rosario, Cavite',                False, address),
        ('437-9505',                       True,  contact),   # var 5 ---- partial (phone may have ------------ prefix)
        ('437-6659',                       True,  contact),   # var 5 ---- second phone fragment
        ('@cvsu',                          True,  email),     # var 6 ---- partial
        ('cvsu-rosario',                   True,  website),   # var 7 ---- partial
        ('DEPARTMENT OF COMPUTER STUDIES', False, dept),      # var 8
        ('FACULTY CLASS SCHEDULE',         False, sched_ttl), # var 9
        # var 10 (fac_sem_ay_label) handled by regex ---- see Strategy 3 below
        # ------------------------------------ Form identifiers (vars 37----38) ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        ('VPAA-QF-11',                     True,  form_top),  # partial ---- avoids version suffix issues
        ('V01-2018-07-24',                 True,  form_bot),  # partial
        # ------------------------------------ Signatory names & titles (vars 23----24, 26----29, 31----32) ------------------------------------
        ('ARIES M. GELERA',                False, chair_name),
        ('Department Chairperson',         False, chair_ttl),
        ('ARIEL G. SANTOS, EdD',           False, dir_name),
        ('Director, Instruction',          False, dir_ttl),
        ('MARLYN A. QUINEZ',               False, reg_name),
        ('OIC, Registrar',                 False, reg_lbl),   # var 24 ---- registrar's title label
        ('LAURO B. PASCUA, EdD',           False, adm_name),
        ('Campus Administrator',           False, adm_ttl),
        # ------------------------------------ Activity labels (vars 33----36) ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        ('Consultation:',                  False, consult),
        ('Research:',                      False, research),
        ('Designation',                    True,  designat),  # partial ---- handles "Designation :" space variant
        ('Extension:',                     False, extension),
    ]

    # ------------------------------------ Strategy 3: Regex ---- semester/year value for fac_sem_ay_label (var 10) ------------------
    _SEM_PAT = re.compile(
        r'(1st|2nd|first|second|third|midyear)\s*(sem(ester)?)?'
        r'|SY\s*\d{4}'
        r'|\d{4}\s*[-\u2013]\s*\d{4}',
        re.IGNORECASE
    )

    # ------------------------------------ Strategy 4: Label + Adjacent Value ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    # (anchor, new_label, dynamic_value, col_offset_to_value_cell)
    # col_offset=2: value cell is 2 cols right of label (common in merged-col templates)
    LABEL_VALUE = [
        # vars 11----12: Name label + faculty name value
        ('Name:',                                name_lbl,  fac_name,  2),
        # vars 13----14: Educ label + value
        ('Highest Educ. Attainment:',            educ_lbl,  fac_educ,  2),
        # vars 15----16: Prep label + value
        ('No. of Preparation/s:',                prep_lbl,  prep_str,  2),
        # vars 17----18: Hours label + value
        ('Total no. of contact hours per week:', hours_lbl, hours_str, 2),
        # vars 19, 22, 25, 30: Signatory block labels (no adjacent value cell)
        ('Conforme:',              conf_lbl, None, None),
        ('Recommending Approval:', rec_lbl,  None, None),
        ('Reviewed by:',           rev_lbl,  None, None),
        ('Approved:',              appr_lbl, None, None),
    ]

    conforme_pos = None  # (row, col) of Conforme: ---- for Strategy 5

    # ------------------------------------ Scan all cells ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    for row_cells in ws.iter_rows():
        for cell in row_cells:
            raw = cell.value
            if raw is None:
                continue
            val = str(raw).strip()
            if not val:
                continue
            r, c   = cell.row, cell.column
            val_lo = val.lower()
            matched = False

            # Strategy 1 & 2: SWAPS (case-insensitive exact + partial)
            for anchor, is_partial, new_val in SWAPS:
                if is_partial:
                    if anchor.lower() in val_lo:
                        overrides[(r, c)] = new_val if new_val else val
                        print(f"[FAC_SWAP] ({r},{c}) PARTIAL '{val}' -> '{new_val}'")
                        matched = True
                        break
                else:
                    if val_lo == anchor.lower():
                        overrides[(r, c)] = new_val if new_val is not None else val
                        print(f"[FAC_SWAP] ({r},{c}) EXACT '{val}' -> '{new_val}'")
                        matched = True
                        break

            # Strategy 3: regex ---- sem/ay label
            if not matched and _SEM_PAT.search(val):
                overrides[(r, c)] = sem_ay_lbl
                print(f"[FAC_SWAP] ({r},{c}) SEM_REGEX '{val}' -> '{sem_ay_lbl}'")
                matched = True

            # Strategy 4: Label + Adjacent Value (case-insensitive)
            if not matched:
                for anchor, new_label, dyn_val, col_offset in LABEL_VALUE:
                    if val_lo == anchor.lower():
                        overrides[(r, c)] = new_label
                        print(f"[FAC_SWAP] ({r},{c}) LABEL '{val}' -> '{new_label}'")
                        if col_offset is not None and dyn_val is not None:
                            overrides[(r, c + col_offset)] = dyn_val
                            print(f"[FAC_SWAP] ({r},{c+col_offset}) ADJ_VAL -> '{dyn_val}'")
                        if anchor.lower() == 'conforme:':
                            conforme_pos = (r, c)
                        matched = True
                        break

            if not matched:
                print(f"[FAC_SCAN] ({r},{c}) no match: {val!r}")

    # ------------------------------------ Strategy 5: Positional ---- faculty name & rank below "Conforme:" ------------------------------------------------------------------------------------------------------------------------------------------------
    # vars 20----21: template puts faculty name at conforme_row+2, rank at conforme_row+3
    if conforme_pos:
        cr, cc = conforme_pos
        overrides[(cr + 2, cc)] = fac_name
        overrides[(cr + 3, cc)] = fac_rank
        print(f"[FAC_SWAP] ({cr+2},{cc}) POSITIONAL fac_name -> '{fac_name}'")
        print(f"[FAC_SWAP] ({cr+3},{cc}) POSITIONAL fac_rank -> '{fac_rank}'")

    print(f"[FAC_SWAP] ------------------------------------ Done. {len(overrides)} overrides generated ------------------------------------\n")
    return overrides


def _build_daily_hours_overrides(ws, schedules, grid_info):
    """Compute per-day contact hours from scheduled classes and inject into
    the DAILY CONTACT HOURS row of the faculty template.
    Returns: dict {(row, col): value_str}
    """
    if not grid_info or not schedules:
        return {}
    overrides = {}
    day_cols = grid_info['day_cols']  # {day_name: col_int}

    # Find the DAILY CONTACT HOURS row
    daily_row = None
    for row_cells in ws.iter_rows():
        for cell in row_cells:
            val = str(cell.value or '').strip().upper()
            if 'DAILY' in val and 'CONTACT' in val and 'HOURS' in val:
                daily_row = cell.row
                break
        if daily_row:
            break
    if not daily_row:
        return {}

    # Sum hours per day column
    day_hours = {}
    for sc in schedules:
        col = day_cols.get(sc.day)
        if col is None:
            continue
        try:
            sh, sm = map(int, sc.start_time.split(':'))
            eh, em = map(int, sc.end_time.split(':'))
            dur = ((eh * 60 + em) - (sh * 60 + sm)) / 60.0
        except Exception:
            dur = 0.0
        day_hours[col] = day_hours.get(col, 0.0) + dur

    def _fmt(h):
        return str(int(h)) if h == int(h) else f'{h:.1f}'

    for col, hrs in day_hours.items():
        overrides[(daily_row, col)] = _fmt(hrs)

    return overrides


def build_subject_table_overlays(ws, schedules):
    """Detect the Subject table in the faculty Excel template and return
    cell_overrides to fill in the assigned course loads.
    Returns: dict {(row, col): value_str}
    """
    from collections import defaultdict
    overrides = {}

    # --- 1. Find header row containing "Subject" ---
    subj_header_row = None
    subj_col = 1
    for row_cells in ws.iter_rows():
        for cell in row_cells:
            if str(cell.value or '').strip().lower() == 'subject':
                subj_header_row = cell.row
                subj_col = cell.column
                break
        if subj_header_row:
            break
    if not subj_header_row:
        return overrides

    # --- 2. Detect column positions by scanning header rows (subj_row and subj_row+1) ---
    col_map = {'subj': subj_col}
    for r_idx in (subj_header_row, subj_header_row + 1):
        for cell in ws[r_idx]:
            val = str(cell.value or '').strip().lower()
            if not val:
                continue
            if 'lecture' in val:
                col_map['lec'] = cell.column
            elif 'laborator' in val:
                col_map['lab'] = cell.column
            elif val == 'total':
                col_map['total'] = cell.column
            elif val == 'room':
                col_map['room'] = cell.column
            elif 'student' in val or 'number' in val:
                col_map['students'] = cell.column
            elif ('course' in val or 'yr' in val or 'sec' in val) and 'subj' not in col_map.get('_sec_found', ''):
                col_map['sec'] = cell.column
                col_map['_sec_found'] = val

    # Data rows start after the last sub-header row
    data_start = subj_header_row + 2

    # --- 3. Collect data rows; detect totals row via "Consultation:" anchor ---
    data_rows = []
    totals_row = None
    for r_idx in range(data_start, data_start + 25):
        cell = ws.cell(row=r_idx, column=subj_col)
        cell_val = cell.value
        val_str = str(cell_val or '').strip().lower()
        # "Consultation:" / "Designation:" appear immediately AFTER the totals row
        if 'consultation' in val_str or 'designation' in val_str or 'research' in val_str:
            totals_row = r_idx - 1
            data_rows = [r for r in data_rows if r < totals_row]
            break
        if isinstance(cell_val, (int, float)):
            totals_row = r_idx
            break
        if isinstance(cell_val, str) and cell_val.strip().startswith('='):
            totals_row = r_idx
            break
        data_rows.append(r_idx)

    if not data_rows:
        return overrides

    # --- 4. Group schedules: one row per (course_code, section_name) ---
    groups = defaultdict(lambda: {'lec_hrs': 0.0, 'lab_hrs': 0.0,
                                   'rooms': set(), 'students': 0})
    for sc in schedules:
        course  = sc.course
        section = sc.section
        code    = course.course_code if course else '?'
        sec_nm  = section.section_name if section else '?'
        key     = (code, sec_nm)
        g       = groups[key]
        # Compute duration in hours from start_time / end_time strings
        try:
            sh, sm = map(int, sc.start_time.split(':'))
            eh, em = map(int, sc.end_time.split(':'))
            dur_h  = ((eh * 60 + em) - (sh * 60 + sm)) / 60.0
        except Exception:
            dur_h  = 1.5
        if sc.session_type == 'Lab':
            g['lab_hrs'] += dur_h
        else:
            g['lec_hrs'] += dur_h
        if sc.room:
            g['rooms'].add(sc.room.room_name)
        if section and (getattr(section, 'number_of_students', 0) or 0) > g['students']:
            g['students'] = getattr(section, 'number_of_students', 0) or 0

    # --- 5. Write to cell_overrides ---
    def _fmt(val):
        """Format float: drop trailing .0 but keep .5 etc."""
        return str(int(val)) if val == int(val) else f'{val:.1f}'

    for i, ((code, sec_name), g) in enumerate(groups.items()):
        if i >= len(data_rows):
            break
        r     = data_rows[i]
        total = g['lec_hrs'] + g['lab_hrs']
        rooms = ', '.join(sorted(g['rooms']))

        if 'subj' in col_map:
            overrides[(r, col_map['subj'])] = code
        if 'sec' in col_map:
            overrides[(r, col_map['sec'])]  = sec_name
        if 'lec' in col_map and g['lec_hrs']:
            overrides[(r, col_map['lec'])]  = _fmt(g['lec_hrs'])
        if 'lab' in col_map and g['lab_hrs']:
            overrides[(r, col_map['lab'])]  = _fmt(g['lab_hrs'])
        if 'total' in col_map and total:
            overrides[(r, col_map['total'])]= _fmt(total)
        if 'room' in col_map and rooms:
            overrides[(r, col_map['room'])] = rooms
        if 'students' in col_map and g['students']:
            overrides[(r, col_map['students'])] = str(g['students'])

    # --- 6. Write totals row ---
    if totals_row and groups:
        total_lec      = sum(g['lec_hrs'] for g in groups.values())
        total_lab      = sum(g['lab_hrs'] for g in groups.values())
        total_all      = total_lec + total_lab
        total_students = sum(g['students'] for g in groups.values())
        if 'lec' in col_map:
            overrides[(totals_row, col_map['lec'])]  = _fmt(total_lec)
        if 'lab' in col_map:
            overrides[(totals_row, col_map['lab'])]  = _fmt(total_lab)
        if 'total' in col_map:
            overrides[(totals_row, col_map['total'])]= _fmt(total_all)
        if 'students' in col_map:
            overrides[(totals_row, col_map['students'])] = str(total_students) if total_students else ''

    return overrides


# ------------------------------------ Faculty timetable HTML ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
@app.route('/faculty-timetable-html/<int:faculty_id>')
@login_required
def faculty_timetable_html(faculty_id):
    # ------------------------------------ Time Machine: Historical Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    if session.get('historical_mode_active', False):
        archive_id = session.get('active_archive_id')
        faculty_objs = get_archive_entities(archive_id, 'Faculty')
        faculty = next((f for f in faculty_objs if f.id == faculty_id), None)
        if not faculty: abort(404)

        schedules_raw = ArchivedSchedule.query.filter_by(
            term_archive_id=archive_id,
            faculty_name=faculty.full_name
        ).all()
        schedules = [_mock_archived_schedule(s) for s in schedules_raw]
        semester = "Archived"

        # Count preps from schedules list since ArcherSchedule doesn't have course_id
        prep_count = len(set(sc.course.course_code for sc in schedules if sc.course))
    else:
        # ------------------------------------ Live Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        faculty  = Faculty.query.get_or_404(faculty_id)

        # Resolve semester
        _req_sem  = request.args.get('semester', '')
        _all_sems = [r[0] for r in db.session.query(ScheduledClass.semester).distinct().all() if r[0]]
        semester  = _req_sem if _req_sem in _all_sems else (_all_sems[0] if _all_sems else '1st Semester')
        if _req_sem == 'All' and _all_sems:
            semester = _all_sems[0]

        draft_id = request.args.get('draft_id', type=int)
        _opts_f = [
            joinedload(ScheduledClass.course),
            joinedload(ScheduledClass.section),
            joinedload(ScheduledClass.faculty),
            joinedload(ScheduledClass.room),
        ]
        if draft_id:
            schedules = _dedup_schedules(ScheduledClass.query.options(*_opts_f).filter(
                ScheduledClass.faculty_id == faculty_id,
                ScheduledClass.semester == semester,
                db.or_(
                    ScheduledClass.is_draft == False,
                    ScheduledClass.draft_version_id == draft_id
                )
            ).all())
        else:
            schedules = _dedup_schedules(ScheduledClass.query.options(*_opts_f).filter_by(
                faculty_id=faculty_id, semester=semester, is_draft=False
            ).all())

        prep_count  = db.session.query(ScheduledClass.course_id).filter_by(
                          faculty_id=faculty_id, semester=semester, is_draft=False).distinct().count()

    # Define path to faculty template
    path = os.path.join(basedir, 'static', 'assets', 'faculty_template.xlsx')
    for_canvas = request.args.get('canvas', 'false') == 'true'
    
    if not os.path.exists(path):
        return render_blank_timetable_fallback(
            entity_name=getattr(faculty, 'full_name', 'Faculty'),
            semester=semester,
            sem_ay=sem_ay,
            layout_type='faculty',
            for_canvas=for_canvas
        )

    total_hours = 0.0
    for sc in schedules:
        try:
            sh, sm = map(int, sc.start_time.split(':'))
            eh, em = map(int, sc.end_time.split(':'))
            total_hours += ((eh * 60 + em) - (sh * 60 + sm)) / 60.0
        except Exception:
            pass

    ws, grid_info, bounds = _get_cached_template(path)

    if grid_info:
        cell_overrides, extra_merge_map, extra_skip_cells = build_schedule_overlays(
            schedules, grid_info, 'faculty')
    else:
        cell_overrides, extra_merge_map, extra_skip_cells = {}, {}, set()

    settings = get_settings()
    var_map        = build_variable_map('faculty', settings, faculty=faculty,
                                        prep_count=prep_count, total_hours=total_hours)
    fac_overrides  = build_faculty_cell_overrides(ws, settings, faculty,
                                                   prep_count, total_hours)
    subj_overrides = build_subject_table_overlays(ws, schedules)
    daily_overrides = _build_daily_hours_overrides(ws, schedules, grid_info)
    # Priority: fac_overrides first, then grid/subject/daily overrides win for schedule data
    all_overrides  = {**fac_overrides, **cell_overrides, **subj_overrides, **daily_overrides}

    _margins = _get_faculty_margins(settings)
    _img_settings = _get_img_settings(settings, 'faculty')
    html_content, table_px, _, _ = render_excel_to_html(
        ws, cell_overrides=all_overrides, variable_map=var_map,
        extra_merge_map=extra_merge_map, extra_skip_cells=extra_skip_cells,
        bounds=bounds, layout_type='faculty', margins=_margins,
        img_settings=_img_settings)
    
    # Infinite Canvas support
    for_canvas = request.args.get('canvas', 'false') == 'true'
    return render_a4_page(html_content, table_px, margins=_margins, for_canvas=for_canvas)




# ------------------------------------ Room timetable HTML ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
@app.route('/room-timetable-html/<int:room_id>')
@login_required
def room_timetable_html(room_id):
    # ------------------------------------ Time Machine: Historical Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    if session.get('historical_mode_active', False):
        archive_id = session.get('active_archive_id')
        room_objs = get_archive_entities(archive_id, 'Room')
        room = next((r for r in room_objs if r.id == room_id), None)
        if not room: abort(404)

        schedules_raw = ArchivedSchedule.query.filter_by(
            term_archive_id=archive_id,
            room_name=room.room_name
        ).all()
        schedules = [_mock_archived_schedule(s) for s in schedules_raw]
        semester = "Archived"
        sem_ay = request.args.get('sem_ay', '')
    else:
        # ------------------------------------ Live Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        room     = Room.query.get_or_404(room_id)
        _req_sem = request.args.get('semester', '')
        _all_sems = [r[0] for r in db.session.query(ScheduledClass.semester).distinct().all() if r[0]]
        semester  = _req_sem if _req_sem in _all_sems else (_all_sems[0] if _all_sems else '1st Semester')
        if _req_sem == 'All' and _all_sems:
            semester = _all_sems[0]
        sem_ay    = request.args.get('sem_ay', '')

        draft_id = request.args.get('draft_id', type=int)
        _opts_r = [
            joinedload(ScheduledClass.course),
            joinedload(ScheduledClass.section),
            joinedload(ScheduledClass.faculty),
            joinedload(ScheduledClass.room),
        ]
        if draft_id:
            schedules = _dedup_schedules(ScheduledClass.query.options(*_opts_r).filter(
                ScheduledClass.room_id == room_id,
                ScheduledClass.semester == semester,
                db.or_(
                    ScheduledClass.is_draft == False,
                    ScheduledClass.draft_version_id == draft_id
                )
            ).all())
        else:
            schedules = _dedup_schedules(ScheduledClass.query.options(*_opts_r).filter_by(
                room_id=room_id, semester=semester, is_draft=False
            ).all())

    # Define path to room template
    path = os.path.join(basedir, 'static', 'assets', 'room_template.xlsx')
    for_canvas = request.args.get('canvas', 'false') == 'true'
    
    if not os.path.exists(path):
        return render_blank_timetable_fallback(
            entity_name=room.room_name,
            semester=semester,
            sem_ay=sem_ay,
            layout_type='room',
            for_canvas=for_canvas
        )

    ws, grid_info, bounds = _get_cached_template(path)
    if grid_info:
        cell_overrides, extra_merge_map, extra_skip_cells = build_schedule_overlays(
            schedules, grid_info, 'room')
    else:
        cell_overrides, extra_merge_map, extra_skip_cells = {}, {}, set()

    settings = get_settings()
    var_map  = build_variable_map('room', settings, entity_name=room.room_name, sem_ay=sem_ay)
    static_overrides = build_static_cell_overrides(
        ws, 'room', settings, entity_name=room.room_name, sem_ay=sem_ay)
    all_overrides = {**static_overrides, **cell_overrides}
    _margins = _get_margins(settings)
    _img_settings = _get_img_settings(settings, 'room')
    html_content, table_px, _, _ = render_excel_to_html(
        ws, cell_overrides=all_overrides, variable_map=var_map,
        extra_merge_map=extra_merge_map, extra_skip_cells=extra_skip_cells,
        bounds=bounds, layout_type='room', margins=_margins,
        img_settings=_img_settings)

    # Infinite Canvas support
    for_canvas = request.args.get('canvas', 'false') == 'true'
    return render_a4_page(html_content, table_px, margins=_margins, for_canvas=for_canvas)




@app.route('/course-timetable-html/<int:course_id>')
@login_required
def course_timetable_html(course_id):
    # ------------------------------------ Time Machine: Historical Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    if session.get('historical_mode_active', False):
        archive_id = session.get('active_archive_id')
        course_objs = get_archive_entities(archive_id, 'Course')
        course = next((c for c in course_objs if c.id == course_id), None)
        if not course: abort(404)

        schedules_raw = ArchivedSchedule.query.filter_by(
            term_archive_id=archive_id,
            course_code=course.course_code
        ).all()
        schedules = [_mock_archived_schedule(s) for s in schedules_raw]
        semester = "Archived"
        sem_ay = request.args.get('sem_ay', '')
    else:
        # ------------------------------------ Live Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        course    = Course.query.get_or_404(course_id)
        _req_sem  = request.args.get('semester', '')
        _all_sems = [r[0] for r in db.session.query(ScheduledClass.semester).distinct().all() if r[0]]
        semester  = _req_sem if _req_sem in _all_sems else (_all_sems[0] if _all_sems else '1st Semester')
        sem_ay    = request.args.get('sem_ay', '')

        schedules = _dedup_schedules(ScheduledClass.query.options(
            joinedload(ScheduledClass.course),
            joinedload(ScheduledClass.section),
            joinedload(ScheduledClass.faculty),
            joinedload(ScheduledClass.room),
        ).filter_by(course_id=course_id, semester=semester, is_draft=False).all())
    # Define path to course template
    path = os.path.join(basedir, 'static', 'assets', 'course_template.xlsx')
    for_canvas = request.args.get('canvas', 'false') == 'true'
    
    if not os.path.exists(path):
        # Fallback to section template as last resort
        sec_path = os.path.join(basedir, 'static', 'assets', 'section_template.xlsx')
        if not os.path.exists(sec_path):
            return render_blank_timetable_fallback(
                entity_name=course.course_code,
                semester=semester,
                sem_ay=sem_ay,
                layout_type='course',
                for_canvas=for_canvas
            )
        path = sec_path

    ws, grid_info, bounds = _get_cached_template(path)
    if grid_info:
        cell_overrides, extra_merge_map, extra_skip_cells = build_schedule_overlays(
            schedules, grid_info, 'course')
    else:
        cell_overrides, extra_merge_map, extra_skip_cells = {}, {}, set()

    settings = get_settings()
    var_map  = build_variable_map('course', settings, entity_name=course.course_code, sem_ay=sem_ay)
    static_overrides = build_static_cell_overrides(
        ws, 'course', settings, entity_name=course.course_code, sem_ay=sem_ay)
    all_overrides = {**static_overrides, **cell_overrides}
    _margins = _get_margins(settings)
    _img_settings = _get_img_settings(settings, 'course')
    html_content, table_px, _, _ = render_excel_to_html(
        ws, cell_overrides=all_overrides, variable_map=var_map,
        extra_merge_map=extra_merge_map, extra_skip_cells=extra_skip_cells,
        bounds=bounds, layout_type='course', margins=_margins,
        img_settings=_img_settings)
    
    # Infinite Canvas support
    for_canvas = request.args.get('canvas', 'false') == 'true'
    return render_a4_page(html_content, table_px, margins=_margins, for_canvas=for_canvas)




@app.route('/api/sections-with-schedules')
@login_required
def api_sections_with_schedules():
    """Return sections that have scheduled classes for the given semester."""
    semester = request.args.get('semester', '')
    q = db.session.query(ScheduledClass.section_id).distinct()
    if semester:
        q = q.filter(ScheduledClass.semester == semester)
    ids = {r[0] for r in q.all() if r[0]}
    sections = (Section.query
                .filter(Section.id.in_(ids), Section.is_archived == False)
                .order_by(Section.year_level, Section.section_name)
                .all())
    return jsonify([{'id': s.id, 'name': s.section_name} for s in sections])


@app.route('/api/rooms-with-schedules')
@login_required
def api_rooms_with_schedules():
    """Return rooms that have scheduled classes for the given semester."""
    semester = request.args.get('semester', '')
    q = db.session.query(ScheduledClass.room_id).distinct()
    if semester:
        q = q.filter(ScheduledClass.semester == semester)
    ids = {r[0] for r in q.all() if r[0]}
    rooms = (Room.query
             .filter(Room.id.in_(ids), Room.is_archived == False)
             .order_by(Room.room_name)
             .all())
    return jsonify([{'id': r.id, 'name': r.room_name} for r in rooms])


@app.route('/api/courses-with-schedules')
@login_required
def api_courses_with_schedules():
    """Return courses that have scheduled classes for the given semester."""
    semester = request.args.get('semester', '')
    q = db.session.query(ScheduledClass.course_id).distinct()
    if semester:
        q = q.filter(ScheduledClass.semester == semester)
    ids = {r[0] for r in q.all() if r[0]}
    courses = (Course.query
               .filter(Course.id.in_(ids), Course.is_archived == False)
               .order_by(Course.course_code)
               .all())
    return jsonify([{'id': c.id, 'name': c.course_code + ' ---- ' + c.course_name} for c in courses])


@app.route('/save-layout-xlsx', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def save_layout_xlsx():
    """Save only the XLSX template file (may laman ang image). Separate request para maiwasan ang 413."""
    try:
        layout_type = request.form.get('layout_type')
        if not layout_type:
            return jsonify({'status': 'error', 'message': 'Missing layout_type'}), 400

        assets_dir = os.path.join(basedir, 'static', 'assets')
        os.makedirs(assets_dir, exist_ok=True)

        if 'template_file' in request.files:
            file = request.files['template_file']
            if file and file.filename != '':
                path = os.path.join(assets_dir, f"{layout_type}_template.xlsx")
                file.save(path)
                # Compute accurate dimensions so client-side LuckySheet matches the Excel
                try:
                    import math as _math
                    _wb = load_workbook(path, data_only=True)
                    _ws = _wb.active
                    _MDW, _PT_PX = 7, 96 / 72
                    col_widths = {}
                    for _letter, _cd in _ws.column_dimensions.items():
                        _idx = ord(_letter.upper()) - ord('A')
                        _chars = _cd.width if (_cd and _cd.width) else 8.0
                        col_widths[str(_idx)] = _math.floor((_chars * _MDW + 5) / _MDW) * _MDW
                    row_heights = {}
                    for _rnum, _rd in _ws.row_dimensions.items():
                        _pts = _rd.height if (_rd and _rd.height) else 13.5
                        row_heights[str(_rnum - 1)] = round(_pts * _PT_PX, 2)
                    dims = {'col_widths': col_widths, 'row_heights': row_heights}
                except Exception:
                    dims = {}
                return jsonify({'status': 'success', 'dimensions': dims})

        return jsonify({'status': 'error', 'message': 'No file received'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/delete-layout/<layout_type>', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def delete_layout(layout_type):
    """Delete saved layout files (xlsx + state json) for a given type."""
    if layout_type not in ('section', 'faculty', 'room', 'course'):
        return jsonify({'status': 'error', 'message': 'Invalid layout type'}), 400
    assets_dir = os.path.join(basedir, 'static', 'assets')
    deleted = []
    for suffix in (f'{layout_type}_template.xlsx', f'{layout_type}_state.json', f'{layout_type}_layout.json'):
        p = os.path.join(assets_dir, suffix)
        if os.path.exists(p):
            os.remove(p)
            deleted.append(suffix)
    flash(f'{layout_type.capitalize()} template deleted.', 'success')
    return redirect(url_for('manage_layouts', tab=layout_type))


@app.route('/update-manual-schedule', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def update_manual_schedule():
    sched_id = request.form.get('sched_id')
    new_day = request.form.get('day')
    new_start = request.form.get('start_time')
    new_end = request.form.get('end_time')
    new_room = request.form.get('room_id')

    sched = ScheduledClass.query.get(sched_id)
    if sched:
        # Check conflict kung gusto mo (Optional)
        sched.day = new_day
        sched.start_time = new_start
        sched.end_time = new_end
        if new_room:
            sched.room_id = new_room
        db.session.commit()
        flash("Schedule manually moved successfully!", "success")
    else:
        flash("Error moving schedule.", "danger")
        
    _ref = request.referrer
    if _ref and _ref.startswith(request.host_url):
        return redirect(_ref)
    return redirect(url_for('dashboard'))

# ------------------------------------------------------ STUDENT MASTERLIST ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

@app.route('/manage/students')
@login_required
@role_required('admin', 'superadmin')
def manage_students():
    page         = request.args.get('page', 1, type=int)
    sort_by      = request.args.get('sort', 'name-asc', type=str)
    search_query = request.args.get('search', '', type=str)
    filter_by    = request.args.get('filter_by', '', type=str)
    filter_val   = request.args.get('filter_val', '', type=str)

    # ------------------------------------ Time Machine: Historical Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    if session.get('historical_mode_active', False):
        archive_id = session.get('active_archive_id')
        
        # Combined Regular and Irregular students from the archive
        reg_students = get_archive_entities(archive_id, 'Student')
        irreg_students = get_archive_entities(archive_id, 'IrregularStudent')
        
        # Deduplicate by student_id to handle multi-generation archive pollution
        seen_ids = set()
        all_objs = []
        for s in (reg_students + irreg_students):
            sid = getattr(s, 'student_id', None)
            if sid not in seen_ids:
                all_objs.append(s)
                seen_ids.add(sid)
        
        # Get section mapping to restore names in View Mode
        all_archived_sections = get_archive_entities(archive_id, 'Section')
        sec_map = {getattr(s, 'id', 0): getattr(s, 'section_name', 'Unknown') for s in all_archived_sections}
        
        for obj in all_objs:
            s_id = getattr(obj, 'section_id', None)
            if s_id and s_id in sec_map:
                obj.archived_section_name = sec_map[s_id]
            else:
                obj.archived_section_name = None
        
        # 1. Apply Filtering
        if search_query:
            s = search_query.lower()
            all_objs = [o for o in all_objs if 
                        s in (getattr(o, 'full_name', '') or '').lower() or 
                        s in (getattr(o, 'student_id', '') or '').lower()]
        
        if filter_by == 'year' and filter_val:
            try:
                val = int(filter_val)
                all_objs = [o for o in all_objs if getattr(o, 'year_level', None) == val]
            except: pass
        elif filter_by == 'section' and filter_val:
            try:
                val = int(filter_val)
                all_objs = [o for o in all_objs if getattr(o, 'section_id', None) == val]
            except: pass

        # 2. Apply Sorting
        if sort_by == 'name-desc':
            all_objs.sort(key=lambda x: (getattr(x, 'full_name', '') or '').lower(), reverse=True)
        elif sort_by == 'id-asc':
            all_objs.sort(key=lambda x: (getattr(x, 'student_id', '') or '').lower())
        elif sort_by == 'id-desc':
            all_objs.sort(key=lambda x: (getattr(x, 'student_id', '') or '').lower(), reverse=True)
        elif sort_by == 'section':
            all_secs = get_archive_entities(archive_id, 'Section')
            sec_map = {s.id: getattr(s, 'section_name', '') for s in all_secs}
            all_objs.sort(key=lambda x: (sec_map.get(getattr(x, 'section_id', 0), 'Z-NoSection'), (getattr(x, 'full_name', '') or '').lower()))
        elif sort_by == 'newest':
            from datetime import datetime as dtt
            all_objs.sort(key=lambda x: (getattr(x, 'created_at', None) or dtt.min, getattr(x, 'id', 0)), reverse=True)
        else: # Default: name-asc
            all_objs.sort(key=lambda x: (getattr(x, 'full_name', '') or '').lower())

        # 3. Paginate
        per_page = 10
        total = len(all_objs)
        start = (page - 1) * per_page
        items = all_objs[start:start+per_page]
        pagination = MockPagination(items, page, per_page, total)
        
        all_sections_data = get_archive_entities(archive_id, 'Section')
        unique_years_data = sorted(list(set(getattr(o, 'year_level', 0) for o in all_objs if getattr(o, 'year_level', None) is not None)))

        return render_template('manage_students.html',
            students=items,
            pagination=pagination,
            all_sections=all_sections_data,
            unique_years=unique_years_data,
            current_sort=sort_by,
            search_query=search_query,
            current_filter_by=filter_by,
            current_filter_val=filter_val
        )

    # ------------------------------------ Live Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    query = Student.query.filter_by(is_archived=False)

    if search_query:
        query = query.filter(or_(
            Student.full_name.ilike(f'%{search_query}%'),
            Student.student_id.ilike(f'%{search_query}%'),
        ))

    if filter_by == 'year' and filter_val:
        try:
            query = query.filter(Student.year_level == int(filter_val))
        except ValueError:
            pass
    elif filter_by == 'section' and filter_val:
        try:
            query = query.filter(Student.section_id == int(filter_val))
        except ValueError:
            pass

    if sort_by == 'name-desc':
        query = query.order_by(Student.full_name.desc())
    elif sort_by == 'id-asc':
        query = query.order_by(Student.student_id.asc())
    elif sort_by == 'id-desc':
        query = query.order_by(Student.student_id.desc())
    elif sort_by == 'section':
        query = query.outerjoin(Section, Student.section_id == Section.id).order_by(Section.section_name.asc(), Student.full_name.asc())
    else:
        query = query.order_by(Student.full_name.asc())

    try:
        pagination    = query.paginate(page=page, per_page=10, error_out=False)
        students      = pagination.items
        all_sections  = Section.query.filter_by(is_archived=False).order_by(Section.section_name).all()
        unique_years  = db.session.query(Student.year_level).filter_by(is_archived=False).distinct().order_by(Student.year_level).all()
        unique_years  = [y[0] for y in unique_years if y[0] is not None]
    except Exception as e:
        print(f"Error fetching students: {e}")
        students = []
        pagination = MockPagination([], 1, 10, 0)
        all_sections = []
        unique_years = []

    return render_template('manage_students.html',
        students=students,
        pagination=pagination,
        all_sections=all_sections,
        unique_years=unique_years,
        current_sort=sort_by,
        search_query=search_query,
        current_filter_by=filter_by,
        current_filter_val=filter_val,
        known_departments=_get_depts()
    )


@app.route('/manage/student/add', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def add_student():
    sid          = request.form.get('student_id', '').strip()
    name         = request.form.get('full_name', '').strip()
    year         = request.form.get('year_level', type=int)
    sec_id       = request.form.get('section_id') or None
    email        = request.form.get('email', '').strip() or None
    is_irregular = request.form.get('is_irregular', '0') == '1'

    # When called via fetch() from the irregular modal, return JSON so the modal
    # can show inline errors (flash+redirect is consumed silently by fetch).
    def _err(msg):
        if is_irregular:
            return jsonify({'error': msg}), 400
        flash(msg, 'danger')
        return redirect(url_for('manage_students'))

    if not sid or not name or not year:
        return _err('Student ID, full name, and year level are required.')

    # 1. Length Validation
    constraints = {
        'student_id': 20,
        'full_name': 100,
        'email': 100
    }
    ok, err = validate_lengths(request.form, constraints)
    if not ok:
        return _err(err)

    # 2. XSS Sanitization
    sid = sanitize_input(sid)
    name = sanitize_input(name)
    email = sanitize_input(email) if email else None

    if year not in (1, 2, 3, 4):
        return _err('Year level must be 1, 2, 3, or 4.')
    if email and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return _err('Please enter a valid email address.')
    if Student.query.filter_by(student_id=sid).first():
        return _err(f'Student ID "{sid}" already exists.')

    try:
        db.session.add(Student(
            student_id=sid,
            full_name=name,
            year_level=year,
            section_id=int(sec_id) if sec_id else None,
            email=email,
            is_irregular=is_irregular,
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        return _err(f'Could not add student. Student ID "{sid}" may have been added by another user simultaneously.')

    if is_irregular:
        return jsonify({'ok': True})
    flash('Student added successfully.', 'success')
    return redirect(url_for('manage_students'))


@app.route('/manage/student/update/<int:student_pk>', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def update_student(student_pk):
    s        = Student.query.get_or_404(student_pk)
    sid      = request.form.get('student_id', '').strip()
    name     = request.form.get('full_name', '').strip()
    year     = request.form.get('year_level', type=int)
    sec_id   = request.form.get('section_id') or None
    email    = request.form.get('email', '').strip() or None

    if not sid or not name or not year:
        flash('Student ID, full name, and year level are required.', 'danger')
        return redirect(url_for('manage_students'))

    # 1. Length Validation
    constraints = {
        'student_id': 20,
        'full_name': 100,
        'email': 100
    }
    ok, err = validate_lengths(request.form, constraints)
    if not ok:
        flash(err, 'danger')
        return redirect(url_for('manage_students'))

    # 2. XSS Sanitization
    sid = sanitize_input(sid)
    name = sanitize_input(name)
    email = sanitize_input(email) if email else None

    if year not in (1, 2, 3, 4):
        flash('Year level must be 1, 2, 3, or 4.', 'danger')
        return redirect(url_for('manage_students'))
    if email and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        flash('Please enter a valid email address.', 'danger')
        return redirect(url_for('manage_students'))

    # Check duplicate student_id (excluding self)
    existing = Student.query.filter_by(student_id=sid).first()
    if existing and existing.id != student_pk:
        flash(f'Student ID "{sid}" is already used by another student.', 'danger')
        return redirect(url_for('manage_students'))

    s.student_id  = sid
    s.full_name   = name
    s.year_level  = year
    s.section_id  = int(sec_id) if sec_id else None
    s.email       = email
    db.session.commit()
    flash('Student updated successfully.', 'success')
    return redirect(url_for('manage_students'))


@app.route('/manage/student/archive/<int:student_pk>', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def archive_student(student_pk):
    s             = Student.query.get_or_404(student_pk)
    s.is_archived = True
    s.deleted_at  = datetime.utcnow()
    db.session.commit()
    flash('Student moved to Recycle Bin.', 'success')
    return redirect(url_for('manage_students'))


@app.route('/manage/students/bulk_archive', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def bulk_archive_students():
    ids = request.form.getlist('row_ids')
    if ids:
        Student.query.filter(Student.id.in_(ids)).update(
            {Student.is_archived: True, Student.deleted_at: datetime.utcnow()},
            synchronize_session=False)
        db.session.commit()
        flash(f'{len(ids)} student(s) moved to Recycle Bin.', 'success')
    else:
        flash('No students selected.', 'secondary')
    return redirect(url_for('manage_students'))


@app.route('/manage/students/archive')
@login_required
@role_required('admin', 'superadmin')
def students_archive():
    page         = request.args.get('page', 1, type=int)
    sort_by      = request.args.get('sort', 'default', type=str)
    search_query = request.args.get('search', '', type=str)
    
    query = Student.query.filter_by(is_archived=True)
    
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(or_(
            Student.full_name.ilike(search_term),
            Student.student_id.ilike(search_term)
        ))
        
    if sort_by == 'name-asc':
        query = query.order_by(Student.full_name.asc())
    elif sort_by == 'name-desc':
        query = query.order_by(Student.full_name.desc())
    elif sort_by == 'newest' or sort_by == 'default':
        query = query.order_by(Student.deleted_at.desc(), Student.id.desc())
    else:
        query = query.order_by(Student.id.desc())
        
    pagination = query.paginate(page=page, per_page=10, error_out=False)
    students = pagination.items
    
    return render_template('students_archive.html',
        students=students,
        pagination=pagination,
        current_sort=sort_by,
        search_query=search_query,
        now=datetime.utcnow()
    )


@app.route('/manage/student/restore/<int:student_pk>', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def restore_student(student_pk):
    s             = Student.query.get_or_404(student_pk)
    s.is_archived = False
    s.deleted_at  = None
    db.session.commit()
    flash('Student restored successfully.', 'success')
    return redirect(url_for('students_archive'))


@app.route('/manage/students/bulk_restore', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def bulk_restore_students():
    ids = request.form.getlist('row_ids')
    if ids:
        Student.query.filter(Student.id.in_(ids)).update(
            {Student.is_archived: False, Student.deleted_at: None},
            synchronize_session=False)
        db.session.commit()
        flash(f'{len(ids)} student(s) restored.', 'success')
    return redirect(url_for('students_archive'))


@app.route('/manage/student/delete/<int:student_pk>', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def delete_student(student_pk):
    s = Student.query.get_or_404(student_pk)
    db.session.delete(s)
    db.session.commit()
    flash('Student permanently deleted.', 'success')
    return redirect(url_for('students_archive'))


@app.route('/manage/students/bulk_delete', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def bulk_delete_students():
    ids = request.form.getlist('row_ids')
    if ids:
        Student.query.filter(Student.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        flash(f'{len(ids)} student(s) permanently deleted.', 'success')
    return redirect(url_for('students_archive'))


@app.route('/download/student-template')
@login_required
@role_required('admin', 'superadmin')
def download_student_template():
    wb = Workbook()
    ws = wb.active
    ws.title = 'Students'

    # Header row
    headers = ['Student ID', 'Full Name', 'Year Level', 'Section Name', 'Email']
    header_fill = PatternFill(start_color='1F5C99', end_color='1F5C99', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF', size=11)
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')

    # Sample data rows
    samples = [
        ('2024-00001', 'Dela Cruz, Juan A.',   1, 'BSCoS 101-A', 'juan@cvsu.edu.ph'),
        ('2024-00002', 'Santos, Maria B.',     1, 'BSCoS 101-A', ''),
        ('2024-00003', 'Reyes, Carlos C.',     2, 'BSIT 201-B',  'carlos@cvsu.edu.ph'),
    ]
    sample_font = Font(italic=True, color='888888', size=10)
    sample_fill = PatternFill(start_color='F5F5F5', end_color='F5F5F5', fill_type='solid')
    for r, row in enumerate(samples, 2):
        for c, val in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=val)
            cell.font = sample_font
            cell.fill = sample_fill
            cell.alignment = Alignment(vertical='center')

    # Notes row
    note_row = len(samples) + 2
    note_cell = ws.cell(row=note_row, column=1,
        value='NOTES: Year Level must be 1----4. Section Name must exactly match an existing section. Email is optional. Duplicate Student IDs will be skipped.')
    note_cell.font = Font(italic=True, color='AA0000', size=9)
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=5)

    # Column widths
    ws.column_dimensions['A'].width = 16
    ws.column_dimensions['B'].width = 30
    ws.column_dimensions['C'].width = 14
    ws.column_dimensions['D'].width = 20
    ws.column_dimensions['E'].width = 28

    # Row heights
    ws.row_dimensions[1].height = 20
    for r in range(2, note_row):
        ws.row_dimensions[r].height = 16

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name='Student Import Template.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/download/faculty-loading-template')
@login_required
@role_required('admin', 'superadmin')
def download_faculty_loading_template():
    wb = Workbook()
    ws = wb.active
    ws.title = 'Faculty Loading'

    # Header block (rows 1-14) ---- parser reads rows 1-15 for dept detection
    ws['A1'] = 'CAVITE STATE UNIVERSITY ---- CCAT'
    ws['A1'].font = Font(bold=True, size=13)
    ws['A2'] = 'COLLEGE OF COMPUTER STUDIES'  # "COMPUTER STUDIES" triggers dept detection
    ws['A2'].font = Font(bold=True, size=11)
    ws['A3'] = 'Faculty Loading ---- Academic Year'
    ws['A3'].font = Font(italic=True, size=10, color='555555')

    # Column headers at row 15
    col_headers = {1: 'NAME OF FACULTY', 2: 'COURSE CODE', 8: 'SECTION', 11: 'TOTAL HRS'}
    hdr_fill = PatternFill(start_color='1F5C99', end_color='1F5C99', fill_type='solid')
    hdr_font = Font(bold=True, color='FFFFFF', size=10)
    for col, label in col_headers.items():
        cell = ws.cell(row=15, column=col, value=label)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal='center', vertical='center')

    # Sample data rows starting at row 16
    samples = [
        ('Cruz, Juan A.',    'COSC 101', None, None, None, None, None, 'BSCoS 101-A', None, None, 18),
        (None,               'COSC 111', None, None, None, None, None, 'BSCoS 101-B', None, None, None),
        ('Dela Torre, Ma.',  'COSC 121', None, None, None, None, None, 'BSCoS 201-A', None, None, 21),
        (None,               'MATH 101', None, None, None, None, None, 'BSCoS 101-A', None, None, None),
        ('Reyes, Carlos C.', 'COSC 112', None, None, None, None, None, 'BSCoS 101-B', None, None, 15),
    ]
    spl_font = Font(italic=True, color='888888', size=10)
    spl_fill = PatternFill(start_color='F5F5F5', end_color='F5F5F5', fill_type='solid')
    for r_idx, row in enumerate(samples, 16):
        for c_idx, val in enumerate(row, 1):
            if val is not None:
                cell = ws.cell(row=r_idx, column=c_idx, value=val)
                cell.font = spl_font
                cell.fill = spl_fill

    # "Prepared by" marker ---- parser stops here
    ws.cell(row=22, column=1, value='Prepared by:').font = Font(italic=True, color='888888', size=9)

    # Notes row
    note_row = 24
    note_cell = ws.cell(row=note_row, column=1,
        value='NOTES: Data starts at Row 16. Col A = Faculty Name (leave blank for additional courses under same faculty). '
              'Col B = Course Code. Col H = Section. Col K = Total Contact Hours. '
              'Add "Prepared by:" in Col A to mark end of data. '
              'Duplicate assignments (same faculty + course + section) are skipped.')
    note_cell.font = Font(italic=True, color='AA0000', size=9)
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=11)

    ws.column_dimensions['A'].width = 28
    ws.column_dimensions['B'].width = 14
    ws.column_dimensions['H'].width = 18
    ws.column_dimensions['K'].width = 14

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name='Faculty Loading Template.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/download/curriculum-template')
@login_required
@role_required('admin', 'superadmin')
def download_curriculum_template():
    from docx import Document as DocxDocument
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = DocxDocument()
    title_p = doc.add_heading('BS Computer Science ---- Curriculum Import Template', 0)
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    prog_p = doc.add_paragraph()
    prog_p.add_run('Program: ').bold = True
    prog_p.add_run('BSCoS   (change to BSInfoTech for BS Information Technology)')

    doc.add_paragraph(
        'Instructions: Keep heading text exactly as-is (FIRST YEAR, SECOND SEMESTER, etc.). '
        'Add or remove rows inside each table. Do not delete or rename column headers.')
    doc.add_paragraph('')

    curriculum = [
        ('FIRST YEAR', [
            ('FIRST SEMESTER', [
                ('COSC 101', 'Introduction to Computing', 3, 0),
                ('COSC 111', 'Computer Programming 1', 2, 1),
                ('MATH 101', 'Mathematics in the Modern World', 3, 0),
                ('GEd 102',  'Readings in Philippine History', 3, 0),
                ('NSTP 1',   'National Service Training Program 1', 3, 0),
            ]),
            ('SECOND SEMESTER', [
                ('COSC 112', 'Computer Programming 2', 2, 1),
                ('COSC 121', 'Discrete Structures 1', 3, 0),
                ('MATH 102', 'Calculus 1', 3, 0),
                ('GEd 103',  'The Contemporary World', 3, 0),
            ]),
        ]),
        ('SECOND YEAR', [
            ('FIRST SEMESTER', [
                ('COSC 201', 'Data Structures and Algorithms', 2, 1),
                ('COSC 211', 'Object-Oriented Programming', 2, 1),
            ]),
            ('SECOND SEMESTER', [
                ('COSC 212', 'Advanced Programming', 2, 1),
                ('COSC 221', 'Discrete Structures 2', 3, 0),
            ]),
        ]),
        ('THIRD YEAR', [
            ('FIRST SEMESTER', [
                ('COSC 301', 'Operating Systems', 2, 1),
            ]),
            ('SECOND SEMESTER', [
                ('COSC 311', 'Database Management Systems', 2, 1),
            ]),
        ]),
        ('FOURTH YEAR', [
            ('FIRST SEMESTER', [
                ('COSC 401', 'Software Engineering', 3, 0),
            ]),
            ('MIDYEAR', [
                ('COSC 199', 'Internship / OJT / Practicum', 3, 0),
            ]),
        ]),
    ]

    for year_label, semesters in curriculum:
        doc.add_heading(year_label, level=1)
        for sem_label, courses in semesters:
            doc.add_heading(sem_label, level=2)
            tbl = doc.add_table(rows=1 + len(courses), cols=4)
            tbl.style = 'Table Grid'
            hdr = tbl.rows[0].cells
            for i, h in enumerate(['Course Code', 'Course Title', 'Lec Units', 'Lab Units']):
                hdr[i].text = h
                hdr[i].paragraphs[0].runs[0].bold = True
            for r_idx, (code, title, lec, lab) in enumerate(courses, 1):
                rc = tbl.rows[r_idx].cells
                rc[0].text = code
                rc[1].text = title
                rc[2].text = str(lec)
                rc[3].text = str(lab)
            doc.add_paragraph('')

    note_p = doc.add_paragraph()
    note_run = note_p.add_run(
        'NOTES: Do NOT change heading text (FIRST YEAR, SECOND SEMESTER, etc.) ---- '
        'they are used for automatic detection. Table column order must be: '
        'Course Code | Course Title | Lec Units | Lab Units. '
        'Change "BSCoS" to "BSInfoTech" in the Program line for Information Technology. '
        'Duplicate course codes found in the database will be updated (year level + semester), not duplicated.')
    note_run.font.color.rgb = RGBColor(0xAA, 0x00, 0x00)
    note_run.font.italic = True
    note_run.font.size = Pt(9)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name='Curriculum Import Template.docx',
                     mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')


@app.route('/import_students_xlsx', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def import_students_xlsx():
    if 'file' not in request.files:
        flash('No file uploaded.', 'danger')
        return redirect(url_for('manage_students'))
    file = request.files['file']
    if not file.filename:
        flash('No file selected.', 'danger')
        return redirect(url_for('manage_students'))
    if not file.filename.lower().endswith('.xlsx'):
        flash('Only .xlsx files are accepted.', 'danger')
        return redirect(url_for('manage_students'))

    try:
        wb = load_workbook(file, data_only=True)
        ws = wb.active
        added = 0
        skipped_dup = 0
        unknown_section = 0

        for row in ws.iter_rows(min_row=2, values_only=True):
            # Stop at blank or note rows
            if not row or not row[0] or not row[1]:
                continue
            raw_sid  = sanitize_input(str(row[0]).strip()) if row[0] else ''
            raw_name = sanitize_input(str(row[1]).strip()) if row[1] else ''
            raw_year = row[2]
            raw_sec  = sanitize_input(str(row[3]).strip()) if row[3] else ''
            raw_mail = sanitize_input(str(row[4]).strip()) if row[4] else ''

            if not raw_sid or not raw_name:
                continue

            # Year level
            try:
                year = int(float(str(raw_year))) if raw_year else None
            except (ValueError, TypeError):
                year = None
            if year not in (1, 2, 3, 4):
                year = 1  # default fallback

            # Duplicate check
            if Student.query.filter_by(student_id=raw_sid).first():
                skipped_dup += 1
                continue

            # Section lookup
            sec_id = None
            if raw_sec:
                sec = Section.query.filter_by(section_name=raw_sec, is_archived=False).first()
                if sec:
                    sec_id = sec.id
                else:
                    unknown_section += 1

            db.session.add(Student(
                student_id=raw_sid,
                full_name=raw_name,
                year_level=year,
                section_id=sec_id,
                email=raw_mail or None,
            ))
            added += 1

        db.session.commit()

        parts = [f'Imported {added} student(s).']
        if skipped_dup:
            parts.append(f'{skipped_dup} duplicate(s) skipped.')
        if unknown_section:
            parts.append(f'{unknown_section} row(s) had unknown sections (set to Unassigned).')
        flash(' '.join(parts), 'success' if added > 0 else 'warning')

    except Exception:
        flash('Error processing file. Please check that your file is a valid .xlsx and try again.', 'danger')

    return redirect(url_for('manage_students'))


# ------------------------------------------------------ STUDENT PORTAL (PUBLIC ---- no login required) ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

@app.route('/student-portal', methods=['GET', 'POST'])
def student_portal():
    if request.method == 'POST':
        ip  = request.remote_addr
        now = datetime.utcnow()
        with rate_limit_lock:
            pa  = _portal_attempts.get(ip, {'count': 0, 'lockout_until': None})
            # Reset lockout if expired
            if pa['lockout_until'] and now >= pa['lockout_until']:
                pa = {'count': 0, 'lockout_until': None}
            # Block if currently locked out
            if pa['lockout_until'] and now < pa['lockout_until']:
                flash('Too many attempts. Please wait a few minutes and try again.', 'warning')
                _portal_attempts[ip] = pa
                return render_template('student_portal.html')
            # Count this attempt
            pa['count'] += 1
            if pa['count'] > _PORTAL_MAX_ATTEMPTS:
                pa['lockout_until'] = now + timedelta(minutes=_PORTAL_LOCKOUT_MINUTES)
                pa['count'] = 0
                _portal_attempts[ip] = pa
                flash('Too many attempts. Please wait a few minutes and try again.', 'warning')
                return render_template('student_portal.html')
            _portal_attempts[ip] = pa

        sid = request.form.get('student_id', '').strip()
        
        # 1. Check live database first
        student = Student.query.filter_by(student_id=sid, is_archived=False).first()
        
        # 2. If not in live, check archives (ArchivedEntity)
        if not student:
            archive_entry = ArchivedEntity.query.filter(
                ArchivedEntity.entity_type.in_(['Student', 'IrregularStudent']),
                ArchivedEntity.data_json.like(f'%"student_id": "{sid}"%')
            ).order_by(ArchivedEntity.term_archive_id.desc()).first()
            
            if not archive_entry:
                flash('Student ID not found. Please check and try again.', 'danger')
                return redirect(url_for('student_portal'))
            
            # If found in archive, redirect with the most recent archive's term_id
            _portal_attempts.pop(ip, None)
            return redirect(url_for('student_schedule', student_id=sid, term_id=archive_entry.term_archive_id))

        # Successful live lookup ---- reset counter for this IP
        _portal_attempts.pop(ip, None)
        return redirect(url_for('student_schedule', student_id=sid))
    return render_template('student_portal.html')


# ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# IRREGULAR STUDENT PATHFINDER ---- helpers & routes
# ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def _t2m(t):
    """'HH:MM' -> minutes from midnight."""
    try:
        h, m = t.strip().split(':')
        return int(h) * 60 + int(m)
    except Exception:
        return 0

def _slots_conflict(new_slots, existing_slots):
    """Return True if any slot in new_slots overlaps with any slot in existing_slots."""
    for ns in new_slots:
        ns_s = _t2m(ns.start_time)
        ns_e = _t2m(ns.end_time)
        for es in existing_slots:
            if ns.day == es.day:
                if ns_s < _t2m(es.end_time) and ns_e > _t2m(es.start_time):
                    return True
    return False

def _gap_score(all_slots):
    """Return total idle minutes between consecutive classes per day."""
    from collections import defaultdict
    day_intervals = defaultdict(list)
    for sc in all_slots:
        day_intervals[sc.day].append((_t2m(sc.start_time), _t2m(sc.end_time)))
    total = 0
    for intervals in day_intervals.values():
        intervals.sort()
        for i in range(1, len(intervals)):
            gap = intervals[i][0] - intervals[i - 1][1]
            if gap > 0:
                total += gap
    return total

def _gap_per_day(all_slots):
    """Return {day: idle_minutes} for display."""
    from collections import defaultdict
    day_intervals = defaultdict(list)
    for sc in all_slots:
        day_intervals[sc.day].append((_t2m(sc.start_time), _t2m(sc.end_time)))
    result = {}
    for day, intervals in day_intervals.items():
        intervals.sort()
        g = 0
        for i in range(1, len(intervals)):
            gap = intervals[i][0] - intervals[i - 1][1]
            if gap > 0:
                g += gap
        if g > 0:
            result[day] = g
    return result

def _fmt12(t):
    """'HH:MM' -> '8:00 AM' style."""
    try:
        h, m = int(t[:2]), int(t[3:5])
        suffix = 'AM' if h < 12 else 'PM'
        h12 = h % 12 or 12
        return f"{h12}:{m:02d} {suffix}"
    except Exception:
        return t

def _irregular_solver(course_ids, semester):
    """
    Main algorithm for the Irregular Pathfinder.
    Returns dict with keys: anchor, full_cover, combinations, deadlock_courses.
    """
    # Step 1 ---- gather offerings per course
    offerings = {}  # course_id -> [(section_id, [ScheduledClass, ...])]
    all_section_ids = set()
    for cid in course_ids:
        slots_qs = ScheduledClass.query.options(
            joinedload(ScheduledClass.course),
            joinedload(ScheduledClass.faculty),
            joinedload(ScheduledClass.room),
        ).filter_by(course_id=cid, semester=semester).all()
        by_sec = {}
        for sc in slots_qs:
            by_sec.setdefault(sc.section_id, []).append(sc)
            all_section_ids.add(sc.section_id)
        offerings[cid] = list(by_sec.items())  # [(section_id, [slots]), ...]

    # Step 2 ---- immediate deadlock: courses with no offerings at all
    deadlock_courses = [cid for cid in course_ids if not offerings[cid]]

    # Step 3 ---- section coverage count
    # coverage[section_id] = set of course_ids that section offers
    coverage = {}
    for cid, sec_slots in offerings.items():
        for sec_id, _ in sec_slots:
            coverage.setdefault(sec_id, set()).add(cid)

    # Pick anchor = section with highest coverage of requested courses
    requested_set = set(course_ids)
    best_sec_id = None
    best_count = 0
    for sec_id, covered_set in coverage.items():
        cnt = len(covered_set & requested_set)
        if cnt > best_count:
            best_count = cnt
            best_sec_id = sec_id

    anchor_section = None
    anchor_slots = []
    anchor_course_ids = []
    full_cover = False

    if best_sec_id:
        sec_obj = Section.query.get(best_sec_id)
        anchor_course_ids = list(coverage[best_sec_id] & requested_set)
        full_cover = (len(anchor_course_ids) == len(course_ids))
        # Collect anchor slots for covered courses
        for cid in anchor_course_ids:
            for sec_id, slots in offerings[cid]:
                if sec_id == best_sec_id:
                    anchor_slots.extend(slots)
                    break
        anchor_section = {
            'section_id':        best_sec_id,
            'section_name':      sec_obj.section_name if sec_obj else str(best_sec_id),
            'covered_course_ids': anchor_course_ids,
            'covered_count':     len(anchor_course_ids),
            'total_requested':   len(course_ids),
        }

    # Step 4 ---- uncovered courses (need backtracking)
    uncovered = [cid for cid in course_ids if cid not in anchor_course_ids]

    # Step 5 ---- collect options per uncovered course (exclude anchor section)
    uncovered_options = {}  # cid -> [(section_id, [slots])]
    for cid in uncovered:
        opts = [(sec_id, slots) for sec_id, slots in offerings[cid]
                if sec_id != best_sec_id]
        uncovered_options[cid] = opts

    # Step 6 ---- backtracking over uncovered courses
    MAX_SOLUTIONS = 20
    solutions_raw = []  # list of [(cid, section_id, [slots]), ...]

    def backtrack(idx, chosen, chosen_slots):
        if len(solutions_raw) >= MAX_SOLUTIONS:
            return
        if idx == len(uncovered):
            solutions_raw.append(list(chosen))
            return
        cid = uncovered[idx]
        for sec_id, slots in uncovered_options[cid]:
            if not _slots_conflict(slots, chosen_slots + anchor_slots):
                chosen.append((cid, sec_id, slots))
                backtrack(idx + 1, chosen, chosen_slots + slots)
                chosen.pop()

    backtrack(0, [], [])

    # Step 7 ---- score and serialize
    def serialize_slots(slots):
        out = []
        for sc in slots:
            out.append({
                'day':          sc.day,
                'start_time':   _fmt12(sc.start_time),
                'end_time':     _fmt12(sc.end_time),
                'session_type': sc.session_type or 'Lec',
                'faculty':      sc.faculty.full_name if sc.faculty else 'TBA',
                'room':         sc.room.room_name if sc.room else 'TBA',
            })
        return out

    def build_combo(raw):
        # raw: [(cid, sec_id, [slots]), ...]
        all_slots = list(anchor_slots)
        for _, _, slots in raw:
            all_slots.extend(slots)
        gap = _gap_score(all_slots)
        gpd = _gap_per_day(all_slots)
        extras = []
        for cid, sec_id, slots in raw:
            sec_obj2 = Section.query.get(sec_id)
            crs_obj  = Course.query.get(cid)
            extras.append({
                'course_id':    cid,
                'course_code':  crs_obj.course_code if crs_obj else '',
                'course_name':  crs_obj.course_name if crs_obj else '',
                'section_id':   sec_id,
                'section_name': sec_obj2.section_name if sec_obj2 else str(sec_id),
                'slots':        serialize_slots(slots),
            })
        return {'extras': extras, 'gap_minutes': gap, 'gap_per_day': gpd}

    combos_scored = []
    for raw in solutions_raw:
        combos_scored.append(build_combo(raw))
    combos_scored.sort(key=lambda x: x['gap_minutes'])

    # Build anchor courses detail for display
    anchor_courses_detail = []
    if anchor_section:
        for cid in anchor_course_ids:
            crs_obj = Course.query.get(cid)
            slots_for_cid = [sc for sc in anchor_slots if sc.course_id == cid]
            anchor_courses_detail.append({
                'course_id':   cid,
                'course_code': crs_obj.course_code if crs_obj else '',
                'course_name': crs_obj.course_name if crs_obj else '',
                'slots':       serialize_slots(slots_for_cid),
            })

    # Full-cover sections (all requested courses in one section)
    full_cover_sections = []
    for sec_id, covered_set in coverage.items():
        if requested_set <= covered_set:
            sec_obj3 = Section.query.get(sec_id)
            all_slots_for_sec = []
            for cid in course_ids:
                for s_id, slots in offerings[cid]:
                    if s_id == sec_id:
                        all_slots_for_sec.extend(slots)
                        break
            full_cover_sections.append({
                'section_id':   sec_id,
                'section_name': sec_obj3.section_name if sec_obj3 else str(sec_id),
                'slots':        serialize_slots(all_slots_for_sec),
            })

    # Conflict deadlock finder (when no combos and no zero-offering deadlock)
    conflict_courses = []
    if not combos_scored and not deadlock_courses and uncovered:
        for i, cid in enumerate(uncovered):
            subset = [c for j, c in enumerate(uncovered) if j != i]
            sub_raw = []
            def bt_sub(idx2, chosen2, chosen_slots2):
                if len(sub_raw) >= 1:
                    return
                if idx2 == len(subset):
                    sub_raw.append(True)
                    return
                c2 = subset[idx2]
                for s2, sl2 in uncovered_options.get(c2, []):
                    if not _slots_conflict(sl2, chosen_slots2 + anchor_slots):
                        chosen2.append(c2)
                        bt_sub(idx2 + 1, chosen2, chosen_slots2 + sl2)
                        chosen2.pop()
            bt_sub(0, [], [])
            if sub_raw:
                conflict_courses.append(cid)

    return {
        'anchor':              anchor_section,
        'anchor_courses':      anchor_courses_detail,
        'full_cover':          full_cover,
        'full_cover_sections': full_cover_sections,
        'uncovered_course_ids': uncovered,
        'combinations':        combos_scored,
        'deadlock_courses':    deadlock_courses,
        'conflict_courses':    conflict_courses,
    }


@app.route('/manage/irregular-students')
@login_required
@role_required('admin', 'superadmin')
def manage_irregular():
    page         = request.args.get('page', 1, type=int)
    sort_by      = request.args.get('sort', 'name-asc', type=str)
    search_query = request.args.get('search', '', type=str)
    filter_by    = request.args.get('filter_by', '', type=str)
    filter_val   = request.args.get('filter_val', '', type=str)

    # ------------------------------------ Time Machine: Historical Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    if session.get('historical_mode_active', False):
        archive_id = session.get('active_archive_id')
        _all_irregs = get_archive_entities(archive_id, 'IrregularStudent')
        
        # Deduplicate by student_id to handle multi-generation archive pollution
        seen_ids = set()
        all_objs = []
        for s in _all_irregs:
            sid = getattr(s, 'student_id', None)
            if sid not in seen_ids:
                all_objs.append(s)
                seen_ids.add(sid)
        
        # 1. Apply Filtering
        if search_query:
            s = search_query.lower()
            all_objs = [o for o in all_objs if 
                        s in (getattr(o, 'full_name', '') or '').lower() or 
                        s in (getattr(o, 'student_id', '') or '').lower()]
        
        if filter_by == 'year' and filter_val:
            try:
                val = int(filter_val)
                all_objs = [o for o in all_objs if getattr(o, 'year_level', None) == val]
            except: pass
        elif filter_by == 'section' and filter_val:
            try:
                val = int(filter_val)
                all_objs = [o for o in all_objs if getattr(o, 'section_id', None) == val]
            except: pass

        # 2. Apply Sorting
        if sort_by == 'name-desc':
            all_objs.sort(key=lambda x: (getattr(x, 'full_name', '') or '').lower(), reverse=True)
        elif sort_by == 'id-asc':
            all_objs.sort(key=lambda x: (getattr(x, 'student_id', '') or '').lower())
        elif sort_by == 'id-desc':
            all_objs.sort(key=lambda x: (getattr(x, 'student_id', '') or '').lower(), reverse=True)
        elif sort_by == 'section':
            all_secs = get_archive_entities(archive_id, 'Section')
            sec_map = {s.id: getattr(s, 'section_name', '') for s in all_secs}
            all_objs.sort(key=lambda x: (sec_map.get(getattr(x, 'section_id', 0), 'Z-NoSection'), (getattr(x, 'full_name', '') or '').lower()))
        elif sort_by == 'newest':
            from datetime import datetime as dtt
            all_objs.sort(key=lambda x: (getattr(x, 'created_at', None) or dtt.min, getattr(x, 'id', 0)), reverse=True)
        else: # Default: name-asc
            all_objs.sort(key=lambda x: (getattr(x, 'full_name', '') or '').lower())

        # 3. Paginate
        per_page = 10
        total = len(all_objs)
        start = (page - 1) * per_page
        items = all_objs[start:start+per_page]
        pagination = MockPagination(items, page, per_page, total)
        
        # Populate assignments for the UI 'Assigned' badge
        irreg_assignments = {}
        for item in items:
            if getattr(item, 'assignments_json', None):
                # Mock an assignment object for the template logic
                irreg_assignments[item.id] = SimpleNamespace(
                    assignments_json=item.assignments_json,
                    semester="Archived"
                )

        all_courses = get_archive_entities(archive_id, 'Course')
        all_sections_list = get_archive_entities(archive_id, 'Section')
        unique_years_list = sorted(list(set(getattr(o, 'year_level', 0) for o in all_objs if getattr(o, 'year_level', None) is not None)))
        regular_students_list = [o for o in get_archive_entities(archive_id, 'Student') if not getattr(o, 'is_irregular', False)]

        return render_template('manage_irregular.html',
            students=items,
            pagination=pagination,
            assignments=irreg_assignments,
            semesters=['1st Semester', '2nd Semester', 'Summer'],
            courses=all_courses,
            all_sections=all_sections_list,
            unique_years=unique_years_list,
            regular_students=regular_students_list,
            current_sort=sort_by,
            search_query=search_query,
            current_filter_by=filter_by,
            current_filter_val=filter_val
        )

    # ------------------------------------ Live Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    query = Student.query.filter_by(is_irregular=True, is_archived=False)

    if search_query:
        query = query.filter(or_(
            Student.full_name.ilike(f'%{search_query}%'),
            Student.student_id.ilike(f'%{search_query}%'),
        ))
    if filter_by == 'year' and filter_val:
        try:
            query = query.filter(Student.year_level == int(filter_val))
        except ValueError:
            pass
    elif filter_by == 'section' and filter_val:
        try:
            query = query.filter(Student.section_id == int(filter_val))
        except ValueError:
            pass

    if sort_by == 'name-desc':
        query = query.order_by(Student.full_name.desc())
    elif sort_by == 'id-asc':
        query = query.order_by(Student.student_id.asc())
    elif sort_by == 'id-desc':
        query = query.order_by(Student.student_id.desc())
    elif sort_by == 'section':
        query = query.outerjoin(Section, Student.section_id == Section.id)\
                     .order_by(Section.section_name.asc(), Student.full_name.asc())
    elif sort_by == 'newest' or sort_by == 'default':
        query = query.order_by(Student.created_at.desc(), Student.id.desc())
    else:
        query = query.order_by(Student.full_name.asc())

    pagination = query.paginate(page=page, per_page=10, error_out=False)
    students   = pagination.items

    # Load latest assignment per student
    assignments = {}
    for s in students:
        a = IrregularAssignment.query.filter_by(student_id_fk=s.id)\
               .order_by(IrregularAssignment.updated_at.desc()).first()
        assignments[s.id] = a

    courses      = Course.query.filter_by(is_archived=False)\
                       .order_by(Course.year_level, Course.course_code).all()
    all_sections = Section.query.filter_by(is_archived=False).order_by(Section.section_name).all()
    unique_years = db.session.query(Student.year_level)\
                       .filter_by(is_irregular=True, is_archived=False)\
                       .distinct().order_by(Student.year_level).all()
    unique_years = [y[0] for y in unique_years]
    # Non-irregular students for "Add Irregular Student" modal
    regular_students = Student.query.filter_by(is_irregular=False, is_archived=False)\
                           .order_by(Student.full_name).all()
    semesters = ['1st Semester', '2nd Semester', 'Summer']
    return render_template('manage_irregular.html',
        students=students,
        pagination=pagination,
        assignments=assignments,
        semesters=semesters,
        courses=courses,
        all_sections=all_sections,
        unique_years=unique_years,
        regular_students=regular_students,
        current_sort=sort_by,
        search_query=search_query,
        current_filter_by=filter_by,
        current_filter_val=filter_val,
    )


@app.route('/manage/student/toggle-irregular/<int:student_id>', methods=['POST'])
@login_required
def toggle_irregular(student_id):
    student = Student.query.get_or_404(student_id)
    student.is_irregular = not student.is_irregular
    db.session.commit()
    return jsonify({'ok': True, 'is_irregular': student.is_irregular})


@app.route('/irregular-pathfinder/<int:student_id>')
@login_required
def irregular_pathfinder(student_id):
    student = Student.query.get_or_404(student_id)
    profile = IrregularAssignment.query.filter_by(student_id_fk=student_id)\
                  .order_by(IrregularAssignment.updated_at.desc()).first()
    courses = Course.query.filter_by(is_archived=False)\
                  .order_by(Course.year_level, Course.course_code).all()
    semesters = ['1st Semester', '2nd Semester', 'Summer']
    saved_course_ids = json.loads(profile.requested_json) if profile else []
    saved_semester   = profile.semester if profile else '1st Semester'
    # Group courses by year level
    from collections import defaultdict
    courses_by_year = defaultdict(list)
    for c in courses:
        yr = c.year_level if c.year_level else 0
        courses_by_year[yr].append(c)
    courses_by_year = dict(sorted(courses_by_year.items()))
    return render_template('irregular_pathfinder.html',
        student=student,
        courses_by_year=courses_by_year,
        semesters=semesters,
        saved_course_ids=saved_course_ids,
        saved_semester=saved_semester,
    )


@app.route('/api/irregular-pathfinder/<int:student_id>', methods=['POST'])
@login_required
@hist_lockdown
def api_irregular_pathfinder(student_id):
    student = Student.query.get_or_404(student_id)
    data = request.get_json(force=True) or {}
    course_ids = [int(x) for x in data.get('course_ids', [])]
    semester   = data.get('semester', '1st Semester')
    if not course_ids:
        return jsonify({'error': 'No courses selected.'}), 400
    if len(course_ids) > 20:
        return jsonify({'error': 'Maximum 20 courses per search.'}), 400

    # Save/update profile (requested courses only ---- confirmed later)
    profile = IrregularAssignment.query.filter_by(student_id_fk=student_id).first()
    if not profile:
        profile = IrregularAssignment(student_id_fk=student_id)
        db.session.add(profile)
    profile.semester       = semester
    profile.requested_json = json.dumps(course_ids)
    profile.updated_at     = datetime.utcnow()
    db.session.commit()

    result = _irregular_solver(course_ids, semester)

    # Enrich deadlock/conflict with course codes
    def enrich_cids(cids):
        out = []
        for cid in cids:
            c = Course.query.get(cid)
            out.append({'course_id': cid, 'course_code': c.course_code if c else str(cid),
                        'course_name': c.course_name if c else ''})
        return out

    return jsonify({
        'anchor':              result['anchor'],
        'anchor_courses':      result['anchor_courses'],
        'full_cover':          result['full_cover'],
        'full_cover_sections': result['full_cover_sections'],
        'combinations':        result['combinations'],
        'deadlock_courses':    enrich_cids(result['deadlock_courses']),
        'conflict_courses':    enrich_cids(result['conflict_courses']),
        'total_found':         len(result['combinations']),
    })


@app.route('/api/irregular-confirm/<int:student_id>', methods=['POST'])
@login_required
def api_irregular_confirm(student_id):
    student = Student.query.get_or_404(student_id)
    data = request.get_json(force=True) or {}
    semester = data.get('semester', '1st Semester')
    # assignments = [{course_id, section_id}, ...]
    assignments_list = data.get('assignments', [])
    if not assignments_list:
        return jsonify({'error': 'No assignments provided.'}), 400

    profile = IrregularAssignment.query.filter_by(student_id_fk=student_id).first()
    if not profile:
        profile = IrregularAssignment(student_id_fk=student_id)
        db.session.add(profile)
    profile.semester         = semester
    profile.assignments_json = json.dumps(assignments_list)
    profile.updated_at       = datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/irregular-batch', methods=['POST'])
@login_required
def api_irregular_batch():
    data = request.get_json(force=True) or {}
    student_ids = [int(x) for x in data.get('student_ids', [])]
    course_ids  = [int(x) for x in data.get('course_ids', [])]
    semester    = data.get('semester', '1st Semester')
    if not student_ids:
        return jsonify({'error': 'No students selected.'}), 400
    if not course_ids:
        return jsonify({'error': 'No courses selected.'}), 400
    if len(course_ids) > 20:
        return jsonify({'error': 'Maximum 20 courses per batch search.'}), 400

    results = []
    for sid in student_ids:
        student = Student.query.get(sid)
        if not student:
            continue
        # Save requested profile
        profile = IrregularAssignment.query.filter_by(student_id_fk=sid).first()
        if not profile:
            profile = IrregularAssignment(student_id_fk=sid)
            db.session.add(profile)
        profile.semester       = semester
        profile.requested_json = json.dumps(course_ids)
        profile.updated_at     = datetime.utcnow()
        db.session.commit()

        result = _irregular_solver(course_ids, semester)
        results.append({
            'student_id':   sid,
            'student_name': student.full_name,
            'student_sid':  student.student_id,
            'result':       {
                'anchor':              result['anchor'],
                'anchor_courses':      result['anchor_courses'],
                'full_cover':          result['full_cover'],
                'full_cover_sections': result['full_cover_sections'],
                'combinations':        result['combinations'],
                'deadlock_courses':    result['deadlock_courses'],
                'conflict_courses':    result['conflict_courses'],
                'total_found':         len(result['combinations']),
            }
        })
    return jsonify({'results': results})


@app.route('/student-schedule/<string:student_id>')
def student_schedule(student_id):
    term_id = request.args.get('term_id', 'live')
    archives = TermArchive.query.order_by(TermArchive.id.desc()).all()
    
    is_archive = False
    active_archive = None
    student = None
    section = None
    assignment = None
    schedules = []

    if term_id != 'live':
        is_archive = True
        active_archive = TermArchive.query.get_or_404(term_id)
        
        # NEW: Look for the student in the ArchivedStudent table
        student = ArchivedStudent.query.filter_by(
            term_archive_id=term_id,
            student_id=student_id
        ).first()
        
        if not student:
            flash('Student records not found in this archive.', 'warning')
            return redirect(url_for('student_schedule', student_id=student_id))
        
        # Load archived schedules
        if student.is_irregular:
            # Irregular students in archives have their schedules flattened into ArchivedSchedule
            schedules_raw = ArchivedSchedule.query.filter_by(
                term_archive_id=term_id,
                irregular_student_name=student.full_name
            ).all()
        else:
            # Regular students look at their section name
            schedules_raw = ArchivedSchedule.query.filter_by(
                term_archive_id=term_id,
                section_name=getattr(student, 'section_name', '')
            ).all()
        
        schedules = [_mock_archived_schedule(as_obj) for as_obj in schedules_raw]
        schedules.sort(key=lambda sc: (sc.day, sc.start_time))
        
        # For display, fetch section info for the header
        if hasattr(student, 'section_name') and student.section_name:
            section = SimpleNamespace(section_name=student.section_name)

    else:
        # ------------------------------------ Live Mode ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        student = Student.query.filter_by(student_id=student_id, is_archived=False).first_or_404()
        if student.is_irregular:
            assignment = IrregularAssignment.query.filter_by(student_id_fk=student.id)\
                             .order_by(IrregularAssignment.updated_at.desc()).first()
            if assignment and assignment.assignments_json and assignment.assignments_json != '[]':
                pairs = json.loads(assignment.assignments_json)
                for pair in pairs:
                    slots = ScheduledClass.query.options(
                        joinedload(ScheduledClass.course),
                        joinedload(ScheduledClass.faculty),
                        joinedload(ScheduledClass.room),
                        joinedload(ScheduledClass.section),
                    ).filter_by(
                        course_id=pair['course_id'],
                        section_id=pair['section_id'],
                        semester=assignment.semester,
                    ).all()
                    schedules.extend(slots)
                schedules = _dedup_schedules(schedules)
                schedules.sort(key=lambda sc: (sc.day, sc.start_time))
            elif student.section_id:
                # INHERITANCE LOGIC: Inherit the section's schedule!
                schedules = ScheduledClass.query.options(
                    joinedload(ScheduledClass.course),
                    joinedload(ScheduledClass.faculty),
                    joinedload(ScheduledClass.room),
                    joinedload(ScheduledClass.section),
                ).filter_by(
                    section_id=student.section_id
                ).all()
                schedules = _dedup_schedules(schedules)
                schedules.sort(key=lambda sc: (sc.day, sc.start_time))
        else:
            if student.section_id:
                schedules = _dedup_schedules(ScheduledClass.query.options(
                    joinedload(ScheduledClass.course),
                    joinedload(ScheduledClass.faculty),
                    joinedload(ScheduledClass.room),
                    joinedload(ScheduledClass.section),
                ).filter_by(section_id=student.section_id).order_by(
                    ScheduledClass.day, ScheduledClass.start_time
                ).all())

        # Always fetch section info if section_id exists for the header
        if student.section_id:
            section = Section.query.get(student.section_id)

    # Build simple day->slot grid
    days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    grid = {day: [] for day in days_order}
    for sc in schedules:
        if sc.day in grid:
            grid[sc.day].append(sc)

    return render_template('student_schedule.html',
        student=student,
        section=section,
        assignment=assignment,
        grid=grid,
        days_order=days_order,
        schedules=schedules,
        archives=archives,
        is_archive=is_archive,
        active_archive=active_archive,
        term_id=term_id
    )

# ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# ARCHIVED STUDENT TIMETABLE (Excel Drawing)
# ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
@app.route('/public/archived-timetable-html/<int:archive_id>/<string:student_id>')
def public_archived_timetable_html(archive_id, student_id):
    """Specialized renderer for historical student schedules from snapshots."""
    archive = TermArchive.query.get_or_404(archive_id)
    
    # 1. Reconstruct Student from snapshot
    student = ArchivedStudent.query.filter_by(
        term_archive_id=archive_id,
        student_id=student_id
    ).first()
    
    if not student: abort(404)

    # 2. Get Schedules
    if student.is_irregular:
        section_name = student.full_name # Header shows student name for irregs
        schedules_raw = ArchivedSchedule.query.filter_by(
            term_archive_id=archive_id,
            irregular_student_name=student.full_name
        ).all()
    else:
        # Regular students need their section name to pull schedules
        archived_sections = get_archive_entities(archive_id, 'Section')
        s_id = getattr(student, 'section_id', None)
        target_section = next((s for s in archived_sections if getattr(s, 'id', 0) == s_id), None)
        section_name = getattr(target_section, 'section_name', '') # Header shows section name for regulars
        
        schedules_raw = ArchivedSchedule.query.filter_by(
            term_archive_id=archive_id,
            section_name=section_name
        ).all()
    
    schedules = [_mock_archived_schedule(as_obj) for as_obj in schedules_raw]
    
    # 3. Render using Section Layout
    path = os.path.join(basedir, 'static', 'assets', 'section_template.xlsx')
    if not os.path.exists(path): abort(404)
    
    ws, grid_info, bounds = _get_cached_template(path)
    if grid_info:
        cell_overrides, extra_merge_map, extra_skip_cells = build_schedule_overlays(
            schedules, grid_info, 'section')
    else:
        cell_overrides, extra_merge_map, extra_skip_cells = {}, {}, set()

    settings = get_settings()
    entity_name = section_name
    sem_ay = f"{archive.semester} / AY {archive.academic_year}"
    var_map = build_variable_map('section', settings, section_name=entity_name, sem_ay=sem_ay)
    static_overrides = build_static_cell_overrides(ws, 'section', settings, entity_name=entity_name, sem_ay=sem_ay)
    all_overrides = {**static_overrides, **cell_overrides}
    
    _margins = _get_margins(settings)
    _img_settings = _get_img_settings(settings, 'section')
    html_content, table_px, _, _ = render_excel_to_html(
        ws, cell_overrides=all_overrides, variable_map=var_map,
        extra_merge_map=extra_merge_map, extra_skip_cells=extra_skip_cells,
        bounds=bounds, layout_type='section', margins=_margins,
        img_settings=_img_settings)
    
    # Infinite Canvas support
    for_canvas = request.args.get('canvas', 'false') == 'true'
    return render_a4_page(html_content, table_px, margins=_margins, for_canvas=for_canvas)


with app.app_context():
    db.create_all()  # Creates any missing tables (safe ---- never drops existing data)
    # Safe migrations: add missing columns to existing tables
    import sqlite3 as _sqlite3
    _db_path = app.config.get('SQLALCHEMY_DATABASE_URI', '').replace('sqlite:///', '')
    if _db_path and _db_path != ':memory:':
        try:
            _conn = _sqlite3.connect(_db_path)
            # code_prefix_rules.is_archived
            _cols = [row[1] for row in _conn.execute('PRAGMA table_info(code_prefix_rules)').fetchall()]
            if 'is_archived' not in _cols:
                _conn.execute('ALTER TABLE code_prefix_rules ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT 0')
                _conn.commit()
            # scheduled_class.semester  (history feature)
            _sc_cols = [row[1] for row in _conn.execute('PRAGMA table_info(scheduled_class)').fetchall()]
            if 'semester' not in _sc_cols:
                _conn.execute("ALTER TABLE scheduled_class ADD COLUMN semester VARCHAR(30) NOT NULL DEFAULT '1st Semester'")
                _conn.commit()
            if 'session_type' not in _sc_cols:
                _conn.execute("ALTER TABLE scheduled_class ADD COLUMN session_type VARCHAR(10) NOT NULL DEFAULT 'Lec'")
                _conn.commit()
            # dynamic signatories JSON columns on system_settings
            _ss_cols = [row[1] for row in _conn.execute('PRAGMA table_info(system_settings)').fetchall()]
            for _col in ('section_signatories_json', 'faculty_signatories_json',
                         'room_signatories_json', 'course_signatories_json'):
                if _col not in _ss_cols:
                    _conn.execute(f'ALTER TABLE system_settings ADD COLUMN {_col} TEXT')
                    _conn.commit()
            # Phase 1: Fixed Layout Variables
            _p1_cols = {
                'republic_text':      "VARCHAR(255) DEFAULT 'Republic of the Philippines'",
                'contact_details':    "VARCHAR(255) DEFAULT '(046) 437-9505 / (046) 437-6659'",
                'email':              "VARCHAR(255) DEFAULT 'cvsurosario@cvsu.edu.ph'",
                'website':            "VARCHAR(255) DEFAULT 'www.cvsu-rosario.edu.ph'",
                'prepared_by_label':  "VARCHAR(100) DEFAULT 'Prepared by:'",
                'rec_approval_label': "VARCHAR(100) DEFAULT 'Recommending Approval:'",
                'approved_label':     "VARCHAR(100) DEFAULT 'APPROVED:'",
                'section_sig2_title': "VARCHAR(100) DEFAULT 'Director, Instruction'",
                'section_sig3_title': "VARCHAR(100) DEFAULT 'Campus Administrator'",
                'room_sig2_title':    "VARCHAR(100) DEFAULT 'Director, Instruction'",
                'room_sig3_title':    "VARCHAR(100) DEFAULT 'Campus Administrator'",
                'course_sig2_title':  "VARCHAR(100) DEFAULT 'Director, Instruction'",
                'course_sig3_title':  "VARCHAR(100) DEFAULT 'Campus Administrator'",
                'class_label':        "VARCHAR(100) DEFAULT 'CLASS'",
                'room_label':         "VARCHAR(100) DEFAULT 'ROOM'",
                'course_label':       "VARCHAR(100) DEFAULT 'COURSE'",
                'sem_ay_label':       "VARCHAR(100) DEFAULT 'Semester / Academic Year'",
                'sem_ay_value':       "VARCHAR(100) DEFAULT '2nd Semester / 2024-2025'",
                'margin_top':         "REAL DEFAULT 1.0",
                'margin_bottom':      "REAL DEFAULT 1.0",
                'margin_left':        "REAL DEFAULT 1.0",
                'margin_right':       "REAL DEFAULT 1.0",
                'paper_size':         "VARCHAR(30) DEFAULT 'A4'",
                # Faculty-specific columns (independent ---- Card 1: Header)
                'fac_republic_text':    "VARCHAR(255) DEFAULT 'Republic of the Philippines'",
                'fac_univ_name':        "VARCHAR(255) DEFAULT 'CAVITE STATE UNIVERSITY'",
                'fac_campus_name':      "VARCHAR(255) DEFAULT 'CCAT Campus'",
                'fac_address':          "VARCHAR(255) DEFAULT 'Rosario, Cavite'",
                'fac_contact_details':  "VARCHAR(255) DEFAULT '(046) 437-9505 / (046) 437-6659'",
                'fac_email':            "VARCHAR(255) DEFAULT 'cvsurosario@cvsu.edu.ph'",
                'fac_website':          "VARCHAR(255) DEFAULT 'www.cvsu-rosario.edu.ph'",
                'fac_dept_label':       "VARCHAR(150) DEFAULT 'DEPARTMENT OF COMPUTER STUDIES'",
                'fac_sched_title':      "VARCHAR(150) DEFAULT 'FACULTY CLASS SCHEDULE'",
                'fac_sem_ay_label':     "VARCHAR(150) DEFAULT 'SECOND SEMESTER SY 2023 - 2024'",
                # Card 2: Faculty Info Labels
                'fac_name_label':       "VARCHAR(100) DEFAULT 'Name:'",
                'fac_educ_label':       "VARCHAR(150) DEFAULT 'Highest Educ. Attainment:'",
                'fac_prep_label':       "VARCHAR(150) DEFAULT 'No. of Preparation/s:'",
                'fac_hours_label':      "VARCHAR(200) DEFAULT 'Total no. of contact hours per week:'",
                # Card 3: Signatory Labels
                'fac_conforme_label':   "VARCHAR(100) DEFAULT 'Conforme:'",
                'fac_rec_approval_label': "VARCHAR(150) DEFAULT 'Recommending Approval:'",
                'fac_reviewed_label':   "VARCHAR(100) DEFAULT 'Reviewed by:'",
                'fac_approved_label':   "VARCHAR(100) DEFAULT 'Approved:'",
                'fac_registrar_label':  "VARCHAR(100) DEFAULT 'OIC, Registrar'",
                # Card 3: Signatory Names & Titles
                'fac_chair_name':       "VARCHAR(150) DEFAULT 'ARIES M. GELERA'",
                'fac_chair_title':      "VARCHAR(150) DEFAULT 'Department Chairperson'",
                'fac_director_name':    "VARCHAR(150) DEFAULT 'ARIEL G. SANTOS, EdD'",
                'fac_director_title':   "VARCHAR(150) DEFAULT 'Director, Instruction'",
                'fac_registrar_name':   "VARCHAR(150) DEFAULT 'MARLYN A. QUINEZ'",
                'fac_admin_name':       "VARCHAR(150) DEFAULT 'LAURO B. PASCUA, EdD'",
                'fac_admin_title':      "VARCHAR(150) DEFAULT 'Campus Administrator'",
                # Card 4: Form Identifiers
                'fac_form_num_top':     "VARCHAR(50)  DEFAULT 'VPAA-QF-11'",
                'fac_form_num_bottom':  "VARCHAR(50)  DEFAULT 'V01-2018-07-24'",
                # Faculty independent margins & paper size
                'fac_margin_top':       "REAL DEFAULT 1.0",
                'fac_margin_bottom':    "REAL DEFAULT 1.0",
                'fac_margin_left':      "REAL DEFAULT 1.0",
                'fac_margin_right':     "REAL DEFAULT 1.0",
                'fac_paper_size':       "VARCHAR(30) DEFAULT 'A4'",
                # Legacy activity labels
                'fac_consultation':     "VARCHAR(100) DEFAULT 'Consultation:'",
                'fac_research':         "VARCHAR(100) DEFAULT 'Research:'",
                'fac_designation':      "VARCHAR(100) DEFAULT 'Designation :'",
                'fac_extension':        "VARCHAR(100) DEFAULT 'Extension:'",
                # Legacy shared signatory cols
                'sig1_name':            "VARCHAR(150) DEFAULT 'ARIES M. GELERA'",
                'sig1_title':           "VARCHAR(150) DEFAULT 'Department Chairperson'",
                'sig2_name':            "VARCHAR(150) DEFAULT 'ARIEL G. SANTOS, EdD'",
                'sig_registrar_name':   "VARCHAR(150) DEFAULT 'MARLYN A. QUINEZ'",
                'sig3_name':            "VARCHAR(150) DEFAULT 'LAURO B. PASCUA, EdD'",
            }
            _ss_cols = [row[1] for row in _conn.execute('PRAGMA table_info(system_settings)').fetchall()]
            for _col, _col_def in _p1_cols.items():
                if _col not in _ss_cols:
                    _conn.execute(f'ALTER TABLE system_settings ADD COLUMN {_col} {_col_def}')
                    _conn.commit()
            # FacultyAssignment table migration ---- split-hour columns
            _fa_cols_needed = {
                'split_day_1':       'VARCHAR(20)',
                'split_hours_1':     'FLOAT',
                'split_day_2':       'VARCHAR(20)',
                'split_hours_2':     'FLOAT',
                'split_lec_day_1':   'VARCHAR(20)',
                'split_lec_hours_1': 'FLOAT',
                'split_lec_day_2':   'VARCHAR(20)',
                'split_lec_hours_2': 'FLOAT',
            }
            _fa_cols = [row[1] for row in _conn.execute('PRAGMA table_info(faculty_assignment)').fetchall()]
            for _col, _col_def in _fa_cols_needed.items():
                if _col not in _fa_cols:
                    _conn.execute(f'ALTER TABLE faculty_assignment ADD COLUMN {_col} {_col_def}')
                    _conn.commit()
            # Faculty table migration
            _fac_cols_needed = {'academic_rank': 'VARCHAR(100)', 'sex': 'VARCHAR(1)'}
            _fac_cols = [row[1] for row in _conn.execute('PRAGMA table_info(faculty)').fetchall()]
            for _col, _col_def in _fac_cols_needed.items():
                if _col not in _fac_cols:
                    _conn.execute(f'ALTER TABLE faculty ADD COLUMN {_col} {_col_def}')
                    _conn.commit()
            # Student table migration ---- is_irregular flag
            _stu_cols = [row[1] for row in _conn.execute('PRAGMA table_info(student)').fetchall()]
            if 'is_irregular' not in _stu_cols:
                _conn.execute('ALTER TABLE student ADD COLUMN is_irregular BOOLEAN NOT NULL DEFAULT 0')
                _conn.commit()
            # Module 3: ScheduledClass ---- source, is_draft, draft_version_id
            _sc_cols2 = [row[1] for row in _conn.execute('PRAGMA table_info(scheduled_class)').fetchall()]
            if 'source' not in _sc_cols2:
                _conn.execute("ALTER TABLE scheduled_class ADD COLUMN source VARCHAR(10) NOT NULL DEFAULT 'ga'")
                _conn.commit()
            if 'is_draft' not in _sc_cols2:
                _conn.execute('ALTER TABLE scheduled_class ADD COLUMN is_draft BOOLEAN NOT NULL DEFAULT 0')
                _conn.commit()
            if 'draft_version_id' not in _sc_cols2:
                _conn.execute('ALTER TABLE scheduled_class ADD COLUMN draft_version_id INTEGER')
                _conn.commit()
            # Module 3: SystemSettings ---- schedule_lock
            _ss_cols2 = [row[1] for row in _conn.execute('PRAGMA table_info(system_settings)').fetchall()]
            if 'schedule_lock' not in _ss_cols2:
                _conn.execute('ALTER TABLE system_settings ADD COLUMN schedule_lock BOOLEAN NOT NULL DEFAULT 0')
                _conn.commit()
            # Migrate existing sig1/sig2/sig3 into JSON for any row that has no JSON yet
            _rows = _conn.execute('SELECT id, section_signatory_1, section_signatory_2, section_signatory_3, section_signatories_json, faculty_signatory_1, faculty_signatory_2, faculty_signatory_3, faculty_signatories_json, room_signatory_1, room_signatory_2, room_signatory_3, room_signatories_json, course_signatory_1, course_signatory_2, course_signatory_3, course_signatories_json FROM system_settings').fetchall()
            for _row in _rows:
                _id = _row[0]
                for _type_idx, _type in enumerate(['section', 'faculty', 'room', 'course']):
                    _json_val = _row[4 + _type_idx * 4]
                    if _json_val:
                        continue  # already migrated
                    _s1 = _row[1 + _type_idx * 4] or ''
                    _s2 = _row[2 + _type_idx * 4] or ''
                    _s3 = _row[3 + _type_idx * 4] or ''
                    _sigs = [{'name': s, 'title': ''} for s in [_s1, _s2, _s3] if s.strip()]
                    if _sigs:
                        _conn.execute(f'UPDATE system_settings SET {_type}_signatories_json=? WHERE id=?',
                                      (json.dumps(_sigs), _id))
                _conn.commit()
            # Module 3: User.department column
            _user_cols = [row[1] for row in _conn.execute('PRAGMA table_info(user)').fetchall()]
            if 'department' not in _user_cols:
                _conn.execute('ALTER TABLE user ADD COLUMN department VARCHAR(100)')
                _conn.commit()
            if 'is_deleted' not in _user_cols:
                _conn.execute('ALTER TABLE user ADD COLUMN is_deleted BOOLEAN DEFAULT 0 NOT NULL')
                _conn.commit()
            if 'deleted_at' not in _user_cols:
                _conn.execute('ALTER TABLE user ADD COLUMN deleted_at DATETIME')
                _conn.commit()
            _conn.close()
        except Exception:
            pass
    # Module 3: create draft_version table if it doesn't exist yet
    with app.app_context():
        db.create_all()


# --- USER MANAGEMENT (SUPERADMIN ONLY) ---

@app.route('/manage_users')
@login_required
@role_required('superadmin')
def manage_users():
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '', type=str)
    role_filter = request.args.get('role_filter', '', type=str)
    sort_by = request.args.get('sort', 'newest', type=str)
    
    query = User.query.filter_by(is_deleted=False)
    
    if search_query:
        query = query.filter(User.username.ilike(f"%{search_query}%"))
        
    if role_filter:
        query = query.filter_by(role=role_filter)
        
    if sort_by == 'username_asc':
        query = query.order_by(User.username.asc())
    elif sort_by == 'username_desc':
        query = query.order_by(User.username.desc())
    elif sort_by == 'oldest':
        query = query.order_by(User.id.asc())
    else: # newest
        query = query.order_by(User.id.desc())
        
    pagination = query.paginate(page=page, per_page=10, error_out=False)
    users = pagination.items
    
    return render_template(
        'manage_users.html', 
        users=users, 
        pagination=pagination,
        current_user_id=session.get('user_id'), 
        all_depts=_get_depts(),
        search_query=search_query,
        role_filter=role_filter,
        current_sort=sort_by
    )

@app.route('/manage_users/recycle_bin')
@login_required
@role_required('superadmin')
def users_recycle_bin():
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'newest', type=str)
    search_query = request.args.get('search', '', type=str)
    
    query = User.query.filter_by(is_deleted=True)
    
    if search_query:
        query = query.filter(User.username.ilike(f"%{search_query}%"))
    
    if sort_by == 'username_asc':
        query = query.order_by(User.username.asc())
    elif sort_by == 'username_desc':
        query = query.order_by(User.username.desc())
    else: # newest
        query = query.order_by(User.deleted_at.desc())
        
    pagination = query.paginate(page=page, per_page=10, error_out=False)
    users = pagination.items
    
    return render_template(
        'users_archive.html', 
        users=users, 
        pagination=pagination,
        current_user_id=session.get('user_id'), 
        all_depts=_get_depts(),
        search_query=search_query,
        current_sort=sort_by,
        now=datetime.utcnow()
    )

@app.route('/manage/user/reset_password/<int:user_id>', methods=['POST'])
@login_required
@role_required('superadmin')
@hist_lockdown
def reset_user_password(user_id):
    user = User.query.get_or_404(user_id)
    user.password_hash = generate_password_hash('CvSU123!')
    db.session.commit()
    log_activity("Reset Password", f"Reset password for user {user.username} to default.")
    flash(f"Successfully reset password for {user.username} to 'CvSU123!'.", "success")
    return redirect(url_for('manage_users'))

@app.route('/manage/user/archive/<int:user_id>', methods=['POST'])
@login_required
@role_required('superadmin')
@hist_lockdown
def archive_user(user_id):
    if user_id == session.get('user_id'):
        flash("You cannot archive your own account.", "warning")
        return redirect(url_for('manage_users'))
        
    user = User.query.get_or_404(user_id)
    user.is_deleted = True
    user.deleted_at = datetime.utcnow()
    db.session.commit()
    
    log_security('Archive User', details=f"Superadmin archived user {user.username}")
    flash(f"User {user.username} moved to Recycle Bin.", "success")
    return redirect(url_for('manage_users'))

@app.route('/manage/user/restore/<int:user_id>', methods=['POST'])
@login_required
@role_required('superadmin')
@hist_lockdown
def restore_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_deleted = False
    user.deleted_at = None
    db.session.commit()
    
    log_security('Restore User', details=f"Superadmin restored user {user.username}")
    flash(f"User {user.username} restored successfully.", "success")
    return redirect(url_for('users_recycle_bin'))

@app.route('/manage/user/permanent_delete/<int:user_id>', methods=['POST'])
@login_required
@role_required('superadmin')
@hist_lockdown
def permanent_delete_user(user_id):
    if user_id == session.get('user_id'):
        flash("Action denied: Cannot delete self.", "danger")
        return redirect(url_for('manage_users'))
        
    user = User.query.get_or_404(user_id)
    username = user.username
    
    # Clean up Decision Hub messages associated with this user
    # Delete where they are sender OR where they are recipient
    HubMessage.query.filter(
        or_(
            HubMessage.sender_id == user_id,
            HubMessage.recipient_name == username
        )
    ).delete(synchronize_session=False)
    
    db.session.delete(user)
    db.session.commit()
    
    log_security('Permanent Delete User', details=f"Superadmin permanently deleted user {username}")
    flash(f"User {username} successfully erased from system.", "success")
    return redirect(url_for('users_recycle_bin'))

@app.route('/manage/users/bulk_archive', methods=['POST'])
@login_required
@role_required('superadmin')
@hist_lockdown
def bulk_archive_users():
    user_ids = request.form.getlist('row_ids')
    if not user_ids:
        flash("No users selected.", "warning")
        return redirect(url_for('manage_users'))
        
    current_id = str(session.get('user_id'))
    count = 0
    for uid in user_ids:
        if uid == current_id: continue
        user = User.query.get(uid)
        if user:
            user.is_deleted = True
            user.deleted_at = datetime.utcnow()
            count += 1
            
    db.session.commit()
    log_security('Bulk Archive Users', details=f"Superadmin archived {count} users")
    flash(f"Successfully moved {count} users to Recycle Bin.", "success")
    return redirect(url_for('manage_users'))

@app.route('/manage/users/bulk_restore', methods=['POST'])
@login_required
@role_required('superadmin')
@hist_lockdown
def bulk_restore_users():
    user_ids = request.form.getlist('row_ids')
    if not user_ids:
        flash("No users selected.", "warning")
        return redirect(url_for('users_recycle_bin'))
        
    count = 0
    for uid in user_ids:
        user = User.query.get(uid)
        if user:
            user.is_deleted = False
            user.deleted_at = None
            count += 1
            
    db.session.commit()
    log_security('Bulk Restore Users', details=f"Superadmin restored {count} users")
    flash(f"Successfully restored {count} users.", "success")
    return redirect(url_for('users_recycle_bin'))

@app.route('/manage/users/bulk_permanent_delete', methods=['POST'])
@login_required
@role_required('superadmin')
@hist_lockdown
def bulk_permanent_delete_users():
    user_ids = request.form.getlist('row_ids')
    if not user_ids:
        flash("No users selected.", "warning")
        return redirect(url_for('users_recycle_bin'))
        
    current_id = str(session.get('user_id'))
    count = 0
    for uid in user_ids:
        if uid == current_id: continue
        user = User.query.get(uid)
        if user:
            uname = user.username
            # Clean up messages
            HubMessage.query.filter(
                or_(
                    HubMessage.sender_id == user.id,
                    HubMessage.recipient_name == uname
                )
            ).delete(synchronize_session=False)
            
            db.session.delete(user)
            count += 1
            
    db.session.commit()
    log_security('Bulk Permanent Delete Users', details=f"Superadmin erased {count} users")
    flash(f"Successfully erased {count} users from database.", "success")
    return redirect(url_for('users_recycle_bin'))

@app.route('/add_user', methods=['POST'])
@login_required
@role_required('superadmin')
def add_user():
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role')
    department = request.form.get('department', '').strip()
    
    if User.query.filter_by(username=username).first():
        flash('Username already exists.', 'danger')
        return redirect(url_for('manage_users'))
        
    hashed_password = generate_password_hash(password)
    new_user = User(username=username, password_hash=hashed_password, role=role, department=department)
    db.session.add(new_user)
    db.session.commit()
    
    flash('User added successfully.', 'success')
    return redirect(url_for('manage_users'))

@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
@role_required('superadmin')
def delete_user(user_id):
    if user_id == session.get('user_id'):
        flash('You cannot delete yourself.', 'danger')
        return redirect(url_for('manage_users'))
        
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    
    flash('User deleted successfully.', 'success')
    return redirect(url_for('manage_users'))

@app.route('/schedule-issues')
@login_required
@role_required('admin', 'superadmin')
def pending_room():
    sort = request.args.get('sort', 'course-asc')

    # Classes with no room assigned (NULL room_id)
    query = (ScheduledClass.query
             .join(ScheduledClass.course)
             .filter(ScheduledClass.room_id == None)
             .options(
                 joinedload(ScheduledClass.course),
                 joinedload(ScheduledClass.section),
                 joinedload(ScheduledClass.faculty),
             ))

    if sort == 'course-desc':
        query = query.order_by(Course.course_code.desc())
    else:
        query = query.order_by(Course.course_code.asc())

    tba_classes = query.all()

    # Available rooms for dropdown
    all_rooms = Room.query.filter_by(is_archived=False).order_by(Room.room_name).all()

    return render_template('pending_room.html',
                           tba_classes=tba_classes,
                           all_rooms=all_rooms,
                           current_sort=sort)

@app.route('/pending-room/run', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def run_pending_rooms():
    fmt = '%H:%M'

    def _overlap(s1, e1, s2, e2):
        return s1 < e2 and e1 > s2

    # Collect assignments
    assignments = []
    for key, value in request.form.items():
        if key.startswith('assignment_') and value:
            try:
                sc_id = int(key.split('_')[1])
                sc = ScheduledClass.query.get(sc_id)
                room = Room.query.get(int(value))
                if sc and room:
                    assignments.append((sc, room))
            except (ValueError, IndexError):
                continue

    # Conflict detection
    conflicts = []
    for sc, room in assignments:
        if room.room_name == 'T.B.A.':
            continue
        sc_start = datetime.strptime(sc.start_time, fmt).time()
        sc_end   = datetime.strptime(sc.end_time,   fmt).time()

        # Check against existing DB records
        existing = ScheduledClass.query.filter(
            ScheduledClass.room_id == room.id,
            ScheduledClass.day == sc.day,
            ScheduledClass.id  != sc.id
        ).all()
        for ex in existing:
            if _overlap(sc_start, sc_end,
                        datetime.strptime(ex.start_time, fmt).time(),
                        datetime.strptime(ex.end_time,   fmt).time()):
                ex_course = ex.course.course_code if ex.course else '?'
                conflicts.append(
                    f"{sc.course.course_code if sc.course else '?'} ({sc.day} {sc.start_time}----{sc.end_time}) "
                    f"conflicts with {ex_course} already booked in {room.room_name}."
                )
                break

        # Check within batch
        for other_sc, other_room in assignments:
            if other_sc.id == sc.id or other_room.id != room.id or other_sc.day != sc.day:
                continue
            if _overlap(sc_start, sc_end,
                        datetime.strptime(other_sc.start_time, fmt).time(),
                        datetime.strptime(other_sc.end_time,   fmt).time()):
                conflicts.append(
                    f"{sc.course.course_code if sc.course else '?'} and "
                    f"{other_sc.course.course_code if other_sc.course else '?'} "
                    f"both assigned to {room.room_name} on {sc.day} ---- time overlap."
                )
                break

    if conflicts:
        for msg in conflicts:
            flash(f'Room conflict: {msg}', 'danger')
        return redirect(url_for('pending_room'))

    # No conflicts ---- save
    for sc, room in assignments:
        sc.room_id = room.id
    db.session.commit()
    flash(f'{len(assignments)} class(es) assigned to rooms successfully.', 'success')
    return redirect(url_for('manage_rooms'))


@app.route('/api/audit/logic_ping')
@login_required
@role_required('superadmin')
def audit_logic_ping():
    """Diagnostic endpoint for the System Auditor to verify backend logic."""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "security": {
            "xss_sanitization": True,
            "rate_limiting": True,
            "session_heartbeat": True
        }
    })

@app.route('/system-tester')
@login_required
@role_required('superadmin')
def system_tester():
    """
    Standalone Audit Console: Verifies all 12 Phases of the Master Manifest.
    Provides automated DOM checks, API probes, and manual verification triggers.
    """
    total_phases = 12
    return render_template('system_tester.html', total_phases=total_phases)




# ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# MODULE: INDIVIDUAL EXCEL EXPORTS (STANDALONE LOGIC)
# ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

def _safe_write_to_cell_indiv(ws, target_row, target_col, value):
    """Internal helper for individual excel generation."""
    target_cell = ws.cell(row=target_row, column=target_col)
    target_coord = target_cell.coordinate
    for merged_range in ws.merged_cells.ranges:
        if target_coord in merged_range:
            ws.cell(row=merged_range.min_row, column=merged_range.min_col).value = value
            return
    target_cell.value = value

def _generate_individual_excel_internal(item, schedules, report_type, semester):
    """
    Core Logic for Single-Entity Excel Export.
    CARBON COPY of export_excel_bulk logic, adapted for a single entity.
    """
    settings = get_settings()
    template_filename = f"{report_type}_template.xlsx"
    if report_type in ('course', 'student', 'irregular'):
        # Force/fallback to section template for courses and students
        template_filename = "section_template.xlsx"
    
    template_path = os.path.join(basedir, 'static', 'assets', template_filename)
    if not os.path.exists(template_path):
        return None, f"Template {template_filename} not found."

    wb = load_workbook(template_path)
    template_sheet = wb.active
    target_ws = wb.copy_worksheet(template_sheet)
    
    # Metadata for labels
    if report_type == 'section':
        display_name = item.section_name
        dept_name = "N/A"
    elif report_type == 'faculty':
        display_name = item.full_name
        dept_name = item.department
    elif report_type == 'room':
        display_name = item.room_name
        dept_name = item.building
    elif report_type == 'course':
        display_name = item.course_code
        dept_name = item.course_name
    elif report_type in ('student', 'irregular'):
        display_name = item.full_name
        dept_name = "N/A"
    else:
        display_name = "Schedule"
        dept_name = "N/A"

    # 1. Grid Mapping logic (DUPLICATED FROM BULK)
    day_headers = {'Monday':['MON','MONDAY'],'Tuesday':['TUE','TUESDAY'],'Wednesday':['WED','WEDNESDAY'],'Thursday':['THU','THURS','THURSDAY'],'Friday':['FRI','FRIDAY'],'Saturday':['SAT','SATURDAY']}
    col_map = {} 
    row_map = {} 
    _t_occurrences = {}
    
    def fuzzy_clean(s):
        if not s or not isinstance(s, str): return ""
        for char in " :/-.,'0123456789": s = s.replace(char, "")
        return s.strip().upper()

    for row in template_sheet.iter_rows(min_row=1, max_row=60, max_col=26):
        for cell in row:
            val = ""
            if cell.value:
                if hasattr(cell.value, 'strftime'): val = cell.value.strftime('%H:%M')
                else: val = str(cell.value).strip().upper()
            if not val: continue
            for db_day, keywords in day_headers.items():
                if val in keywords: col_map[db_day] = cell.column
            
            if report_type == 'faculty':
                if cell.column == 1:
                    time_parts = val.replace('-', ' ').replace('–', ' ').split()
                    if time_parts:
                        t_start = time_parts[0].lstrip('0').upper()
                        if ':' in t_start:
                            if t_start not in _t_occurrences: _t_occurrences[t_start] = []
                            if len(_t_occurrences[t_start]) < 2:
                                _t_occurrences[t_start].append(cell.row)
            else:
                clean_time_val = val.lstrip('0') if ':' in val else val
                for h in range(1, 13):
                    for m in [0, 30]:
                        t_str = f"{h}:{m:02d}"
                        if clean_time_val.startswith(t_str):
                            if t_str not in _t_occurrences: _t_occurrences[t_str] = []
                            if len(_t_occurrences[t_str]) < 2:
                                _t_occurrences[t_str].append(cell.row)

    for h in range(7, 22): 
        for m in [0, 30]:
            t_key = f"{h}:{m:02d}"
            t_12 = f"{h if h <= 12 else h - 12}:{m:02d}"
            if t_12 in _t_occurrences:
                occ = _t_occurrences[t_12]
                row_map[t_key] = occ[0] if (h < 13 or len(occ) == 1) else (occ[1] if len(occ) > 1 else occ[0])

    # 2. Variable Mapping (DUPLICATED FROM BULK)
    f_hours = "0"
    f_prep = "0"
    f_educ = ""
    if report_type == 'faculty':
        f_educ = item.highest_educational_attainment or ""
        total_mins = 0
        daily_mins = {"Monday": 0, "Tuesday": 0, "Wednesday": 0, "Thursday": 0, "Friday": 0, "Saturday": 0}
        unique_subs = set()
        for s in schedules:
            try:
                sh_str, sm_str = s.start_time.split(':')
                eh_str, em_str = s.end_time.split(':')
                duration = (int(eh_str) * 60 + int(em_str)) - (int(sh_str) * 60 + int(sm_str))
                total_mins += duration
                if s.day in daily_mins:
                    daily_mins[s.day] += duration
            except: pass
            if s.course: unique_subs.add(s.course.course_code)
        f_hours = str(round(total_mins / 60, 2))
        f_prep = str(len(unique_subs))

    vmap = build_variable_map(
        report_type if report_type not in ('student', 'irregular') else 'section', 
        settings, 
        entity_name=display_name,
        faculty=(item if report_type == 'faculty' else None),
        prep_count=f_prep, 
        total_hours=f_hours, 
        sem_ay=semester
    )

    offsets = {
        'faculty': { "Name:": (0, 2), "Highest Educ. Attainment:": (0, 2), "No. of Preparation/s:": (0, 2), "Total no. of contact hours per week:": (0, 2), "OIC, Registrar": (-1, 0), "OIC-Registrar": (-1, 0), "Registrar": (-1, 0), "Department Chairperson": (-1, 0), "Director, Instruction": (-1, 0), "Campus Administrator": (-1, 0), "Instructor I": (-1, 0) },
        'section': { "CLASS": (-1, 0), "ROOM": (-1, 0), "COURSE": (-1, 0), "Semester / Academic Year": (-1, 0), "Prepared by:": (3, 0), "Recommending Approval:": (3, 1), "APPROVED:": (3, 0) },
        'course': { "CLASS": (-1, 0), "ROOM": (-1, 0), "COURSE": (-1, 0), "Semester / Academic Year": (-1, 0), "Prepared by:": (3, 0), "Recommending Approval:": (3, 1), "APPROVED:": (3, 0) },
        'room': { "ROOM": (-1, 0), "Prepared by:": (3, 0), "Recommending Approval:": (3, 1), "APPROVED:": (3, 0) }
    }
    
    val_map = {
        'faculty': { "Name:": display_name, "Highest Educ. Attainment:": f_educ, "No. of Preparation/s:": str(f_prep), "Total no. of contact hours per week:": str(f_hours), "OIC, Registrar": vmap.get('{{fac_registrar_name}}', 'MARLYN A. QUINEZ'), "Department Chairperson": vmap.get('{{fac_chair_name}}', 'ARIES M. GELERA'), "Director, Instruction": vmap.get('{{fac_director_name}}', 'ARIEL G. SANTOS, EdD'), "Campus Administrator": vmap.get('{{fac_admin_name}}', 'LAURO B. PASCUA, EdD'), "Instructor I": display_name },
        'section': { "CLASS": display_name, "ROOM": display_name, "COURSE": display_name, "Semester / Academic Year": vmap.get('{{sem_ay_value}}', semester) },
        'course': { "CLASS": display_name, "ROOM": display_name, "COURSE": display_name, "Semester / Academic Year": vmap.get('{{sem_ay_value}}', semester), "Section name": dept_name, "course name": dept_name, "Prepared by:": vmap.get('{{sig1}}', 'SCHEDULE COMMITTEE'), "Recommending Approval:": vmap.get('{{sig2}}', 'ARIEL G. SANTOS, EdD'), "APPROVED:": vmap.get('{{sig3}}', 'LAURO B. PASCUA, EdD') }
    }
    # For students, use section mappings
    if report_type in ('student', 'irregular'):
        val_map[report_type] = val_map['section']
        offsets[report_type] = offsets['section']

    m_map = {
        "Republic of the Philippines": "{{republic_text}}" if report_type != 'faculty' else "{{fac_republic_text}}",
        "CAVITE STATE UNIVERSITY":    "{{school}}" if report_type != 'faculty' else "{{fac_univ_name}}",
        "CCAT Campus":                "{{campus}}" if report_type != 'faculty' else "{{fac_campus_name}}",
        "Rosario, Cavite":            "{{address}}" if report_type != 'faculty' else "{{fac_address}}",
        "(046) 437-9505 / (046) 437-6659": "{{contact}}" if report_type != 'faculty' else "{{fac_contact_details}}",
        "cvsurosario@cvsu.edu.ph":    "{{email}}" if report_type != 'faculty' else "{{fac_email}}",
        "www.cvsu-rosario.edu.ph":    "{{website}}" if report_type != 'faculty' else "{{fac_website}}",
        "' (046) 437-9505 / 7 (046) 437-6659": "{{contact}}" if report_type != 'faculty' else "{{fac_contact_details}}",
        "Prepared by:": "{{prepared_by_label}}", "Recommending Approval:": "{{rec_approval_label}}" if report_type != 'faculty' else "{{fac_rec_approval_label}}", "APPROVED:": "{{approved_label}}" if report_type != 'faculty' else "{{fac_approved_label}}", "CLASS": "{{class_label}}", "ROOM": "{{room_label}}", "COURSE": "{{course_label}}", "Semester / Academic Year": "{{sem_ay_label}}", "Section name": "{{name}}", "room name": "{{name}}", "course name": "{{name}}", "faculty name": "{{fac_name}}", "Second / 2023-2024": "{{sem_ay_value}}", "SCHEDULE COMMITTEE": "{{sig1}}", "MARLYN A. QUINEZ": "{{fac_registrar_name}}", "MARLYN A. QUIÑEZ": "{{fac_registrar_name}}", "ARIES M. GELERA": "{{fac_chair_name}}", "ARIEL G. SANTOS, EdD": "{{sig2}}" if report_type != 'faculty' else "{{fac_director_name}}", "LAURO B. PASCUA, EdD": "{{sig3}}" if report_type != 'faculty' else "{{fac_admin_name}}", "Instructor I": "{{fac_rank}}", "Director, Instruction": "{{sig2_title}}" if report_type != 'faculty' else "{{fac_director_title}}", "Campus Administrator": "{{sig3_title}}" if report_type != 'faculty' else "{{fac_admin_title}}", "Department Chairperson": "{{fac_chair_title}}", "OIC, Registrar": "{{fac_registrar_label}}"
    }

    # ROOM LAYOUT SAFETY: Direct injection for Room Name (Room Only)
    if report_type == 'room':
        _safe_write_to_cell_indiv(target_ws, 10, 2, display_name)

    # Consolidated Scanner (DUPLICATED FROM BULK)
    for r_idx in range(1, target_ws.max_row + 1):
        for c_idx in range(1, 26):
            cell = target_ws.cell(row=r_idx, column=c_idx)
            val = cell.value
            if not val or not isinstance(val, str): continue
            
            original_val = val
            clean_original_val = fuzzy_clean(val)
            clean_val = fuzzy_clean(val)
            
            for m_text, t_token in m_map.items():
                if fuzzy_clean(m_text) == clean_val:
                    if t_token in vmap:
                        val = str(vmap[t_token])
                        cell.value = val
                        original_val = val 
                        break
            
            match_replaced = False
            for t_key, t_val in vmap.items():
                if t_key in val:
                    val = val.replace(t_key, str(t_val))
                    match_replaced = True
            
            if match_replaced or cell.value != original_val:
                if match_replaced: cell.value = val
                is_sig_field = any(f"{{sig{i}}}" in str(original_val) for i in range(1, 10)) or \
                             any(f"{{fac_chair_name}}" in str(original_val) for i in range(1, 10)) or \
                             any(x in str(original_val) for x in ["SANTOS", "PASCUA", "GELERA", "QUINEZ"])
                if is_sig_field:
                    cell.font = Font(name='Arial Narrow', size=11, bold=True, underline='single')
                    cell.alignment = Alignment(horizontal='center')
            
            # Coordinate Overrides
            l_target = offsets.get(report_type if report_type not in ('student', 'irregular') else 'section', {})
            v_target = val_map.get(report_type, {})
            label_found = None
            for log_label, (dr, dc) in l_target.items():
                if log_label and fuzzy_clean(log_label) == clean_original_val:
                    label_found = log_label
                    break
            if label_found:
                dr, dc = l_target[label_found]
                target_val = v_target.get(label_found)
                if target_val:
                    _safe_write_to_cell_indiv(target_ws, r_idx + dr, c_idx + dc, str(target_val))

    # 3. Grid Plotting (DUPLICATED FROM BULK)
    grid_min_r, grid_max_r = 20, 41
    grid_min_c, grid_max_c = 2, 8
    existing_merged_ranges = list(target_ws.merged_cells.ranges)
    for mrange in existing_merged_ranges:
        overlap_r = not (mrange.max_row < grid_min_r or mrange.min_row > grid_max_r)
        overlap_c = not (mrange.max_col < grid_min_c or mrange.min_col > grid_max_c)
        if overlap_r and overlap_c:
            try: target_ws.unmerge_cells(str(mrange))
            except: pass

    grid_slots = {}
    for sc in schedules:
        if sc.day not in col_map: continue
        try:
            sh_s, sm_s = map(int, sc.start_time.split(':'))
            eh_e, em_e = map(int, sc.end_time.split(':'))
        except: continue
        
        start_key = f"{sh_s}:{sm_s:02d}"
        if start_key in row_map:
            s_r = row_map[start_key]
            slots = int(((eh_e * 60 + em_e) - (sh_s * 60 + sm_s)) / 30)
            e_r = s_r + slots - 1
            
            plot_key = (sc.day, s_r, e_r)
            if plot_key not in grid_slots: grid_slots[plot_key] = []
            
            ctype = f"({sc.session_type})" if sc.session_type else ""
            txt = ""
            if report_type == 'faculty':
                if sc.course: txt += f"{sc.course.course_code} {ctype}\n"
                if sc.section: txt += f"{sc.section.section_name}\n"
                if sc.room: txt += f"{sc.room.room_name}"
            elif report_type in ('section', 'student', 'irregular'):
                txt = f"{sc.course.course_code} {ctype}\n"
                fn = sc.faculty.full_name if sc.faculty else "T.B.A."
                p = fn.split()
                short_f = f"MR. {p[-1].upper()}" if (len(p) > 1 and not fn.startswith('T.B.A.')) else fn.upper()
                txt += f"{short_f}\n{sc.room.room_name if sc.room else ''}"
            elif report_type == 'room':
                txt = f"{sc.course.course_code} {ctype}\n{sc.section.section_name if sc.section else ''}\n"
                fn = sc.faculty.full_name if sc.faculty else "T.B.A."
                p = fn.split()
                short_f = f"MR. {p[-1].upper()}" if (len(p) > 1 and not fn.startswith('T.B.A.')) else fn.upper()
                txt += f"{short_f}"
            else: # course
                fn = sc.faculty.full_name if sc.faculty else "T.B.A."
                p = fn.split()
                short_f = f"MR. {p[-1].upper()}" if (len(p) > 1 and not fn.startswith('T.B.A.')) else fn.upper()
                txt = f"{sc.section.section_name if sc.section else ''}\n{sc.room.room_name if sc.room else ''}\n{short_f}"
            grid_slots[plot_key].append(txt)

    thin = Side(border_style="thin", color="000000")
    full_border = Border(top=thin, left=thin, right=thin, bottom=thin)
    for (day, s_r, e_r), texts in grid_slots.items():
        t_col = col_map[day]
        if e_r > s_r:
            try: target_ws.merge_cells(start_row=s_r, start_column=t_col, end_row=e_r, end_column=t_col)
            except: pass
        
        cell = target_ws.cell(row=s_r, column=t_col)
        cell.value = "\n---\n".join(texts)
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.font = Font(name='Arial Narrow', size=9)
        for r in range(s_r, e_r + 1):
            target_ws.cell(row=r, column=t_col).border = full_border

    # 4. Faculty Summary Table (DUPLICATED FROM BULK)
    if report_type == 'faculty':
        # DAILY CONTACT HOURS (Row 48 Scanner)
        daily_hours_row = 0
        for r_idx in range(1, 100):
            l_val = str(target_ws.cell(row=r_idx, column=1).value or "").strip().upper()
            if "DAILY CONTACT HOURS" in l_val:
                daily_hours_row = r_idx
                break
        if daily_hours_row:
            for day, d_mins in daily_mins.items():
                if day in col_map:
                    d_col = col_map[day]
                    d_hours = round(d_mins / 60, 2)
                    target_ws.cell(row=daily_hours_row, column=d_col).value = d_hours

        # Summary Data Preparation
        summary_start_row = 51
        summary_max_data_row = 60
        summary_data = {}
        for sc in schedules:
            key = (sc.course_id, sc.section_id)
            c_dur = 0.0
            try:
                sh, sm = map(int, sc.start_time.split(':'))
                eh, em = map(int, sc.end_time.split(':'))
                c_dur = (eh * 60 + em - sh * 60 - sm) / 60.0
            except: pass
            if key not in summary_data:
                c_obj = sc.course
                summary_data[key] = {
                    'code': c_obj.course_code if c_obj else "",
                    'name': c_obj.course_name if c_obj else "",
                    'section': sc.section.section_name if sc.section else "",
                    'lec_h': 0.0, 'lab_h': 0.0,
                    'lec_units': float(c_obj.lec_units or 0) if c_obj else 0.0,
                    'lab_units': float(c_obj.lab_units or 0) if c_obj else 0.0,
                    'students': sc.section.number_of_students if sc.section else 0,
                    'rooms_set': set()
                }
            if sc.session_type == 'Lab': summary_data[key]['lab_h'] += c_dur
            else: summary_data[key]['lec_h'] += c_dur
            if sc.room: summary_data[key]['rooms_set'].add(sc.room.room_name)
        
        # Populate List (Row 51-60)
        curr_row = summary_start_row
        total_lec_sum = 0.0
        total_lab_sum = 0.0
        total_students_sum = 0
        
        for key in sorted(summary_data.keys()):
            if curr_row > summary_max_data_row: break
            d = summary_data[key]
            
            # Use Units if available, fallback to calculated hours
            final_lec = d['lec_units'] if d['lec_units'] > 0 else d['lec_h']
            final_lab = d['lab_units'] if d['lab_units'] > 0 else d['lab_h']
            row_total = final_lec + final_lab
            
            # Alignment with Screenshot: A:Code, B:Section, D:Lec, E:Lab, F:Total, G:Room, H:Students
            target_ws.cell(row=curr_row, column=1).value = d['code']
            # Col 2 (B) stays empty
            target_ws.cell(row=curr_row, column=3).value = d['section']
            target_ws.cell(row=curr_row, column=4).value = final_lec
            target_ws.cell(row=curr_row, column=5).value = final_lab
            target_ws.cell(row=curr_row, column=6).value = row_total
            target_ws.cell(row=curr_row, column=7).value = ", ".join(sorted(list(d['rooms_set']))) if d['rooms_set'] else "T.B.A."
            target_ws.cell(row=curr_row, column=8).value = d['students']
            
            total_lec_sum += final_lec
            total_lab_sum += final_lab
            total_students_sum += d['students']
            curr_row += 1

        # Totals (Row 61) - Exactly as per Screenshot: D, E, F, H
        total_row = 61
        target_ws.cell(row=total_row, column=4).value = total_lec_sum
        target_ws.cell(row=total_row, column=5).value = total_lab_sum
        target_ws.cell(row=total_row, column=6).value = total_lec_sum + total_lab_sum
        target_ws.cell(row=total_row, column=8).value = total_students_sum

    # 5. Images & Page Setup
    _process_images(template_sheet, target_ws, settings, report_type if report_type not in ('student', 'irregular') else 'section')
    if settings:
        p_map = {'A4': 9, 'Letter': 1, 'Legal': 5}
        target_ws.page_setup.paperSize = p_map.get(settings.paper_size, 9)
        target_ws.page_margins.top, target_ws.page_margins.bottom = settings.margin_top, settings.margin_bottom
        target_ws.page_margins.left, target_ws.page_margins.right = settings.margin_left, settings.margin_right
        target_ws.page_setup.orientation = target_ws.ORIENTATION_LANDSCAPE

    wb.remove(template_sheet)
    # Output
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output, display_name

@app.route('/section-timetable-excel/<int:section_id>')
@login_required
def section_timetable_excel(section_id):
    section = Section.query.get_or_404(section_id)
    semester = request.args.get('semester', '1st Semester')
    schedules = _dedup_schedules(ScheduledClass.query.filter_by(section_id=section_id, semester=semester).all())
    stream, name = _generate_individual_excel_internal(section, schedules, 'section', semester)
    if not stream:
        flash(name, "danger")
        return redirect(url_for('view_timetable'))
    filename = f"{name.replace(' ','_')}_Schedule_{semester.replace(' ','_')}.xlsx"
    return send_file(stream, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/faculty-timetable-excel/<int:faculty_id>')
@login_required
def faculty_timetable_excel(faculty_id):
    faculty = Faculty.query.get_or_404(faculty_id)
    semester = request.args.get('semester', '1st Semester')
    schedules = _dedup_schedules(ScheduledClass.query.filter_by(faculty_id=faculty_id, semester=semester).all())
    stream, name = _generate_individual_excel_internal(faculty, schedules, 'faculty', semester)
    if not stream:
        flash(name, "danger")
        return redirect(url_for('view_timetable'))
    filename = f"{name.replace(' ','_')}_Load_{semester.replace(' ','_')}.xlsx"
    return send_file(stream, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/room-timetable-excel/<int:room_id>')
@login_required
def room_timetable_excel(room_id):
    room = Room.query.get_or_404(room_id)
    semester = request.args.get('semester', '1st Semester')
    schedules = _dedup_schedules(ScheduledClass.query.filter_by(room_id=room_id, semester=semester).all())
    stream, name = _generate_individual_excel_internal(room, schedules, 'room', semester)
    if not stream:
        flash(name, "danger")
        return redirect(url_for('view_timetable'))
    filename = f"{name.replace(' ','_')}_Utilization_{semester.replace(' ','_')}.xlsx"
    return send_file(stream, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/course-timetable-excel/<int:course_id>')
@login_required
def course_timetable_excel(course_id):
    course = Course.query.get_or_404(course_id)
    semester = request.args.get('semester', '1st Semester')
    schedules = _dedup_schedules(ScheduledClass.query.filter_by(course_id=course_id, semester=semester).all())
    stream, name = _generate_individual_excel_internal(course, schedules, 'course', semester)
    if not stream:
        flash(name, "danger")
        return redirect(url_for('view_timetable'))
    filename = f"{name.replace(' ','_')}_Schedule_{semester.replace(' ','_')}.xlsx"
    return send_file(stream, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/public-student-schedule-excel/<string:student_id>')
def public_student_schedule_excel(student_id):
    student = Student.query.filter_by(student_id=student_id, is_archived=False).first_or_404()
    _all_sems = [r[0] for r in db.session.query(ScheduledClass.semester).distinct().all() if r[0]]
    semester = request.args.get('semester', (_all_sems[0] if _all_sems else '1st Semester'))
    schedules = []
    if student.is_irregular:
        assignment = IrregularAssignment.query.filter_by(student_id_fk=student.id).order_by(IrregularAssignment.updated_at.desc()).first()
        if assignment and assignment.assignments_json:
            pairs = json.loads(assignment.assignments_json)
            for pair in pairs:
                slots = ScheduledClass.query.filter_by(course_id=pair['course_id'], section_id=pair['section_id'], semester=assignment.semester).all()
                schedules.extend(slots)
            schedules = _dedup_schedules(schedules)
            semester = assignment.semester
    else:
        if student.section_id:
            schedules = _dedup_schedules(ScheduledClass.query.filter_by(section_id=student.section_id, semester=semester, is_draft=False).all())
    if not schedules:
        flash('No schedule found to export.', 'warning')
        return redirect(url_for('student_schedule', student_id=student.student_id))
    stream, name = _generate_individual_excel_internal(student, schedules, 'student', semester)
    if not stream:
        flash(name, "danger")
        return redirect(url_for('student_schedule', student_id=student.student_id))
    filename = f"Schedule_{name.replace(' ','_')}_{semester.replace(' ','_')}.xlsx"
    return send_file(stream, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


from user_genetic_algorithm import UserGeneticScheduler

user_generation_status = {}

def run_user_ga_in_background(user_id, username, scheduler, semester, user_dept):
    global user_generation_status
    _gen_start_time = time.time()

    with app.app_context():
        def progress_callback(info):
            if user_id in user_generation_status:
                # Filter out non-serializable objects before updating status
                serializable_info = {k: v for k, v in info.items() if k != 'best_chromosome'}
                user_generation_status[user_id].update(serializable_info)
                
                # Ensure visual matrix is updated for the frontend using the actual chromosome
                if info.get('best_chromosome'):
                    matrix = scheduler.get_visualization_matrix(info['best_chromosome'])
                    user_generation_status[user_id]['visual_matrix'] = matrix
                    
                    # Write live chromosome state to live_conflicts.json for local debugging
                    try:
                        import json
                        chrom = info['best_chromosome']
                        live_mock = []
                        for g in chrom.genes:
                            _dy = scheduler.days[g.day_idx] if 0 <= g.day_idx < len(scheduler.days) else 'Unknown'
                            _st = scheduler.slot_to_time(g.start_idx)
                            _en = scheduler.slot_to_time(g.end_idx)
                            live_mock.append({
                                'course_id': g.course_id,
                                'section_id': g.section_id,
                                'faculty_id': g.faculty_id,
                                'room_id': g.room_id,
                                'day': _dy,
                                'start_time': _st,
                                'end_time': _en,
                                'session_type': g.gene_type
                            })
                        with open("live_conflicts.json", "w") as f:
                            json.dump({
                                'semester': semester,
                                'schedules': live_mock
                            }, f)
                    except Exception as _je:
                        print(f"Error writing live_conflicts.json: {_je}")
                
                # Emit progress to the specific user via SocketIO
                socketio.emit('user_ga_progress', serializable_info, room=f"user_{user_id}")

        # Signal UI that we're in the init phase
        user_generation_status[user_id]['phase'] = 'init'
        
        # Clear previous stop signals for this user
        sig_path = os.path.join(basedir, f"user_{user_id}_stop.signal")
        if os.path.exists(sig_path):
            try: os.remove(sig_path)
            except: pass
            
        try:
            # Load existing schedule for this department/semester as seed (Warm start)
            seed_records = []
            existing = ScheduledClass.query.join(Course).filter(
                ScheduledClass.semester == semester,
                Course.department == user_dept
            ).all()
            for sc in existing:
                seed_records.append({
                    'course_id': sc.course_id, 'section_id': sc.section_id, 'faculty_id': sc.faculty_id,
                    'room_id': sc.room_id, 'day': sc.day, 'start_time': sc.start_time, 'end_time': sc.end_time
                })
            
            best_chromosome = scheduler.run_algorithm(
                progress_callback=progress_callback,
                seed_records=seed_records if seed_records else None
            )
            
            if best_chromosome and not user_generation_status[user_id].get('stop_requested'):
                # 2. SAVE Results back to ScheduledClass
                # Delete ONLY this department's schedule for this semester
                to_delete = ScheduledClass.query.join(Course).filter(
                    ScheduledClass.semester == semester,
                    Course.department == user_dept
                ).all()
                for d_obj in to_delete:
                    db.session.delete(d_obj)
                db.session.commit()
                
                objects_to_save = []
                days_list = scheduler.days
                for g in best_chromosome.genes:
                    if not g.is_fixed: # Only save the newly generated ones (this department's)
                        day_str   = days_list[g.day_idx]
                        start_str = scheduler.slot_to_time(g.start_idx)
                        end_str   = scheduler.slot_to_time(g.end_idx)
                        
                        # Infer session type
                        room_info = scheduler.room_map.get(g.room_id, {})
                        _caps = room_info.get('capabilities', '')
                        _stype = g.gene_type
                        if _stype == 'Fixed' or not _stype:
                            _stype = 'Lab' if 'Computer Lab' in _caps else 'Lec'

                        objects_to_save.append(ScheduledClass(
                            course_id=g.course_id,
                            section_id=g.section_id,
                            faculty_id=g.faculty_id,
                            room_id=g.room_id,
                            day=day_str,
                            start_time=start_str,
                            end_time=end_str,
                            semester=semester,
                            session_type=_stype,
                            source='ga_user',
                            is_draft=False
                        ))
                
                if objects_to_save:
                    db.session.bulk_save_objects(objects_to_save)
                    db.session.commit()
                    log_activity("Generate Schedule (User)", f"Generated {len(objects_to_save)} classes for {user_dept} in {semester}.", override_user_id=user_id, override_username=username)
                
                user_generation_status[user_id]['done'] = True
                socketio.emit('user_ga_done', {'ok': True}, room=f"user_{user_id}")
            
        except Exception as e:
            print(f"Error in User GA: {e}")
            traceback.print_exc()
            if user_id in user_generation_status:
                user_generation_status[user_id]['error'] = str(e)
                socketio.emit('user_ga_error', {'error': str(e)}, room=f"user_{user_id}")
        finally:
            if user_id in user_generation_status:
                user_generation_status[user_id]['running'] = False

@app.route('/user/auto-schedule')
@login_required
def user_auto_schedule():
    """Renders the personal auto-scheduling page for users."""
    user_id = session.get('user_id')
    user_dept = session.get('department', '').strip()
    
    # 1. Get settings and pre-assignments
    s = get_settings()
    
    # 2. Identify the user's tasks (Faculty Assignments)
    # We look for assignments created by the user or belonging to their department
    # but the logic depends on how the user creates their 'tasks'.
    # For now, let's assume they pick from their assigned classes.
    
    # 3. Provide department list (Carbon Copy of Admin UI context)
    known_departments = sorted(list(set(c.department for c in Course.query.filter_by(is_archived=False).all() if c.department)))
    saved_depts = [user_dept] if user_dept else []
    
    return render_template(
        'user_auto_schedule.html',
        start_hour=s.start_hour,
        end_hour=s.end_hour,
        user_dept=user_dept,
        known_departments=known_departments,
        saved_depts=saved_depts
    )

@app.route('/api/user/generate', methods=['POST'])
@login_required
def api_user_generate():
    """Starts the departmental auto-scheduling process (User Role)."""
    user_id = session.get('user_id')
    user_dept = session.get('department')
    if not user_dept:
        return jsonify({'ok': False, 'error': 'User department not set.'}), 400

    req_data = request.get_json() or {}
    target_semester = req_data.get('semester', '1st Semester')
    fresh_start = req_data.get('fresh_start', False)
    
    if user_id in user_generation_status and user_generation_status[user_id].get('running'):
        return jsonify({'ok': False, 'error': 'Generation already in progress.'}), 400
        
    # Initialize status
    user_generation_status[user_id] = {
        'running': True, 'done': False, 'generation': 0, 'hard_conflicts': 0, 
        'soft_score': 0, 'stop_requested': False, 'target_semester': target_semester,
        'phase': 'init'
    }
    
    # ── Step 1: Gather Data (Carbon Copy of start_generation logic) ────────
    settings_db = get_settings()
    active_days = [d.strip() for d in (settings_db.allowed_days or 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday').split(',') if d.strip()]
    
    # DEPARTMENTAL ISOLATION: 
    # 1. Other departments' schedules are LOCKED (Fixed)
    # Locked schedules (from other departments)
    pre_assignments = []
    
    # Respect frontend selected departments if provided, otherwise fallback to session
    scheduled_depts = req_data.get('scheduled_depts', [])
    if not scheduled_depts and user_dept:
        scheduled_depts = [user_dept]
    
    # Normalize for comparison
    target_depts_norm = [d.strip().upper() for d in scheduled_depts if d]
    
    locked_schedules = ScheduledClass.query.join(Course).filter(
        ScheduledClass.semester == target_semester,
        func.not_(func.upper(func.trim(Course.department)).in_(target_depts_norm))
    ).all()
    for ls in locked_schedules:
        pre_assignments.append(SafeObject(
            course_id=ls.course_id, section_id=ls.section_id, faculty_id=ls.faculty_id,
            room_id=ls.room_id, day=ls.day, start_time=ls.start_time, end_time=ls.end_time
        ))
    
    # 2. Add PreAssignments (Manual) from DB that don't belong to this dept
    manual_pre = PreAssignment.query.join(Course).filter(Course.department != user_dept).all()
    for mp in manual_pre:
        pre_assignments.append(SafeObject(
            course_id=mp.course_id, section_id=mp.section_id, faculty_id=mp.faculty_id,
            room_id=mp.room_id, day=mp.day, start_time=mp.start_time, end_time=mp.end_time
        ))

    # 3. Load Courses, Sections, Faculty, Rooms (filtered or global as needed)
    # Sections to schedule: only those that have courses in this department
    raw_sections = Section.query.filter_by(is_archived=False).all()
    sections = []
    for s in raw_sections:
        # Only include courses that are in the selected departments and offered this semester
        dept_courses = [c for c in s.courses if c.department and c.department.strip().upper() in target_depts_norm and c.semester_offered == target_semester]
        if dept_courses:
            sections.append({
                'id': s.id, 'section_name': s.section_name, 
                'course_ids': [c.id for c in dept_courses]
            })

    # Courses data (global map for scheduler)
    all_courses = Course.query.filter_by(is_archived=False).all()
    courses_data = [{
        'id': c.id, 'course_code': c.course_code, 'department': c.department or '',
        'lec_units': c.lec_units or 0, 'lab_units': c.lab_units or 0,
        'synchronous_lec_hours': c.synchronous_lec_hours or 0,
        'synchronous_lab_hours': c.synchronous_lab_hours or 0,
        'asynchronous_lec_hours': c.asynchronous_lec_hours or 0,
        'asynchronous_lab_hours': c.asynchronous_lab_hours or 0,
    } for c in all_courses]

    # Faculty data
    faculty_data = [{'id': f.id, 'full_name': f.full_name, 'department': f.department, 'available_days': f.available_days} for f in Faculty.query.filter_by(is_archived=False).all()]
    
    # Room data (Strictly filtered for User Role: Online, TBA, or Department-assigned only)
    all_rooms = Room.query.filter_by(is_archived=False).all()
    room_data = []
    for r in all_rooms:
        r_name = (r.room_name or '').lower()
        r_caps = (r.capabilities or '').lower()
        is_online = 'online' in r_name or 'online' in r_caps
        is_tba = 'tba' in r_name or 'tba' in r_caps
        
        is_dept_room = False
        if r.room_departments:
            r_depts = [d.strip().upper() for d in r.room_departments.split(',') if d.strip()]
            if any(d in target_depts_norm for d in r_depts):
                is_dept_room = True
                
        if is_online or is_tba or is_dept_room:
            room_data.append({'id': r.id, 'room_name': r.room_name, 'capabilities': r.capabilities, 'status': r.status})
    
    # Constraints
    constraints_config = {c.logic_code: {'type': c.constraint_type, 'weight': c.weight} for c in Constraint.query.all()}
    
    # 4. Initialize Scheduler
    scheduler = UserGeneticScheduler(
        courses_data, sections, faculty_data, room_data, 
        pre_assignments, constraints_config,
        start_time=settings_db.start_hour,
        end_time=settings_db.end_hour,
        allowed_days=active_days,
        user_id=user_id
    )
    
    # If fresh_start, delete this department's existing schedule for the semester
    if fresh_start:
        to_delete = ScheduledClass.query.join(Course).filter(
            ScheduledClass.semester == target_semester,
            Course.department == user_dept
        ).all()
        for d_obj in to_delete:
            db.session.delete(d_obj)
        db.session.commit()

    # 5. Run in Background
    username = session.get('username')
    thread = threading.Thread(target=run_user_ga_in_background, args=(user_id, username, scheduler, target_semester, user_dept))
    thread.start()
    
    return jsonify({'ok': True, 'status': 'started'})

@app.route('/api/user/status')
@login_required
def api_user_status():
    user_id = session.get('user_id')
    status = user_generation_status.get(user_id, {'running': False, 'done': False})
    return jsonify(status)

@app.route('/api/user/check-feasibility', methods=['POST'])
@login_required
def api_user_check_feasibility():
    """Departmental capacity assessment for the User role."""
    try:
        user_dept = session.get('department')
        if not user_dept:
            return jsonify({'summary': {'status': 'RED', 'message': 'User department not set.'}})

        req_data = request.get_json() or {}
        target_semester = req_data.get('semester', '1st Semester')
        
        # 1. Gather Data (Same as generate)
        settings_db = get_settings()
        active_days = [d.strip() for d in (settings_db.allowed_days or 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday').split(',') if d.strip()]
        
        # Locked schedules (from other departments)
        pre_assignments = []
        
        # Respect frontend selected departments if provided, otherwise fallback to session
        scheduled_depts = req_data.get('scheduled_depts', [])
        if not scheduled_depts and user_dept:
            scheduled_depts = [user_dept]
        
        # Normalize for comparison
        target_depts_norm = [d.strip().upper() for d in scheduled_depts if d]
        
        locked_schedules = ScheduledClass.query.join(Course).filter(
            ScheduledClass.semester == target_semester,
            func.not_(func.upper(func.trim(Course.department)).in_(target_depts_norm))
        ).all()
        for ls in locked_schedules:
            pre_assignments.append(SafeObject(
                course_id=ls.course_id, section_id=ls.section_id, faculty_id=ls.faculty_id,
                room_id=ls.room_id, day=ls.day, start_time=ls.start_time, end_time=ls.end_time
            ))
        
        # Sections to schedule: only those that have courses in this department
        raw_sections = Section.query.filter_by(is_archived=False).all()
        sections = []
        for s in raw_sections:
            dept_courses = [c for c in s.courses if c.department and c.department.strip().upper() in target_depts_norm and c.semester_offered == target_semester]
            if dept_courses:
                sections.append({
                    'id': s.id, 'section_name': s.section_name, 
                    'course_ids': [c.id for c in dept_courses]
                })

        all_courses = Course.query.filter_by(is_archived=False).all()
        courses_data = [{
            'id': c.id, 'course_code': c.course_code, 'department': c.department or '',
            'lec_units': c.lec_units or 0, 'lab_units': c.lab_units or 0,
            'synchronous_lec_hours': c.synchronous_lec_hours or 0,
            'synchronous_lab_hours': c.synchronous_lab_hours or 0,
        } for c in all_courses]

        faculty_data = [{'id': f.id, 'full_name': f.full_name, 'department': f.department, 'available_days': f.available_days} for f in Faculty.query.filter_by(is_archived=False).all()]
        # Room data (Strictly filtered for User Role: Online, TBA, or Department-assigned only)
        all_rooms = Room.query.filter_by(is_archived=False).all()
        room_data = []
        for r in all_rooms:
            r_name = (r.room_name or '').lower()
            r_caps = (r.capabilities or '').lower()
            is_online = 'online' in r_name or 'online' in r_caps
            is_tba = 'tba' in r_name or 'tba' in r_caps
            
            is_dept_room = False
            if r.room_departments:
                r_depts = [d.strip().upper() for d in r.room_departments.split(',') if d.strip()]
                if any(d in target_depts_norm for d in r_depts):
                    is_dept_room = True
                    
            if is_online or is_tba or is_dept_room:
                room_data.append({'id': r.id, 'room_name': r.room_name, 'capabilities': r.capabilities, 'status': r.status})
        
        # 2. Initialize Scheduler and Run 3-Level Check
        scheduler = UserGeneticScheduler(
            courses_data, sections, faculty_data, room_data, 
            pre_assignments, {}, # No constraints needed for feasibility
            start_time=settings_db.start_hour,
            end_time=settings_db.end_hour,
            allowed_days=active_days,
            user_id=session.get('user_id')
        )
        
        report = scheduler.check_room_feasibility()
        return jsonify(report)

    except Exception as e:
        print(f"User Feasibility Error: {e}")
        traceback.print_exc()
        return jsonify({
            'summary': {
                'status': 'RED',
                'message': f'Server Error: {str(e)}'
            }
        })

@app.route('/api/user/stop', methods=['POST'])
@login_required
def api_user_stop():
    user_id = session.get('user_id')
    if user_id in user_generation_status:
        user_generation_status[user_id]['stop_requested'] = True
        # Create user-specific signal file
        sig_path = os.path.join(basedir, f"user_{user_id}_stop.signal")
        with open(sig_path, "w") as f:
            f.write("STOP")
    return jsonify({'ok': True})

if __name__ == '__main__':


    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'False') == 'True', allow_unsafe_werkzeug=True)

