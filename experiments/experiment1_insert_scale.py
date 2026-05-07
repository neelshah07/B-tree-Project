"""
Experiment 1: INSERT Performance vs. Data Scale
================================================
Tests how insert time per batch changes as the table grows.
Two conditions: sequential integers vs. random text keys.

Run: python experiment1_insert_scale.py
"""

import sqlite3
import time
import random
import string
import os
import tempfile

BATCH_SIZE = 10_000
TOTAL_RECORDS = 500_000
BATCHES = TOTAL_RECORDS // BATCH_SIZE


def random_string(length=16):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def run_sequential_experiment(db_path):
    """Sequential integer primary keys — best case for SQLite B-Tree."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")

    results = []
    rowid = 1
    for batch_num in range(BATCHES):
        rows = [(rowid + i, random_string()) for i in range(BATCH_SIZE)]
        rowid += BATCH_SIZE

        start = time.perf_counter()
        conn.executemany("INSERT INTO t VALUES (?, ?)", rows)
        conn.commit()
        elapsed_ms = (time.perf_counter() - start) * 1000

        total_rows = (batch_num + 1) * BATCH_SIZE
        results.append((total_rows, elapsed_ms))
        print(f"  Sequential | {total_rows:>7,} rows | {elapsed_ms:>7.1f} ms/batch | "
              f"{elapsed_ms / BATCH_SIZE * 1000:.2f} µs/row")

    conn.close()
    return results


def run_random_experiment(db_path):
    """Random UUID-like text keys — stress case for B-Tree balancing."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("CREATE TABLE t (id TEXT PRIMARY KEY, val TEXT)")

    results = []
    for batch_num in range(BATCHES):
        rows = [(random_string(32), random_string()) for _ in range(BATCH_SIZE)]

        start = time.perf_counter()
        try:
            conn.executemany("INSERT OR IGNORE INTO t VALUES (?, ?)", rows)
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()

        elapsed_ms = (time.perf_counter() - start) * 1000
        total_rows = (batch_num + 1) * BATCH_SIZE
        results.append((total_rows, elapsed_ms))
        print(f"  Random     | {total_rows:>7,} rows | {elapsed_ms:>7.1f} ms/batch | "
              f"{elapsed_ms / BATCH_SIZE * 1000:.2f} µs/row")

    conn.close()
    return results


def get_tree_stats(db_path):
    """Read page stats from the database."""
    conn = sqlite3.connect(db_path)
    page_count = conn.execute("PRAGMA page_count").fetchone()[0]
    page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    leaf_pages = conn.execute(
        "SELECT count(*) FROM sqlite_stat1"
    ).fetchone()
    conn.close()
    return page_count, page_size


def analyze_page_types(db_path):
    """
    Read the raw SQLite file and count interior vs. leaf pages.
    Page type is stored at offset 0 of each page.
    - 0x05 = interior table btree page
    - 0x0d = leaf table btree page
    """
    import struct
    interior, leaf, other = 0, 0, 0

    with open(db_path, 'rb') as f:
        # Page size is at bytes 16-17 of the 100-byte file header
        header = f.read(100)
        page_size = struct.unpack('>H', header[16:18])[0]
        if page_size == 1:
            page_size = 65536  # SQLite encodes 65536 as 1

        f.seek(0, 2)
        file_size = f.tell()
        total_pages = file_size // page_size

        for i in range(total_pages):
            # Page 1 has a 100-byte file header before page data
            offset = i * page_size + (100 if i == 0 else 0)
            f.seek(offset)
            byte = f.read(1)
            if not byte:
                break
            page_type = struct.unpack('B', byte)[0]
            if page_type in (0x02, 0x05):   # interior index/table
                interior += 1
            elif page_type in (0x0a, 0x0d): # leaf index/table
                leaf += 1
            else:
                other += 1

    return interior, leaf, other, total_pages


def main():
    print("=" * 70)
    print("EXPERIMENT 1: INSERT PERFORMANCE vs. DATA SCALE")
    print("=" * 70)

    tmpdir = tempfile.mkdtemp()
    seq_db = os.path.join(tmpdir, "sequential.db")
    rnd_db = os.path.join(tmpdir, "random.db")

    print(f"\n[1/2] Sequential integer keys (best case)")
    print("-" * 50)
    seq_results = run_sequential_experiment(seq_db)

    print(f"\n[2/2] Random text keys (stress case)")
    print("-" * 50)
    rnd_results = run_random_experiment(rnd_db)

    print("\n" + "=" * 70)
    print("PAGE STRUCTURE ANALYSIS (Sequential DB)")
    print("=" * 70)
    interior, leaf, other, total = analyze_page_types(seq_db)
    print(f"Total pages    : {total:,}")
    print(f"Interior pages : {interior:,}  (routing nodes)")
    print(f"Leaf pages     : {leaf:,}  (data nodes)")
    print(f"Other pages    : {other:,}  (freelist, overflow, etc.)")
    if interior > 0:
        print(f"Leaf:Interior ratio: {leaf/interior:.0f}:1")
        import math
        est_height = math.ceil(math.log(total) / math.log(max(leaf/interior, 2)))
        print(f"Estimated tree height: {est_height}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"{'Rows':>10}  {'Seq (ms)':>12}  {'Rand (ms)':>12}  {'Ratio':>8}")
    print("-" * 50)
    for (rows, seq_t), (_, rnd_t) in zip(seq_results[::5], rnd_results[::5]):
        ratio = rnd_t / seq_t if seq_t > 0 else 0
        print(f"{rows:>10,}  {seq_t:>12.1f}  {rnd_t:>12.1f}  {ratio:>8.2f}x")

    # Save CSV for graphing
    results_path = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(results_path, exist_ok=True)
    with open(os.path.join(results_path, "experiment1.csv"), "w") as f:
        f.write("rows,sequential_ms,random_ms\n")
        for (rows, seq_t), (_, rnd_t) in zip(seq_results, rnd_results):
            f.write(f"{rows},{seq_t:.2f},{rnd_t:.2f}\n")
    print(f"\nResults saved to experiments/results/experiment1.csv")

    # Cleanup
    for db in [seq_db, rnd_db]:
        for ext in ['', '-wal', '-shm']:
            try:
                os.remove(db + ext)
            except FileNotFoundError:
                pass
    os.rmdir(tmpdir)


if __name__ == "__main__":
    main()
