import pytest
import werkzeug
if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "3.0.0"

from app.app import app, get_db

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_pending_application_can_be_edited_without_creating_duplicates(client):
    """
    FEATURE: Allow citizens to correct spelling mistakes or bank details
    on PENDING applications without deleting/canceling or creating duplicate records.
    """
    conn = get_db()
    cur = conn.cursor()
    test_mobile = "9999900050"
    test_app_no = "SSPTEST_EDIT_01"

    cur.execute("DELETE FROM applications WHERE mobile = %s", (test_mobile,))
    cur.execute(
        """INSERT INTO applications
           (application_no, applicant_name, mobile, dob, gender, marital_status,
            village, block, bank_account, ifsc, status, submitted_at)
           VALUES (%s, 'Wrong Speling Name', %s, '1958-05-10', 'Male', 'Married',
                   'Sonari Gaon', 'Sonari', '111122223333', 'SBIN0001234', 'PENDING', NOW())
           RETURNING id""",
        (test_app_no, test_mobile)
    )
    app_id = cur.fetchone()[0]
    conn.commit()

    try:
        # Simulate login as the applicant
        with client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["portal_mobile"] = test_mobile

        # 1. GET /application/<id>/edit should load the correction form
        res_get = client.get(f"/application/{app_id}/edit")
        assert res_get.status_code == 200, f"Expected 200 for edit page, got {res_get.status_code}"
        assert b"Correct Application Details" in res_get.data or b"Edit Application" in res_get.data

        # 2. POST /application/<id>/edit with corrected details
        res_post = client.post(
            f"/application/{app_id}/edit",
            data={
                "applicant_name": "Corrected Citizen Name",
                "dob": "10/05/1958",
                "gender": "Male",
                "marital_status": "Married",
                "husband_name": "",
                "husband_employer": "",
                "village": "Corrected Village",
                "block": "Sonari",
                "bank_account": "999988887777",
                "ifsc": "SBIN0005678"
            },
            follow_redirects=True
        )
        assert res_post.status_code == 200

        # 3. Verify in database: details are updated
        cur.execute(
            "SELECT applicant_name, village, bank_account, ifsc FROM applications WHERE id = %s",
            (app_id,)
        )
        row = cur.fetchone()
        assert row[0] == "Corrected Citizen Name"
        assert row[1] == "Corrected Village"
        assert row[2] == "999988887777"
        assert row[3] == "SBIN0005678"

        # 4. Verify NO DUPLICATE record was created (count remains exactly 1 for this mobile)
        cur.execute("SELECT count(*) FROM applications WHERE mobile = %s", (test_mobile,))
        count = cur.fetchone()[0]
        assert count == 1, f"Expected exactly 1 application record, but found {count} (duplicate created!)"

    finally:
        cur.execute("DELETE FROM applications WHERE mobile = %s", (test_mobile,))
        conn.commit()
        cur.close()
        conn.close()

def test_decided_application_cannot_be_edited(client):
    """
    CRITICAL INVARIANT: Decided applications (APPROVED, DEEMED_APPROVED, REJECTED)
    must NOT be editable once decided by the department or law.
    """
    conn = get_db()
    cur = conn.cursor()
    test_mobile = "9999900051"
    test_app_no = "SSPTEST_EDIT_02"

    cur.execute("DELETE FROM applications WHERE mobile = %s", (test_mobile,))
    cur.execute(
        """INSERT INTO applications
           (application_no, applicant_name, mobile, dob, gender, marital_status,
            village, block, bank_account, ifsc, status, submitted_at, decided_at, decided_by)
           VALUES (%s, 'Approved Citizen', %s, '1955-01-01', 'Male', 'Married',
                   'Sonari Gaon', 'Sonari', '111122223333', 'SBIN0001234', 'APPROVED', NOW(), NOW(), 'admin')
           RETURNING id""",
        (test_app_no, test_mobile)
    )
    app_id = cur.fetchone()[0]
    conn.commit()

    try:
        with client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["portal_mobile"] = test_mobile

        # Attempt to edit an approved application
        res_get = client.get(f"/application/{app_id}/edit")
        assert res_get.status_code in (400, 403, 302), f"Expected editing to be blocked, but got {res_get.status_code}"

    finally:
        cur.execute("DELETE FROM applications WHERE mobile = %s", (test_mobile,))
        conn.commit()
        cur.close()
        conn.close()

def test_status_login_explains_default_dob_password(client):
    """
    UX REQUIREMENT:
    Citizens report confusion on /status because it asks for a password they never explicitly set.
    The status login page must clearly inform the user that their default password is
    their Date of Birth in DDMMYYYY format.
    """
    res = client.get("/status")
    assert res.status_code == 200
    # Must explain that default password is Date of Birth in DDMMYYYY format
    page_text = res.data.decode("utf-8")
    assert "Date of Birth" in page_text or "DOB" in page_text
    assert "DDMMYYYY" in page_text
