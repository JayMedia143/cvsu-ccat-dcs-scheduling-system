import sqlite3
import os

def migrate():
    db_path = 'site.db'
    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Using quotes for table names that might be reserved keywords (like 'constraint')
    table = '"constraint"'
    try:
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [info[1] for info in cursor.fetchall()]
        
        if 'created_at' not in columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN created_at DATETIME")
            print(f"Added created_at to {table}")
        else:
            print(f"created_at already exists in {table}")
            
    except sqlite3.OperationalError as e:
        print(f"Error updating {table}: {e}")

    conn.commit()
    conn.close()
    print("\nMigration finished.")

if __name__ == '__main__':
    migrate()
