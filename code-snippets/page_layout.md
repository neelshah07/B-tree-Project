# SQLite Page Layout: Binary Format Reference

## File Header (Page 1 only, bytes 0–99)

```
Offset  Size  Description                          Value
------  ----  -----------                          -----
0       16    Magic string                         "SQLite format 3\000"
16      2     Page size (bytes)                    512–65536 (or 1 = 65536)
18      1     File format write version            1=journal, 2=WAL
19      1     File format read version             1=journal, 2=WAL
20      1     Reserved space per page              Usually 0
21      1     Max embedded payload fraction        Must be 64
22      1     Min embedded payload fraction        Must be 32
23      1     Leaf payload fraction                Must be 32
24      4     File change counter                  Increments on each write
28      4     Total page count                     0 = unknown
32      4     First trunk page of freelist         0 = no freelist
36      4     Total freelist pages                 
40      4     Schema cookie                        Increments on schema changes
44      4     Schema format number                 1-4
48      4     Default page cache size              
52      4     Largest root B-tree page (autovac)   
56      4     Text encoding                        1=UTF8, 2=UTF16le, 3=UTF16be
60      4     User version                         Set by PRAGMA user_version
64      4     Incremental vacuum mode              
68      4     Application ID                       Set by PRAGMA application_id
72      20    Reserved for expansion               All zeros
92      4     Version-valid-for number             
96      4     SQLite version number                e.g., 3045000 = 3.45.0
```

## B-Tree Page Header

Every page (after the file header if page 1) begins with:

### Leaf Page Header (8 bytes)

```
Offset  Size  Description
------  ----  -----------
0       1     Page type:
               0x0d = leaf table B-tree page
               0x0a = leaf index B-tree page
1       2     Byte offset of first freeblock (0 = none)
3       2     Number of cells on page
5       2     Byte offset of start of cell content area
7       1     Number of fragmented free bytes
```

### Interior Page Header (12 bytes = leaf header + 4 more)

```
0-7     8     Same as leaf header (type is 0x05 or 0x02)
8       4     Page number of rightmost child
```

## Cell Pointer Array

Immediately follows the page header:

```
[2 bytes: offset to cell_0] [2 bytes: offset to cell_1] ... [2 bytes: offset to cell_N-1]
```

Cell pointers are 2-byte big-endian integers, pointing into the cell content area. They are stored **in sorted key order** — not in physical order. This allows binary search without moving cell content.

## Cell Content Area

Cells are stored at the **bottom** of the page, growing upward. The header tracks `cell content area start` — below this offset, the page is fully used by cells.

### Table Leaf Cell (page type 0x0d)

```
[varint: total payload length]
[varint: rowid]
[payload bytes...]
[4-byte overflow page number]  ← only if payload overflows
```

### Table Interior Cell (page type 0x05)

```
[4-byte left child page number]
[varint: integer key (rowid)]
```

### Index Leaf Cell (page type 0x0a)

```
[varint: total payload length]
[payload: serialized index key + rowid]
[4-byte overflow page number]  ← only if payload overflows
```

### Index Interior Cell (page type 0x02)

```
[4-byte left child page number]
[varint: total payload length]
[payload: serialized key]
[4-byte overflow page number]  ← only if payload overflows
```

## Freeblock Structure

When a cell is deleted, its space becomes a freeblock. Freeblocks form a linked list:

```
[2-byte: offset of next freeblock (0 = end of list)]
[2-byte: size of this freeblock including header]
[remaining bytes: available for new cell content]
```

SQLite coalesces adjacent freeblocks and defragments a page when needed (function `defragmentPage()` in btree.c).

## Page Capacity Formula

```python
# For a table leaf page inserting rows with:
#   rowid: up to 9 bytes (varint)
#   payload: P bytes

def page_capacity(page_size, avg_rowid_varint=2, avg_payload=50):
    usable = page_size - 0  # no reserved space in default config
    header = 8              # leaf page header
    cell_ptr = 2            # 2 bytes per cell in pointer array
    
    # Minimum cell size: varint(payload_len) + varint(rowid) + payload
    avg_cell = 1 + avg_rowid_varint + avg_payload  # ~53 bytes
    
    # Each cell also consumes 2 bytes in pointer array
    capacity = (usable - header) // (avg_cell + cell_ptr)
    return capacity

print(page_capacity(4096))   # → ~70 rows per leaf page
print(page_capacity(16384))  # → ~287 rows per leaf page
```

## Visual: Page Memory Layout (4KB page)

```
Byte 0
┌─────────────────────────────────────────────────────────────┐
│ Page Header (8 or 12 bytes)                                 │
├─────────────────────────────────────────────────────────────┤
│ Cell Pointer Array                                          │
│ [ptr_0=3800][ptr_1=3740][ptr_2=3680] ...                   │
│ ↓ grows downward                                            │
├ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┤
│                                                             │
│                  FREE SPACE                                 │
│                                                             │
├ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┤
│ ↑ grows upward                                              │
│ Cell 2: [payload_len varint][rowid varint][data...]         │ ← offset 3680
│ Cell 1: [payload_len varint][rowid varint][data...]         │ ← offset 3740
│ Cell 0: [payload_len varint][rowid varint][data...]         │ ← offset 3800
└─────────────────────────────────────────────────────────────┘
Byte 4095
```

Cell pointers (in header) are sorted by key → binary search is O(log cells_per_page).
Cell content (at bottom) is in physical insertion order → no movement needed on insert.
