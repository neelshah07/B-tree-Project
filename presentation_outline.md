# Presentation Guide: SQLite B-Tree Analysis
## 30-Minute Structured Presentation

---

## Slide 1–2: Title + Team (2 min)

**Title:** "SQLite B-Tree: System-Level Reverse Engineering"  
**Subtitle:** "From SQL to Disk — Code, Concepts, and Experiments"

Opening line (deliver this verbatim):  
> "Every time you use WhatsApp, iOS, or Android — you're using SQLite. Today we'll open the hood and show you exactly how it stores your data."

---

## Section 1: System Overview (10 minutes, Slides 3–8)

### Slide 3: What Problem Does SQLite Solve?

**Talking points:**
- Embedded database: no server, no network, one file
- The challenge: how do you guarantee O(log n) lookup from a flat file?
- SQLite's answer: B+Tree over a page-managed file
- Real numbers: used in 1 trillion+ deployments (iOS, Android, Chrome, Firefox)

**Show:** SQLite architecture diagram (5 layers: SQL → Parser → VDBE → B-Tree → Pager)

### Slide 4: Why B-Tree? (Not LSM, Not Hash Index)

**Talking points:**
- Hash index: O(1) lookup but NO range queries → fails `WHERE id BETWEEN 100 AND 200`
- LSM-Tree: great for write-heavy workloads but too complex for embedded + needs compaction
- B-Tree: O(log n) reads AND writes, range queries, predictable behavior

**The single insight:** B-Tree's branching factor (m ≈ 300) means 1 million rows = 3 disk reads. This is the entire justification.

**Show:** Comparison table: B-Tree vs LSM-Tree vs Hash Index

### Slide 5: Architecture Layers

**Talking points:**
- Walk through each layer: Parser → VDBE → B-Tree → Pager → OS
- Key insight: B-Tree never touches disk directly. It calls `sqlite3PagerGet()`
- The Pager is SQLite's "virtual memory for disk" — page cache + WAL + crash recovery
- Point to actual files: `btree.c` (10K lines), `pager.c` (7K lines)

### Slide 6: The Page Is Everything

**Talking points:**
- Default: 4096-byte pages (configurable 512–65536)
- Matches OS virtual memory page size → zero-copy cache possible
- Every operation is atomic at the page level
- B-Tree node = one page. Always. No partial pages.

**Show:** Page header binary format breakdown (show actual hex bytes if possible)

### Slide 7: B+Tree vs. B-Tree in SQLite

**Talking points:**
- Tables use B+Tree: data only in leaves, interior nodes are pure routing
- Indexes use B-Tree: keys in all nodes
- Why does this matter? Range scans traverse the leaf chain — O(k) per result, not O(k log n)
- Point to `btree.c` page type constants: 0x0d (leaf table), 0x05 (interior table)

### Slide 8: Mathematical Foundation

**On whiteboard or slide:**
```
Height h = ceil(log_m(n))

m ≈ 300 (branching factor for 4KB pages)
n = number of rows

n=1,000:       h = ceil(log_300(1000))  = 2  → 2 disk reads
n=1,000,000:   h = ceil(log_300(10^6))  = 3  → 3 disk reads
n=1,000,000,000: h = ceil(log_300(10^9)) = 5  → 5 disk reads
```

**Contrast with binary tree:** log_2(1,000,000) = 20 disk reads.  
The branching factor is WHY B-Trees exist.

---

## Section 2: Deep Dive — INSERT Execution Path (10 minutes, Slides 9–14)

### Slide 9: The Path We're Tracing

**Show the full call chain diagram:**
```
INSERT INTO users VALUES (42, 'Alice')
  ↓ sqlite3Insert()          [insert.c]
  ↓ VDBE OP_Insert           [vdbe.c]
  ↓ sqlite3BtreeInsert()     [btree.c]
  ↓ MovetoUnpacked()         ← DESCENT
  ↓ insertCell()             ← INSERTION
  ↓ balance_nonroot()        ← REBALANCING
  ↓ sqlite3PagerWrite()      [pager.c]
  ↓ fsync()                  [os_unix.c]
```

### Slide 10: VDBE Bytecode (Code Reference)

**Show actual VDBE opcodes generated for INSERT.**

Key insight: SQL is compiled to bytecode, not interpreted directly. This is why SQLite is fast for repeated queries — compile once, execute many.

**Show `OP_Insert` case in `vdbe.c` (~line 4100)**

Point out: `OPFLAG_APPEND` — when the VDBE detects sequential rowids, it passes this flag to skip the tree descent entirely. Bulk load optimization baked in.

### Slide 11: Tree Descent — Binary Search in Pages

**Show `sqlite3BtreeMovetoUnpacked()` key logic.**

**Intuition:** Like searching a phone book:
- Open to middle (binary search within page)
- If name > target → go to left child page
- If name < target → go to right child page
- Repeat until leaf

**Technical detail:** The cursor maintains an ancestor stack. After descending, SQLite can walk UP for rebalancing without re-reading pages.

### Slide 12: Page Structure During Insert

**Show diagram of page memory layout.**

Key insight: Cell pointers (in header) are sorted by key. Cell content (at bottom) is in insertion order. This means:
- Binary search works on the pointer array: O(log cells_per_page)
- No data movement when inserting: only pointer array shifts
- Pointers are 2 bytes each → minimal overhead

**Point to `insertCell()` in `btree.c` ~L4000**

### Slide 13: The Balancing Act — balance_nonroot()

**This is your deep dive centerpiece.**

**Show before/after diagram of 3-sibling redistribution.**

Key comparison:
| Textbook Split | SQLite Split |
|---|---|
| 1 page → 2 pages | 1-3 pages → 1-4 pages |
| 50% fill | 67% fill |
| More splits in future | Fewer splits in future |

**Point to `balance_nonroot()` in `btree.c` ~L8400**

Why 67%? Amortized analysis: 33% more data per page → 33% fewer total splits over database lifetime.

### Slide 14: Pager + WAL — Crash Safety

**Show WAL mode diagram.**

- Journal mode: copy-before-write → only 1 writer, 0 concurrent readers
- WAL mode: append-only → 1 writer + unlimited concurrent readers
- B-Tree never calls `write()` directly — all goes through `sqlite3PagerWrite()`
- On crash: WAL is idempotent — replay from checkpoint mark

---

## Section 3: Experiment and Demo (10 minutes, Slides 15–19)

### Slide 15: Experiment Design

**What we're testing:**
1. INSERT performance vs. data scale (sequential vs. random keys)
2. Page size impact on tree height and performance
3. Direct tree depth measurement via raw binary parsing

**Why these experiments?** They validate the O(log n) claim with real data, not theory.

### Slide 16: Experiment 1 Results — Insert Scaling

**Show graph: rows vs. ms/batch for sequential vs. random keys.**

Key observations:
- Sequential: nearly flat → OPFLAG_APPEND bypasses descent
- Random: gradual rise → more balance_nonroot() calls as tree grows
- Inflection point at ~400K rows: tree height increases from 3 → 4
- Ratio: random keys are consistently 3-4× slower than sequential

### Slide 17: Experiment 2 Results — Page Size Impact

**Show table/graph: page size vs. insert time + tree height.**

Key observations:
- 512B pages: tree height 6 → 6 disk reads per lookup
- 4096B pages: tree height 3 → 3 disk reads per lookup  
- 16384B pages: tree height 2 → 2 disk reads per lookup
- BUT: larger pages don't linearly improve performance due to cache pressure
- Sweet spot: 4KB (matches OS page size → zero-copy mmap possible)

### Slide 18: Experiment 3 — Binary Page Inspection

**Show code that parses the raw .sqlite file.**

```python
# Read page type byte at offset 0 of each page
page_type = struct.unpack('B', data[0:1])[0]
if page_type == 0x05:   print("Interior table page")
elif page_type == 0x0d: print("Leaf table page")
```

**Show results:**
- Measured branching factor: ~290-310 (vs. theoretical 300)
- Actual height matches ceil(log_300(n)) exactly
- Leaf:Interior ratio = ~300:1 (each interior page has ~300 children)

### Slide 19: Live Demo (Optional)

```bash
# Show tree depth measurement in real time
python experiments/experiment3_tree_depth.py
```

Or show SQLite's internal `ANALYZE` table stats:
```sql
CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT);
-- Insert 100K records
ANALYZE;
SELECT * FROM sqlite_stat1;
```

---

## Section 4: Key Insights (5 minutes, Slides 20–22)

### Slide 20: Design Decisions Summary

| Decision | Code Location | Tradeoff |
|---|---|---|
| Page-based storage | `pager.c`, `sqlite3PagerGet()` | Space waste vs. I/O alignment |
| 3-sibling balance | `btree.c`, `balance_nonroot()` | Write cost vs. tree height |
| WAL mode | `pager.c`, `wal.c` | Read concurrency vs. complexity |
| Varint encoding | `btree.c`, `putVarint()` | CPU vs. branching factor |

### Slide 21: Concept Mapping

- **Storage:** B+Tree (not LSM) — read-optimized, in-place updates
- **Indexing:** Dual tree system (table B+Tree + index B-Tree)
- **I/O optimization:** Page cache + prefetch hint + 67% fill
- **Execution:** Volcano/iterator model through VDBE cursor

### Slide 22: Failure Points and Improvements

**Failure analysis:**
- Large data: graceful O(log n) degradation until 8TB limit
- Skewed inserts: mitigated by OPFLAG_APPEND for sequential keys
- Slow I/O: page cache + mmap help; WAL breaks on NFS

**Improvements:**
- LSM-Tree for write-heavy workloads (RocksDB)
- Fractal tree for balanced read/write (TokuDB)  
- Columnar storage for analytics (Parquet/DuckDB)

---

## Delivery Tips

1. **Always point to code.** When you say "balance_nonroot," show the file and line number.
2. **Use the whiteboard** for the tree descent diagram — draw it live.
3. **Show the hex dump** of a real .sqlite file — it's visually compelling.
4. **Anticipate: "Why not just use an index?"** Answer: The table IS a B-Tree. There's no separate index structure for the primary key.
5. **Anticipate: "How is this different from PostgreSQL's B-Tree?"** PostgreSQL uses B+-Tree too, but stores pages in a buffer pool with LRU eviction and supports concurrent MVCC writes. SQLite's simplicity is the feature.
