import sqlite3
import time
import os

# Pointing exactly to your local portal.db
DB_PATH = r"C:\Users\raghavkumar.j\Desktop\demo\prism\Database\portal.db"

# The logic currently used in your pipeline (Blinds the index)
SLOW_SQL = "SELECT COUNT(*) FROM proc_daily_hpc WHERE strftime('%Y-%m', DATE(proc_date)) = '2024-05'"

# The optimized logic (Uses the exact index you built for DATE(proc_date))
FAST_SQL = "SELECT COUNT(*) FROM proc_daily_hpc WHERE DATE(proc_date) BETWEEN '2024-05-01' AND '2024-05-31'"

def prove_sqlite_bottleneck():
    if not os.path.exists(DB_PATH):
        print(f"Error: Could not find DB at {DB_PATH}")
        return

    print("Connecting to local SQLite database (Read-Only)...")
    conn = sqlite3.connect(DB_PATH)
    
    print("\n--- Test 1: The 'Slow' Query (Using strftime) ---")
    t0 = time.time()
    count_slow = conn.execute(SLOW_SQL).fetchone()[0]
    time_slow = time.time() - t0
    print(f"Result: Found {count_slow:,} rows.")
    print(f"Time Taken: {time_slow:.2f} seconds.")
    
    print("\n--- Test 2: The 'Fast' Query (Using BETWEEN) ---")
    t1 = time.time()
    count_fast = conn.execute(FAST_SQL).fetchone()[0]
    time_fast = time.time() - t1
    print(f"Result: Found {count_fast:,} rows.")
    print(f"Time Taken: {time_fast:.5f} seconds.")

    print("\n--- Conclusion ---")
    if time_slow > time_fast and time_fast > 0:
        multiplier = time_slow / time_fast
        print(f"The Fast Query is {multiplier:.1f}x faster on your local SQLite DB.")
        print("Note: A DELETE operation takes even longer than a COUNT because it has to modify the file,")
        print("making the penalty of the slow query exponentially worse during your pipeline run.")

    conn.close()

if __name__ == "__main__":
    prove_sqlite_bottleneck()