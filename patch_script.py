import sys

with open('sqlite-src/sqlite3.c', 'r', encoding='utf-8') as f:
    content = f.read()

# Add fflush to Traversal
content = content.replace(
    'printf("[DEBUG] B-Tree Traversal: Moving to child page %u at depth %d\\n", newPgno, pCur->iPage);',
    'printf("[DEBUG] B-Tree Traversal: Moving to child page %u at depth %d\\n", newPgno, pCur->iPage); fflush(stdout);'
)

# Add fflush to Split
content = content.replace(
    'printf("[DEBUG] B-Tree Split: balance_nonroot() called on page within parent %u\\n", pParent->pgno);',
    'printf("[DEBUG] B-Tree Split: balance_nonroot() called on page within parent %u\\n", pParent->pgno); fflush(stdout);'
)

# Add Insert tweak
old_insert = """){
  int rc;
  int loc = seekResult;          /* -1: before desired location  +1: after */"""
new_insert = """){
  int rc;
  int loc = seekResult;          /* -1: before desired location  +1: after */
  
  printf("[DEBUG] B-Tree Insert: sqlite3BtreeInsert called for key %lld into table root %u\\n", pX->nKey, pCur->pgnoRoot);
  fflush(stdout);"""
content = content.replace(old_insert, new_insert)

with open('sqlite-src/sqlite3.c', 'w', encoding='utf-8') as f:
    f.write(content)

print('Patched sqlite3.c successfully!')
