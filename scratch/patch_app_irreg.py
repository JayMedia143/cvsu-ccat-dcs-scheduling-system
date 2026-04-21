import datetime

def patch_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Patch Historical Sorting
    target_hist = (
        "        # 2. Apply Sorting\n"
        "        if sort_by == 'name-desc':\n"
        "            all_objs.sort(key=lambda x: (getattr(x, 'full_name', '') or '').lower(), reverse=True)\n"
        "        elif sort_by == 'id-asc':\n"
        "            all_objs.sort(key=lambda x: (getattr(x, 'student_id', '') or '').lower())\n"
        "        elif sort_by == 'id-desc':\n"
        "            all_objs.sort(key=lambda x: (getattr(x, 'student_id', '') or '').lower(), reverse=True)\n"
        "        elif sort_by == 'section':\n"
        "            all_secs = get_archive_entities(archive_id, 'Section')\n"
        "            sec_map = {s.id: getattr(s, 'section_name', '') for s in all_secs}\n"
        "            all_objs.sort(key=lambda x: (sec_map.get(getattr(x, 'section_id', 0), 'Z-NoSection'), (getattr(x, 'full_name', '') or '').lower()))\n"
        "        else: # Default: name-asc\n"
        "            all_objs.sort(key=lambda x: (getattr(x, 'full_name', '') or '').lower())"
    )
    replacement_hist = (
        "        # 2. Apply Sorting\n"
        "        if sort_by == 'name-desc':\n"
        "            all_objs.sort(key=lambda x: (getattr(x, 'full_name', '') or '').lower(), reverse=True)\n"
        "        elif sort_by == 'id-asc':\n"
        "            all_objs.sort(key=lambda x: (getattr(x, 'student_id', '') or '').lower())\n"
        "        elif sort_by == 'id-desc':\n"
        "            all_objs.sort(key=lambda x: (getattr(x, 'student_id', '') or '').lower(), reverse=True)\n"
        "        elif sort_by == 'section':\n"
        "            all_secs = get_archive_entities(archive_id, 'Section')\n"
        "            sec_map = {s.id: getattr(s, 'section_name', '') for s in all_secs}\n"
        "            all_objs.sort(key=lambda x: (sec_map.get(getattr(x, 'section_id', 0), 'Z-NoSection'), (getattr(x, 'full_name', '') or '').lower()))\n"
        "        elif sort_by == 'newest':\n"
        "            from datetime import datetime as dtt\n"
        "            all_objs.sort(key=lambda x: (getattr(x, 'created_at', None) or dtt.min, getattr(x, 'id', 0)), reverse=True)\n"
        "        else: # Default: name-asc\n"
        "            all_objs.sort(key=lambda x: (getattr(x, 'full_name', '') or '').lower())"
    )

    # 2. Patch Live Sorting
    target_live = (
        "    if sort_by == 'name-desc':\n"
        "        query = query.order_by(Student.full_name.desc())\n"
        "    elif sort_by == 'id-asc':\n"
        "        query = query.order_by(Student.student_id.asc())\n"
        "    elif sort_by == 'id-desc':\n"
        "        query = query.order_by(Student.student_id.desc())\n"
        "    elif sort_by == 'section':\n"
        "        query = query.outerjoin(Section, Student.section_id == Section.id)\\\n"
        "                     .order_by(Section.section_name.asc(), Student.full_name.asc())\n"
        "    else:\n"
        "        query = query.order_by(Student.full_name.asc())"
    )
    replacement_live = (
        "    if sort_by == 'name-desc':\n"
        "        query = query.order_by(Student.full_name.desc())\n"
        "    elif sort_by == 'id-asc':\n"
        "        query = query.order_by(Student.student_id.asc())\n"
        "    elif sort_by == 'id-desc':\n"
        "        query = query.order_by(Student.student_id.desc())\n"
        "    elif sort_by == 'section':\n"
        "        query = query.outerjoin(Section, Student.section_id == Section.id)\\\n"
        "                     .order_by(Section.section_name.asc(), Student.full_name.asc())\n"
        "    elif sort_by == 'newest' or sort_by == 'default':\n"
        "        query = query.order_by(Student.created_at.desc(), Student.id.desc())\n"
        "    else:\n"
        "        query = query.order_by(Student.full_name.asc())"
    )

    new_content = content
    
    # Try LF version
    if target_hist in new_content:
        new_content = new_content.replace(target_hist, replacement_hist)
        print("Patched Historical sorting (LF).")
    elif target_hist.replace('\n', '\r\n') in new_content:
        new_content = new_content.replace(target_hist.replace('\n', '\r\n'), replacement_hist.replace('\n', '\r\n'))
        print("Patched Historical sorting (CRLF).")
    else:
        print("Could not find Historical sorting block.")

    if target_live in new_content:
        new_content = new_content.replace(target_live, replacement_live)
        print("Patched Live sorting (LF).")
    elif target_live.replace('\n', '\r\n') in new_content:
        new_content = new_content.replace(target_live.replace('\n', '\r\n'), replacement_live.replace('\n', '\r\n'))
        print("Patched Live sorting (CRLF).")
    else:
        print("Could not find Live sorting block.")

    if new_content != content:
        with open(filepath, 'w', encoding='utf-8', newline='') as f:
            f.write(new_content)
        print("app.py updated successfully.")
    else:
        print("No changes made to app.py.")

if __name__ == '__main__':
    patch_file('app.py')
