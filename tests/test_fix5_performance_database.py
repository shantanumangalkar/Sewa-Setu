import pytest
import psycopg2
from app.app import get_db

def test_database_indexes_prevent_sequential_scans():
    """
    PERFORMANCE DEFECT:
    In a 100,000-row table, queries on mobile and status/submitted_at perform
    full table sequential scans (Seq Scan), driving CPU to 100% and causing 504 timeouts.
    Expected: EXPLAIN query plan must use an Index Scan, NOT a full Seq Scan.
    """
    conn = get_db()
    cur = conn.cursor()

    # 1. Check query plan for mobile lookup (used in /status login and /apply check)
    cur.execute("EXPLAIN SELECT id FROM applications WHERE mobile = '9861908220'")
    plan_lines = [row[0] for row in cur.fetchall()]
    plan_text = " ".join(plan_lines)

    assert "Index Scan" in plan_text or "Bitmap Index Scan" in plan_text, (
        f"Query on mobile performed full table Seq Scan instead of Index Scan!\nPlan:\n{plan_text}"
    )

    # 2. Check query plan for overdue deemed-approval and admin filter
    cur.execute("EXPLAIN SELECT count(*) FROM applications WHERE status = 'PENDING' AND submitted_at < NOW()")
    plan_lines_sla = [row[0] for row in cur.fetchall()]
    plan_text_sla = " ".join(plan_lines_sla)

    assert "Index Scan" in plan_text_sla or "Bitmap Index Scan" in plan_text_sla, (
        f"Query on status/submitted_at performed full table Seq Scan!\nPlan:\n{plan_text_sla}"
    )

    cur.close()
    conn.close()

def test_connection_handling_under_concurrency():
    """
    Test that multiple concurrent requests do not exhaust database connections.
    """
    import concurrent.futures

    def worker():
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM portal_users")
        res = cur.fetchone()[0]
        cur.close()
        conn.close()
        return res

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(worker) for _ in range(30)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 30
    assert all(r > 0 for r in results)
