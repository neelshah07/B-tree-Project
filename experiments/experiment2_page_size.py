"""
Experiment 2: Page Size Impact on Tree Height and Performance
=============================================================
Tests how different page sizes affect:
  - Insert performance
  - File size (storage efficiency)
  - Estimated tree height (via page structure analysis)

NOTE: page_size must be set BEFORE any table is created.
      Changing it after the fact has no effect.

Run: python experiment2_page_size.py
"""

import sqlite3
import time
import os
import tempfile
import struct
import math

RECORD_COUNT = 100_000
PAGE_SIZES = [512, 1024, 2048, 4096, 8192, 16384, 32768, 65536]


def create_and_fill(db_path, page_size, n_records):
    """Create a fresh database with the given page size and insert n_records."""
    conn = sqlite3.connect(db_path)
    conn.execute(f"PRAGMA page_size = {page_size}")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")  # Speed up experiment
    conn.execute("""
        CREATE TABLE records (
            id   INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            data TEXT NOT NULL
        )
    """)

    # Batch insert
    BATCH = 5000
    rows = [(i, f"user_{i}", "x" * 50) for i in range(n_records)]
    start = time.perf_counter()
    for i in range(0, n_records, BATCH):
        conn.executemany("INSERT INTO records VALUES (?,?,?)", rows[i:i+BATCH])
        conn.commit()
    elapsed = time.perf_counter() - start
    conn.close()
    return elapsed


def analyze_page_types(db_path):
    """Parse raw file to count interior/leaf pages."""
    interior, leaf = 0, 0
    with open(db_path, 'rb') as f:
        header = f.read(100)
        ps = struct.unpack('>H', header[16:18])[0]
        if ps == 1:
            ps = 65536
        f.seek(0, 2)
        total = f.tell() // ps
        for i in range(total):
            f.seek(i * ps + (100 if i == 0 else 0))
            b = f.read(1)
            if not b:
                break
            t = struct.unpack('B', b)[0]
            if t in (0x02, 0x05):
                interior += 1
            elif t in (0x0a, 0x0d):
                leaf += 1
    return interior, leaf, total, ps


def estimate_height(interior, leaf, branching_factor):
    """Estimate tree height from page counts."""
    if interior == 0:
        return 1  # root is a leaf
    # approx: interior pages ≈ (branching^(h-1) - 1) / (branching - 1)
    # but simpler: height ≈ log_branching(leaf_count)
    return math.ceil(math.log(max(leaf, 1)) / math.log(max(branching_factor, 2)))


def main():
    print("=" * 75)
    print("EXPERIMENT 2: PAGE SIZE IMPACT ON PERFORMANCE AND TREE HEIGHT")
    print("=" * 75)
    print(f"Inserting {RECORD_COUNT:,} records per page size configuration\n")

    tmpdir = tempfile.mkdtemp()
    results = []

    for ps in PAGE_SIZES:
        db_path = os.path.join(tmpdir, f"db_{ps}.sqlite")
        elapsed = create_and_fill(db_path, ps, RECORD_COUNT)
        file_size = os.path.getsize(db_path)
        interior, leaf, total, actual_ps = analyze_page_types(db_path)
        branching = leaf / interior if interior > 0 else leaf
        height = estimate_height(interior, leaf, branching)

        results.append({
            'page_size': ps,
            'elapsed': elapsed,
            'file_size_kb': file_size / 1024,
            'interior': interior,
            'leaf': leaf,
            'total_pages': total,
            'height': height,
            'branching': branching
        })

        marker = " ← default" if ps == 4096 else ""
        print(f"Page size {ps:>6} B | {elapsed:5.2f}s | "
              f"{file_size/1024:>8.0f} KB | "
              f"pages={total:>5} (int={interior}, leaf={leaf}) | "
              f"est_h={height}{marker}")

        # Cleanup
        for ext in ['', '-wal', '-shm']:
            try:
                os.remove(db_path + ext)
            except FileNotFoundError:
                pass

    os.rmdir(tmpdir)

    # Save CSV
    results_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(results_dir, exist_ok=True)
    csv_path = os.path.join(results_dir, "experiment2.csv")
    with open(csv_path, "w") as f:
        f.write("page_size,elapsed_s,file_size_kb,interior_pages,leaf_pages,total_pages,est_height,branching_factor\n")
        for r in results:
            f.write(f"{r['page_size']},{r['elapsed']:.4f},{r['file_size_kb']:.1f},"
                    f"{r['interior']},{r['leaf']},{r['total_pages']},{r['height']},{r['branching']:.1f}\n")

    print(f"\nResults saved to experiments/results/experiment2.csv")

    print("\n" + "=" * 75)
    print("KEY OBSERVATIONS")
    print("=" * 75)
    baseline = results[PAGE_SIZES.index(4096)]
    for r in results:
        speedup = baseline['elapsed'] / r['elapsed'] if r['elapsed'] > 0 else 0
        size_ratio = r['file_size_kb'] / baseline['file_size_kb']
        print(f"  {r['page_size']:>6}B: height={r['height']}, "
              f"speedup vs 4KB={speedup:.2f}x, "
              f"size vs 4KB={size_ratio:.2f}x")

    print("""
Analysis:
  - Larger pages → lower tree height → fewer disk reads per lookup
  - But: larger pages = more wasted space per page (internal fragmentation)
  - And: larger pages = higher cost on cache miss (more bytes to fetch)
  - 4096 bytes is optimal because it matches OS virtual memory page size:
    the OS can satisfy a pager read with a single TLB entry
  - For write-heavy workloads: prefer smaller pages (less write amplification)
  - For read-heavy analytical workloads: prefer larger pages (fewer I/Os per scan)
""")


if __name__ == "__main__":
    main()
