# -*- coding: utf-8 -*-
"""
Nightly deemed-approval job.

Under the Purvanchal Right to Public Services Act, an application not processed
within the statutory SLA stands approved. This job marks such applications
DEEMED_APPROVED and notifies the applicant by SMS.

Scheduled via cron, 02:00 daily. See deploy/crontab.
"""

import os
import sys
import configparser
from datetime import datetime, timedelta

import psycopg2
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

config = configparser.ConfigParser()
# In CR-2026-031, settings.ini was consolidated to app.ini
CONFIG_PATH = os.path.join(BASE_DIR, "config", "app.ini")
if not os.path.exists(CONFIG_PATH):
    CONFIG_PATH = os.path.join(BASE_DIR, "config", "settings.ini")
with open(CONFIG_PATH) as fh:
    config.read_file(fh)

SLA_DAYS = int(os.getenv("SLA_DAYS", config.getint("pension", "sla_days", fallback=15)))
SMS_GATEWAY_URL = os.getenv("SMS_GATEWAY_URL", config.get("app", "sms_gateway_url", fallback="http://127.0.0.1:8025"))


def main():
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(db_url)
    else:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", config.get("database", "host", fallback="127.0.0.1")),
            port=os.getenv("DB_PORT", config.get("database", "port", fallback="5432")),
            dbname=os.getenv("DB_NAME", config.get("database", "name", fallback="sewasetu")),
            user=os.getenv("DB_USER", config.get("database", "user", fallback="sewasetu")),
            password=os.getenv("DB_PASSWORD", config.get("database", "password", fallback="sewasetu123")),
        )
    cur = conn.cursor()
    cutoff = datetime.now() - timedelta(days=SLA_DAYS)
    cur.execute(
        """UPDATE applications
           SET status = 'DEEMED_APPROVED', decided_at = %s, decided_by = 'RTPS-AUTO'
           WHERE status = 'PENDING' AND submitted_at < %s
           RETURNING application_no, mobile""",
        (datetime.now(), cutoff))
    rows = cur.fetchall()
    conn.commit()
    for app_no, mobile in rows:
        try:
            requests.post(SMS_GATEWAY_URL + "/api/send", json={
                "to": mobile,
                "text": "Sewa Setu: your pension application %s stands approved "
                        "under the RTPS Act." % app_no}, timeout=5)
        except Exception:
            pass
    print("%s deemed approval: %d applications approved"
          % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), len(rows)))
    cur.close()
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
