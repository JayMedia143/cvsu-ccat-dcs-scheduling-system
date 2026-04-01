import sqlite3
import os

def migrate():
    db_path = 'site.db'
    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found.")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if recipient_name already exists
        cursor.execute("PRAGMA table_info(hub_message)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'recipient_name' not in columns:
            print("Adding recipient_name column to hub_message table...")
            cursor.execute("ALTER TABLE hub_message ADD COLUMN recipient_name VARCHAR(50)")
            conn.commit()
            print("Successfully added recipient_name column!")
        else:
            print("recipient_name column already exists.")
            
    except Exception as e:
        print(f"Error during migration: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
