import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db, Faculty, Section, Course, SystemSettings

with app.app_context():
    print("=== SEEDING VERIFICATION ===")
    
    # 1. Check System Settings
    settings = SystemSettings.query.first()
    if settings:
        print(f"[OK] System Settings:")
        print(f"     Allowed Days: {settings.allowed_days}")
        print(f"     Start Hour: {settings.start_hour} (8 AM)")
        print(f"     End Hour: {settings.end_hour} (6 PM)")
    else:
        print("[ERROR] System Settings not found!")
        
    # 2. Check Faculty counts and schedule constraints
    faculties = Faculty.query.all()
    print(f"[OK] Total seeded faculty: {len(faculties)}")
    
    mp = [f for f in faculties if "PELIÑA" in f.full_name.upper()]
    if mp:
        peliña = mp[0]
        print(f"[OK] {peliña.full_name} availability: {peliña.available_days} (Expected: Monday,Tuesday,Wednesday)")
    else:
        print("[ERROR] Mary Ann Peliña not found!")
        
    other_facs = [f for f in faculties if "PELIÑA" not in f.full_name.upper() and f.full_name != "T.B.A."]
    mismatch_days = [f for f in other_facs if f.available_days != "Monday,Tuesday,Wednesday,Thursday"]
    if mismatch_days:
        print(f"[ERROR] Some faculties do not have Mon-Thu days: {[f.full_name for f in mismatch_days]}")
    else:
        print(f"[OK] All other {len(other_facs)} faculties are mapped strictly to Monday-Thursday.")
        
    # 3. Check Sections count
    sections = Section.query.all()
    print(f"[OK] Total seeded sections: {len(sections)}")
    mismatch_sec_days = [s for s in sections if s.available_days != "Monday,Tuesday,Wednesday,Thursday"]
    if mismatch_sec_days:
        print(f"[ERROR] Some sections do not have Mon-Thu days: {[s.section_name for s in mismatch_sec_days]}")
    else:
        print("[OK] All sections are mapped strictly to Monday-Thursday.")
        
    # 4. Check Courses count
    courses = Course.query.all()
    print(f"[OK] Total seeded courses: {len(courses)}")
