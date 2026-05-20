import re

with open('genetic_algorithm.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Remove eventlet imports and sleeps
code = re.sub(r'import eventlet', '', code)
code = re.sub(r'eventlet\.sleep\(.*?\)', 'pass', code)

# 2. Remove get_visualization_matrix
# Find the start and the next def
start_vis = code.find('def get_visualization_matrix')
if start_vis != -1:
    # Find the next method after it
    # It ends at line 366 approx, next method is check_room_feasibility usually
    next_def = code.find('def ', start_vis + 30)
    if next_def != -1:
        code = code[:start_vis] + code[next_def:]

# 3. Replace progress_callback block in run_algorithm
# We look for the Telemetry Update section
telemetry_start = code.find('# ── Telemetry Update ───────────────────────────────────────────')
if telemetry_start != -1:
    # Find the next section or the end of the method
    # It usually ends before # ── Termination
    term_start = code.find('# ── Termination ────────────────────────────────────────────────')
    if term_start != -1:
        print_code = '''# ── Telemetry Update (Console Only for Test 11) ───────────────────
                prog_now = time.time()
                prog_elapsed = prog_now - _algo_t0
                if generation % 10 == 0:
                    speed = round(prog_elapsed / generation, 4) if generation > 0 else 0
                    print(f"Gen {generation:04d} [{current_phase.upper()}] | Elapsed: {prog_elapsed:.1f}s | Speed: {speed}s/gen | HC: {current_best.hard_conflicts} | SS: {current_best.soft_score}")
                '''
        code = code[:telemetry_start] + print_code + code[term_start:]

# 4. Replace class name
code = code.replace('class GeneticScheduler:', 'class GeneticSchedulerTC11:')

# 5. Add the test runner at the bottom
test_runner = '''

if __name__ == '__main__':
    print("================================================================")
    print("🧪 ALPHA TESTING: TEST CASE 11 (FINAL INTEGRATION & FLAWLESS AUTOSTOP)")
    print("================================================================")
    
    from app import app, Course, Section, Room, Faculty, PreAssignment, Constraint, get_settings
    import time
    
    class SafePA:
        def __init__(self, course_id, section_id, faculty_id, room_id, day, start_time, end_time):
            self.course_id = course_id
            self.section_id = section_id
            self.faculty_id = faculty_id
            self.room_id = room_id
            self.day = day
            self.start_time = start_time
            self.end_time = end_time

    with app.app_context():
        target_semester = '1st Semester'
        settings_db = get_settings()
        _adays_str = settings_db.allowed_days or 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'
        active_days = [d.strip() for d in _adays_str.split(',') if d.strip()]
        
        raw_courses = Course.query.filter_by(is_archived=False, semester_offered=target_semester).all()
        courses = [{'id': c.id, 'course_code': c.course_code, 'department': c.department or '', 'lec_units': c.lec_units or 0, 'lab_units': c.lab_units or 0, 'synchronous_lec_hours': c.synchronous_lec_hours or 0, 'synchronous_lab_hours': c.synchronous_lab_hours or 0, 'asynchronous_lec_hours': c.asynchronous_lec_hours or 0, 'asynchronous_lab_hours': c.asynchronous_lab_hours or 0} for c in raw_courses]
        
        raw_rooms = Room.query.filter_by(is_archived=False).all()
        rooms = [{'id': r.id, 'room_name': r.room_name, 'capabilities': r.capabilities, 'status': r.status, 'capacity': r.capacity} for r in raw_rooms]
        
        raw_faculty = Faculty.query.filter_by(is_archived=False).all()
        faculty = [{'id': f.id, 'full_name': f.full_name, 'available_days': f.available_days or ''} for f in raw_faculty]
        
        raw_sections = Section.query.filter_by(is_archived=False).all()
        sections = [{'id': s.id, 'course_ids': [c.id for c in s.courses], 'number_of_students': s.number_of_students, 'available_days': s.available_days} for s in raw_sections]
        
        valid_course_ids = {c['id'] for c in courses}
        raw_pre = PreAssignment.query.filter_by(is_archived=False).all()
        pre_assignments = [SafePA(pa.course_id, pa.section_id, pa.faculty_id, room_id=pa.room_id, day=pa.day, start_time=pa.start_time, end_time=pa.end_time) for pa in raw_pre if pa.course_id in valid_course_ids]
        
        constraints_config = {}
            
        scheduler = GeneticSchedulerTC11(courses, sections, faculty, rooms, pre_assignments, constraints_config, start_time=7, end_time=21, allowed_days=active_days)
        
        start_time = time.time()
        best = scheduler.run_algorithm()
        print(f"\\nTest 11 Completed in {time.time() - start_time:.2f} seconds.")
        print(f"Final HC: {best.hard_conflicts}, Final SS: {best.soft_score}")
'''

with open('alpha_test11_flawless_autostop.py', 'w', encoding='utf-8') as f:
    f.write(code + test_runner)

print("Successfully stripped and created alpha_test11_flawless_autostop.py")
