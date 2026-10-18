import os
import sys
import subprocess
import psycopg2
import configparser
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(BASE_DIR, "app")
SCRIPT_PATH = os.path.join(APP_DIR, "scripts", "deemed_approval.py")

# Read DB configuration
config = configparser.ConfigParser()
ini_path = os.path.join(APP_DIR, "config", "app.ini")
config.read(ini_path)

DB_HOST = os.getenv("DB_HOST", config.get("database", "host", fallback="127.0.0.1"))
DB_PORT = os.getenv("DB_PORT", config.get("database", "port", fallback="5432"))
DB_NAME = os.getenv("DB_NAME", config.get("database", "name", fallback="sewasetu"))
DB_USER = os.getenv("DB_USER", config.get("database", "user", fallback="sewasetu"))
DB_PASS = os.getenv("DB_PASSWORD", config.get("database", "password", fallback="sewasetu123"))

def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

def test_deemed_approval_script_execution():
    """
    Test that the nightly deemed-approval script runs successfully without FileNotFoundError,
    correctly reads configuration, and marks overdue applications as DEEMED_APPROVED.
    """
    conn = get_connection()
    cur = conn.cursor()

    # Insert a test application that is 16 days old (overdue beyond 15-day SLA)
    test_app_no = "SSPTEST_OVERDUE_01"
    cur.execute("DELETE FROM applications WHERE application_no = %s", (test_app_no,))
    submitted_time = datetime.now() - timedelta(days=16)
    cur.execute(
        """INSERT INTO applications
           (application_no, applicant_name, mobile, dob, gender, marital_status,
            village, block, bank_account, ifsc, status, submitted_at)
           VALUES (%s, 'Test Citizen', '9999900001', '1960-01-01', 'Male', 'Married',
                   'Sonari Gaon', 'Sonari', '123456789012', 'SBIN0001234', 'PENDING', %s)
           RETURNING id""",
        (test_app_no, submitted_time)
    )
    test_id = cur.fetchone()[0]
    conn.commit()

    try:
        # Execute the deemed_approval.py script
        env = os.environ.copy()
        env["PYTHONPATH"] = APP_DIR
        res = subprocess.run(
            [sys.executable, SCRIPT_PATH],
            cwd=APP_DIR,
            env=env,
            capture_output=True,
            text=True
        )

        # 1. The script must execute without errors
        assert res.returncode == 0, f"deemed_approval.py failed with returncode {res.returncode}:\nStdout: {res.stdout}\nStderr: {res.stderr}"

        # 2. The application must be updated to DEEMED_APPROVED
        cur.execute("SELECT status, decided_by FROM applications WHERE id = %s", (test_id,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "DEEMED_APPROVED", f"Expected DEEMED_APPROVED but got {row[0]}"
        assert row[1] == "RTPS-AUTO", f"Expected decided_by='RTPS-AUTO' but got {row[1]}"

    finally:
        # Cleanup test record
        cur.execute("DELETE FROM applications WHERE application_no = %s", (test_app_no,))
        conn.commit()
        cur.close()
        conn.close()
