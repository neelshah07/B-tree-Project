# Annotated INSERT Execution Trace

## Overview

This document traces the exact function call chain for:
```sql
INSERT INTO users (id, name) VALUES (42, 'Alice');
```

All line numbers reference SQLite 3.45.x source.

---

## Call Chain

```
sqlite3Insert()                                [insert.c ~L350]
  └─ sqlite3CodeInsert()                       [insert.c ~L800]
       └─ VDBE generates OP_Insert opcode
            └─ vdbeExec() dispatches case OP_Insert [vdbe.c ~L4100]
                 └─ sqlite3BtreeInsert()        [btree.c ~L9200]
                      ├─ sqlite3BtreeMovetoUnpacked()  [btree.c ~L8100]
                      │    └─ moveToChild()     [btree.c ~L4600]  × height
                      ├─ insertCell()           [btree.c ~L4000]
                      │    └─ sqlite3PagerWrite()  [pager.c ~L1800]
                      └─ balance()              [btree.c ~L9100]
                           └─ balance_nonroot() [btree.c ~L8400]
```

---

## Function Annotations

### `sqlite3Insert()` — insert.c ~L350

Entry point for the code generator. Handles:
- Determining the target table from AST
- Resolving column list
- Generating VDBE opcodes

Key opcodes emitted for `INSERT INTO users VALUES (42, 'Alice')`:
```
OP_Transaction  0, 1             -- begin write transaction
OP_OpenWrite    0, 2, 2          -- open cursor 0 on table root page 2
OP_Integer      42, 1            -- reg[1] = 42
OP_String8      0, 2, 0, "Alice" -- reg[2] = "Alice"  
OP_MakeRecord   1, 2, 3          -- reg[3] = packed record of reg[1..2]
OP_NewRowid     0, 4, 0          -- reg[4] = new rowid (or use rowid=42)
OP_Insert       0, 3, 4, "users" -- INSERT reg[3] with key reg[4]
OP_Halt         0, 0, 0
```

---

### `OP_Insert` handler — vdbe.c ~L4100

```c
case OP_Insert: {
  Mem *pData = &aMem[pOp->p2];   // data record
  Mem *pKey  = &aMem[pOp->p3];   // rowid
  VdbeCursor *pC = p->apCsr[pOp->p1]; // cursor 0
  
  // Mark table as changed (for triggers etc.)
  if( pOp->p4.z ) db->xUpdateCallback(db, SQLITE_INSERT, ...);
  
  // Critical: OPFLAG_APPEND tells btree to skip search on sequential inserts
  rc = sqlite3BtreeInsert(pC->uc.pCursor, &x,
    (pOp->p5 & (OPFLAG_APPEND|OPFLAG_SAVEPOSITION)),
    seekResult
  );
  break;
}
```

**Note:** `OPFLAG_APPEND` is set when the query planner detects monotonically increasing rowids (e.g., from a SELECT with ORDER BY rowid). This bypasses the binary search descent, making bulk loads ~5× faster.

---

### `sqlite3BtreeInsert()` — btree.c ~L9200

```c
int sqlite3BtreeInsert(
  BtCursor *pCur,          // positioned cursor
  const BtreePayload *pX,  // key + data
  int flags,               // OPFLAG_APPEND, etc.
  int seekResult           // pre-positioned? 0 = no
){
  BtShared *pBt = pCur->pBt;
  MemPage *pPage;
  int loc = seekResult;

  /* Verify transaction state */
  assert( cursorOwnsBtShared(pCur) );
  assert( (pCur->curFlags & BTCF_WriteFlag)!=0 );

  /* Position cursor if not already positioned */
  if( loc==0 ){
    rc = sqlite3BtreeMovetoUnpacked(pCur, 0, pX->nKey, 0, &loc);
    // loc < 0: position is before target key (insert here)
    // loc = 0: key exists (for tables: just update; for UNIQUE: error)
    // loc > 0: position is after target key
  }

  /* loc != 0 means we're inserting new key, not updating */
  if( loc!=0 ){
    pPage = pCur->pPage;
    
    /* Build the cell bytes in a scratch buffer */
    /* cellSizePtr() computes: varint(payload_size) + varint(rowid) + payload */
    unsigned char *pCell;
    int szNew = /* computed from pX sizes */;
    
    /* Insert cell at position pCur->ix in the cell pointer array */
    rc = insertCell(pPage, pCur->ix, pCell, szNew, 0, 0);
    
    /* Mark page as dirty (write to journal/WAL on commit) */
    /* insertCell already called sqlite3PagerWrite() internally */
  }

  /* Rebalance if page overflowed */
  if( rc==SQLITE_OK ){
    rc = balance(pCur);
  }

  return rc;
}
```

---

### `sqlite3BtreeMovetoUnpacked()` — btree.c ~L8100

Binary search descent from root to leaf:

```c
int sqlite3BtreeMovetoUnpacked(
  BtCursor *pCur,       // cursor to position
  UnpackedRecord *pIdxKey, // NULL for table lookup
  i64 intKey,           // rowid to find (42 in our example)
  int biasRight,        // hint: bias toward right side
  int *pRes             // result: 0=found, <0=before, >0=after
){
  int rc;
  RecordCompare xRecordCompare;
  
  /* Start at root page */
  rc = moveToRoot(pCur);  // loads root page into pCur->pPage
  
  for(;;){
    int lwr, upr, idx, c;
    Pgno chldPg;
    MemPage *pPage = pCur->pPage;
    
    /* Binary search within current page's cell array */
    lwr = 0;
    upr = pPage->nCell - 1;
    while( lwr <= upr ){
      idx = (lwr + upr) >> 1;  // midpoint
      /* Compare intKey with cell[idx].key */
      c = sqlite3VdbeRecordCompare(/* cell key */, intKey);
      if( c < 0 )      lwr = idx + 1;  // search right half
      else if( c > 0 ) upr = idx - 1;  // search left half
      else { *pRes = 0; return SQLITE_OK; } // exact match
    }
    
    /* At a leaf: stop */
    if( pPage->leaf ) break;
    
    /* At interior: descend to appropriate child */
    if( lwr >= pPage->nCell ){
      chldPg = pPage->pgnoOvfl != 0 ? ... : pPage->aData[8]; // right child
    } else {
      chldPg = /* child pointer from cell[lwr] */;
    }
    rc = moveToChild(pCur, chldPg);  // loads child page, pushes parent onto stack
  }
  
  pCur->ix = lwr;  // insertion point
  *pRes = c < 0 ? -1 : 1;
  return SQLITE_OK;
}
```

**Key detail:** The cursor maintains an **ancestor stack** (`pCur->apPage[]`, `pCur->aiIdx[]`) so that after descending to a leaf, SQLite can walk back up for rebalancing without re-reading parent pages.

---

### `insertCell()` — btree.c ~L4000

```c
static void insertCell(
  MemPage *pPage,   // target page
  int i,            // cell index to insert at
  u8 *pCell,        // cell bytes
  int sz,           // cell size
  u8 *pTemp,        // scratch buffer
  Pgno iChild       // child page (for interior page splits)
){
  int idx;          // where to write cell content
  int j;            // loop counter
  u8 *data = pPage->aData;
  u8 *pIns;         // pointer into cell pointer array

  /* Grow cell pointer array by 2 bytes and shift right */
  pIns = pPage->aCellIdx + 2 * i;  // insertion point in cell ptr array
  memmove(pIns+2, pIns, 2*(pPage->nCell - i));  // shift existing pointers

  /* Find space for cell content (allocated from free space area) */
  idx = allocateSpace(pPage, sz);

  /* Write cell content at idx */
  memcpy(&data[idx], pCell, sz);

  /* Write cell pointer */
  put2byte(pIns, idx);

  pPage->nCell++;
  
  /* If page is now over-full, mark overflow */
  if( pPage->nFree < 0 ){
    pPage->nOverflow = 1;
    pPage->aiOvfl[0] = i;
    pPage->apOvfl[0] = pCell;
  }
}
```

**Page layout after insertCell:**
```
[8/12 byte header]
[Cell Pointer Array: offset_0, offset_1, ..., offset_n] ← grows down
[           Free Space (middle of page)                ]
[Cell n content] ... [Cell 1 content] [Cell 0 content] ← grows up
```

---

### `balance_nonroot()` — btree.c ~L8400 (simplified)

```c
static int balance_nonroot(
  MemPage *pParent,
  int iParentIdx,
  u8 *aOvflSpace,
  int isRoot,
  int bBulk        // bulk insert hint
){
  MemPage *apOld[NB];   /* NB = 3 sibling pages */
  MemPage *apNew[NB+2]; /* up to 4 new pages after redistribution */
  u8 *apCell[MX_CELL*(NB+2)]; /* flat array of all cells */
  int szCell[MX_CELL*(NB+2)]; /* sizes of each cell */
  int nCell = 0;        /* total cells across all siblings */
  int nOld, nNew;       /* count of old/new sibling pages */

  /* Step 1: Find siblings */
  /* Left sibling: iParentIdx > 0 → apOld[0] = page at parent.child[iParentIdx-1] */
  /* Overflowing page: apOld[nOld-1] */
  /* Right sibling: exists if iParentIdx < parent.nCell */

  /* Step 2: Collect all cells into flat array */
  for(i=0; i<nOld; i++){
    for(j=0; j<apOld[i]->nCell; j++){
      apCell[nCell] = findCell(apOld[i], j);
      szCell[nCell] = cellSizePtr(apOld[i], apCell[nCell]);
      nCell++;
    }
  }

  /* Step 3: Determine optimal page count and distribution */
  /* Target: 67% fill per page (usableSpace * 2/3) */
  usableSpace = pBt->usableSize;
  for(subtotal=d=0, i=0; i<nCell; i++){
    subtotal += szCell[i] + 2;  /* +2 for cell pointer entry */
    if( subtotal > usableSpace ){
      nNew++;
      subtotal = szCell[i] + 2;
    }
  }
  /* cntNew[i] = last cell index on new page i */

  /* Step 4: Rewrite new pages with redistributed cells */
  for(i=0; i<nNew; i++){
    assemblePage(apNew[i], cntNew[i]-j, apCell+j, szCell+j);
    j = cntNew[i];
  }

  /* Step 5: Update parent with new divider keys */
  /* Remove old child pointers, insert new ones */
  /* This may cause parent to overflow → recursive balance() call */
}
```

**The 3-sibling algorithm is the core production insight:**
Instead of "split 1 page into 2," SQLite takes the overflowing page plus up to 2 neighbors and redistributes all their cells optimally. Result: pages are 67% full (not 50%), tree stays shallower, and fewer future splits occur.
