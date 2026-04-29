import sqlite3
import csv
import time
import os

PAGE_SIZES = [1024, 4096, 8192]
RECORD_LIMIT = 20000

# Load dataset
rows = []
with open("ratings.csv", "r") as f:
    reader = csv.reader(f)
    next(reader)
    for i, row in enumerate(reader):
        if i >= RECORD_LIMIT:
            break
        rows.append((int(row[0]), int(row[1]), float(row[2]), int(row[3])))

results = []

for ps in PAGE_SIZES:
    db_name = f"ps_{ps}.db"

    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Set page size BEFORE table creation
    cursor.execute(f"PRAGMA page_size = {ps}")

    cursor.execute("DROP TABLE IF EXISTS ratings")

    cursor.execute("""
    CREATE TABLE ratings (
        userId INTEGER,
        movieId INTEGER,
        rating REAL,
        timestamp INTEGER
    )
    """)

    start = time.time()

    cursor.executemany("INSERT INTO ratings VALUES (?, ?, ?, ?)", rows)
    conn.commit()

    elapsed = time.time() - start

    # Get page info
    page_count = cursor.execute("PRAGMA page_count").fetchone()[0]
    page_size = cursor.execute("PRAGMA page_size").fetchone()[0]

    conn.close()

    file_size = os.path.getsize(db_name) / 1024  # KB

    results.append((ps, elapsed, file_size, page_count))

    print(f"\nPage Size: {ps}")
    print(f"Time: {elapsed:.4f} sec")
    print(f"File Size: {file_size:.2f} KB")
    print(f"Pages: {page_count}")

print("\n--- SUMMARY ---")
for r in results:
    print(f"PageSize={r[0]}, Time={r[1]:.3f}s, Size={r[2]:.1f}KB, Pages={r[3]}")