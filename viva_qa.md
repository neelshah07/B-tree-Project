# Viva Questions and Answers

## Category 1: Design Choices

---

**Q: Why does SQLite use B-Tree instead of a hash table for storage?**

A: Hash tables provide O(1) average lookup but cannot support range queries. `WHERE age BETWEEN 18 AND 25` requires visiting all records with hash storage — O(n). SQLite's B+Tree maintains sorted order, so range queries traverse a leaf chain: O(log n) to find the start, then O(k) to read k results. Additionally, hash tables need rehashing when they grow — expensive and unpredictable. B-Trees grow gracefully by splitting pages, which fits the page-by-page storage model. SQLite is used heavily for things like contact lists and email history — both heavily range-queried — so B-Tree is the right choice.

---

**Q: Why 4096-byte pages? Why not 8192 or 512?**

A: 4096 bytes matches the OS virtual memory page size on both Linux and Windows. This alignment enables memory-mapped I/O (`mmap`) where reading a SQLite page requires no copy — the OS maps the same physical memory into the process's address space. Smaller pages (512B) increase tree height, requiring more disk reads per lookup. Larger pages (64KB) reduce height but increase write amplification — modifying 1 byte requires writing 64KB — and waste cache capacity. 4KB is the Goldilocks size. It's worth noting that MySQL/InnoDB uses 16KB pages optimized for server workloads with much larger buffer pools.

---

**Q: Why does balance_nonroot() look at 3 siblings instead of just splitting 1 page into 2?**

A: The textbook "split in half" produces two pages at 50% fill. This wastes space (50% empty) and causes frequent future splits. By redistributing across 3 siblings and targeting 67% fill, SQLite achieves two things: first, 33% better space utilization → fewer pages → lower tree height → fewer disk reads. Second, pages at 67% fill last 2× as long before the next split compared to 50% fill pages, reducing the frequency of the expensive rebalancing operation. The cost is complexity — `balance_nonroot()` is ~500 lines and reads/writes up to 4 pages per call.

---

**Q: What is WAL mode and why would you choose it?**

A: WAL (Write-Ahead Log) mode appends changed pages to a separate `.sqlite-wal` file instead of modifying the main database file in-place. This enables multiple simultaneous readers while a writer is active — impossible in rollback journal mode where the writer holds an exclusive lock. You'd choose WAL for applications with concurrent read access — like a mobile app where the UI thread reads while a background sync thread writes. The tradeoff is managing 3 files (`.sqlite`, `.sqlite-wal`, `.sqlite-shm`) and occasional checkpointing overhead. WAL also breaks on network filesystems (NFS) because it requires shared memory.

---

## Category 2: Code References

---

**Q: What function actually inserts a cell into a page? Walk me through it.**

A: `insertCell()` in `btree.c` around line 4000. It:
1. Finds the insertion point in the cell pointer array using `pCur->ix` (set by `MovetoUnpacked`)
2. Calls `allocateSpace(pPage, sz)` to carve space from the free area at the bottom of the page
3. Copies cell bytes to that space using `memcpy`
4. Shifts the cell pointer array right to make room at position i: `memmove(pIns+2, pIns, 2*(nCell-i))`
5. Writes the new cell's offset into the pointer array: `put2byte(pIns, idx)`
6. Calls `sqlite3PagerWrite()` to mark the page dirty

If `allocateSpace()` fails (no contiguous free block large enough), it first tries `defragmentPage()` to coalesce fragmented free space, then retries. If that also fails, the page is marked as overflowed, and `balance()` is called by the caller.

---

**Q: Where is the branching factor determined? Can you change it?**

A: The branching factor is not set as a constant — it emerges from `page_size / avg_cell_size`. The page size is set via `PRAGMA page_size = N` before the database is created and stored in the file header at offset 16. The cell size is determined by the actual data being stored. You can't change page size after creation without dumping and reloading. Indirectly, you can increase branching factor by: (a) using integer primary keys (varint-encoded, 1-9 bytes) instead of text UUIDs (variable but often 36 bytes), or (b) using larger page sizes. The relevant code is in `btree.c`'s `btreeCellSize()` and `btreePayloadToLocal()` functions.

---

**Q: What is a BtCursor and what does it track?**

A: `BtCursor` (`btree.h`) is the traversal state for a single query operation. It tracks:
- `pBt`: pointer to the shared BTree structure (the actual file)
- `pPage`: the current page being examined
- `ix`: index of the current cell within `pPage`
- `apPage[]` / `aiIdx[]`: ancestor stack (parent pages and their child indices), used to walk UP the tree during rebalancing
- `curFlags`: write/read mode, whether positioned, etc.
- `info`: cached info about the current cell (key, payload size, overflow)

Multiple cursors can exist simultaneously on the same B-Tree (for joins, triggers, etc.). Each cursor has its own position. This is why SQLite can handle `SELECT` inside a trigger while an `INSERT` is in progress — they use separate cursors.

---

## Category 3: Tradeoffs

---

**Q: What's the worst-case performance for INSERT in SQLite?**

A: The worst case is when every single INSERT triggers a full chain of splits up the tree. This happens with adversarial key patterns (e.g., inserting in exactly reverse sorted order into a B-Tree with no redistribution). In SQLite:
1. Each split calls `balance_nonroot()` — O(1) pages written per level
2. This propagates up tree_height levels
3. Tree height = O(log n)
4. So worst-case INSERT is O(log n) pages written

Each page write involves `sqlite3PagerWrite()` marking it dirty and `fsync()` on commit. With `synchronous=FULL`, each INSERT that triggers a split can cause multiple `fsync()` calls — the real bottleneck on HDDs. This is why SQLite recommends batching inserts inside transactions: the fsync cost amortizes across all inserts in the transaction.

---

**Q: SQLite's documentation says it handles databases up to 281 TB. But you said 8TB. Why the discrepancy?**

A: Good catch — it depends on page size. SQLite stores page numbers as 32-bit integers, giving a maximum of 2^32 - 2 ≈ 4 billion pages. With the default 4KB page size: 4 billion × 4KB = 16TB theoretical maximum. With 65536B (64KB) pages: 4 billion × 64KB = 256TB. The "281 TB" figure is with maximum page size (65536 bytes). The "8TB" I stated was conservative assuming a 2GB max from an older limit. The actual architectural limit is 281TB at maximum page size. However, at this scale SQLite's single-writer model would be a serious bottleneck long before you hit the storage limit.

---

**Q: How does SQLite handle the case where two processes try to write simultaneously?**

A: SQLite uses **POSIX advisory file locks** (5 levels: UNLOCKED, SHARED, RESERVED, PENDING, EXCLUSIVE). The write sequence is:
1. Writer acquires RESERVED lock (signals intent to write; readers can still read)
2. Writer accumulates changes in memory (dirty pages in pager cache)
3. Writer upgrades to PENDING lock (new readers blocked, existing readers finish)
4. Writer acquires EXCLUSIVE lock (all readers gone)
5. Writer flushes dirty pages to journal/WAL
6. Writer commits

In WAL mode, step 4 is replaced by writing to the WAL file — readers never need to wait because they can read from the WAL overlay. The lock upgrade is managed in `pager.c`, `sqlite3PagerBegin()` and `sqlite3PagerExclusiveLock()`.

---

## Category 4: Alternatives and Improvements

---

**Q: If you were designing SQLite today, what would you change?**

A: Three things:
1. **Adaptive page size:** Choose page size based on row size at table creation time. Small rows (key-value) → 512B pages for better memory efficiency. Large rows (documents) → 8KB pages for fewer overflow chains.
2. **Concurrent writers via MVCC:** SQLite's single-writer model is the main real-world bottleneck. A log-structured approach with multi-version concurrency (like what PostgreSQL does) would enable concurrent writes at the cost of compaction overhead.
3. **Native columnar pages for analytics:** SQLite is increasingly used for analytics (via DuckDB-style extensions). Adding a columnar page type where each "column" is stored as a separate B-Tree leaf chain would allow predicate pushdown and column pruning — huge gains for `SELECT SUM(x) FROM t WHERE y > 5` type queries.

---

**Q: When would you NOT use SQLite and why?**

A: Four scenarios:
1. **High write concurrency:** >100 writes/second from multiple threads/processes → single-writer WAL becomes a bottleneck → use PostgreSQL
2. **Write-dominant workloads with no reads:** Logging, event ingestion → LSM-Tree (RocksDB) is 10-100× faster for sequential writes
3. **Data larger than available disk on one machine:** SQLite is single-file, single-machine → need distributed storage (Cassandra, CockroachDB)
4. **Network-accessible multi-user database:** SQLite is not designed to be a server. Concurrent access over NFS is unreliable. Use a client-server database.

The official SQLite documentation says: "SQLite is not a replacement for Oracle. It is a replacement for fopen()." This is the right mental model.

---

**Q: What's the relationship between SQLite's B-Tree and the indexes you create with CREATE INDEX?**

A: They're two separate B-Trees, both implemented by the same code in `btree.c`. When you do `CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)`:
- SQLite creates a **table B+Tree** rooted at some page N. The key is `id` (rowid), and the data is the full row.

When you do `CREATE INDEX idx_name ON t(name)`:
- SQLite creates a **separate index B-Tree** rooted at page M. Each cell stores `(name, rowid)`.
- Lookup by name: search index B-Tree for `name` → get `rowid` → search table B+Tree for `rowid` (two tree traversals)

A **covering index** avoids the second traversal: `CREATE INDEX idx ON t(name, id)` includes all columns needed by `SELECT id FROM t WHERE name = 'Alice'` — the index B-Tree already has `id`, no need to look up the table B+Tree.

The relevant distinction in `btree.c` is the `intKey` flag in `BtShared` — table B-Trees use integer keys (rowids), index B-Trees use arbitrary byte-string keys.
