import sqlite3
import csv
import time
import random

# Load dataset into memory
rows = []
with open("ratings.csv", "r") as f:
    reader = csv.reader(f)
    next(reader)
    for row in reader:
        rows.append((int(row[0]), int(row[1]), float(row[2]), int(row[3])))

# Limit size (important)
rows = rows[:50000]

# ---------------------------
# SEQUENTIAL INSERT
# ---------------------------
conn = sqlite3.connect("seq.db")
cursor = conn.cursor()

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

seq_time = time.time() - start
conn.close()

print(f"\nSequential Insert Time: {seq_time:.4f} seconds")


# ---------------------------
# RANDOM INSERT
# ---------------------------
random.shuffle(rows)

conn = sqlite3.connect("rand.db")
cursor = conn.cursor()

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

rand_time = time.time() - start
conn.close()

print(f"Random Insert Time: {rand_time:.4f} seconds")