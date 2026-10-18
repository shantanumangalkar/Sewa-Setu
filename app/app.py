# -*- coding: utf-8 -*-
"""
Sewa Setu - Old Age Pension Portal
Government of Purvanchal, Department of Social Welfare

Developed by: Netlink Infosolutions Pvt Ltd (2023)
Maintenance contract ended 31/01/2026.
"""

import os
import io
import csv
import random
import hashlib
import configparser
from datetime import datetime, date, timedelta

import time
import re
import requests
import psycopg2
from flask import (Flask, request, session, redirect, url_for, render_template,
                   flash, send_file, abort, jsonify, render_template_string)
from fpdf import FPDF

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

config = configparser.ConfigParser()
config.read(os.path.join(BASE_DIR, "config", "app.ini"))

app = Flask(__name__)
app.secret_key = config.get("app", "secret_key")
app.config["PERMANENT_SESSION_LIFETIME"] = 300

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "sewasetu@123"

SMS_GATEWAY_URL = os.getenv("SMS_GATEWAY_URL", config.get("app", "sms_gateway_url"))
OTP_VALIDITY_SECONDS = int(os.getenv("OTP_VALIDITY_SECONDS", config.get("app", "otp_validity_seconds")))
UPLOAD_DIR = os.getenv("UPLOAD_DIR", config.get("app", "upload_dir"))
SCHEME_DEADLINE = datetime.strptime(os.getenv("SCHEME_DEADLINE", config.get("pension", "scheme_deadline")),
                                    "%Y-%m-%d %H:%M")
MIN_AGE = int(os.getenv("MIN_AGE", config.get("pension", "min_age")))
SLA_DAYS = int(os.getenv("SLA_DAYS", config.get("pension", "sla_days")))

BLOCKS = ["Sonari", "Rajapara", "Dhemaji Pathar", "Borgaon", "Namti", "Khelua"]

import logging
_logdir = "/var/log/sewasetu"
try:
    os.makedirs(_logdir, exist_ok=True)
    _fh = logging.FileHandler(os.path.join(_logdir, "sewasetu-app.log"))
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s in app: %(message)s"))
    app.logger.addHandler(_fh)
    app.logger.setLevel(logging.INFO)
except Exception:
    pass


def get_db():
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return psycopg2.connect(db_url)
    return psycopg2.connect(
        host=os.getenv("DB_HOST", config.get("database", "host", fallback="127.0.0.1")),
        port=os.getenv("DB_PORT", config.get("database", "port", fallback="5432")),
        dbname=os.getenv("DB_NAME", config.get("database", "name", fallback="sewasetu")),
        user=os.getenv("DB_USER", config.get("database", "user", fallback="sewasetu")),
        password=os.getenv("DB_PASSWORD", config.get("database", "password", fallback="sewasetu123")),
    )


def init_db_if_needed():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT to_regclass('public.applications');")
        exists = cur.fetchone()[0]
        if not exists:
            app.logger.info("Initializing database schema on first run...")
            schema_file = os.path.join(BASE_DIR, "schema.sql")
            if os.path.exists(schema_file):
                with open(schema_file, "r", encoding="utf-8") as f:
                    cur.execute(f.read())
                conn.commit()
                app.logger.info("Schema initialized successfully.")
        cur.close()
        conn.close()
    except Exception as e:
        app.logger.warning("Could not auto-initialize database schema: %s" % e)


init_db_if_needed()


def sanitize(value, maxlen=100):
    # Preserve full citizen name up to schema character length (VARCHAR(100))
    # Avoid byte-slicing which corrupts multi-byte Indic/Assamese characters.
    if value is None:
        return ""
    value = value.strip()
    return value[:maxlen]


def hash_password(p):
    return hashlib.sha256(p.encode("utf-8")).hexdigest()


import threading

_EMBEDDED_MESSAGES = []

def send_sms(mobile, text):
    # Store message locally in case external gateway is not deployed
    now = time.time()
    _EMBEDDED_MESSAGES.append({
        "id": len(_EMBEDDED_MESSAGES) + 1,
        "to": mobile,
        "text": text,
        "sent_at": now,
        "delivery_at": now + 1,
    })

    # Decouple external SMS HTTP latency from user request-response cycle
    def _async():
        try:
            requests.post(SMS_GATEWAY_URL + "/api/send",
                          json={"to": mobile, "text": text}, timeout=3)
        except Exception as e:
            app.logger.debug("sms gateway error: %s" % e)
    t = threading.Thread(target=_async, daemon=True)
    t.start()


def deadline_remaining():
    delta = SCHEME_DEADLINE - datetime.now()
    if delta.total_seconds() <= 0:
        return None
    return int(delta.total_seconds() // 3600)


def new_application_no():
    return "SSP" + datetime.now().strftime("%y") + str(random.randint(100000, 999999))


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", hours_left=deadline_remaining())


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/__gateway/", defaults={"subpath": ""})
@app.route("/__gateway/<path:subpath>")
def gateway_proxy(subpath):
    # Convenience proxy to the internal SMS gateway, so the OTP inbox is reachable
    # on the main site without opening a second port on the host.
    try:
        r = requests.get(SMS_GATEWAY_URL + "/" + subpath,
                         params=request.args, timeout=2)
        if r.status_code == 200:
            return (r.content, r.status_code,
                    {"Content-Type": r.headers.get("Content-Type", "text/html")})
    except Exception:
        pass

    # In-process simulation fallback if external gateway is unavailable
    if subpath == "api/messages":
        to = request.args.get("to", "")
        now = time.time()
        out = []
        for m in _EMBEDDED_MESSAGES:
            if to and m["to"] != to:
                continue
            out.append({
                "id": m["id"], "to": m["to"],
                "text": m["text"],
                "delivered": now >= m["delivery_at"],
                "sent_at": m["sent_at"], "delivery_at": m["delivery_at"]
            })
        return jsonify({"messages": out})

    now = time.time()
    view = []
    for m in reversed(_EMBEDDED_MESSAGES[-100:]):
        view.append({
            "id": m["id"], "to": m["to"], "text": m["text"],
            "sent_hhmm": time.strftime("%H:%M:%S", time.localtime(m["sent_at"])),
            "delivered": True,
            "eta": 0,
        })
    CONSOLE_HTML = """<!doctype html><html><head><title>PurvSMS Console</title>
<meta http-equiv="refresh" content="5">
<style>
body{font-family:Arial,sans-serif;margin:24px;background:#f4f4f4}
h2{color:#1a3c6e} table{border-collapse:collapse;background:#fff;width:100%}
td,th{border:1px solid #ccc;padding:6px 10px;font-size:14px;text-align:left}
.d{color:#1b7e3c}
</style></head><body>
<h2>PurvSMS Gateway Console (simulation)</h2>
<p>Messages appear below once delivered. Auto-refreshes every 5s.</p>
<table><tr><th>#</th><th>To</th><th>Message</th><th>Sent</th><th>Status</th></tr>
{% for m in messages %}
<tr><td>{{m.id}}</td><td>{{m.to}}</td><td>{{m.text}}</td><td>{{m.sent_hhmm}}</td><td><span class="d">Delivered</span></td></tr>
{% endfor %}
</table></body></html>"""
    return render_template_string(CONSOLE_HTML, messages=view)


# ---------------------------------------------------------------------------
# Application flow: mobile -> OTP -> form steps -> upload -> declaration
# ---------------------------------------------------------------------------

@app.route("/apply", methods=["GET", "POST"])
def apply():
    if deadline_remaining() is None:
        flash("The application window for this scheme has closed.")
        return redirect(url_for("index"))
    if request.method == "POST":
        mobile_raw = request.form.get("mobile", "").strip()
        captcha = request.form.get("captcha", "")
        # Clean mobile: strip spaces, dashes, +91 or 0 prefix
        mobile = re.sub(r"\D", "", mobile_raw)
        if mobile.startswith("91") and len(mobile) == 12:
            mobile = mobile[2:]
        elif mobile.startswith("0") and len(mobile) == 11:
            mobile = mobile[1:]
        if len(mobile) != 10 or not mobile.isdigit() or mobile[0] not in "6789":
            flash("Please enter a valid 10-digit Indian mobile number.")
            return render_template("apply.html", captcha_q=make_captcha())
        code = str(random.randint(100000, 999999))
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO otps (mobile, code, created_at) VALUES (%s, %s, %s)",
                    (mobile, code, datetime.now()))
        conn.commit()
        cur.close(); conn.close()
        send_sms(mobile, "Your Sewa Setu OTP is %s. Valid for 5 minutes." % code)
        session.permanent = True
        session["apply_mobile"] = mobile
        return redirect(url_for("verify"))
    return render_template("apply.html", captcha_q=make_captcha())


def make_captcha():
    a, b = random.randint(1, 9), random.randint(1, 9)
    session["captcha_answer"] = a + b
    return "%d + %d" % (a, b)


@app.route("/verify", methods=["GET", "POST"])
def verify():
    mobile = session.get("apply_mobile")
    if not mobile:
        return redirect(url_for("apply"))
    if request.method == "POST":
        code = request.form.get("otp", "").strip()
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT code, created_at FROM otps WHERE mobile = %s "
                    "ORDER BY id DESC LIMIT 1", (mobile,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row and row[0] == code:
            age = (datetime.now() - row[1]).total_seconds()
            if age > OTP_VALIDITY_SECONDS:
                app.logger.warning("otp expired mobile=%s age=%ds" % (mobile, int(age)))
                flash("OTP expired. Please request a new OTP.")
                return redirect(url_for("apply"))
            session["verified_mobile"] = mobile
            return redirect(url_for("form_step", step=1))
        flash("Invalid OTP.")
    return render_template("verify.html", mobile=mobile)


@app.route("/form/<int:step>", methods=["GET", "POST"])
def form_step(step):
    if not session.get("verified_mobile"):
        flash("Session expired. Please verify your mobile number again.")
        return redirect(url_for("apply"))
    if step not in (1, 2, 3):
        abort(404)
    if request.method == "POST":
        data = session.get("form_data", {})
        for k, v in request.form.items():
            data[k] = v
        session["form_data"] = data
        if step < 3:
            return redirect(url_for("form_step", step=step + 1))
        return redirect(url_for("upload"))
    return render_template("form_step%d.html" % step,
                           data=session.get("form_data", {}), blocks=BLOCKS)


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if not session.get("verified_mobile"):
        flash("Session expired. Please verify your mobile number again.")
        return redirect(url_for("apply"))
    if request.method == "POST":
        f = request.files.get("document")
        if f is None or f.filename == "":
            flash("Please select a document to upload.")
            return render_template("upload.html")
        filename = f.filename.lower()
        content = f.read()
        # Accept PDF, JPG, JPEG, and PNG files up to 5 MB as stated in the UI
        allowed_exts = (".pdf", ".jpg", ".jpeg", ".png")
        if not any(filename.endswith(ext) for ext in allowed_exts):
            flash("Invalid file format. Accepted formats: JPG or PDF.")
            return render_template("upload.html")
        if len(content) > 5242880:  # 5 MB
            flash("File too large. Maximum size allowed is 5 MB.")
            return render_template("upload.html")
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        safe_fname = os.path.basename(f.filename)
        path = os.path.join(UPLOAD_DIR, "%s_%s" % (session["verified_mobile"], safe_fname))
        with open(path, "wb") as out:
            out.write(content)
        session["doc_path"] = path
        return redirect(url_for("declaration"))
    return render_template("upload.html")


@app.route("/declaration", methods=["GET", "POST"])
def declaration():
    if not session.get("verified_mobile"):
        flash("Session expired. Please verify your mobile number again.")
        return redirect(url_for("apply"))
    if request.method == "POST":
        return handle_submission()
    return render_template("declaration.html")


def handle_submission():
    # TODO: split this up some day. It grew. - RK, 09/2024
    mobile = session.get("verified_mobile")
    data = session.get("form_data", {})
    doc_path = session.get("doc_path", "")

    name = sanitize(data.get("applicant_name", ""))
    village = data.get("village", "").strip()
    block = data.get("block", "").strip()
    gender = data.get("gender", "")
    marital = data.get("marital_status", "")
    husband_name = data.get("husband_name", "")
    husband_employer = data.get("husband_employer", "")
    bank_account = data.get("bank_account", "").strip()
    ifsc = data.get("ifsc", "").strip().upper()
    dob_raw = data.get("dob", "").strip()

    if not name:
        flash("Please provide the full name of the applicant.")
        return redirect(url_for("form_step", step=1))
    if not village or not block:
        flash("Please enter complete address details (Village and Block).")
        return redirect(url_for("form_step", step=2))
    if not bank_account or not ifsc:
        flash("Please enter valid bank account and IFSC details.")
        return redirect(url_for("form_step", step=3))
    if not dob_raw:
        flash("Please enter a valid Date of Birth in DD/MM/YYYY format.")
        return redirect(url_for("form_step", step=1))

    # Parse date prioritizing Indian standard format DD/MM/YYYY
    dob = None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            dob = datetime.strptime(dob_raw, fmt).date()
            break
        except ValueError:
            continue
    if dob is None:
        flash("Invalid Date of Birth format. Please enter as DD/MM/YYYY.")
        return redirect(url_for("form_step", step=1))

    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age < MIN_AGE:
        flash("Applicant must be at least %d years of age to be eligible." % MIN_AGE)
        return redirect(url_for("form_step", step=1))

    if datetime.now() > SCHEME_DEADLINE:
        flash("The application deadline has passed.")
        return redirect(url_for("index"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM applications WHERE mobile = %s", (mobile,))
    if cur.fetchone()[0] > 0:
        cur.close(); conn.close()
        flash("An application already exists for this mobile number. "
              "Duplicate applications are not permitted.")
        return redirect(url_for("index"))

    app_no = new_application_no()
    cur.execute(
        """INSERT INTO applications
           (application_no, applicant_name, mobile, dob, gender, marital_status,
            husband_name, husband_employer, village, block, bank_account, ifsc,
            doc_path, status, submitted_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING',%s)
           RETURNING id""",
        (app_no, name, mobile, dob, gender, marital, husband_name,
         husband_employer, village, block, bank_account, ifsc, doc_path,
         datetime.now()))
    new_id = cur.fetchone()[0]

    # status portal account; password is DOB as DDMMYYYY per dept. circular
    portal_pass = dob.strftime("%d%m%Y")
    cur.execute("SELECT count(*) FROM portal_users WHERE mobile = %s", (mobile,))
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO portal_users (mobile, password_hash) VALUES (%s,%s)",
                    (mobile, hash_password(portal_pass)))
    conn.commit()

    app.logger.info("generating acknowledgment pdf application=%d" % new_id)
    pdf_bytes = generate_acknowledgment(cur, new_id)
    ack_dir = os.path.join(UPLOAD_DIR, "ack")
    os.makedirs(ack_dir, exist_ok=True)
    with open(os.path.join(ack_dir, "%d.pdf" % new_id), "wb") as out:
        out.write(pdf_bytes)

    cur.close(); conn.close()
    session.pop("form_data", None)
    session.pop("doc_path", None)
    session.pop("verified_mobile", None)
    send_sms(mobile, "Sewa Setu: application %s received. Track at the status portal "
                     "with mobile no. and password (DOB as DDMMYYYY)." % app_no)
    return render_template("confirmation.html", app_no=app_no, app_id=new_id)


def generate_acknowledgment(cur, app_id):
    cur.execute("SELECT application_no, applicant_name, mobile, dob, village, block, "
                "bank_account, ifsc, submitted_at, status FROM applications WHERE id = %s",
                (app_id,))
    row = cur.fetchone()
    pdf = FPDF()
    pdf.add_page()

    fonts_dir = os.path.join(BASE_DIR, "fonts")
    latin_font = os.path.join(fonts_dir, "NotoSans-Regular.ttf")
    bengali_font = os.path.join(fonts_dir, "NotoSansBengali-Regular.ttf")

    if os.path.exists(latin_font):
        pdf.add_font("NotoSans", "", latin_font)
        pdf.set_font("NotoSans", "", 12)
        font_name = "NotoSans"
    else:
        pdf.set_font("Helvetica", "", 12)
        font_name = "Helvetica"

    if os.path.exists(bengali_font):
        pdf.add_font("NotoBengali", "", bengali_font)
        pdf.set_fallback_fonts(["NotoBengali"])

    # Header
    pdf.set_font(font_name, "", 14)
    pdf.cell(0, 10, "GOVERNMENT OF PURVANCHAL", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(font_name, "", 11)
    pdf.cell(0, 8, "Department of Social Welfare", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "Old Age Pension Scheme - Acknowledgment", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Approved decorative border (optimized from 4000-line loop to vector lines)
    pdf.set_line_width(0.8)
    pdf.line(10, 12, 200, 12)
    pdf.line(10, 282, 200, 282)
    pdf.set_line_width(0.2)

    labels = ["Application No", "Applicant Name", "Mobile", "Date of Birth",
              "Village", "Block", "Bank Account", "IFSC", "Submitted At", "Status"]
    pdf.set_font(font_name, "", 10)
    for label, val in zip(labels, row):
        try:
            pdf.cell(60, 8, label, border=1)
            pdf.cell(0, 8, str(val) if val is not None else "", border=1, new_x="LMARGIN", new_y="NEXT")
        except Exception:
            pdf.cell(0, 8, str(val).encode("ascii", "replace").decode("ascii") if val else "", border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_font(font_name, "", 9)
    pdf.multi_cell(0, 5, "This is a computer generated acknowledgment. Processing SLA "
                         "as per the Purvanchal Right to Public Services Act applies.")
    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# Status portal (citizen login)
# ---------------------------------------------------------------------------

@app.route("/status", methods=["GET", "POST"])
def status_login():
    if request.method == "POST":
        mobile = request.form.get("mobile", "").strip()
        password = request.form.get("password", "")

        # Candidate passwords to support natural variations in DOB entry
        # (e.g. DDMMYYYY, DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD, spaces, swapped month/day)
        candidates = set()
        if password:
            candidates.add(password)
            candidates.add(password.strip())
            clean = re.sub(r"[^0-9a-zA-Z]", "", password)
            if clean:
                candidates.add(clean)
                if len(clean) == 8 and clean.isdigit():
                    # DDMMYYYY <-> MMDDYYYY
                    candidates.add(clean[2:4] + clean[0:2] + clean[4:])
                    # YYYYMMDD -> DDMMYYYY
                    candidates.add(clean[6:8] + clean[4:6] + clean[0:4])
                    # DDMMYYYY -> YYYYMMDD
                    candidates.add(clean[4:8] + clean[2:4] + clean[0:2])

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM portal_users WHERE mobile = %s", (mobile,))
        row = cur.fetchone()
        cur.close(); conn.close()

        matched = False
        if row:
            for cand in candidates:
                if row[0] == hash_password(cand):
                    matched = True
                    break

        # Fallback: check applications table DOB for this mobile
        if not matched and mobile:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT dob FROM applications WHERE mobile = %s ORDER BY submitted_at DESC LIMIT 1", (mobile,))
            app_row = cur.fetchone()
            cur.close(); conn.close()
            if app_row and app_row[0]:
                expected_dob = app_row[0].strftime("%d%m%Y")
                if any(cand == expected_dob for cand in candidates):
                    matched = True
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO portal_users (mobile, password_hash)
                        VALUES (%s, %s)
                        ON CONFLICT (mobile) DO UPDATE SET password_hash = EXCLUDED.password_hash
                    """, (mobile, hash_password(expected_dob)))
                    conn.commit()
                    cur.close(); conn.close()

        if matched:
            session["logged_in"] = True
            session["portal_mobile"] = mobile
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT id FROM applications WHERE mobile = %s "
                        "ORDER BY submitted_at DESC LIMIT 1", (mobile,))
            r = cur.fetchone()
            cur.close(); conn.close()
            if r:
                return redirect(url_for("view_application", app_id=r[0]))
            flash("No application found for this mobile number.")
            return redirect(url_for("status_login"))
        flash("Invalid mobile number or password. Default password is your Date of Birth in DDMMYYYY format (e.g. 15081958).")
    return render_template("status_login.html")


@app.route("/application/<int:app_id>")
def view_application(app_id):
    if not session.get("logged_in"):
        flash("Please login to view application status.")
        return redirect(url_for("status_login"))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT application_no, applicant_name, mobile, dob, village, block, "
                "bank_account, ifsc, status, submitted_at, decided_at "
                "FROM applications WHERE id = %s", (app_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        abort(404)
    # Authorization check: only admin or the application owner can view
    if not session.get("admin") and session.get("portal_mobile") != row[2]:
        abort(403)
    return render_template("application.html", a=row, app_id=app_id)


@app.route("/application/<int:app_id>/edit", methods=["GET", "POST"])
def edit_application(app_id):
    if not session.get("logged_in"):
        flash("Please login to edit your application.")
        return redirect(url_for("status_login"))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT application_no, applicant_name, mobile, dob, gender, "
                "marital_status, husband_name, village, block, bank_account, ifsc, status "
                "FROM applications WHERE id = %s", (app_id,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        abort(404)
    # Authorization check: only admin or the application owner can edit
    if not session.get("admin") and session.get("portal_mobile") != row[2]:
        cur.close(); conn.close()
        abort(403)
    # Decided applications cannot be edited
    if row[11] != "PENDING":
        cur.close(); conn.close()
        flash("Only pending applications can be edited. This application has already been decided.")
        return redirect(url_for("view_application", app_id=app_id))

    if request.method == "POST":
        name = sanitize(request.form.get("applicant_name", ""))
        dob_raw = request.form.get("dob", "").strip()
        gender = request.form.get("gender", "")
        marital = request.form.get("marital_status", "")
        husband_name = request.form.get("husband_name", "").strip()
        village = request.form.get("village", "").strip()
        block = request.form.get("block", "").strip()
        bank_account = request.form.get("bank_account", "").strip()
        ifsc = request.form.get("ifsc", "").strip().upper()

        if not name or not village or not block or not bank_account or not ifsc or not dob_raw:
            flash("All required fields must be filled.")
            cur.close(); conn.close()
            return render_template("application_edit.html", a=row, app_id=app_id, blocks=BLOCKS)

        dob = None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                dob = datetime.strptime(dob_raw, fmt).date()
                break
            except ValueError:
                continue
        if dob is None:
            flash("Invalid Date of Birth format. Please enter as DD/MM/YYYY.")
            cur.close(); conn.close()
            return render_template("application_edit.html", a=row, app_id=app_id, blocks=BLOCKS)

        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age < MIN_AGE:
            flash("Applicant must be at least %d years of age to be eligible." % MIN_AGE)
            cur.close(); conn.close()
            return render_template("application_edit.html", a=row, app_id=app_id, blocks=BLOCKS)

        # Update in-place: preserves single application rule, strictly prevents duplicates
        cur.execute(
            """UPDATE applications
               SET applicant_name = %s, dob = %s, gender = %s, marital_status = %s,
                   husband_name = %s, village = %s, block = %s, bank_account = %s, ifsc = %s
               WHERE id = %s AND status = 'PENDING'""",
            (name, dob, gender, marital, husband_name, village, block, bank_account, ifsc, app_id)
        )
        # Update portal login password to match corrected date of birth
        new_pass = dob.strftime("%d%m%Y")
        cur.execute("UPDATE portal_users SET password_hash = %s WHERE mobile = %s",
                    (hash_password(new_pass), row[2]))
        conn.commit()

        # Refresh cached PDF acknowledgment if it was already generated
        try:
            ack_file = os.path.join(UPLOAD_DIR, "ack", "%d.pdf" % app_id)
            if os.path.exists(ack_file):
                pdf_bytes = generate_acknowledgment(cur, app_id)
                with open(ack_file, "wb") as out:
                    out.write(pdf_bytes)
        except Exception as e:
            app.logger.error("error refreshing ack pdf: %s" % e)

        cur.close(); conn.close()
        send_sms(row[2], "Sewa Setu: your application %s details have been updated." % row[0])
        flash("Application details updated successfully.")
        return redirect(url_for("view_application", app_id=app_id))

    cur.close(); conn.close()
    return render_template("application_edit.html", a=row, app_id=app_id, blocks=BLOCKS)


@app.route("/ack/<int:app_id>.pdf")
def ack_pdf(app_id):
    # Enforce authentication: prevent public scraping of citizen bank accounts and PII
    if not session.get("logged_in"):
        flash("Please login to download the acknowledgment receipt.")
        return redirect(url_for("status_login"))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT mobile FROM applications WHERE id = %s", (app_id,))
    app_row = cur.fetchone()
    if not app_row:
        cur.close(); conn.close()
        abort(404)
    if not session.get("admin") and session.get("portal_mobile") != app_row[0]:
        cur.close(); conn.close()
        abort(403)

    path = os.path.join(UPLOAD_DIR, "ack", "%d.pdf" % app_id)
    if not os.path.exists(path):
        data = generate_acknowledgment(cur, app_id)
        cur.close(); conn.close()
        return send_file(io.BytesIO(data), mimetype="application/pdf")
    cur.close(); conn.close()
    return send_file(path, mimetype="application/pdf")


@app.route("/status/reset", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        mobile = request.form.get("mobile", "").strip()
        conn = get_db()
        cur = conn.cursor()
        # Parameterized queries to prevent SQL injection
        cur.execute("SELECT mobile FROM portal_users WHERE mobile = %s", (mobile,))
        row = cur.fetchone()
        if row:
            cur.execute("SELECT dob FROM applications WHERE mobile = %s LIMIT 1", (mobile,))
            r2 = cur.fetchone()
            if r2:
                newpass = r2[0].strftime("%d%m%Y")
                cur.execute("UPDATE portal_users SET password_hash = %s WHERE mobile = %s",
                            (hash_password(newpass), row[0]))
                conn.commit()
                send_sms(row[0], "Sewa Setu: your password has been reset to your "
                                 "date of birth (DDMMYYYY).")
        cur.close(); conn.close()
        flash("If the mobile number exists, the password has been reset and sent by SMS.")
    return render_template("reset.html")


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if (request.form.get("username") == ADMIN_USERNAME and
                request.form.get("password") == ADMIN_PASSWORD):
            session["logged_in"] = True
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Invalid credentials.")
    return render_template("admin_login.html")


@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT status, count(*) FROM applications GROUP BY status")
    by_status = cur.fetchall()
    cur.execute("SELECT count(*) FROM applications WHERE status = 'PENDING' "
                "AND submitted_at < %s", (datetime.now() - timedelta(days=SLA_DAYS),))
    overdue = cur.fetchone()[0]
    cur.execute("SELECT block, count(*) FROM applications WHERE status = 'PENDING' "
                "GROUP BY block ORDER BY count(*) DESC")
    by_block = cur.fetchall()
    cur.close(); conn.close()
    return render_template("admin_dashboard.html", by_status=by_status,
                           overdue=overdue, by_block=by_block, sla=SLA_DAYS)


@app.route("/admin/applications")
def admin_list():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    status = request.args.get("status", "")
    q = request.args.get("q", "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    # Default to PENDING if neither search query nor status is specified
    if not q and not status:
        status = "PENDING"

    where_clauses = []
    params = []

    if status:
        where_clauses.append("status = %s")
        params.append(status)

    if q:
        where_clauses.append(
            "(applicant_name ILIKE %s OR application_no ILIKE %s OR mobile ILIKE %s OR bank_account ILIKE %s)"
        )
        like_q = f"%{q}%"
        params.extend([like_q, like_q, like_q, like_q])

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT count(*) FROM applications {where_sql}", tuple(params))
    total_count = cur.fetchone()[0]

    limit = 50
    offset = (page - 1) * limit
    cur.execute(
        f"SELECT id, application_no, applicant_name, mobile, block, status, "
        f"submitted_at FROM applications {where_sql} "
        f"ORDER BY submitted_at DESC LIMIT %s OFFSET %s",
        tuple(params + [limit, offset])
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return render_template(
        "admin_list.html",
        rows=rows,
        status=status,
        page=page,
        q=q,
        total_count=total_count
    )


@app.route("/admin/application/<int:app_id>")
def admin_view(app_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT application_no, applicant_name, mobile, dob, gender, "
                "marital_status, village, block, bank_account, ifsc, doc_path, "
                "status, submitted_at, decided_at, decided_by "
                "FROM applications WHERE id = %s", (app_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        abort(404)
    return render_template("admin_view.html", a=row, app_id=app_id)


@app.route("/admin/approve/<int:app_id>", methods=["POST"])
def admin_approve(app_id):
    if not session.get("admin"):
        abort(403)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE applications SET status = 'APPROVED', decided_at = %s, decided_by = %s "
                "WHERE id = %s", (datetime.now(), session.get("admin_user", "admin"), app_id))
    conn.commit()
    cur.close(); conn.close()
    flash("Application approved.")
    return redirect(url_for("admin_list"))


@app.route("/admin/reject/<int:app_id>", methods=["POST"])
def admin_reject(app_id):
    if not session.get("admin"):
        abort(403)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE applications SET status = 'REJECTED', decided_at = %s, decided_by = %s "
                "WHERE id = %s", (datetime.now(), session.get("admin_user", "admin"), app_id))
    conn.commit()
    cur.close(); conn.close()
    flash("Application rejected.")
    return redirect(url_for("admin_list"))


# ---------------------------------------------------------------------------
# Unused / legacy
# ---------------------------------------------------------------------------

def export_to_excel(rows):
    # Was used for the monthly disbursement report before eKosh integration.
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["application_no", "name", "account", "ifsc", "amount"])
    for r in rows:
        writer.writerow(list(r) + ["250"])
    return out.getvalue()


def old_payment_gateway_callback(txn):
    # retained for reference; eChallan integration was descoped in Phase 2
    status = txn.get("STATUS")
    if status == "0300":
        return "SUCCESS"
    elif status == "0399":
        return "FAILED"
    return "PENDING"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
