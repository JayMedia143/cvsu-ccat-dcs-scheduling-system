import re

def update_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Define the patterns and replacements for Add
    add_patterns = [
        # Course (already existing course_code)
        (r"(def add_course\(\):\n)(\s+)(#*\s*)(db\.session\.add\(Course\()", 
         r"\1\2course_code = request.form.get('course_code')\n\2existing = Course.query.filter_by(course_code=course_code, is_archived=False).first()\n\2if existing:\n\2    flash(f\"Course code '{course_code}' already exists!\", \"danger\")\n\2    return redirect(url_for('manage_courses'))\n\n\2\4"),
        
        # Room
        (r"(def add_room\(\):\n)(\s+)(#*\s*)(db\.session\.add\(Room\()", 
         r"\1\2room_name = request.form.get('room_name')\n\2existing = Room.query.filter_by(room_name=room_name, is_archived=False).first()\n\2if existing:\n\2    flash(f\"Room name '{room_name}' already exists!\", \"danger\")\n\2    return redirect(url_for('manage_rooms'))\n\n\2\4"),
         
        # Section
        (r"(def add_section\(\):\n)(\s+)(#*\s*)(db\.session\.add\(Section\()", 
         r"\1\2section_name = request.form.get('section_name')\n\2existing = Section.query.filter_by(section_name=section_name, is_archived=False).first()\n\2if existing:\n\2    flash(f\"Section name '{section_name}' already exists!\", \"danger\")\n\2    return redirect(url_for('manage_sections'))\n\n\2\4"),

        # Faculty
        (r"(def add_faculty\(\):\n)(\s+)(#*\s*)(db\.session\.add\(Faculty\()", 
         r"\1\2employee_id = request.form.get('employee_id')\n\2existing = Faculty.query.filter_by(employee_id=employee_id, is_archived=False).first()\n\2if existing:\n\2    flash(f\"Faculty Employee ID '{employee_id}' already exists!\", \"danger\")\n\2    return redirect(url_for('manage_faculty'))\n\n\2\4"),

        # Student
        (r"(def add_student\(\):\n)(\s+)(#*\s*)(db\.session\.add\(Student\()", 
         r"\1\2student_id = request.form.get('student_id')\n\2existing = Student.query.filter_by(student_id=student_id, is_archived=False).first()\n\2if existing:\n\2    flash(f\"Student ID '{student_id}' already exists!\", \"danger\")\n\2    return redirect(url_for('manage_students'))\n\n\2\4"),
         
        # User
        (r"(def add_user\(\):\n)(\s+)(new_user = User)", 
         r"\1\2username = request.form.get('username')\n\2existing = User.query.filter_by(username=username).first()\n\2if existing:\n\2    flash(f\"Username '{username}' is already taken!\", \"danger\")\n\2    return redirect(url_for('manage_users'))\n\n\2\3")
    ]

    for p, repl in add_patterns:
        content = re.sub(p, repl, content, count=1)

    # Define the patterns and replacements for Update
    update_patterns = [
        # Course Update
        (r"(def update_course\(course_id\):\n\s+course = Course\.query\.get_or_404\(course_id\)\n)(\s+)course\.course_code = request\.form\.get\('course_code'\)", 
         r"\1\2new_code = request.form.get('course_code')\n\2existing = Course.query.filter(Course.course_code == new_code, Course.id != course_id, Course.is_archived == False).first()\n\2if existing:\n\2    flash(f\"Course code '{new_code}' is already taken.\", \"danger\")\n\2    return redirect(url_for('manage_courses'))\n\2course.course_code = new_code"),

        # Room Update
        (r"(def update_room\(room_id\):\n\s+room = Room\.query\.get_or_404\(room_id\)\n)(\s+)room\.room_name = request\.form\.get\('room_name'\)", 
         r"\1\2new_name = request.form.get('room_name')\n\2existing = Room.query.filter(Room.room_name == new_name, Room.id != room_id, Room.is_archived == False).first()\n\2if existing:\n\2    flash(f\"Room name '{new_name}' is already taken.\", \"danger\")\n\2    return redirect(url_for('manage_rooms'))\n\2room.room_name = new_name"),

        # Section Update
        (r"(def update_section\(section_id\):\n\s+section = Section\.query\.get_or_404\(section_id\)\n)(\s+)section\.section_name = request\.form\.get\('section_name'\)", 
         r"\1\2new_name = request.form.get('section_name')\n\2existing = Section.query.filter(Section.section_name == new_name, Section.id != section_id, Section.is_archived == False).first()\n\2if existing:\n\2    flash(f\"Section name '{new_name}' is already taken.\", \"danger\")\n\2    return redirect(url_for('manage_sections'))\n\2section.section_name = new_name"),

        # Faculty Update
        (r"(def update_faculty\(faculty_id\):\n\s+faculty = Faculty\.query\.get_or_404\(faculty_id\)\n)(\s+)faculty\.employee_id = request\.form\.get\('employee_id'\)", 
         r"\1\2new_id = request.form.get('employee_id')\n\2existing = Faculty.query.filter(Faculty.employee_id == new_id, Faculty.id != faculty_id, Faculty.is_archived == False).first()\n\2if existing:\n\2    flash(f\"Faculty Employee ID '{new_id}' is already taken.\", \"danger\")\n\2    return redirect(url_for('manage_faculty'))\n\2faculty.employee_id = new_id"),
        
        # Student Update
        (r"(def update_student\(student_pk\):\n\s+student = Student\.query\.get_or_404\(student_pk\)\n)(\s+)student\.student_id = request\.form\.get\('student_id'\)", 
         r"\1\2new_id = request.form.get('student_id')\n\2existing = Student.query.filter(Student.student_id == new_id, Student.id != student_pk, Student.is_archived == False).first()\n\2if existing:\n\2    flash(f\"Student ID '{new_id}' is already taken.\", \"danger\")\n\2    return redirect(url_for('manage_students'))\n\2student.student_id = new_id"),

        # User Update (Note: username check might exist, but usually simple)
        (r"(def update_user\(user_id\):\n\s+user_to_update = User\.query\.get_or_404\(user_id\)\n)(\s+)new_username = request\.form\.get\('username'\)", 
         r"\1\2new_username = request.form.get('username')\n\2existing = User.query.filter(User.username == new_username, User.id != user_id).first()\n\2if existing:\n\2    flash(f\"Username '{new_username}' is already taken.\", \"danger\")\n\2    return redirect(url_for('manage_users'))")
    ]

    for p, repl in update_patterns:
        content = re.sub(p, repl, content, count=1)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print("File properly injected")

update_file('app.py')
