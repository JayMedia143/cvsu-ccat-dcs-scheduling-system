import json
from app import app, db, ArchivedEntity, ArchivedCourse, ArchivedSection, ArchivedFaculty, ArchivedRoom, ArchivedStudent

def migrate():
    with app.app_context():
        print("Starting Archive Migration...")
        legacy_rows = ArchivedEntity.query.all()
        total = len(legacy_rows)
        print(f"Found {total} legacy records to migrate.")
        
        migrated_count = 0
        
        for row in legacy_rows:
            try:
                data = json.loads(row.data_json)
                term_id = row.term_archive_id
                e_type = row.entity_type
                
                new_obj = None
                if e_type == 'Course':
                    new_obj = ArchivedCourse(
                        term_archive_id=term_id,
                        course_code=data.get('course_code'),
                        course_name=data.get('course_name'),
                        year_level=data.get('year_level'),
                        program=data.get('program'),
                        department=data.get('department'),
                        lec_units=data.get('lec_units'),
                        lab_units=data.get('lab_units'),
                        semester_offered=data.get('semester_offered')
                    )
                elif e_type == 'Section':
                    new_obj = ArchivedSection(
                        term_archive_id=term_id,
                        section_name=data.get('section_name'),
                        year_level=data.get('year_level'),
                        number_of_students=data.get('number_of_students')
                    )
                elif e_type == 'Faculty':
                    new_obj = ArchivedFaculty(
                        term_archive_id=term_id,
                        employee_id=data.get('employee_id'),
                        full_name=data.get('full_name'),
                        department=data.get('department'),
                        employment_status=data.get('employment_status')
                    )
                elif e_type == 'Room':
                    new_obj = ArchivedRoom(
                        term_archive_id=term_id,
                        room_name=data.get('room_name'),
                        building=data.get('building'),
                        capacity=data.get('capacity'),
                        status=data.get('status')
                    )
                elif e_type == 'Student':
                    new_obj = ArchivedStudent(
                        term_archive_id=term_id,
                        student_id=data.get('student_id'),
                        full_name=data.get('full_name'),
                        year_level=data.get('year_level'),
                        is_irregular=data.get('is_irregular', False)
                    )
                
                if new_obj:
                    db.session.add(new_obj)
                    migrated_count += 1
                
                if migrated_count % 100 == 0:
                    print(f"Migrated {migrated_count}/{total}...")
                    db.session.commit()
            except Exception as e:
                print(f"Failed to migrate row {row.id}: {e}")
        
        db.session.commit()
        print(f"Migration complete! Successfully moved {migrated_count} records.")

if __name__ == '__main__':
    migrate()
