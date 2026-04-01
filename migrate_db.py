import sqlite3

def migrate():
    conn = sqlite3.connect('site.db')
    cursor = conn.cursor()
    
    # 1. Existing migrations (created_by_id)
    tables = ['course', 'room', 'section', 'faculty']
    for table in tables:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN created_by_id INTEGER REFERENCES user(id)")
            print(f"Added created_by_id to {table}")
        except sqlite3.OperationalError:
            pass

    # 2. Module 6: HubMessage Table
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hub_message (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                content TEXT,
                message_type VARCHAR(20) DEFAULT 'chat',
                draft_id INTEGER,
                proposal_status VARCHAR(20),
                metadata_json TEXT,
                FOREIGN KEY(sender_id) REFERENCES user(id),
                FOREIGN KEY(draft_id) REFERENCES draft_version(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hub_msg_timestamp ON hub_message(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hub_msg_type ON hub_message(message_type)")
        print("Created hub_message table and indices.")
    except Exception as e:
        print(f"Error creating hub_message: {e}")

    # 3. Module 6: DraftVersion columns
    draft_cols = [
        ("status", "VARCHAR(20) DEFAULT 'draft'"),
        ("submission_justification", "TEXT"),
        ("admin_justification", "TEXT")
    ]
    for col_name, col_type in draft_cols:
        try:
            cursor.execute(f"ALTER TABLE draft_version ADD COLUMN {col_name} {col_type}")
            print(f"Added {col_name} to draft_version")
        except sqlite3.OperationalError:
            pass
    
    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
