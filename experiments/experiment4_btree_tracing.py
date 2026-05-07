import os
import time
import subprocess
import textwrap

def run_experiment():
    print("==================================================")
    print(" EXPERIMENT 4: B-TREE TRAVERSAL AND SPLIT TRACING ")
    print("==================================================")
    
    exe_path = 'sqlite3_custom.exe'
    
    if os.path.exists(exe_path):
        print(f"[INFO] Found custom compiled SQLite ({exe_path})!")
        print("       We will pipe SQL directly to it to see the C-level B-Tree tracing (printf).\n")
    else:
        print("[ERROR] Custom SQLite executable not found.")
        print("        Please run 'build_sqlite.bat' first to compile it with your B-Tree tweaks.")
        return

    # SQL commands to trigger B-Tree operations
    # We do 5000 inserts to guarantee page splits (balance_nonroot)
    sql_script = textwrap.dedent("""
    .bail on
    DROP TABLE IF EXISTS users;
    CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER);
    BEGIN TRANSACTION;
    """)
    
    # Generate 5000 inserts
    for i in range(5000):
        sql_script += f"INSERT INTO users (id, name, age) VALUES ({i}, 'User_{i}', {i % 100});\n"
        
    sql_script += textwrap.dedent("""
    COMMIT;
    
    .print \\n[RUN] Querying by Primary Key (id=4500) -> Table B-Tree Traversal
    .print       (You should see 'moveToChild()' depth logs here)
    SELECT * FROM users WHERE id = 4500;
    
    .print \\n[RUN] Creating an Index on 'age'...
    CREATE INDEX idx_age ON users(age);
    
    .print \\n[RUN] Querying by indexed column (age=42) -> Index B-Tree Traversal
    SELECT COUNT(*) FROM users WHERE age = 42;
    """)
    
    # Write to a temporary file
    with open("temp_trace.sql", "w") as f:
        f.write(sql_script)

    print("[RUN] Executing SQL script via custom SQLite engine...")
    start_time = time.time()
    
    # Run the custom executable and stream output
    # We use subprocess to run the custom exe with our SQL script
    process = subprocess.Popen(
        [exe_path, "test_trace.db"],
        stdin=open("temp_trace.sql", "r"),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    stdout_output, _ = process.communicate()
    
    # Filter output so we don't spam thousands of lines
    # We only want to see the trace for the SELECT queries, not the 5000 inserts.
    show_debug = False
    for line in stdout_output.splitlines():
        if "[RUN]" in line:
            show_debug = True
            print(line)
        elif "User_4500" in line:
            print(line)
        elif show_debug and "[DEBUG]" in line:
            if "B-Tree Insert" not in line and "allocateSpace()" not in line:
                print(line)

    print(f"\n      Execution complete in {time.time() - start_time:.3f} seconds.\n")
    
    # Cleanup
    if os.path.exists("temp_trace.sql"):
        os.remove("temp_trace.sql")
    if os.path.exists("test_trace.db"):
        os.remove("test_trace.db")

if __name__ == "__main__":
    run_experiment()
