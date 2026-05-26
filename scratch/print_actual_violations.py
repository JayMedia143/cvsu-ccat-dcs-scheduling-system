import sys; sys.path.insert(0, '.')
from app import app
with app.app_context():
    import json
    from debug_schedule import build_scheduler, records_to_chromosome
    scheduler = build_scheduler('1st Semester', 7, 20, ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'])
    with open('live_conflicts.json') as f:
        data = json.load(f)
    records = data.get('schedules', [])
    chrom = records_to_chromosome(scheduler, records)
    
    # Let's run a custom check to see which genes are violating HC-19 and HC-21!
    genes = chrom.genes
    room_map = scheduler.room_map
    pen = scheduler._pen
    cmap = scheduler.CONSTRAINT_MAP
    
    from collections import defaultdict
    room_bits = defaultdict(int)
    fac_bits = defaultdict(int)
    sec_bits = defaultdict(int)
    
    # We will build masks first
    for g in genes:
        _m = g.bitmask
        _d = g.day_idx
        if g.room_id not in scheduler.online_room_ids and g.room_id not in scheduler.multi_assignment_rooms:
            room_bits[(g.room_id, _d)] |= _m
        if g.faculty_id and g.faculty_id not in scheduler.multi_assignment_faculty:
            fac_bits[(g.faculty_id, _d)] |= _m
        sec_bits[(g.section_id, _d)] |= _m
        
    print("VIOLATING GENES FOR HC-19 (Lunch Break):")
    for i, g in enumerate(genes):
        # Let's see if this gene violates lunch break
        # In seeder12, HC-19 is LUNCH_BREAK (HC-19 is category Faculty / Student)
        # Wait, in calculate_fitness, HC-19 is LUNCH_BREAK!
        pass
        
    # Let's check max consecutive hours (HC-21)
    print("\nVIOLATING FACULTY FOR HC-21 (Consecutive Hours):")
    from genetic_algorithm import _is_valid_break_mask
    for (fac_id, d), mask in fac_bits.items():
        if fac_id in scheduler.multi_assignment_faculty:
            continue
        if not _is_valid_break_mask(mask):
            from app import Faculty
            fac = Faculty.query.get(fac_id)
            fn = fac.full_name if fac else f"ID={fac_id}"
            print(f"Faculty {fn} on day {scheduler.days[d]} has consecutive hours violation! Mask: {bin(mask)}")
