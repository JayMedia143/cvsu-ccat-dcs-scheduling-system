from app import app, db, SystemSettings
with app.app_context():
    s = SystemSettings.query.first()
    print(s.sem_ay_value if s else 'None')
