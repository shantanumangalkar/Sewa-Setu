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


def test_friendly_mobile_normalization_and_error_message(client):
    """
    Citizens frequently enter mobile numbers formatted with country code (+91),
    leading zero, or spaces. The application must normalize these formats instead
    of rejecting with generic errors. If invalid, a clear polite error must be shown.
    """
    # 1. Test invalid mobile gives friendly error message, not generic 'Something went wrong'
    res_invalid = client.post("/apply", data={"mobile": "12345"})
    assert res_invalid.status_code == 200
    assert b"Please enter a valid 10-digit" in res_invalid.data or b"valid 10-digit" in res_invalid.data

    # 2. Test +91 formatted mobile normalizes and succeeds
    res_plus91 = client.post("/apply", data={"mobile": "+91 9999900014"})
    assert res_plus91.status_code == 302
    assert "/verify" in res_plus91.headers.get("Location", "")
    with client.session_transaction() as sess:
        assert sess.get("apply_mobile") == "9999900014"

    # Cleanup any OTP created for 9999900014
    from app.app import get_db
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM otps WHERE mobile = '9999900014'")
    conn.commit()
    cur.close()
    conn.close()

