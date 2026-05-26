from app import app, PreAssignment
with app.app_context():
    pas = PreAssignment.query.filter_by(is_archived=False).all()
    for pa in pas:
        ccode = pa.course.course_code if pa.course else "None"
        sname = pa.section.section_name if pa.section else "None"
        rname = pa.room.room_name if pa.room else "None"
        print(f"PA ID: {pa.id} | {ccode} | {sname} | {rname} | {pa.day} | {pa.start_time} - {pa.end_time}")
