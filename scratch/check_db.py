from app import app, db, Section
with app.app_context():
    import sqlalchemy
    inspector = sqlalchemy.inspect(db.engine)
    print([c['name'] for c in inspector.get_columns('section')])
