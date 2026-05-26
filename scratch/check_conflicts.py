import sys
sys.path.insert(0, '.')
from app import app, db, ScheduledClass
from debug_schedule import build_scheduler, records_to_chromosome

with app.app_context():
    # Load all draft classes (is_draft=True)
    draft_classes = ScheduledClass.query.filter_by(is_draft=True).all()
    if not draft_classes:
        print("No draft classes found!")
        sys.exit(0)
        
    print(f"Loaded {len(draft_classes)} draft classes.")
    
    # Get active semester from the draft classes
    semester = draft_classes[0].semester
    print(f"Semester: {semester}")
    
    # Get system settings
    from app import SystemSettings
    sys_settings = SystemSettings.query.first()
    start_hour = sys_settings.start_hour
    end_hour = sys_settings.end_hour
    allowed_days = [d.strip() for d in (sys_settings.allowed_days or "Monday,Tuesday,Wednesday,Thursday,Friday").split(",") if d.strip()]
    
    # Build scheduler
    scheduler = build_scheduler(selected_semester=semester, start_hour=start_hour, end_hour=end_hour, allowed_days=allowed_days)
    
    # Convert draft classes to chromosome records
    records = []
    for sc in draft_classes:
        records.append({
            'course_id': sc.course_id,
            'section_id': sc.section_id,
            'faculty_id': sc.faculty_id,
            'room_id': sc.room_id,
            'day': sc.day,
            'start_time': sc.start_time,
            'end_time': sc.end_time,
            'gene_type': sc.session_type,
        })
        
    chrom = records_to_chromosome(scheduler, records)
    
    print("\n--- CHROMOSOME EVALUATION ---")
    print(f"Hard Conflicts: {chrom.hard_conflicts}")
    print(f"Violation Codes: {chrom.violation_codes}")
    
    # Print individual hard conflict details
    # We can run human report
    from debug_schedule import print_accurate_report
    print_accurate_report(scheduler, chrom, "Draft Chromosome Diagnostic", semester)
