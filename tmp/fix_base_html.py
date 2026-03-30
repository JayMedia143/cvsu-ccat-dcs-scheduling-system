import os

file_path = r'c:\WFH\jeremy\12. CvSU_Scheduling_System-Version-2.25_send\CvSU_Scheduling_System-Version-2 - antigravity_2_claude - Copy\templates\base.html'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

old_text = """                    {% if not is_hist %}
                    <li><a class="dropdown-item" href="#" onclick="openArchiveModal()"><i
                                 class="bi bi-exclamation-triangle-fill text-warning me-2"></i> Finalize & Archive Semester</a></li>
                    {% endif %}"""

new_text = """                    {% if not is_hist %}
                    <li><a class="dropdown-item" href="#" onclick="openArchiveModal()"><i
                                 class="bi bi-exclamation-triangle-fill text-warning me-2"></i> Finalize & Archive Semester</a></li>
                    <li><a class="dropdown-item" href="{{ url_for('manage_archives') }}"><i
                                class="bi bi-archive-fill text-success me-2"></i> Manage Archives</a></li>
                    {% endif %}"""

if old_text in content:
    new_content = content.replace(old_text, new_text)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Replacement success!")
else:
    # Try with a slightly different version (maybe spaces or line endings)
    print("Old text not found exactly. Trying more flexible match...")
    import re
    pattern = re.escape(old_text).replace(r'\ ', r'\s+')
    new_content, count = re.subn(pattern, new_text, content)
    if count > 0:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Replacement success via Regex! ({count} matches)")
    else:
        print("Replacement failed via Regex too.")
