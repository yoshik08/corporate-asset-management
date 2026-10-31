"""Corporate Asset Management System — Flask backend.

Run:  python app.py        (auto-creates + seeds the DB on first run)
Then open http://127.0.0.1:5000

API (all JSON):
  GET    /api/stats
  GET    /api/assets?category=&status=&q=     POST /api/assets
  GET    /api/assets/<id>  PUT /api/assets/<id>  DELETE /api/assets/<id>
  GET    /api/employees    POST /api/employees
  PUT    /api/employees/<id>  DELETE /api/employees/<id>
  GET    /api/assignments?status=   POST /api/assignments  (assign)
  POST   /api/assignments/<id>/return
  GET    /api/returns
  GET    /api/maintenance?asset_id=  POST /api/maintenance
  GET    /api/predictions
  GET    /api/audit?entity_type=&limit=

Every change is written to audit_log in the same transaction.
"""
import os
import time
from datetime import date

from flask import Flask, jsonify, request, send_from_directory

import db as dbmod
import predictor
import seed

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "public")

app = Flask(__name__, static_folder=STATIC_DIR)

if dbmod.ON_VERCEL and not dbmod.db_exists():
    # First request on a fresh serverless instance: build a seeded demo
    # database in /tmp. A lock file keeps concurrent cold starts from
    # seeding over each other.
    lock = "/tmp/.asset-seed.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        seed.seed()
    except FileExistsError:
        for _ in range(50):
            if dbmod.db_exists():
                break
            time.sleep(0.2)


# ---------------------------------------------------------------- helpers
def err(message, code=400):
    return jsonify({"error": message}), code


def asset_dict(row):
    d = dbmod.row_to_dict(row)
    if d:
        d["assigned_to"] = None
        return d
    return d


def _today():
    return date.today().isoformat()


def _overdue(a):
    return (a["status"] == "active" and a["expected_return_date"]
            and a["expected_return_date"] < _today())


# ---------------------------------------------------------------- pages
@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


# ---------------------------------------------------------------- stats
@app.route("/api/stats")
def stats():
    conn = dbmod.get_connection()
    total = conn.execute("SELECT COUNT(*) c FROM assets").fetchone()["c"]
    by_status = dict(conn.execute(
        "SELECT status, COUNT(*) c FROM assets GROUP BY status").fetchall())
    employees = conn.execute("SELECT COUNT(*) c FROM employees").fetchone()["c"]
    active = conn.execute(
        "SELECT COUNT(*) c FROM assignments WHERE status='active'").fetchone()["c"]
    overdue = conn.execute(
        "SELECT COUNT(*) c FROM assignments WHERE status='active'"
        " AND expected_return_date IS NOT NULL AND expected_return_date < ?",
        (_today(),)).fetchone()["c"]
    maint_cost = conn.execute(
        "SELECT COALESCE(SUM(cost), 0) c FROM maintenance").fetchone()["c"]
    preds, _info = predictor.predict_all(conn)
    due_soon = sum(1 for p in preds if p["risk_level"] == "high")
    conn.close()
    return jsonify({
        "total_assets": total,
        "available": by_status.get("available", 0),
        "assigned": by_status.get("assigned", 0),
        "in_maintenance": by_status.get("in_maintenance", 0),
        "retired": by_status.get("retired", 0),
        "total_employees": employees,
        "active_assignments": active,
        "overdue_returns": overdue,
        "total_maintenance_cost": round(maint_cost, 2),
        "maintenance_due_soon": due_soon,
    })


# ---------------------------------------------------------------- assets
@app.route("/api/assets", methods=["GET"])
def list_assets():
    conn = dbmod.get_connection()
    q = request.args.get("q", "").strip()
    cat = request.args.get("category", "")
    status = request.args.get("status", "")
    sql = "SELECT * FROM assets WHERE 1=1"
    params = []
    if cat:
        sql += " AND category = ?"
        params.append(cat)
    if status:
        sql += " AND status = ?"
        params.append(status)
    if q:
        sql += " AND (name LIKE ? OR asset_tag LIKE ? OR brand LIKE ? OR serial_no LIKE ?)"
        params += [f"%{q}%"] * 4
    sql += " ORDER BY id"
    rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        holder = conn.execute(
            "SELECT e.name FROM assignments a JOIN employees e ON e.id = a.employee_id"
            " WHERE a.asset_id = ? AND a.status = 'active' LIMIT 1",
            (d["id"],)).fetchone()
        d["assigned_to"] = holder["name"] if holder else None
        out.append(d)
    conn.close()
    return jsonify(out)


@app.route("/api/assets", methods=["POST"])
def create_asset():
    data = request.get_json(force=True)
    for f in ("asset_tag", "name", "category", "purchase_date"):
        if not data.get(f):
            return err(f"missing required field: {f}")
    if data["category"] not in ("laptop", "phone", "vehicle", "equipment"):
        return err("category must be laptop, phone, vehicle or equipment")
    conn = dbmod.get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO assets (asset_tag, name, category, brand, model, serial_no,"
            " purchase_date, purchase_cost, status, location, usage_hours, condition, notes)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (data["asset_tag"], data["name"], data["category"],
             data.get("brand"), data.get("model"), data.get("serial_no"),
             data["purchase_date"], data.get("purchase_cost", 0),
             data.get("status", "available"), data.get("location"),
             data.get("usage_hours", 0), data.get("condition", "good"),
             data.get("notes")))
        dbmod.audit(conn, "asset", cur.lastrowid, "created",
                    {"asset_tag": data["asset_tag"], "name": data["name"]})
        conn.commit()
        row = conn.execute("SELECT * FROM assets WHERE id = ?",
                           (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201
    except Exception as e:
        conn.rollback()
        return err(str(e))
    finally:
        conn.close()


@app.route("/api/assets/<int:asset_id>", methods=["GET", "PUT", "DELETE"])
def asset_detail(asset_id):
    conn = dbmod.get_connection()
    row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if not row:
        conn.close()
        return err("asset not found", 404)
    if request.method == "GET":
        d = dict(row)
        holder = conn.execute(
            "SELECT e.name FROM assignments a JOIN employees e ON e.id = a.employee_id"
            " WHERE a.asset_id = ? AND a.status = 'active' LIMIT 1",
            (asset_id,)).fetchone()
        d["assigned_to"] = holder["name"] if holder else None
        conn.close()
        return jsonify(d)
    if request.method == "DELETE":
        active = conn.execute(
            "SELECT COUNT(*) c FROM assignments WHERE asset_id = ? AND status='active'",
            (asset_id,)).fetchone()["c"]
        if active:
            conn.close()
            return err("cannot delete an asset that is currently assigned")
        conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
        dbmod.audit(conn, "asset", asset_id, "deleted",
                    {"asset_tag": row["asset_tag"]})
        conn.commit()
        conn.close()
        return jsonify({"deleted": asset_id})
    # PUT
    data = request.get_json(force=True)
    allowed = ("name", "category", "brand", "model", "serial_no", "purchase_date",
               "purchase_cost", "status", "location", "usage_hours", "condition", "notes")
    sets, params = [], []
    for f in allowed:
        if f in data:
            sets.append(f"{f} = ?")
            params.append(data[f])
    if not sets:
        conn.close()
        return err("nothing to update")
    params.append(asset_id)
    try:
        conn.execute(f"UPDATE assets SET {', '.join(sets)} WHERE id = ?", params)
        dbmod.audit(conn, "asset", asset_id, "updated",
                    {"asset_tag": row["asset_tag"], "changes": data})
        conn.commit()
        row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        return jsonify(dict(row))
    except Exception as e:
        conn.rollback()
        return err(str(e))
    finally:
        conn.close()


# ---------------------------------------------------------------- employees
@app.route("/api/employees", methods=["GET", "POST"])
def employees():
    conn = dbmod.get_connection()
    if request.method == "GET":
        rows = conn.execute("SELECT * FROM employees ORDER BY name").fetchall()
        conn.close()
        return jsonify(dbmod.rows_to_dicts(rows))
    data = request.get_json(force=True)
    for f in ("name", "email", "department", "joined_date"):
        if not data.get(f):
            conn.close()
            return err(f"missing required field: {f}")
    try:
        cur = conn.execute(
            "INSERT INTO employees (name, email, department, role, phone, joined_date)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (data["name"], data["email"], data["department"], data.get("role"),
             data.get("phone"), data["joined_date"]))
        dbmod.audit(conn, "employee", cur.lastrowid, "created",
                    {"name": data["name"], "department": data["department"]})
        conn.commit()
        row = conn.execute("SELECT * FROM employees WHERE id = ?",
                           (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201
    except Exception as e:
        conn.rollback()
        return err(str(e))
    finally:
        conn.close()


@app.route("/api/employees/<int:emp_id>", methods=["PUT", "DELETE"])
def employee_detail(emp_id):
    conn = dbmod.get_connection()
    row = conn.execute("SELECT * FROM employees WHERE id = ?", (emp_id,)).fetchone()
    if not row:
        conn.close()
        return err("employee not found", 404)
    if request.method == "DELETE":
        active = conn.execute(
            "SELECT COUNT(*) c FROM assignments WHERE employee_id = ? AND status='active'",
            (emp_id,)).fetchone()["c"]
        if active:
            conn.close()
            return err("cannot delete an employee with active assignments")
        conn.execute("DELETE FROM employees WHERE id = ?", (emp_id,))
        dbmod.audit(conn, "employee", emp_id, "deleted", {"name": row["name"]})
        conn.commit()
        conn.close()
        return jsonify({"deleted": emp_id})
    data = request.get_json(force=True)
    allowed = ("name", "email", "department", "role", "phone", "joined_date")
    sets, params = [], []
    for f in allowed:
        if f in data:
            sets.append(f"{f} = ?")
            params.append(data[f])
    if not sets:
        conn.close()
        return err("nothing to update")
    params.append(emp_id)
    try:
        conn.execute(f"UPDATE employees SET {', '.join(sets)} WHERE id = ?", params)
        dbmod.audit(conn, "employee", emp_id, "updated", {"changes": data})
        conn.commit()
        row = conn.execute("SELECT * FROM employees WHERE id = ?", (emp_id,)).fetchone()
        return jsonify(dict(row))
    except Exception as e:
        conn.rollback()
        return err(str(e))
    finally:
        conn.close()


# ---------------------------------------------------------------- assignments & returns
@app.route("/api/assignments", methods=["GET", "POST"])
def assignments():
    conn = dbmod.get_connection()
    if request.method == "GET":
        status = request.args.get("status", "")
        sql = ("SELECT a.*, ast.asset_tag, ast.name AS asset_name, ast.category,"
               " e.name AS employee_name FROM assignments a"
               " JOIN assets ast ON ast.id = a.asset_id"
               " JOIN employees e ON e.id = a.employee_id WHERE 1=1")
        params = []
        if status == "overdue":
            sql += (" AND a.status = 'active' AND a.expected_return_date IS NOT NULL"
                    " AND a.expected_return_date < ?")
            params.append(_today())
        elif status:
            sql += " AND a.status = ?"
            params.append(status)
        sql += " ORDER BY a.id DESC"
        rows = conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["overdue"] = _overdue(d)
            out.append(d)
        conn.close()
        return jsonify(out)
    data = request.get_json(force=True)
    for f in ("asset_id", "employee_id", "assigned_date"):
        if not data.get(f):
            conn.close()
            return err(f"missing required field: {f}")
    asset = conn.execute("SELECT * FROM assets WHERE id = ?",
                         (data["asset_id"],)).fetchone()
    if not asset:
        conn.close()
        return err("asset not found", 404)
    if asset["status"] != "available":
        conn.close()
        return err(f"asset is {asset['status']}, only available assets can be assigned")
    emp = conn.execute("SELECT * FROM employees WHERE id = ?",
                       (data["employee_id"],)).fetchone()
    if not emp:
        conn.close()
        return err("employee not found", 404)
    try:
        cur = conn.execute(
            "INSERT INTO assignments (asset_id, employee_id, assigned_date,"
            " expected_return_date, notes) VALUES (?, ?, ?, ?, ?)",
            (data["asset_id"], data["employee_id"], data["assigned_date"],
             data.get("expected_return_date"), data.get("notes")))
        conn.execute("UPDATE assets SET status = 'assigned' WHERE id = ?",
                     (data["asset_id"],))
        dbmod.audit(conn, "assignment", cur.lastrowid, "created",
                    {"asset_tag": asset["asset_tag"], "employee": emp["name"]})
        conn.commit()
        row = conn.execute("SELECT * FROM assignments WHERE id = ?",
                           (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201
    except Exception as e:
        conn.rollback()
        return err(str(e))
    finally:
        conn.close()


@app.route("/api/assignments/<int:assignment_id>/return", methods=["POST"])
def return_assignment(assignment_id):
    conn = dbmod.get_connection()
    a = conn.execute(
        "SELECT a.*, ast.asset_tag, e.name AS employee_name FROM assignments a"
        " JOIN assets ast ON ast.id = a.asset_id"
        " JOIN employees e ON e.id = a.employee_id WHERE a.id = ?",
        (assignment_id,)).fetchone()
    if not a:
        conn.close()
        return err("assignment not found", 404)
    if a["status"] != "active":
        conn.close()
        return err("assignment is already returned")
    data = request.get_json(force=True, silent=True) or {}
    condition = data.get("condition_on_return", "good")
    if condition not in ("excellent", "good", "fair", "poor", "damaged"):
        conn.close()
        return err("invalid condition_on_return")
    today = _today()
    try:
        conn.execute(
            "INSERT INTO returns (assignment_id, asset_id, employee_id, return_date,"
            " condition_on_return, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (assignment_id, a["asset_id"], a["employee_id"], today, condition,
             data.get("notes")))
        conn.execute(
            "UPDATE assignments SET status = 'returned', returned_date = ? WHERE id = ?",
            (today, assignment_id))
        new_status = "in_maintenance" if condition in ("poor", "damaged") else "available"
        conn.execute(
            "UPDATE assets SET status = ?, condition = ? WHERE id = ?",
            (new_status, "poor" if condition == "damaged" else condition, a["asset_id"]))
        dbmod.audit(conn, "return", assignment_id, "created",
                    {"asset_tag": a["asset_tag"], "employee": a["employee_name"],
                     "condition": condition})
        conn.commit()
        return jsonify({"returned": assignment_id, "asset_status": new_status})
    except Exception as e:
        conn.rollback()
        return err(str(e))
    finally:
        conn.close()


@app.route("/api/returns", methods=["GET"])
def list_returns():
    conn = dbmod.get_connection()
    rows = conn.execute(
        "SELECT r.*, ast.asset_tag, ast.name AS asset_name, e.name AS employee_name"
        " FROM returns r JOIN assets ast ON ast.id = r.asset_id"
        " JOIN employees e ON e.id = r.employee_id ORDER BY r.id DESC").fetchall()
    conn.close()
    return jsonify(dbmod.rows_to_dicts(rows))


# ---------------------------------------------------------------- maintenance
@app.route("/api/maintenance", methods=["GET", "POST"])
def maintenance():
    conn = dbmod.get_connection()
    if request.method == "GET":
        asset_id = request.args.get("asset_id", "")
        sql = ("SELECT m.*, ast.asset_tag, ast.name AS asset_name FROM maintenance m"
               " JOIN assets ast ON ast.id = m.asset_id WHERE 1=1")
        params = []
        if asset_id:
            sql += " AND m.asset_id = ?"
            params.append(asset_id)
        sql += " ORDER BY m.maintenance_date DESC, m.id DESC"
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return jsonify(dbmod.rows_to_dicts(rows))
    data = request.get_json(force=True)
    for f in ("asset_id", "maintenance_date", "maintenance_type", "description"):
        if not data.get(f):
            conn.close()
            return err(f"missing required field: {f}")
    asset = conn.execute("SELECT * FROM assets WHERE id = ?",
                         (data["asset_id"],)).fetchone()
    if not asset:
        conn.close()
        return err("asset not found", 404)
    try:
        cur = conn.execute(
            "INSERT INTO maintenance (asset_id, maintenance_date, maintenance_type,"
            " description, cost, performed_by, next_due_date)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (data["asset_id"], data["maintenance_date"], data["maintenance_type"],
             data["description"], data.get("cost", 0), data.get("performed_by"),
             data.get("next_due_date")))
        if asset["status"] == "in_maintenance":
            conn.execute("UPDATE assets SET status = 'available' WHERE id = ?",
                         (data["asset_id"],))
        dbmod.audit(conn, "maintenance", cur.lastrowid, "logged",
                    {"asset_tag": asset["asset_tag"], "type": data["maintenance_type"]})
        conn.commit()
        row = conn.execute("SELECT * FROM maintenance WHERE id = ?",
                           (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201
    except Exception as e:
        conn.rollback()
        return err(str(e))
    finally:
        conn.close()


# ---------------------------------------------------------------- predictions & audit
@app.route("/api/predictions")
def predictions():
    conn = dbmod.get_connection()
    preds, info = predictor.predict_all(conn)
    conn.close()
    return jsonify({"predictions": preds, "model": info})


@app.route("/api/audit")
def audit_log():
    conn = dbmod.get_connection()
    entity = request.args.get("entity_type", "")
    limit = min(int(request.args.get("limit", 100)), 500)
    sql = "SELECT * FROM audit_log WHERE 1=1"
    params = []
    if entity:
        sql += " AND entity_type = ?"
        params.append(entity)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return jsonify(dbmod.rows_to_dicts(rows))


if __name__ == "__main__":
    if not dbmod.db_exists():
        print("database not found, creating + seeding demo data ...")
        seed.seed()
    app.run(host="127.0.0.1", port=5000, debug=True)
