import json
import os
import socket
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
HTTP = build_opener(ProxyHandler({}))


def call(method, path, tenant, data=None, expected=200):
    headers = {"Authorization": f"Bearer demo-token-{tenant.lower()}"}
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")
    print(f"\nREQUEST {method} {BASE_URL}{path}")
    for name, value in headers.items():
        print(f"{name}: {value}")
    if body is not None:
        print(body.decode("utf-8"))
    req = Request(BASE_URL + path, data=body, headers=headers, method=method)
    try:
        response = HTTP.open(req, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        status = response.getcode()
        text = response.read().decode("utf-8")
        print(f"RESPONSE HTTP {status}")
        print(str(response.headers).strip())
        print(text)
    assert status == expected, f"{method} {path}: expected {expected}, got {status}"
    return json.loads(text)


def create(tenant, number):
    return call("POST", "/objects", tenant, {
        "name": f"Cabinet {tenant}{number}",
        "location": f"Room {tenant}",
        "seal_number": f"{tenant}{number:03d}",
    }, expected=201)


def normal_use():
    for tenant in ("A", "B"):
        obj = create(tenant, 1)
        path = f"/objects/{obj['id']}"
        inspection = call("POST", path + "/inspections", tenant,
                          {"result": "intact", "note": "Regular check."}, 201)
        replacement = call("POST", path + "/seals", tenant,
                           {"seal_number": f"{tenant}002"}, 201)
        current = call("GET", path, tenant)
        history = call("GET", path + "/history", tenant)
        assert current["tenant_id"] == tenant
        assert current["current_seal"]["number"] == f"{tenant}002"
        old, new = history["seals"]
        assert old["id"] == obj["current_seal"]["id"]
        assert old["removed_at"] is not None
        assert old["inspections"] == [inspection]
        assert new["id"] == replacement["id"]
        assert new["removed_at"] is None
    for tenant in ("A", "B"):
        objects = call("GET", "/objects", tenant)["objects"]
        assert len(objects) == 1 and objects[0]["tenant_id"] == tenant
    return "A and B complete the workflow", "Both completed it; own lists and history verified"


def tenant_isolation():
    obj = create("B", 1)
    path = f"/objects/{obj['id']}"
    call("POST", path + "/inspections", "B", {"result": "intact"}, 201)
    before = call("GET", path, "B")
    history_before = call("GET", path + "/history", "B")
    assert call("GET", path, "A", expected=404) == {"error": "Not found"}
    call("GET", path + "/history", "A", expected=404)
    call("POST", path + "/inspections", "A", {"result": "missing"}, 404)
    call("POST", path + "/seals", "A", {"seal_number": "BAD001"}, 404)
    assert call("GET", path, "B") == before
    assert call("GET", path + "/history", "B") == history_before
    return "A is rejected; B data stays intact", "All 4 A requests return 404; B record and history unchanged"


def plan_limit():
    for tenant in ("A", "B"):
        for number in range(1, 6):
            create(tenant, number)
    rejected = call("POST", "/objects", "A", {
        "name": "Cabinet A6", "location": "Room A", "seal_number": "A006"
    }, 403)
    assert rejected["error"] == "Object limit reached (5)."
    a = call("GET", "/me", "A")
    a_objects = call("GET", "/objects", "A")["objects"]
    assert a["objects_used"] == 5 and len(a_objects) == 5
    created_b = create("B", 6)
    b = call("GET", "/me", "B")
    b_objects = call("GET", "/objects", "B")["objects"]
    assert created_b["tenant_id"] == "B"
    assert b["objects_used"] == 6 and len(b_objects) == 6
    return "A sixth fails; B sixth succeeds", f"A: 403 and {len(a_objects)} objects; B: 201 and {len(b_objects)} objects"


checks = {"normal": normal_use, "isolation": tenant_isolation, "limit": plan_limit}
name = sys.argv[1]
print("UTC time:", datetime.now(timezone.utc).isoformat())
print("Container hostname:", socket.gethostname())
print("Check:", name)
for attempt in range(25):
    try:
        with HTTP.open(BASE_URL + "/health", timeout=1) as response:
            if response.status == 200:
                break
    except (URLError, OSError):
        pass
    time.sleep(0.2)
else:
    raise RuntimeError("Application did not become ready")
for tenant, limit in (("A", 5), ("B", 20)):
    info = call("GET", "/me", tenant)
    assert info["id"] == tenant and info["object_limit"] == limit
    assert info["objects_used"] == 0, "Each check needs a fresh database"
expected, actual = checks[name]()
print(f"RESULT: | {name} | {expected} | {actual} | PASS |")
