import os
import sys

# Ensure we can import from current directory
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import app, db, get_settings, SCHEDULED_DEPARTMENTS
from genetic_algorithm import GeneticScheduler

class MockOccSec(dict):
    pass

def run_fast_unit_test():
    print("=======================================================================")
    print("STARTING DENSITY SORTING UNIT TEST")
    print("=======================================================================")
    
    with app.app_context():
        # Setup basic mock data for GeneticScheduler
        courses = []
        sections = [{'id': 1, 'course_ids': [], 'number_of_students': 30}]
        faculty = []
        rooms = []
        pre_assignments = []
        constraints_config = {}
        
        # Instantiate scheduler (it won't run full GA, just acts as a parent for the helper)
        scheduler = GeneticScheduler(
            courses, sections, faculty, rooms, pre_assignments, constraints_config,
            start_time=7, end_time=20, allowed_days=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        )
        
        # Mock some active section loads (as integer bitmasks)
        # Recall that bit_count() counts 1s in the binary representation of the mask.
        # - Day 0 (Monday): load = 4 slots (e.g. mask = 0b1111 -> bit_count = 4)
        # - Day 1 (Tuesday): load = 0 slots (mask = 0b0 -> bit_count = 0) - Empty day
        # - Day 2 (Wednesday): load = 12 slots (mask = 0b111111111111 -> bit_count = 12) - Saturated day (>= 6 hours)
        # - Day 3 (Thursday): load = 8 slots (mask = 0b11111111 -> bit_count = 8)
        # - Day 4 (Friday): load = 0 slots (mask = 0b0 -> bit_count = 0) - Empty day
        
        sec_id = 1
        occ_sec = {
            (sec_id, 0): 0b1111,          # bit_count = 4 (Active, space available)
            (sec_id, 1): 0b0,             # bit_count = 0 (Empty)
            (sec_id, 2): 0b111111111111,  # bit_count = 12 (Saturated)
            (sec_id, 3): 0b11111111,      # bit_count = 8 (Active, space available)
            (sec_id, 4): 0b0,             # bit_count = 0 (Empty)
        }
        
        print("\nInput Day Loads:")
        for d in range(5):
            load = occ_sec[(sec_id, d)].bit_count()
            status = "Empty" if load == 0 else ("Saturated (>=12)" if load >= 12 else "Active")
            print(f"  Day {d} ({scheduler.days[d]}): Load = {load} slots ({status})")
            
        # Retrieve density guided days
        sorted_days = scheduler._get_density_guided_days(sec_id, occ_sec)
        
        print("\nOutput Day Order (Sorted by Density Priority):")
        for rank, d in enumerate(sorted_days):
            load = occ_sec[(sec_id, d)].bit_count()
            status = "Empty" if load == 0 else ("Saturated (>=12)" if load >= 12 else "Active")
            print(f"  Rank {rank+1}: Day {d} ({scheduler.days[d]}) -> Load = {load} slots ({status})")
            
        # Expected priorities:
        # Priority 1: Active with space (descending load): Day 3 (load 8), Day 0 (load 4)
        # Priority 2: Saturated (load >= 12): Day 2 (load 12)
        # Priority 3: Empty (load = 0): Day 1, Day 4 (order can be 1 then 4 or 4 then 1 as they tie)
        
        # Validate order:
        # First two elements MUST be 3 and 0 (in that exact order as 8 > 4)
        assert sorted_days[0] == 3, f"Expected Rank 1 to be Day 3, got Day {sorted_days[0]}"
        assert sorted_days[1] == 0, f"Expected Rank 2 to be Day 0, got Day {sorted_days[1]}"
        # Third element MUST be 2 (saturated)
        assert sorted_days[2] == 2, f"Expected Rank 3 to be Day 2, got Day {sorted_days[2]}"
        # Last two elements MUST be the empty days (1 and 4, order does not matter)
        assert set(sorted_days[3:]) == {1, 4}, f"Expected Ranks 4-5 to be empty days {{1, 4}}, got {sorted_days[3:]}"
        
        print("\n=======================================================================")
        print("ALL MATHEMATICAL ASSERTIONS PASSED! DESIGN IS 100% CORRECT!")
        print("=======================================================================")

if __name__ == '__main__':
    run_fast_unit_test()
