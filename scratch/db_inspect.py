import sqlite3
import json

conn = sqlite3.connect('ccut_backend/ccut_app.db')
cursor = conn.cursor()

# Get tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [row[0] for row in cursor.fetchall()]
print("Tables in database:", tables)

# Query recent projects or proposal data if they exist
for table in tables:
    try:
        cursor.execute(f"SELECT count(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"Table '{table}': {count} rows")
    except Exception as e:
        print(f"Error querying {table}: {e}")

# Try to find tables containing project info, fragments, or thumbnails
# Let's inspect schema for some tables
for table in ['fragments', 'projects', 'proposals', 'video_fragments', 'source_videos', 'project_sources']:
    if table in tables:
        print(f"\n--- Schema of {table} ---")
        cursor.execute(f"PRAGMA table_info({table});")
        for col in cursor.fetchall():
            print(f"  Column: {col[1]} ({col[2]})")
        
        # Select first row
        cursor.execute(f"SELECT * FROM {table} LIMIT 1")
        row = cursor.fetchone()
        if row:
            print(f"  First row: {row}")
