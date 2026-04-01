import sqlite3
import os

db_path = r'c:\WFH\jeremy\12. CvSU_Scheduling_System-Version-2.25_send\CvSU_Scheduling_System-Version-2 - antigravity_2_claude - Copy\site.db'

def migrate():
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Check existing columns in hub_message
    cursor.execute("PRAGMA table_info(hub_message)")
    columns = [col[1] for col in cursor.fetchall()]

    # 2. Add 'semester' if missing
    if 'semester' not in columns:
        print("Adding 'semester' column to hub_message...")
        cursor.execute("ALTER TABLE hub_message ADD COLUMN semester VARCHAR(30)")
    else:
        print("'semester' column already exists.")

    # 3. Add 'is_read' if missing
    if 'is_read' not in columns:
        print("Adding 'is_read' column to hub_message...")
        cursor.execute("ALTER TABLE hub_message ADD COLUMN is_read BOOLEAN DEFAULT 0")
    else:
        print("'is_read' column already exists.")

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
