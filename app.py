import os
import sqlite3
from pathlib import Path

from flask import Flask, abort, g, jsonify, request

app = Flask(__name__)
DATABASE_PATH = os.environ.get("DATABASE_PATH", "/data/seal-log.db")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.cli.command("init-db")
def init_db():
    db = get_db()
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    db.executescript(schema)
    with db:
        db.executemany(
            """INSERT INTO tenants (id, name, plan, object_limit, api_token)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO NOTHING""",
            [
                ("A", "Office A", "Basic", 5, "demo-token-a"),
                ("B", "Office B", "Pro", 20, "demo-token-b"),
            ],
        )
    print("Database ready. Office A: Basic 5. Office B: Pro 20.")


@app.before_request
def authenticate():
    if request.endpoint == "health":
        return None

    parts = request.headers.get("Authorization", "").split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return jsonify(error="Unauthorized"), 401

    g.tenant = get_db().execute(
        "SELECT id, name, plan, object_limit FROM tenants WHERE api_token = ?",
        (parts[1],),
    ).fetchone()
    if g.tenant is None:
        return jsonify(error="Unauthorized"), 401


@app.errorhandler(404)
def not_found(error):
    return jsonify(error="Not found"), 404


@app.get("/health")
def health():
    return jsonify(service="Seal Log", status="ok")


@app.get("/me")
def me():
    result = dict(g.tenant)
    result["objects_used"] = get_db().execute(
        "SELECT COUNT(*) FROM objects WHERE tenant_id = ?",
        (g.tenant["id"],),
    ).fetchone()[0]
    return jsonify(result)


def tenant_object(object_id):
    row = get_db().execute(
        "SELECT * FROM objects WHERE id = ? AND tenant_id = ?",
        (object_id, g.tenant["id"]),
    ).fetchone()
    if row is None:
        abort(404)
    return row


def object_view(row):
    result = dict(row)
    seal = get_db().execute(
        """SELECT id, number, installed_at FROM seals
           WHERE object_id = ? AND tenant_id = ? AND removed_at IS NULL""",
        (row["id"], g.tenant["id"]),
    ).fetchone()
    result["current_seal"] = dict(seal) if seal is not None else None
    return result


@app.get("/objects")
def list_objects():
    rows = get_db().execute(
        "SELECT * FROM objects WHERE tenant_id = ? ORDER BY id",
        (g.tenant["id"],),
    ).fetchall()
    return jsonify(objects=[object_view(row) for row in rows])


@app.get("/objects/<int:object_id>")
def get_object(object_id):
    return jsonify(object_view(tenant_object(object_id)))


@app.post("/objects")
def create_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="A JSON object is required."), 400

    for field in ("name", "location", "seal_number"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            return jsonify(error=f"Field '{field}' is required."), 400
        if len(value) > 200:
            return jsonify(error=f"Field '{field}' is too long."), 400
        data[field] = value.strip()

    db = get_db()
    with db:
        db.execute("BEGIN IMMEDIATE")
        count = db.execute(
            "SELECT COUNT(*) FROM objects WHERE tenant_id = ?",
            (g.tenant["id"],),
        ).fetchone()[0]
        if count >= g.tenant["object_limit"]:
            limit = g.tenant["object_limit"]
            return jsonify(error=f"Object limit reached ({limit})."), 403

        cursor = db.execute(
            "INSERT INTO objects (tenant_id, name, location) VALUES (?, ?, ?)",
            (g.tenant["id"], data["name"], data["location"]),
        )
        object_id = cursor.lastrowid
        db.execute(
            "INSERT INTO seals (tenant_id, object_id, number) VALUES (?, ?, ?)",
            (g.tenant["id"], object_id, data["seal_number"]),
        )

    return jsonify(object_view(tenant_object(object_id))), 201


def current_seal(object_id):
    return get_db().execute(
        """SELECT * FROM seals
           WHERE object_id = ? AND tenant_id = ? AND removed_at IS NULL""",
        (object_id, g.tenant["id"]),
    ).fetchone()


@app.post("/objects/<int:object_id>/inspections")
def add_inspection(object_id):
    tenant_object(object_id)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="A JSON object is required."), 400

    result = data.get("result")
    if result not in ("intact", "broken", "missing"):
        return jsonify(error="Result must be intact, broken or missing."), 400

    note = data.get("note", "")
    if not isinstance(note, str) or len(note) > 1000:
        return jsonify(error="Note must be text up to 1000 characters."), 400

    db = get_db()
    with db:
        db.execute("BEGIN IMMEDIATE")
        seal = current_seal(object_id)
        if seal is None:
            return jsonify(error="Object has no current seal."), 409

        cursor = db.execute(
            """INSERT INTO inspections (tenant_id, seal_id, result, note)
               VALUES (?, ?, ?, ?)""",
            (g.tenant["id"], seal["id"], result, note.strip()),
        )
        row = db.execute(
            "SELECT * FROM inspections WHERE id = ? AND tenant_id = ?",
            (cursor.lastrowid, g.tenant["id"]),
        ).fetchone()

    return jsonify(dict(row)), 201


@app.post("/objects/<int:object_id>/seals")
def replace_seal(object_id):
    tenant_object(object_id)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="A JSON object is required."), 400

    number = data.get("seal_number")
    if not isinstance(number, str) or not number.strip() or len(number) > 200:
        return jsonify(error="Seal number must be text from 1 to 200 characters."), 400
    number = number.strip()

    db = get_db()
    with db:
        db.execute("BEGIN IMMEDIATE")
        seal = current_seal(object_id)
        if seal is None:
            return jsonify(error="Object has no current seal."), 409
        if number == seal["number"]:
            return jsonify(error="New seal number must be different."), 400

        db.execute(
            """UPDATE seals SET removed_at = CURRENT_TIMESTAMP
               WHERE id = ? AND tenant_id = ? AND object_id = ?
               AND removed_at IS NULL""",
            (seal["id"], g.tenant["id"], object_id),
        )
        cursor = db.execute(
            "INSERT INTO seals (tenant_id, object_id, number) VALUES (?, ?, ?)",
            (g.tenant["id"], object_id, number),
        )
        row = db.execute(
            "SELECT * FROM seals WHERE id = ? AND tenant_id = ?",
            (cursor.lastrowid, g.tenant["id"]),
        ).fetchone()

    return jsonify(dict(row)), 201


@app.get("/objects/<int:object_id>/history")
def object_history(object_id):
    db = get_db()
    with db:
        db.execute("BEGIN")
        obj = tenant_object(object_id)
        seals = db.execute(
            """SELECT * FROM seals WHERE object_id = ? AND tenant_id = ?
               ORDER BY id""",
            (object_id, g.tenant["id"]),
        ).fetchall()

        history = []
        for seal in seals:
            entry = dict(seal)
            inspections = db.execute(
                """SELECT * FROM inspections WHERE seal_id = ? AND tenant_id = ?
                   ORDER BY id""",
                (seal["id"], g.tenant["id"]),
            ).fetchall()
            entry["inspections"] = [dict(row) for row in inspections]
            history.append(entry)

    return jsonify(object=dict(obj), seals=history)
