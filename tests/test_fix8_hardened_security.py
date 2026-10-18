import pytest
import hmac
import hashlib
from app.app import app, get_db, hash_password, verify_password

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_salted_password_hashing_and_legacy_compatibility():
    """
    VULN-04: Test that hash_password uses salted hashes (not plain SHA-256)
    and verify_password supports both modern and legacy SHA-256 hashes.
    """
    raw_pass = "15081958"
    new_hash = hash_password(raw_pass)

    # 1. Must NOT be a plain 64-character SHA-256 hex string
    assert new_hash != hashlib.sha256(raw_pass.encode("utf-8")).hexdigest()
    assert new_hash.startswith("scrypt:") or new_hash.startswith("pbkdf2:")

    # 2. Modern hash verification
    assert verify_password(new_hash, raw_pass) is True
    assert verify_password(new_hash, "wrongpass") is False

    # 3. Legacy SHA-256 hash backwards compatibility
    legacy_sha = hashlib.sha256(raw_pass.encode("utf-8")).hexdigest()
    assert verify_password(legacy_sha, raw_pass) is True
    assert verify_password(legacy_sha, "wrongpass") is False


def test_otp_rate_limiting_and_invalidation(client):
    """
    VULN-06: Test that repeated invalid OTP attempts trigger lockout and invalidation.
    """
    conn = get_db()
    cur = conn.cursor()
    test_mobile = "9999900088"
    cur.execute("DELETE FROM otps WHERE mobile = %s", (test_mobile,))
    cur.execute("INSERT INTO otps (mobile, code, created_at) VALUES (%s, '123456', NOW())", (test_mobile,))
    conn.commit()

    try:
        with client.session_transaction() as sess:
            sess["apply_mobile"] = test_mobile

        # Attempt 1-5 with wrong OTP
        for attempt in range(1, 6):
            res = client.post("/verify", data={"otp": "000000"})
            assert res.status_code == 200

        # Attempt 6: should be locked out and OTP deleted
        res_exceeded = client.post("/verify", data={"otp": "000000"}, follow_redirects=True)
        assert b"Too many failed OTP attempts" in res_exceeded.data or b"invalidated" in res_exceeded.data

        # Check DB: OTP must be purged from database
        cur.execute("SELECT count(*) FROM otps WHERE mobile = %s", (test_mobile,))
        assert cur.fetchone()[0] == 0, "Expected OTP to be invalidated and removed from DB"

    finally:
        cur.execute("DELETE FROM otps WHERE mobile = %s", (test_mobile,))
        conn.commit()
        cur.close()
        conn.close()


def test_csrf_protection_rejects_missing_token():
    """
    VULN-05: Test that state-changing requests without CSRF token are blocked with 403
    when testing mode is disabled.
    """
    app.config["TESTING"] = False
    try:
        with app.test_client() as unittester:
            res = unittester.post("/apply", data={"mobile": "9876543210"})
            assert res.status_code == 403, f"Expected 403 Forbidden without CSRF token, got {res.status_code}"
    finally:
        app.config["TESTING"] = True
