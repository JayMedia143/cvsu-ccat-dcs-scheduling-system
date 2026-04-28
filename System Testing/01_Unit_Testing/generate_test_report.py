import subprocess
import json
import os

def run_tests_and_generate_table():
    print("🤖 Starting Automated System Testing...")
    
    # Run pytest and capture results in JSON format
    # Note: requires pytest-json-report (pip install pytest-json-report)
    try:
        subprocess.run(['pip', 'install', 'pytest-json-report'], check=True)
        # Use relative paths since we are running from within the infra folder or root
        test_file = os.path.join(os.path.dirname(__file__), 'tests', 'unit', 'test_ga_logic.py')
        report_file = os.path.join(os.path.dirname(__file__), 'report.json')
        subprocess.run(['python', '-m', 'pytest', '--json-report', f'--json-report-file={report_file}', test_file], capture_output=True)
    except Exception as e:
        print(f"Error running tests: {e}")
        return

    if not os.path.exists('report.json'):
        print("Error: report.json not found.")
        return

    with open('report.json', 'r') as f:
        data = json.load(f)

    # -------------------------------------------------------------------------
    # GENERATE MARKDOWN TABLE (For Thesis Copy-Paste)
    # -------------------------------------------------------------------------
    table_header = "| Test Case ID | Test Description | Expected Result | Actual Result | Status |\n"
    table_divider = "| :--- | :--- | :--- | :--- | :--- |\n"
    table_rows = ""

    for test in data.get('tests', []):
        nodeid = test.get('nodeid', '')
        outcome = test.get('outcome', 'failed').upper()
        
        # Extract ID and Description from docstring
        doc = test.get('metadata', {}).get('doc', '') # This might need manual mapping if metadata isn't captured
        # Since standard pytest doesn't capture docstrings easily in JSON without plugins, 
        # we will use a manual mapping for this demonstration.
        
        test_name = nodeid.split('::')[-1]
        
        # Manual Mapping for Thesis Table
        mapping = {
            'test_tc_u1_faculty_overlap': ('TC-U1', 'Detect faculty overlap', 'Conflict Detected (True)'),
            'test_tc_u2_room_overlap': ('TC-U2', 'Detect room overlap', 'Conflict Detected (True)'),
            'test_tc_u3_section_overlap': ('TC-U3', 'Detect section overlap', 'Conflict Detected (True)'),
            'test_tc_u4_different_days_no_conflict': ('TC-U4', 'Different days test', 'No Conflict (False)'),
            'test_tc_u5_back_to_back_no_conflict': ('TC-U5', 'Back-to-back test', 'No Conflict (False)'),
            'test_tc_u6_room_suitability_mismatch': ('TC-U6', 'Room suitability check', 'Suitability Error'),
            'test_tc_u7_consecutive_hours_violation': ('TC-U7', 'Consecutive hours limit', 'Violation Detected'),
            'test_tc_u8_lec_lab_sequence': ('TC-U8', 'Lec-Lab sequence rule', 'Sequence Error'),
            'test_tc_u9_slot_conversion_accuracy': ('TC-U9', 'Hour-to-Slot conversion', '6 Slots (3 Hrs)'),
            'test_tc_u10_max_weekly_hours_violation': ('TC-U10', 'Max weekly hours limit', 'Violation Detected'),
            'test_tc_u11_faculty_preferred_day_restriction': ('TC-U11', 'Preferred day restriction', 'Day Restriction Error'),
            'test_tc_u12_room_capacity_check': ('TC-U12', 'Room capacity validation', 'Capacity Error'),
            'test_tc_u13_bitmask_generation': ('TC-U13', 'Bitmask shifting accuracy', 'Bitmask 48'),
            'test_tc_u14_gene_initialization_defaults': ('TC-U14', 'Gene default initialization', 'Valid Defaults'),
            'test_tc_u15_population_creation_logic': ('TC-U15', 'Population size check', 'Valid Size'),
            'test_tc_u16_min_duration_logic': ('TC-U16', 'Min duration (1 slot)', 'Valid Slot'),
            'test_tc_u17_max_duration_logic': ('TC-U17', 'Max duration boundary', 'Valid Slots'),
            'test_tc_u18_start_of_day_boundary': ('TC-U18', 'Start of day boundary', 'Start Idx 0'),
            'test_tc_u19_end_of_day_boundary': ('TC-U19', 'End of day boundary', 'Valid End Idx'),
            'test_tc_u20_fixed_gene_mutation_protection': ('TC-U20', 'Fixed gene protection', 'No Mutation'),
            'test_tc_u21_crossover_identical_parents': ('TC-U21', 'Identical crossover', 'Identical Offspring'),
            'test_tc_u22_zero_conflict_fitness': ('TC-U22', 'Zero conflict fitness', 'Score 1.0'),
            'test_tc_u23_penalty_weight_scaling': ('TC-U23', 'Penalty weight scaling', 'Correct Multiplier'),
            'test_tc_u24_empty_schedule_handling': ('TC-U24', 'Empty schedule handling', 'No Crash'),
            'test_tc_u25_duplicate_gene_detection': ('TC-U25', 'Duplicate gene check', 'Detection OK'),
            'test_tc_u26_lec_lab_same_day_valid_sequence': ('TC-U26', 'Same day Lec-Lab sequence', 'Valid Order'),
            'test_tc_u27_lec_lab_different_day_sequence': ('TC-U27', 'Different day Lec-Lab', 'Valid Sequence'),
            'test_tc_u28_multi_section_faculty_collision': ('TC-U28', 'Faculty multi-section collision', 'Conflict OK'),
            'test_tc_u29_multi_faculty_room_collision': ('TC-U29', 'Room multi-faculty collision', 'Conflict OK'),
            'test_tc_u30_async_duration_validation': ('TC-U30', 'Async duration validation', 'Valid Duration')
        }
        
        tc_id, desc, expected = mapping.get(test_name, ('Unknown', test_name, 'Success'))
        actual = expected if outcome == 'PASSED' else 'Failed/Mismatch'
        
        table_rows += f"| {tc_id} | {desc} | {expected} | {actual} | {outcome} |\n"

    final_table = table_header + table_divider + table_rows
    
    with open('THESIS_TEST_RESULTS.md', 'w') as f:
        f.write("# 📊 Thesis Automated Test Results\n\n")
        f.write(final_table)
    
    print("\n✅ SUCCESS! Thesis results generated in: THESIS_TEST_RESULTS.md")
    print("You can now copy-paste the table below into your Chapter 4.")
    print("\n" + final_table)

if __name__ == "__main__":
    run_tests_and_generate_table()
