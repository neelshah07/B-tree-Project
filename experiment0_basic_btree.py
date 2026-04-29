import sqlite3
import csv

# Connect to database
conn = sqlite3.connect("movielens.db")
cursor = conn.cursor()

# Drop table if exists (for clean run)
cursor.execute("DROP TABLE IF EXISTS ratings")

# Create table
cursor.execute("""
CREATE TABLE ratings (
    userId INTEGER,
    movieId INTEGER,
    rating REAL,
    timestamp INTEGER
)
""")

# Load CSV data
with open("ratings.csv", "r", encoding="utf-8") as f:
    reader = csv.reader(f)
    next(reader)
    cursor.executemany("INSERT INTO ratings VALUES (?, ?, ?, ?)", reader)

conn.commit()

# Count rows
count = cursor.execute("SELECT COUNT(*) FROM ratings").fetchone()[0]
print(f"\nTotal rows inserted: {count}")

# -------------------------------
# WITHOUT INDEX
# -------------------------------
print("\n--- Query Plan WITHOUT INDEX ---")
for row in cursor.execute("EXPLAIN QUERY PLAN SELECT * FROM ratings WHERE rating = 5"):
    print(row)

# -------------------------------
# CREATE INDEX (B-TREE)
# -------------------------------
cursor.execute("CREATE INDEX idx_rating ON ratings(rating)")

# -------------------------------
# WITH INDEX
# -------------------------------
print("\n--- Query Plan WITH INDEX ---")
for row in cursor.execute("EXPLAIN QUERY PLAN SELECT * FROM ratings WHERE rating = 5"):
    print(row)

conn.close()