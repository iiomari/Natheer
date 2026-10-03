"""Fictional related tables for the demo database, and their idempotent provisioning.

patients (PK patient_id) and appointments (FK patient_id -> patients). All values are generated.

Provisioning runs on the hosted API at startup only when DEMO_DB_RO_PASSWORD is set: with the main
database's admin URL (private network) it creates the database `nazeer_demo_source`, a user
`nazeer_demo_ro` with SELECT only, and the two tables (filled once). Nothing secret is logged.
"""
from __future__ import annotations

import logging
import os
import random
from datetime import date, timedelta

import pandas as pd

log = logging.getLogger("nazeer_api.demo_seed")
DB, USER = "nazeer_demo_source", "nazeer_demo_ro"
MALE = ["سلمان", "تركي", "فيصل", "حمد", "ناصر", "عبدالرحمن", "يوسف", "معاذ", "أسامة", "هاني", "نواف", "سامي"]
FEMALE = ["أمل", "فاطمة", "خلود", "روان", "ليان", "جواهر", "نورة", "حصة", "مشاعل", "منى", "سلمى", "عبير"]
FAMILY = ["الشهراني", "المري", "الهاجري", "العجمي", "السديري", "التميمي", "الكثيري", "باوزير", "الزامل", "النعيمي"]
CITIES = ["الرياض", "جدة", "الدمام", "مكة المكرمة", "المدينة المنورة", "أبها", "تبوك"]
CLINICS = ["الباطنية", "الأطفال", "العيون", "الأسنان", "الجلدية", "العظام"]
NOTES = ["أكّد المريض الموعد عبر الرسائل", "يفضّل المريض المواعيد الصباحية", "يحتاج تحاليل قبل الزيارة",
         "حضر المريض مبكراً وأنهى التسجيل", "طلب المريض تغيير الطبيب المعالج"]

DDL = [
    "DROP TABLE IF EXISTS appointments",
    "DROP TABLE IF EXISTS patients",
    """CREATE TABLE patients (patient_id VARCHAR(16) PRIMARY KEY, full_name VARCHAR(80) NOT NULL,
       gender VARCHAR(8), national_id VARCHAR(10) NOT NULL, mobile VARCHAR(10), birth_year INT, city VARCHAR(40))""",
    """CREATE TABLE appointments (appointment_id VARCHAR(16) PRIMARY KEY, patient_id VARCHAR(16) NOT NULL,
       clinic VARCHAR(40), appointment_date DATE, reminder_sent INT, no_show INT, reception_note VARCHAR(200),
       FOREIGN KEY (patient_id) REFERENCES patients(patient_id))""",
]


def _national(rng: random.Random, first: str) -> str:
    digits = [int(first)] + [rng.randrange(10) for _ in range(8)]
    total = sum((d * 2) // 10 + (d * 2) % 10 if i % 2 == 0 else d for i, d in enumerate(digits))
    return "".join(map(str, digits)) + str((10 - total % 10) % 10)


def _mobile(rng: random.Random) -> str:
    return "05" + str(rng.choice([0, 3, 4, 5, 6, 9])) + "".join(str(rng.randrange(10)) for _ in range(7))


def build(seed: int = 21, patients: int = 300, appointments: int = 900) -> dict[str, pd.DataFrame]:
    rng = random.Random(seed)
    p_rows = []
    for i in range(patients):
        female = rng.random() < 0.5
        p_rows.append({"patient_id": f"PT-{i + 1:05d}",
                       "full_name": f"{rng.choice(FEMALE if female else MALE)} {rng.choice(FAMILY)}",
                       "gender": "أنثى" if female else "ذكر", "national_id": _national(rng, "1" if rng.random() < 0.8 else "2"),
                       "mobile": _mobile(rng), "birth_year": rng.randint(1945, 2020), "city": rng.choice(CITIES)})
    a_rows, start = [], date(2026, 1, 3)
    for j in range(appointments):
        note = rng.choice(NOTES)
        if rng.random() < 0.08:
            note = f"طلب المريض التواصل على الرقم {_mobile(rng)} لتأكيد الموعد"
        a_rows.append({"appointment_id": f"AP-{j + 1:06d}", "patient_id": rng.choice(p_rows)["patient_id"],
                       "clinic": rng.choice(CLINICS), "appointment_date": (start + timedelta(days=rng.randrange(0, 200))).isoformat(),
                       "reminder_sent": rng.choice([0, 1]), "no_show": int(rng.random() < 0.18), "reception_note": note})
    return {"patients": pd.DataFrame(p_rows), "appointments": pd.DataFrame(a_rows)}


def write(url, tables: dict[str, pd.DataFrame]) -> None:
    from sqlalchemy import create_engine, text

    eng = create_engine(url)
    with eng.begin() as conn:
        for stmt in DDL:
            conn.execute(text(stmt))
        for name in ("patients", "appointments"):
            tables[name].to_sql(name, conn, if_exists="append", index=False)
    eng.dispose()


def provision_from_env() -> None:
    """Hosted API startup hook. Never raises: the demo database is optional."""
    pw = os.environ.get("DEMO_DB_RO_PASSWORD", "")
    admin = os.environ.get("DATABASE_URL", "")
    if not pw or not admin.startswith("mysql"):
        return
    try:
        from sqlalchemy import create_engine, inspect, text
        from sqlalchemy.engine import make_url

        root = make_url(admin.replace("mysql://", "mysql+pymysql://", 1))
        eng = create_engine(root.set(database="mysql"))
        with eng.begin() as c:
            c.execute(text(f"CREATE DATABASE IF NOT EXISTS {DB} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
            c.execute(text(f"CREATE USER IF NOT EXISTS '{USER}'@'%' IDENTIFIED BY :pw"), {"pw": pw})
            c.execute(text(f"ALTER USER '{USER}'@'%' IDENTIFIED BY :pw"), {"pw": pw})
            c.execute(text(f"GRANT SELECT ON {DB}.* TO '{USER}'@'%'"))
        eng.dispose()
        target = root.set(database=DB, query={"charset": "utf8mb4"})
        eng = create_engine(target)
        with eng.connect() as c:
            have = set(inspect(c).get_table_names())
        eng.dispose()
        if not {"patients", "appointments"} <= have:
            write(target, build())
            log.info("demo database seeded (patients, appointments)")
        else:
            log.info("demo database ready")
    except Exception as e:  # noqa: BLE001 - optional; never echo URLs or driver messages
        log.warning("demo database provisioning skipped (%s)", type(e).__name__)
