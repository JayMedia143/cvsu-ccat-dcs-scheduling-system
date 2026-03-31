from app import app, db, get_archive_entities
with app.app_context():
    print('Faculty:', len(get_archive_entities(1, 'Faculty')))
    print('Irregular:', len(get_archive_entities(1, 'IrregularStudent')))
