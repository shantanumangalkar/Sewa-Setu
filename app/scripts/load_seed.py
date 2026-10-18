# -*- coding: utf-8 -*-
"""
Helper script to load seed/seed.sql into the target database.
Supports both DATABASE_URL (Render/Railway) and local app.ini config.
"""

import os
import sys
import psycopg2

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(BASE_DIR)

def get_connection():
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return psycopg2.connect(db_url)
    
    import configparser
    config = configparser.ConfigParser()
    config.read(os.path.join(BASE_DIR, "config", "app.ini"))
    return psycopg2.connect(
        host=os.getenv("DB_HOST", config.get("database", "host", fallback="127.0.0.1")),
        port=os.getenv("DB_PORT", config.get("database", "port", fallback="5432")),
        dbname=os.getenv("DB_NAME", config.get("database", "name", fallback="sewasetu")),
        user=os.getenv("DB_USER", config.get("database", "user", fallback="sewasetu")),
        password=os.getenv("DB_PASSWORD", config.get("database", "password", fallback="sewasetu123")),
    )

def main():
    seed_path = os.path.join(ROOT_DIR, "seed", "seed.sql")
    if not os.path.exists(seed_path):
        seed_path = os.path.join(BASE_DIR, "seed", "seed.sql")
    if not os.path.exists(seed_path):
        print("seed.sql not found at %s" % seed_path)
        sys.exit(1)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM applications;")
    count = cur.fetchone()[0]
    print("Current application count:", count)
    if count >= 100000:
        print("Database already contains >= 100,000 records. Skipping seed.")
        cur.close()
        conn.close()
        return

    print("Loading seed records from %s (this takes ~15-30 seconds)..." % seed_path)
    with open(seed_path, "r", encoding="utf-8") as f:
        cur.execute(f.read())
    conn.commit()
    cur.execute("SELECT count(*) FROM applications;")
    new_count = cur.fetchone()[0]
    print("Seed loaded successfully! New application count: %d" % new_count)
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
