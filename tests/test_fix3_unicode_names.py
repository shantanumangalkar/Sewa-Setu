import pytest
import io
import psycopg2
from app.app import sanitize, generate_acknowledgment, get_db

def test_sanitize_preserves_full_assamese_name():
    """
    BUG: sanitize() currently truncates UTF-8 strings at 20 bytes.
    Since Assamese/Bengali characters take 3 bytes each, names are cut in half after 6 characters!
    E.g. 'প্ৰণৱ কলিতা' (28 bytes) is truncated to 'প্ৰণৱ ক' (19 bytes).
    Expected: Name must be preserved up to 100 characters (matching DB schema VARCHAR(100)).
    """
    full_name = "প্ৰণৱ কলিতা"  # 10 characters, 28 bytes
    sanitized = sanitize(full_name)
    assert sanitized == full_name, f"Expected full name '{full_name}' but got '{sanitized}' (truncated)"

def test_acknowledgment_pdf_renders_assamese_name():
    """
    BUG: Helvetica core font in fpdf2 fails on Assamese Unicode text,
    causing errors or replacing characters with question marks (????).
    Expected: generate_acknowledgment() must handle Assamese characters and return valid PDF bytes.
    """
    conn = get_db()
    cur = conn.cursor()
    test_app_no = "SSPTEST_UNICODE_01"
    assamese_name = "প্ৰণৱ কলিতা"

    cur.execute("DELETE FROM applications WHERE application_no = %s", (test_app_no,))
    cur.execute(
        """INSERT INTO applications
           (application_no, applicant_name, mobile, dob, gender, marital_status,
            village, block, bank_account, ifsc, status, submitted_at)
           VALUES (%s, %s, '9999900002', '1955-05-15', 'Male', 'Married',
                   'Sonari Gaon', 'Sonari', '123456789012', 'SBIN0001234', 'PENDING', NOW())
           RETURNING id""",
        (test_app_no, assamese_name)
    )
    test_id = cur.fetchone()[0]
    conn.commit()

    try:
        pdf_bytes = generate_acknowledgment(cur, test_id)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000, "Generated PDF bytes too small"
        # The PDF output should not fallback to '?' for the applicant name
        # If Helvetica failed, row[1] was replaced by '?'
        assert b"?" * 4 not in pdf_bytes, "PDF contains question marks (????) instead of Unicode characters"
    finally:
        cur.execute("DELETE FROM applications WHERE application_no = %s", (test_app_no,))
        conn.commit()
        cur.close()
        conn.close()
