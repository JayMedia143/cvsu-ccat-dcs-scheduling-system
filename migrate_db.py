import sqlite3

def migrate():
    conn = sqlite3.connect('site.db')
    cursor = conn.cursor()
    
    tables = ['course', 'room', 'section', 'faculty']
    
    for table in tables:
        try:
            print(f"Adding created_by_id to {table}...")
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN created_by_id INTEGER REFERENCES user(id)")
            print(f"Successfully added to {table}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"Column already exists in {table}")
            else:
                print(f"Error adding to {table}: {e}")
    
    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
