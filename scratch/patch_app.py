def patch_file(filepath):
    import datetime
    from datetime import datetime as dt
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    target = (
        "if sort_by == 'course-asc': query = query.join(Course).order_by(Course.course_code.asc())\n"
        "    elif sort_by == 'section-asc': query = query.join(Section).order_by(Section.section_name.asc())\n"
        "    else: query = query.order_by(PreAssignment.id.desc())"
    )
    
    replacement_active = (
        "if sort_by == 'course-asc': query = query.join(Course).order_by(Course.course_code.asc())\n"
        "    elif sort_by == 'course-desc': query = query.join(Course).order_by(Course.course_code.desc())\n"
        "    elif sort_by == 'section-asc': query = query.join(Section).order_by(Section.section_name.asc())\n"
        "    elif sort_by == 'section-desc': query = query.join(Section).order_by(Section.section_name.desc())\n"
        "    elif sort_by == 'newest' or sort_by == 'default': query = query.order_by(PreAssignment.created_at.desc(), PreAssignment.id.desc())\n"
        "    else: query = query.order_by(PreAssignment.id.desc())"
    )
    
    replacement_archive = (
        "if sort_by == 'course-asc': query = query.join(Course).order_by(Course.course_code.asc())\n"
        "    elif sort_by == 'course-desc': query = query.join(Course).order_by(Course.course_code.desc())\n"
        "    elif sort_by == 'section-asc': query = query.join(Section).order_by(Section.section_name.asc())\n"
        "    elif sort_by == 'section-desc': query = query.join(Section).order_by(Section.section_name.desc())\n"
        "    elif sort_by == 'newest' or sort_by == 'default': query = query.order_by(PreAssignment.deleted_at.desc(), PreAssignment.id.desc())\n"
        "    else: query = query.order_by(PreAssignment.id.desc())"
    )

    new_content = None
    parts = content.split(target)
    if len(parts) == 3:
        new_content = parts[0] + replacement_active + parts[1] + replacement_archive + parts[2]
        print("Patched both active and archive logic.")
    else:
        target_rn = target.replace('\n', '\r\n')
        parts = content.split(target_rn)
        if len(parts) == 3:
            new_content = parts[0] + replacement_active.replace('\n', '\r\n') + parts[1] + replacement_archive.replace('\n', '\r\n') + parts[2]
            print("Patched both active and archive logic (with CRLF).")

    if new_content:
        with open(filepath, 'w', encoding='utf-8', newline='') as f:
            f.write(new_content)
        print("app.py updated successfully.")
    else:
        print(f"Could not find exact match. Found {len(content.split(target))-1} matches with LF and {len(content.split(target.replace(chr(10), chr(13)+chr(10))))-1} matches with CRLF.")

if __name__ == '__main__':
    patch_file('app.py')
