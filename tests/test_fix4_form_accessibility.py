import io
import pytest
import werkzeug
if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "3.0.0"

from app.app import app
from datetime import date

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_upload_accepts_jpg_image(client):
    """
    BUG: upload() currently rejects all non-PDF files with ERR_VAL_47,
    even though the UI says 'Accepted formats: JPG or PDF, maximum size 5 MB'.
    Expected: A valid JPG file must be accepted and redirect to /declaration.
    """
    with client.session_transaction() as sess:
        sess["verified_mobile"] = "9999900010"

    # 150 KB JPEG dummy file
    jpg_data = io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 150000)
    res = client.post(
        "/upload",
        data={"document": (jpg_data, "voter_id.jpg")},
        content_type="multipart/form-data"
    )
    assert res.status_code == 302
    assert "/declaration" in res.headers.get("Location", "")

def test_upload_accepts_pdf_larger_than_100kb(client):
    """
    BUG: upload() has an undocumented 100 KB limit (len > 102400) throwing ERR_VAL_47,
    even though the UI states maximum size 5 MB.
    Expected: A 500 KB PDF must be accepted and redirect to /declaration.
    """
    with client.session_transaction() as sess:
        sess["verified_mobile"] = "9999900011"

    # 500 KB PDF dummy data
    pdf_data = io.BytesIO(b"%PDF-1.4 " + b"x" * 500000)
    res = client.post(
        "/upload",
        data={"document": (pdf_data, "age_proof.pdf")},
        content_type="multipart/form-data"
    )
    assert res.status_code == 302
    assert "/declaration" in res.headers.get("Location", "")

def test_date_parsing_prioritizes_indian_dd_mm_yyyy(client):
    """
    BUG: handle_submission() tests ('%m/%d/%Y', '%d/%m/%Y') in that order!
    An applicant entering 04/09/1958 (4th September) gets month and day swapped to April 9th!
    Expected: DD/MM/YYYY format must take precedence.
    """
    with client.session_transaction() as sess:
        sess["verified_mobile"] = "9999900012"
        sess["form_data"] = {
            "applicant_name": "Test Citizen",
            "village": "Sonari Gaon",
            "block": "Sonari",
            "gender": "Female",
            "marital_status": "Married",
            "bank_account": "123456789012",
            "ifsc": "SBIN0001234",
            "dob": "04/09/1958"  # 4th September 1958
        }
        sess["doc_path"] = "uploads/dummy.pdf"

    res = client.post("/declaration")
    assert res.status_code == 200

    # Query the stored application to verify dob
    from app.app import get_db
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT dob FROM applications WHERE mobile = '9999900012'")
    row = cur.fetchone()
    cur.execute("DELETE FROM applications WHERE mobile = '9999900012'")
    cur.execute("DELETE FROM portal_users WHERE mobile = '9999900012'")
    conn.commit()
    cur.close()
    conn.close()

    assert row is not None
    # Must be September 4th (month=9, day=4), NOT April 9th (month=4, day=9)
    assert row[0] == date(1958, 9, 4), f"Expected date 1958-09-04 but got {row[0]} (month/day swapped!)"

def test_widow_submission_does_not_require_deceased_husband_employer(client):
    """
    BUG: handle_submission() requires husband_employer for widows, causing
    rejection loops for elderly widows.
    Expected: A widow should be allowed to submit without entering husband_employer.
    """
    with client.session_transaction() as sess:
        sess["verified_mobile"] = "9999900013"
        sess["form_data"] = {
            "applicant_name": "Widow Citizen",
            "village": "Sonari Gaon",
            "block": "Sonari",
            "gender": "Female",
            "marital_status": "Widowed",
            "husband_name": "Late Ramesh",
            "husband_employer": "",  # Empty employer for deceased husband
            "bank_account": "123456789013",
            "ifsc": "SBIN0001234",
            "dob": "15/05/1955"
        }
        sess["doc_path"] = "uploads/dummy.pdf"

    res = client.post("/declaration")
    # Current code flashes 'Something went wrong' and redirects back to /form/1
    assert res.status_code == 200, f"Expected successful submission (status 200) but got {res.status_code}"

    # Cleanup
    from app.app import get_db
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM applications WHERE mobile = '9999900013'")
    cur.execute("DELETE FROM portal_users WHERE mobile = '9999900013'")
    conn.commit()
    cur.close()
    conn.close()
