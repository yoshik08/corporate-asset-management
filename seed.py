"""Seed realistic demo data for the Corporate Asset Management System.

Deterministic (random.seed(7)) so re-seeding always gives the same data.
Maintenance history is generated per category at realistic intervals
(laptop ~90d, phone ~120d, vehicle ~60d, equipment ~180d) with jitter,
which is what the predictor trains on.

Usage:  python seed.py           (wipes and re-seeds the database)
"""
import random
import sqlite3
from datetime import date, timedelta

from db import DB_PATH, audit, get_connection, init_db

random.seed(7)
TODAY = date(2026, 10, 31)

EMPLOYEES = [
    ("Aarav Mehta", "aarav.mehta@techcore.in", "Engineering", "Senior Software Engineer", "9876543210", "2023-04-10"),
    ("Priya Sharma", "priya.sharma@techcore.in", "Design", "Product Designer", "9876543211", "2023-06-01"),
    ("Rahul Verma", "rahul.verma@techcore.in", "Engineering", "DevOps Engineer", "9876543212", "2022-11-15"),
    ("Sneha Iyer", "sneha.iyer@techcore.in", "HR", "HR Manager", "9876543213", "2022-08-20"),
    ("Vikram Rao", "vikram.rao@techcore.in", "Sales", "Regional Sales Lead", "9876543214", "2023-01-09"),
    ("Ananya Gupta", "ananya.gupta@techcore.in", "Finance", "Finance Analyst", "9876543215", "2024-02-12"),
    ("Karthik Nair", "karthik.nair@techcore.in", "Engineering", "QA Engineer", "9876543216", "2023-09-05"),
    ("Divya Reddy", "divya.reddy@techcore.in", "Operations", "Office Manager", "9876543217", "2022-05-18"),
    ("Arjun Singh", "arjun.singh@techcore.in", "Engineering", "Backend Developer", "9876543218", "2024-05-27"),
    ("Meera Nair", "meera.nair@techcore.in", "Design", "UX Researcher", "9876543219", "2024-08-14"),
    ("Sanjay Patel", "sanjay.patel@techcore.in", "Sales", "Account Executive", "9876543220", "2023-03-22"),
    ("Kavya Menon", "kavya.menon@techcore.in", "Operations", "Logistics Coordinator", "9876543221", "2024-01-15"),
]

# (asset_tag, name, category, brand, model, serial, purchase_date, cost,
#  status, location, usage_hours, condition)
ASSETS = [
    ("AST-LAP-001", "Dell Latitude 5540", "laptop", "Dell", "Latitude 5540", "DL5540-88101", "2023-05-12", 92000, "assigned", "Hyderabad HQ", 4200, "good"),
    ("AST-LAP-002", "MacBook Pro 14", "laptop", "Apple", "MacBook Pro 14 M3", "MBP14-55201", "2024-01-20", 189000, "assigned", "Hyderabad HQ", 3100, "excellent"),
    ("AST-LAP-003", "HP EliteBook 840", "laptop", "HP", "EliteBook 840 G10", "HP840-77120", "2023-08-30", 98000, "assigned", "Hyderabad HQ", 3900, "good"),
    ("AST-LAP-004", "Lenovo ThinkPad T14", "laptop", "Lenovo", "ThinkPad T14 Gen 4", "LTP14-33902", "2024-03-11", 105000, "assigned", "Hyderabad HQ", 2600, "good"),
    ("AST-LAP-005", "Dell XPS 13", "laptop", "Dell", "XPS 13 9340", "DXPS13-90210", "2024-06-25", 135000, "available", "Hyderabad HQ", 1200, "excellent"),
    ("AST-LAP-006", "MacBook Air M3", "laptop", "Apple", "MacBook Air 13 M3", "MBA13-12045", "2024-09-02", 115000, "assigned", "Hyderabad HQ", 900, "excellent"),
    ("AST-LAP-007", "Acer Aspire 5", "laptop", "Acer", "Aspire 5 A515", "AC515-77100", "2022-12-05", 54000, "in_maintenance", "Hyderabad HQ", 6100, "poor"),
    ("AST-PHN-001", "iPhone 15", "phone", "Apple", "iPhone 15 128GB", "IP15-44120", "2023-10-14", 79900, "assigned", "Hyderabad HQ", 2800, "good"),
    ("AST-PHN-002", "Samsung Galaxy S24", "phone", "Samsung", "Galaxy S24 256GB", "SGS24-90211", "2024-02-08", 74999, "assigned", "Hyderabad HQ", 2100, "good"),
    ("AST-PHN-003", "OnePlus 12", "phone", "OnePlus", "OnePlus 12 256GB", "OP12-55310", "2024-04-19", 64999, "available", "Hyderabad HQ", 800, "excellent"),
    ("AST-PHN-004", "iPhone 14", "phone", "Apple", "iPhone 14 128GB", "IP14-22015", "2023-03-27", 69900, "assigned", "Hyderabad HQ", 3400, "fair"),
    ("AST-PHN-005", "Google Pixel 8", "phone", "Google", "Pixel 8 128GB", "GP8-11902", "2024-05-30", 75999, "available", "Hyderabad HQ", 500, "excellent"),
    ("AST-VEH-001", "Hyundai Creta SX", "vehicle", "Hyundai", "Creta SX Diesel", "HY-CRETA-01", "2023-02-10", 1850000, "assigned", "Hyderabad HQ", 48200, "good"),
    ("AST-VEH-002", "Maruti Swift VXi", "vehicle", "Maruti Suzuki", "Swift VXi", "MS-SWIFT-02", "2022-09-18", 720000, "assigned", "Hyderabad HQ", 61500, "fair"),
    ("AST-VEH-003", "Tata Nexon EV", "vehicle", "Tata", "Nexon EV Max", "TT-NEXON-03", "2024-01-15", 1990000, "available", "Hyderabad HQ", 19400, "excellent"),
    ("AST-VEH-004", "Honda Activa 6G", "vehicle", "Honda", "Activa 6G", "HN-ACT-04", "2023-07-22", 92000, "retired", "Hyderabad HQ", 22100, "poor"),
    ("AST-EQP-001", "Epson Projector EB-E01", "equipment", "Epson", "EB-E01", "EP-E01-3301", "2023-04-05", 42000, "available", "Conference Room A", 1500, "good"),
    ("AST-EQP-002", "HP LaserJet Pro M404", "equipment", "HP", "LaserJet Pro M404dn", "HP-M404-2210", "2023-06-14", 28000, "assigned", "Finance Wing", 3200, "good"),
    ("AST-EQP-003", "Dell 27 inch Monitor", "equipment", "Dell", "P2723DE", "DL-P27-8810", "2024-02-20", 24000, "available", "Store Room", 900, "excellent"),
    ("AST-EQP-004", "APC UPS 2KVA", "equipment", "APC", "Smart-UPS 2000VA", "APC-2K-1102", "2022-11-30", 36000, "assigned", "Server Room", 8400, "fair"),
    ("AST-EQP-005", "Cisco Router RV340", "equipment", "Cisco", "RV340", "CS-RV340-09", "2023-01-25", 31000, "assigned", "Server Room", 9100, "good"),
    ("AST-EQP-006", "Logitech Conference Cam", "equipment", "Logitech", "MeetUp", "LG-MU-7712", "2024-07-08", 58000, "available", "Conference Room B", 300, "excellent"),
]

BASE_INTERVAL = {"laptop": 90, "phone": 120, "vehicle": 60, "equipment": 180}

MAINT_DESC = {
    "laptop": [("preventive", "Full hardware diagnostics, fan cleaning, thermal paste check"),
               ("preventive", "OS updates, disk health check, battery calibration"),
               ("corrective", "Keyboard replacement"),
               ("corrective", "SSD replaced after SMART errors"),
               ("corrective", "Battery swelling reported, battery replaced")],
    "phone": [("preventive", "Battery health check, software update, port cleaning"),
              ("preventive", "Screen protector and case replacement"),
              ("corrective", "Cracked screen replaced"),
              ("corrective", "Charging port repaired")],
    "vehicle": [("preventive", "Engine oil and filter change, brake inspection"),
                ("preventive", "Tyre rotation, alignment and coolant top-up"),
                ("corrective", "Clutch plate replacement"),
                ("corrective", "Battery replaced, alternator check")],
    "equipment": [("preventive", "Filter cleaning, lamp hours check"),
                  ("preventive", "Firmware update and calibration"),
                  ("corrective", "Power supply unit replaced"),
                  ("corrective", "Paper feed mechanism repaired")],
}

PERFORMED_BY = {"laptop": "IT Support", "phone": "IT Support",
                "vehicle": "AutoCare Services", "equipment": "Vendor AMC"}
COST_RANGE = {"laptop": (800, 9000), "phone": (500, 12000),
              "vehicle": (2500, 22000), "equipment": (1000, 15000)}


def seed():
    init_db()
    conn = get_connection()
    for t in ("audit_log", "maintenance", "returns", "assignments", "assets", "employees"):
        conn.execute(f"DELETE FROM {t}")
    conn.execute("DELETE FROM sqlite_sequence")

    emp_ids = {}
    for e in EMPLOYEES:
        cur = conn.execute(
            "INSERT INTO employees (name, email, department, role, phone, joined_date)"
            " VALUES (?, ?, ?, ?, ?, ?)", e)
        emp_ids[e[0]] = cur.lastrowid
        audit(conn, "employee", cur.lastrowid, "created",
              {"name": e[0], "department": e[2]})

    asset_ids = {}
    for a in ASSETS:
        cur = conn.execute(
            "INSERT INTO assets (asset_tag, name, category, brand, model, serial_no,"
            " purchase_date, purchase_cost, status, location, usage_hours, condition)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", a)
        asset_ids[a[0]] = cur.lastrowid
        audit(conn, "asset", cur.lastrowid, "created",
              {"asset_tag": a[0], "name": a[1], "category": a[2]})

    # ---- maintenance history (trains the predictor) ----
    for a in ASSETS:
        tag, _name, cat = a[0], a[1], a[2]
        purchase = date.fromisoformat(a[6])
        interval = BASE_INTERVAL[cat]
        d = purchase + timedelta(days=random.randint(50, interval))
        while d <= TODAY:
            mtype, desc = random.choice(MAINT_DESC[cat])
            lo, hi = COST_RANGE[cat]
            cost = random.randint(lo, hi) if mtype == "corrective" else random.randint(lo, lo + 2000)
            nxt = d + timedelta(days=interval + random.randint(-15, 15))
            conn.execute(
                "INSERT INTO maintenance (asset_id, maintenance_date, maintenance_type,"
                " description, cost, performed_by, next_due_date)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (asset_ids[tag], d.isoformat(), mtype, desc, cost,
                 PERFORMED_BY[cat], nxt.isoformat()))
            audit(conn, "maintenance", asset_ids[tag], "logged",
                  {"asset_tag": tag, "type": mtype, "date": d.isoformat()})
            d = nxt if nxt > d else d + timedelta(days=interval)

    # ---- assignments: (asset_tag, employee_name, assigned, expected_return, status) ----
    ASSIGNMENTS = [
        ("AST-LAP-001", "Aarav Mehta", "2026-08-01", "2027-07-31", "active"),
        ("AST-LAP-002", "Priya Sharma", "2026-07-15", "2027-07-14", "active"),
        ("AST-LAP-003", "Rahul Verma", "2026-06-10", "2027-06-09", "active"),
        ("AST-LAP-004", "Arjun Singh", "2026-09-01", "2027-08-31", "active"),
        ("AST-LAP-006", "Meera Nair", "2026-09-20", "2027-09-19", "active"),
        ("AST-PHN-001", "Vikram Rao", "2026-05-12", "2026-10-20", "active"),   # overdue
        ("AST-PHN-002", "Sanjay Patel", "2026-08-25", "2027-02-24", "active"),
        ("AST-PHN-004", "Divya Reddy", "2026-04-02", "2026-10-15", "active"),  # overdue
        ("AST-VEH-001", "Kavya Menon", "2026-03-01", "2027-02-28", "active"),
        ("AST-VEH-002", "Sanjay Patel", "2026-02-14", "2027-02-13", "active"),
        ("AST-EQP-002", "Ananya Gupta", "2026-05-05", "2027-05-04", "active"),
        ("AST-EQP-004", "Rahul Verma", "2026-01-10", "2027-01-09", "active"),
        ("AST-EQP-005", "Rahul Verma", "2026-01-10", "2027-01-09", "active"),
        # returned ones
        ("AST-LAP-005", "Karthik Nair", "2026-01-06", "2026-06-30", "returned"),
        ("AST-PHN-003", "Sneha Iyer", "2026-02-01", "2026-07-31", "returned"),
        ("AST-EQP-001", "Divya Reddy", "2026-03-10", "2026-09-30", "returned"),
        ("AST-VEH-003", "Vikram Rao", "2026-04-15", "2026-10-10", "returned"),
    ]
    for tag, emp, assigned, expected, status in ASSIGNMENTS:
        returned = None
        if status == "returned":
            returned = (date.fromisoformat(expected) - timedelta(days=random.randint(0, 12))).isoformat()
        cur = conn.execute(
            "INSERT INTO assignments (asset_id, employee_id, assigned_date,"
            " expected_return_date, returned_date, status)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (asset_ids[tag], emp_ids[emp], assigned, expected, returned, status))
        audit(conn, "assignment", cur.lastrowid, "created",
              {"asset_tag": tag, "employee": emp, "status": status})
        if status == "returned":
            cond = random.choice(["excellent", "good", "good", "fair"])
            conn.execute(
                "INSERT INTO returns (assignment_id, asset_id, employee_id,"
                " return_date, condition_on_return, notes)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (cur.lastrowid, asset_ids[tag], emp_ids[emp], returned, cond,
                 "Returned in working condition"))
            audit(conn, "return", cur.lastrowid, "created",
                  {"asset_tag": tag, "employee": emp, "condition": cond})

    conn.commit()
    counts = {t: conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
              for t in ("employees", "assets", "assignments", "returns",
                        "maintenance", "audit_log")}
    conn.close()
    print(f"seeded {DB_PATH}: {counts}")


if __name__ == "__main__":
    seed()
