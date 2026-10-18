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

def test_admin_dashboard_has_search_form(client):
    """
    FEATURE: Admin dashboard must provide a search bar so officers can immediately
    look up any candidate when an issue or grievance is reported.
    """
    with client.session_transaction() as sess:
        sess["admin"] = True

    res = client.get("/admin/dashboard")
    assert res.status_code == 200
    page_text = res.data.decode("utf-8")
    assert 'name="q"' in page_text, "Admin dashboard missing search input field name='q'"
    assert 'action="/admin/applications"' in page_text, "Search form must submit to /admin/applications"

def test_admin_search_candidate_by_mobile_and_app_no(client):
    """
    FEATURE: Search candidate across any status by mobile or application number.
    """
    conn = get_db()
    cur = conn.cursor()
    test_mobile = "9999900077"
    test_app_no = "SSP_SRCH_TEST99"
    test_name = "Searchable Candidate"

    cur.execute("DELETE FROM applications WHERE mobile = %s", (test_mobile,))
    cur.execute(
        """INSERT INTO applications
           (application_no, applicant_name, mobile, dob, gender, marital_status,
            village, block, bank_account, ifsc, status, submitted_at)
           VALUES (%s, %s, %s, '1952-08-15', 'Male', 'Married',
                   'Sonari Gaon', 'Sonari', '777788889999', 'SBIN0001234', 'APPROVED', NOW())
           RETURNING id""",
        (test_app_no, test_name, test_mobile)
    )
    app_id = cur.fetchone()[0]
    conn.commit()

    try:
        with client.session_transaction() as sess:
            sess["admin"] = True

        # 1. Search by mobile number
        res_mob = client.get(f"/admin/applications?q={test_mobile}")
        assert res_mob.status_code == 200
        assert test_app_no.encode() in res_mob.data
        assert test_name.encode() in res_mob.data

        # 2. Search by application number
        res_app = client.get(f"/admin/applications?q={test_app_no}")
        assert res_app.status_code == 200
        assert test_mobile.encode() in res_app.data
        assert test_name.encode() in res_app.data

        # 3. Search by partial candidate name
        res_name = client.get("/admin/applications?q=Searchable")
        assert res_name.status_code == 200
        assert test_app_no.encode() in res_name.data

    finally:
        cur.execute("DELETE FROM applications WHERE mobile = %s", (test_mobile,))
        conn.commit()
        cur.close()
        conn.close()
