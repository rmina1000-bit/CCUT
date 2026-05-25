import sqlite3

def inspect_db():
    db_path = r'D:\CCUT1.0.4\ccut_backend\ccut_app.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    print("Tables:", tables)
    
    for table in tables:
        print(f"\n--- Table: {table} ---")
        cursor.execute(f"PRAGMA table_info({table});")
        columns = cursor.fetchall()
        for col in columns:
            print(f"  Col: {col[1]} ({col[2]})")
            
        # Let's inspect some rows to see the data structure if they exist
        try:
            cursor.execute(f"SELECT * FROM {table} LIMIT 2;")
            rows = cursor.fetchall()
            print(f"  Sample Rows (up to 2):")
            for r in rows:
                print(f"    {r}")
        except Exception as e:
            print(f"    Error reading rows: {e}")
            
    conn.close()

if __name__ == "__main__":
    inspect_db()
