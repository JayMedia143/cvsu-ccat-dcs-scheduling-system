import os

app_path = r"c:\WFH\jeremy\12. CvSU_Scheduling_System-Version-2.25_send\CvSU_Scheduling_System-Version-2 - antigravity_2_claude - Copy\app.py"

with open(app_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line that starts with "if __name__ == '__main__':"
insert_idx = -1
for i, line in enumerate(lines):
    if line.strip().startswith("if __name__ == '__main__':"):
        insert_idx = i
        break

if insert_idx != -1:
    # Code to insert
    new_code = [
        "\n",
        "@app.route('/system-tester')\n",
        "@login_required\n",
        "@role_required('superadmin')\n",
        "def system_tester():\n",
        "    \"\"\"\n",
        "    Standalone Audit Console: Verifies all 12 Phases of the Master Manifest.\n",
        "    Provides automated DOM checks, API probes, and manual verification triggers.\n",
        "    \"\"\"\n",
        "    total_phases = 12\n",
        "    return render_template('system_tester.html', total_phases=total_phases)\n",
        "\n"
    ]
    
    # Insert before the if __name__ block
    final_lines = lines[:insert_idx] + new_code + lines[insert_idx:]
    
    with open(app_path, 'w', encoding='utf-8') as f:
        f.writelines(final_lines)
    print(f"Successfully inserted route at line {insert_idx}")
else:
    print("Could not find the main execution block.")
