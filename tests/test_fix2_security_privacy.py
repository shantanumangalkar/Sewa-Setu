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

def test_unauthenticated_ack_pdf_is_blocked(client):
    """
    VULNERABILITY: /ack/<id>.pdf has zero authentication.
    Anyone can scrape all citizen bank accounts and PII.
    Expected: Unauthenticated access must be rejected (302 redirect or 403/401).
    """
    # Fetch application 1 acknowledgment without any login
    res = client.get("/ack/1.pdf")
    # Current code returns 200 OK with the PDF content!
    assert res.status_code in (302, 401, 403), f"Expected authentication barrier but got status {res.status_code}"

def test_idor_view_other_citizen_application_is_blocked(client):
    """
    VULNERABILITY (IDOR): Citizen logged in with mobile A can access /application/<id> of Citizen B.
    Expected: Accessing another citizen's application must return 403 Forbidden.
    """
    # Simulate login as citizen with mobile 9861908220 (id 1 in seed)
    with client.session_transaction() as sess:
        sess["logged_in"] = True
        sess["portal_mobile"] = "9861908220"

    # Attempt to access Application ID 2 (which belongs to a different mobile: 6950273123)
    res = client.get("/application/2")
    assert res.status_code == 403, f"Expected 403 Forbidden for IDOR access, but got status {res.status_code}"

def test_privilege_escalation_citizen_cannot_approve(client):
    """
    VULNERABILITY: /admin/approve/<id> checks session.get('logged_in'), not session.get('admin').
    Any logged-in citizen can approve applications!
    Expected: Must return 403 Forbidden when not an admin.
    """
    with client.session_transaction() as sess:
        sess["logged_in"] = True
        sess["portal_mobile"] = "9861908220"
        # sess['admin'] is NOT set

    res = client.post("/admin/approve/1")
    assert res.status_code == 403, f"Expected 403 Forbidden for non-admin approve attempt, but got status {res.status_code}"

def test_privilege_escalation_citizen_cannot_reject(client):
    """
    VULNERABILITY: /admin/reject/<id> checks session.get('logged_in'), not session.get('admin').
    Any logged-in citizen can reject applications!
    Expected: Must return 403 Forbidden when not an admin.
    """
    with client.session_transaction() as sess:
        sess["logged_in"] = True
        sess["portal_mobile"] = "9861908220"

    res = client.post("/admin/reject/1")
    assert res.status_code == 403, f"Expected 403 Forbidden for non-admin reject attempt, but got status {res.status_code}"

def test_sql_injection_on_reset_password(client):
    """
    VULNERABILITY: /status/reset string interpolates mobile into SQL query.
    Expected: Input must be parameterized so malicious SQL injection payload is treated as a literal string.
    """
    # Malicious SQL payload
    payload = "' OR '1'='1"
    res = client.post("/status/reset", data={"mobile": payload})
    assert res.status_code == 200
