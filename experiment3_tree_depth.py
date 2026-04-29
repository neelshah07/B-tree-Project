import sqlite3
import struct
import os
import tempfile
import math

# Page type constants
INTERIOR_TYPES = {0x02, 0x05}
LEAF_TYPES = {0x0a, 0x0d}


class SQLitePageReader:
    def __init__(self, db_path):
        self.f = open(db_path, 'rb')

        header = self.f.read(100)
        self.page_size = struct.unpack('>H', header[16:18])[0]
        if self.page_size == 1:
            self.page_size = 65536

    def read_page(self, page_num):
        offset = (page_num - 1) * self.page_size
        if page_num == 1:
            self.f.seek(100)
            return self.f.read(self.page_size - 100)
        else:
            self.f.seek(offset)
            return self.f.read(self.page_size)

    def parse_page(self, page_num):
        data = self.read_page(page_num)
        if len(data) < 8:
            return None

        page_type = data[0]
        num_cells = struct.unpack('>H', data[3:5])[0]

        result = {
            "is_interior": page_type in INTERIOR_TYPES,
            "is_leaf": page_type in LEAF_TYPES,
            "num_cells": num_cells,
            "children": []
        }

        if result["is_interior"]:
            right_child = struct.unpack('>I', data[8:12])[0]
            result["children"].append(right_child)

            header_size = 12
            for i in range(num_cells):
                ptr = struct.unpack('>H', data[header_size + i*2:header_size + i*2 + 2])[0]
                child = struct.unpack('>I', data[ptr:ptr+4])[0]
                result["children"].append(child)

        return result

    def measure_height(self, root):
        level = [root]
        height = 0

        while level:
            next_level = []
            for page in level:
                try:
                    p = self.parse_page(page)
                    if p and p["is_interior"]:
                        next_level.extend(p["children"])
                except:
                    pass
            height += 1
            level = next_level[:5000]

        return height - 1

    def close(self):
        self.f.close()


def run_experiment(sizes):
    print("\n===== EXPERIMENT 3: TREE DEPTH =====\n")

    tmpdir = tempfile.mkdtemp()

    for n in sizes:
        db_path = os.path.join(tmpdir, f"db_{n}.db")

        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")

        # Insert data
        for i in range(n):
            conn.execute("INSERT INTO t VALUES (?, ?)", (i, f"val_{i}"))
        conn.commit()
        conn.close()

        # Read B-Tree
        reader = SQLitePageReader(db_path)

        # Get root page
        conn = sqlite3.connect(db_path)
        root = conn.execute(
            "SELECT rootpage FROM sqlite_schema WHERE name='t'"
        ).fetchone()[0]
        conn.close()

        actual_height = reader.measure_height(root)

        # Theoretical height
        m = 200  # approx branching factor
        theoretical = math.ceil(math.log(max(n, 1), m))

        print(f"Records: {n}")
        print(f"Actual Height     : {actual_height}")
        print(f"Theoretical Height: {theoretical}")
        print("-" * 40)

        reader.close()

        # Cleanup
        try:
            os.remove(db_path)
        except:
            pass

    os.rmdir(tmpdir)


if __name__ == "__main__":
    run_experiment([1000, 5000, 10000, 20000])