# Sewa Setu — Old Age Pension Portal
> **Government of Purvanchal &middot; Department of Social Welfare**  
> *Build for Bharat Digital Fellowship 2027 &mdash; Full System Audit, Remediation & Cloud Modernization*

[![Tests](https://img.shields.io/badge/tests-24%20passed-brightgreen.svg)](#automated-testing)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.14-blue.svg)](https://www.python.org/)
[![Database](https://img.shields.io/badge/database-PostgreSQL%2017-blue.svg)](https://www.postgresql.org/)
[![Deployment](https://img.shields.io/badge/deployed-Render%20Cloud-success.svg)](https://sewa-setu-09vo.onrender.com)

---

## 🌐 Live Production Deployment

- **Public Citizen Portal**: [https://sewa-setu-09vo.onrender.com](https://sewa-setu-09vo.onrender.com)
- **Administrative Portal**: [https://sewa-setu-09vo.onrender.com/admin](https://sewa-setu-09vo.onrender.com/admin)
  - **Username**: `admin`
  - **Password**: `sewasetu@123`
- **SMS Gateway Mock Console**: [https://sewa-setu-09vo.onrender.com/__gateway/](https://sewa-setu-09vo.onrender.com/__gateway/)
- **Health Check Endpoint**: [https://sewa-setu-09vo.onrender.com/health](https://sewa-setu-09vo.onrender.com/health)

---

## 📌 Executive Summary

**Sewa Setu** is the official state welfare management portal for the **Indira Gandhi National Old Age Pension Scheme (IGNOAPS)** in Purvanchal. Built originally in 2023, the platform suffered from critical operational, security, and performance bottlenecks, leading to citizen grievances, silent SLA violations, and data integrity degradation across 100,000+ historical records.

This repository represents the completed, comprehensive remediation and production hardening undertaken during the **Build for Bharat Fellowship 2027**.

---

## 🛠️ Key Remediations & Technical Innovations

### 1. Statutory 15-Day Deemed Approval Automation (RTPS Act, 2019)
- **The Issue**: Thousands of elderly citizens remained trapped in `PENDING` status for months due to administrative backlog, violating the statutory 15-day service guarantee.
- **Remediation**: Implemented an automated cron daemon (`app/scripts/deemed_approval.py`) that systematically queries pending applications older than 15 days, transitions their status to `DEEMED_APPROVED`, stamps audit metadata (`decided_at`, `decided_by = 'SYSTEM_DEEMED'`), and dispatches SMS confirmation to applicants.

### 2. Privacy & Access Control Protection
- **The Issue**: Citizen acknowledgment receipts (`/ack/<id>.pdf`) were completely unauthenticated, allowing arbitrary scraping of citizen banking details and PII. Additionally, citizens could access other applicants' records (IDOR), and citizens could invoke administrative approval/rejection endpoints.
- **Remediation**:
  - Enforced strict session barriers on `/ack/<id>.pdf` allowing only the authenticated application owner or verified submitter.
  - Mitigated IDOR vulnerabilities on citizen status views.
  - Enforced role-based administrative checks (`session.get("admin")`) on `/admin/approve/<id>` and `/admin/reject/<id>`.

### 3. Unicode & Indic/Assamese Name Preservation
- **The Issue**: UTF-8 multi-byte Assamese and Bengali characters were truncated by byte-slicing logic (`value[:maxlen]`), producing corrupted corrupted glyphs and failing PDF generation.
- **Remediation**: Sanitization now respects unicode codepoints up to the `VARCHAR(100)` database schema length. Configured FPDF2 with Latin and Bengali Noto Sans font fallbacks to guarantee legible rendering of Indic citizen names.

### 4. Form Accessibility & Data Quality
- **The Issue**: Valid JPG uploads were rejected, file sizes were restricted to an undocumented 100 KB limit, widows were blocked by mandatory deceased husband employer fields, and non-standard mobile number formats threw generic server errors.
- **Remediation**:
  - Expanded document upload handler to accept both PDF and JPG/PNG up to 5 MB.
  - Prioritized Indian standard `DD/MM/YYYY` date parsing over ambiguous US `MM/DD/YYYY` formats.
  - Relaxed validation constraints for widows (`marital_status == 'Widow'`).
  - Added mobile number normalization stripping leading `+91`, `0`, spaces, and dashes.

### 5. High-Performance Database Indexing (100k+ Records)
- **The Issue**: Queries on the 100,000+ historical record dataset triggered exhaustive sequential table scans (`Seq Scan`), causing server lag and query timeouts.
- **Remediation**: Built optimized composite B-tree indexes:
  - `idx_applications_mobile` on `applications(mobile)`
  - `idx_applications_app_no` on `applications(application_no)`
  - `idx_applications_status_submitted` on `applications(status, submitted_at)`
  - `idx_applications_block_status` on `applications(block, status)`

### 6. Citizen Self-Correction Workflow
- **The Issue**: Applicants with minor spelling mistakes in their names or IFSC codes were forced to submit duplicate applications, causing fraud alerts and rejected records.
- **Remediation**: Added an in-place editing workflow (`/application/<id>/edit`) for `PENDING` claims that updates records and synchronizes portal passwords without creating duplicate entries. Decided records remain immutable.

### 7. Administrative Command Center & Multi-Field Search
- **The Issue**: District administrators could not search or filter applications efficiently across high volumes.
- **Remediation**: Implemented a responsive administration dashboard with district-wise workload breakdown, overdue SLA tracking, and multi-field search across applicant names, application numbers, mobile numbers, and bank account numbers.

### 8. Enterprise Security Hardening
- **Anti-CSRF Protection**: Native cryptographic token verification (`generate_csrf_token()`) across all forms via automatic request interception (`@app.before_request`) and response injection (`@app.after_request`).
- **Salted Password Hashing**: Upgraded password storage from unsalted single-round SHA-256 to modern salted hashes (`werkzeug.security.generate_password_hash`), with backward compatibility and auto-upgrade for existing records.
- **CAPTCHA Bot Protection**: Server-side math CAPTCHA verification on `/apply` preventing automated SMS toll fraud and bot spam.
- **Brute-Force Rate Limiting**:
  - Citizen OTP verification: 5-attempt limit with automatic OTP invalidation and replay protection.
  - Administrative login: 15-minute lockout (HTTP 429) after 5 failed attempts from any IP.

---

### 📄 Official Redesigned Acknowledgment Receipt

The citizen PDF receipt (`/ack/<id>.pdf`) has been rebuilt to official government standards:
- **Framing**: Clean double-line outer border (`10mm` margins) with centered state department typography and saffron brand accent line.
- **Data Table**: Balanced 2-column layout with 55mm shaded label cells (`#f4f7fa`) and 125mm clean value cells.
- **Date Formatting**: Citizen-friendly timestamps (`DD/MM/YYYY` and `DD/MM/YYYY HH:MM AM/PM`).
- **Legal Guarantee Callout**: Embedded RTPS Statutory SLA box outlining the 15-day deemed approval guarantee.
- **Legal Watermark**: Bottom tracking URL and computer-generated acknowledgment disclaimer.

---

## 🧪 Automated Testing

The repository includes a comprehensive automated test suite covering all functional, architectural, and security invariants:

```bash
python -m pytest tests/
```

### Test Coverage Summary (24 Passing Tests)
| Test Module | Focus Area | Status |
| :--- | :--- | :---: |
| `test_fix1_deemed_approval.py` | RTPS statutory 15-day auto-approval automation | ✅ Passed |
| `test_fix2_security_privacy.py` | PDF access barriers, IDOR prevention, RBAC, SQL injection | ✅ Passed |
| `test_fix3_unicode_names.py` | Unicode Assamese/Bengali text preservation & rendering | ✅ Passed |
| `test_fix4_form_accessibility.py` | 5MB uploads, DD/MM/YYYY parsing, widow validation, mobile normalization | ✅ Passed |
| `test_fix5_performance_database.py` | B-tree index coverage & query plan verification on 100k+ rows | ✅ Passed |
| `test_fix6_application_correction.py` | In-place editing without duplicates & immutability of decided claims | ✅ Passed |
| `test_fix7_admin_search.py` | Multi-field search and pagination across 100,000+ records | ✅ Passed |
| `test_fix8_hardened_security.py` | Math CAPTCHA validation, salted password hashes, anti-CSRF, rate limiting | ✅ Passed |

---

## 🚀 Running Locally

### Option 1: Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/shantanumangalkar/Sewa-Setu.git
cd Sewa-Setu

# Spin up web app, SMS gateway, and PostgreSQL container
docker compose up --build
```
- Web Application: `http://localhost:8000`
- Simulated SMS Gateway: `http://localhost:8000/__gateway/`

### Option 2: Python Virtual Environment

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations and load schema
python -c "from app.app import init_db_if_needed; init_db_if_needed()"

# Start local server
python app/app.py
```

---

## 📂 Project Structure

```
Sewa-Setu/
├── app/
│   ├── app.py                     # Main Flask web service & route controllers
│   ├── schema.sql                 # PostgreSQL schema definition & performance indexes
│   ├── config/
│   │   └── app.ini                # Application configuration defaults
│   ├── fonts/                     # Noto Sans Latin and Bengali TrueType fonts
│   ├── scripts/
│   │   ├── deemed_approval.py     # 15-day statutory RTPS cron worker
│   │   └── load_seed.py           # Database seeder utility
│   └── templates/                 # Jinja2 HTML templates
├── smsgw/
│   └── app.py                     # Mock telecom SMS gateway service
├── tests/                         # Pytest automated test suite (24 tests)
├── docker-compose.yml             # Local multi-container orchestration
├── Dockerfile                     # Production container specification
├── Procfile                       # PaaS process file (Render / Gunicorn)
├── render.yaml                    # Infrastructure-as-Code for Render Cloud
└── README.md                      # Comprehensive project documentation
```

---

## 📜 License & Compliance

Developed for the **Department of Social Welfare, Government of Purvanchal** under the **Right to Public Services (RTPS) Act, 2019**. All personal citizen data is sanitized and protected under standard government data protection guidelines.
