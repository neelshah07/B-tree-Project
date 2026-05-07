# B-Tree Rebalancing Logic: Deep Dive

## Overview

The `balance_nonroot()` function in `btree.c` (~line 8400) is the most complex
and most important function in SQLite. It implements a **3-sibling redistribution**
algorithm that is fundamentally different from textbook B-Tree splitting.

## Textbook Split vs. SQLite Split

### Textbook (naive) split:
```
Before:  [A B C D E F G] ← overflowed (8 cells, max=7)
After:   [A B C] [D] [E F G]
                  ↑
              promoted to parent
Fill: 43%, 43% → wastes space, causes frequent future splits
```

### SQLite's 3-sibling redistribution:
```
Before:  [A B C] [D E F G H] [I J K]
                  ^ overflow
After:   [A B C D] [E F G] [H I J K]
Fill: 57%, 43%, 57% → better space utilization
```

## Algorithm Steps

### Step 1: Identify Siblings

```c
/* btree.c balance_nonroot() */
/* The overflowing page is at parent.child[iParentIdx] */

nOld = 0;

/* Try to get left sibling */
if( iParentIdx > 0 ){
    /* left sibling = parent.child[iParentIdx - 1] */
    apOld[nOld++] = btreePageLookup(pBt, ...);
}

/* Overflowing page itself */
apOld[nOld++] = pPage; /* the overflowing page */

/* Try to get right sibling */
if( iParentIdx < pParent->nCell ){
    /* right sibling = parent.child[iParentIdx + 1] */
    apOld[nOld++] = btreePageLookup(pBt, ...);
}

/* nOld is 1, 2, or 3 */
```

### Step 2: Flatten All Cells

```c
/* Collect all cells from all siblings into one flat array */
nCell = 0;
for(i=0; i<nOld; i++){
    for(j=0; j<apOld[i]->nCell + apOld[i]->nOverflow; j++){
        apCell[nCell] = findCellPastPtr(apOld[i], j);
        szCell[nCell] = cellSizePtr(apOld[i], apCell[nCell]);
        nCell++;
    }
    /* Include the divider key from parent between siblings */
    /* (for table btrees, divider is implicit; for index btrees, explicit) */
}
```

### Step 3: Compute Optimal Distribution

```c
/*
 * Goal: distribute nCell cells across as few pages as possible,
 * where each page can hold at most usableSpace bytes.
 *
 * This is essentially a bin-packing problem, solved greedily.
 */
usableSpace = pBt->usableSize;  /* page_size - reserved_space */

for(subtotal=d=0, i=0; i<nCell; i++){
    subtotal += szCell[i] + 2;  /* +2 for cell pointer entry */
    if( subtotal > usableSpace ){
        cntNew[d++] = i;        /* page d ends before cell i */
        subtotal = szCell[i] + 2;
    }
}
nNew = d + 1;

/* Adjust: if we need fewer pages than we have siblings,
 * SQLite may MERGE pages (reducing nNew below nOld) */
```

### Step 4: Write New Pages

```c
for(i=j=0; i<nNew; i++){
    /* Clear old page content */
    zeroPage(apNew[i], /* leaf or interior flag */);
    
    /* Pack cells cntOld[i] through cntNew[i]-1 into apNew[i] */
    assemblePage(apNew[i],
                 cntNew[i] - j,    /* number of cells */
                 &apCell[j],       /* cells */
                 &szCell[j]);      /* sizes */
    j = cntNew[i];
    
    /* Mark as dirty → will be written on commit */
    sqlite3PagerWrite(apNew[i]->pDbPage);
}
```

### Step 5: Update Parent

```c
/* Remove old dividers from parent for old siblings */
for(i=0; i<nOld-1; i++){
    dropCell(pParent, iParentIdx+i, szParent[i], ...);
}

/* Insert new dividers for new siblings */
for(i=0; i<nNew-1; i++){
    insertCell(pParent, iParentIdx+i, pNew, szNew, ...);
}

/* Update right child pointer of last new sibling */
put4byte(findOverflowCell(pParent, iParentIdx+nNew-1),
         apNew[nNew-1]->pgno);

/* Parent may now overflow → caller's balance() will recurse */
```

## Why 67% Fill Target?

The distribution algorithm targets **2/3 fill** (not 1/2):

```
If we split one page into two at 50%:
  - Each new page has 50% fill
  - After (page_capacity × 0.5) more inserts → splits again
  - Amortized: 1 split per 0.5 × page_capacity inserts

If we redistribute 3 → 3 pages at 67% fill:
  - Each page has 67% fill
  - After (page_capacity × 0.33) more inserts → split
  - But: fewer total splits because pages hold more

Net result: ~33% fewer split operations over the database lifetime.
```

Additionally, the 67% fill means the tree is ~33% more space-efficient than
a tree always split at 50% fill — fewer pages → lower height → fewer disk reads.

## Recursion and Stack Depth

```
Level 0 (leaf): overflow → balance_nonroot() 
  → may overflow parent (level 1) → balance_nonroot() again
    → may overflow grandparent (level 2) → balance_nonroot() again
      → ... up to tree height times
        → if root overflows → balance_deeper()
           → creates new root, increases tree height by 1
```

**Maximum recursion depth = tree height ≈ 3-5 for typical SQLite databases.**

This is why each balance call is O(1) in terms of pages written (up to 4 pages),
but worst-case an INSERT can write O(height × 4) pages — still O(log n) total.

## balance_deeper(): Root Splits

When the root itself overflows, SQLite can't create a "parent of root."
Instead:

```c
static int balance_deeper(BtCursor *pCur){
  MemPage *pChild;
  Pgno pgnoChild;
  
  /* Allocate a new child page */
  rc = allocateBtreePage(pBt, &pChild, &pgnoChild, pRoot->pgno, 0);
  
  /* Copy root's content into the child */
  copyNodeContent(pRoot, pChild, ...);
  
  /* Make root an empty interior page pointing to pChild */
  zeroPage(pRoot, PTF_INTKEY | PTF_LEAF ^ PTF_LEAF); // interior type
  put4byte(pRoot->aData + 8, pgnoChild); // right child = pChild
  
  /* Now balance_nonroot() on pChild will split it into 2 */
  pCur->iPage++;
  pCur->apPage[1] = pChild;
  return balance_nonroot(pRoot, 0, ...);
}
```

This is how SQLite increases tree height — always by making the root an interior
node and pushing its content down. The root page number NEVER changes. This is
critical because the root page number is stored in `sqlite_schema` and changing
it would require updating the schema — expensive and risky.
