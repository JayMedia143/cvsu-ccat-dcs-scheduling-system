# seed_db.py (KUMPLETO AT FINAL VERSION)

from app import app, db, User, Course, Room, Section, Faculty, Constraint, SystemSettings, section_courses, faculty_courses, FacultyAssignment, PreAssignment, ScheduledClass, CodePrefixRule
from werkzeug.security import generate_password_hash
import seeder11

if __name__ == '__main__':
    print("🚀 Initializing Seeder 11 for First Semester 2026-2027...")
    seeder11.seed_database()