import sys

with open('sqlite-src/sqlite3.c', 'r', encoding='utf-8') as f:
    content = f.read()

old_alloc = """static SQLITE_INLINE int allocateSpace(MemPage *pPage, int nByte, int *pIdx){
  const int hdr = pPage->hdrOffset;    /* Local cache of pPage->hdrOffset */
  u8 * const data = pPage->aData;      /* Local cache of pPage->aData */"""

new_alloc = """static SQLITE_INLINE int allocateSpace(MemPage *pPage, int nByte, int *pIdx){
  const int hdr = pPage->hdrOffset;    /* Local cache of pPage->hdrOffset */
  u8 * const data = pPage->aData;      /* Local cache of pPage->aData */
  printf("[DEBUG] B-Tree Page Manager: allocateSpace() called on page %u for %d bytes\\n", pPage->pgno, nByte);
  fflush(stdout);"""

content = content.replace(old_alloc, new_alloc)

with open('sqlite-src/sqlite3.c', 'w', encoding='utf-8') as f:
    f.write(content)

print('Patched sqlite3.c successfully for tweak 2!')
