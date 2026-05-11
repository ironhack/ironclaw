import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "jobs.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.executescript("""
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  company TEXT,
  location TEXT,
  source TEXT,
  url TEXT NOT NULL,
  description TEXT,
  language_req TEXT,
  experience_level TEXT,
  bootcamp TEXT NOT NULL,
  found_date TEXT,
  active INTEGER DEFAULT 1,
  last_checked TEXT
);

CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  generated_date TEXT NOT NULL,
  s3_url TEXT NOT NULL,
  job_count INTEGER,
  notes TEXT
);
""")

conn.commit()
conn.close()
print(f"Database initialized at {DB_PATH}")
