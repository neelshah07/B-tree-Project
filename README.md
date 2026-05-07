# 🗄️ SQLite B-Tree Internals: System-Level Reverse Engineering & Analysis

> **Course:** DS614 – Big Data Engineering  
> **Topic:** SQLite Core Architecture (B-Trees & Page Caching)  
> **Approach:** Source Code Instrumentation → Empirical Benchmarking → System Design Analysis  

![SQLite](https://img.shields.io/badge/sqlite-%2307405e.svg?style=for-the-badge&logo=sqlite&logoColor=white)
![C](https://img.shields.io/badge/c-%2300599C.svg?style=for-the-badge&logo=c&logoColor=white)
![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)

---

## 🚀 Project Overview

SQLite is the most widely deployed database engine in the world, powering billions of mobile apps, browsers, and embedded systems. Its core challenge is deceptively complex: **how do you guarantee extremely fast $O(\log n)$ search and retrieval from a flat file on disk without background servers or massive memory overhead?**

The answer lies in its **B+Tree** architecture, managed by a highly optimized Page Cache (`pager.c`). 

This project reverse-engineers SQLite's storage layer. Instead of treating the database as a black box, we **instrumented the actual SQLite C source code (`sqlite3.c`)** to print live traces of memory allocation, page splitting, and tree traversals. We then validated these C-level mechanics using automated Python benchmarks and raw binary file inspection.

---

## 🛠️ Methodology: C-Level Instrumentation

To see exactly how the B-Tree behaves, we patched the SQLite amalgamation file (`sqlite3.c`) with custom `[DEBUG]` hooks inside three critical B-Tree operations:

1. **Tree Descent (`moveToChild`)**: Tracks how SQLite navigates from the root node down to the leaf nodes during a `SELECT` query.
2. **Page Splitting (`balance_nonroot`)**: Exposes SQLite's advanced 3-sibling redistribution algorithm, which optimizes page fills to 67% (rather than the textbook 50%) to prevent future fragmentation.
3. **Memory Allocation (`allocateSpace`)**: Tracks byte-level allocation inside 4KB pages when a new cell/row is inserted.

We then compiled this patched source code into a custom executable (`sqlite3_custom.exe`). Pumping SQL queries into this engine allows us to watch the B-Tree restructure itself in real-time.

---

## 📊 Python Benchmarks & Experiments

To complement the C-level tracing, we built three major empirical experiments using Python to validate the theoretical math behind B-Trees.

### 🧪 Experiment 1: Insert Performance vs. Data Scale
* **Goal**: Measure insertion speed degradation as the database scales.
* **Method**: Inserted 500,000 rows using Sequential Integer IDs vs. Random UUIDs.
* **Finding**: Sequential inserts are lightning-fast because SQLite uses an `OPFLAG_APPEND` optimization to bypass tree descent. Random inserts are 3-4x slower because they constantly trigger expensive `balance_nonroot` page splits and tree restructuring.

### 🧪 Experiment 2: Page Size Impact
* **Goal**: Evaluate how changing the database page size (512B to 64KB) affects tree height and I/O speed.
* **Finding**: Smaller pages (512B) result in tall trees (6 levels deep) and high disk read costs. Larger pages (64KB) flatten the tree but cause write-amplification and waste cache. **4096 Bytes (4KB)** emerged as the perfect "Goldilocks" size because it matches OS virtual memory pages, enabling zero-copy caching.

### 🧪 Experiment 3: Raw Binary Page Inspection
* **Goal**: Prove the $O(\log n)$ height mathematically by reading the raw `.sqlite` file byte-by-byte.
* **Method**: Parsed binary headers to count the exact number of interior routing pages vs. leaf data pages.
* **Finding**: The measured branching factor is ~300. We mathematically verified that a table with 1,000,000 rows has a tree height of exactly $\lceil \log_{300}(1,000,000) \rceil \approx 3$. **Finding any row out of a million requires a maximum of 3 disk reads.**

---

## 🧠 Why B-Tree? (And Not LSM-Tree or Hash)

| Storage Engine | Average Read | Average Write | Range Queries (`BETWEEN`) | Best For |
|---|---|---|---|---|
| **B-Tree (SQLite)** | $O(\log n)$ | $O(\log n)$ | **Extremely Fast** | Read-heavy, Embedded, ACID |
| **LSM-Tree (RocksDB)**| $O(\log n)$* | $O(1)$ | Slower (Multiple SSTs) | Write-heavy, Server-side |
| **Hash Index** | $O(1)$ | $O(1)$ | **Impossible** | Key-Value Lookups Only |

SQLite utilizes **B+Trees for Tables** (data stored exclusively in leaf nodes) and **B-Trees for Indexes** (keys in all nodes). This enables $O(1)$ sequential range scans across the linked leaf chain, which is essential for relational queries.

---

## ⚙️ How to Build and Run

### 1. Compile the Custom SQLite Engine
*Requires GCC or MSVC.*
```bash
./build_sqlite.bat
```
*(This produces `sqlite3_custom.exe` and `sqlite3_custom.dll` with our B-Tree tracing enabled).*

### 2. Run the Real-Time B-Tree Trace
Watch the C-level B-Tree traverse and split in real-time:
```bash
python experiment4_btree_tracing.py
```

### 3. Run the Empirical Benchmarks
Generate performance data and raw binary tree depth metrics:
```bash
python experiment1_insert_scale.py
python experiment2_page_size.py
python experiment3_tree_depth.py
```

---

## 📂 Repository Structure

```text
├── sqlite-src/                   # Forked SQLite C Source Code
│   ├── sqlite3.c                 # Patched with B-Tree Tracing
├── experiments/
│   ├── experiment1_insert_scale.py  # Benchmark: Sequential vs Random
│   ├── experiment2_page_size.py     # Benchmark: 512B vs 64KB Pages
│   ├── experiment3_tree_depth.py    # Binary parser for Tree Height
│   ├── experiment4_btree_tracing.py # Real-time custom engine runner
├── results/                      # Output CSVs for graphing
├── patch_script.py               # Script used to inject printf hooks
├── full_report.md                # Comprehensive Project Report
```

---
*Built as a final project for Big Data Engineering. Showcasing the bridge between theoretical data structures and production-grade systems programming.*
