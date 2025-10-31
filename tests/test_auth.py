import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from api.v1 import app

client = TestClient(app)

def test_login_and_whoami_flow():
    # login com defaults (ADMIN_USER=admin / ADMIN_PASSWORD=admin)
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin"},
    )
    assert r.status_code == 200
    tok = r.json().get("access_token")
    assert isinstance(tok, str) and len(tok) > 10

    # whoami com bearer
    r2 = client.get("/api/v1/auth/whoami", headers={"Authorization": f"Bearer {tok}"})
    assert r2.status_code == 200
    assert r2.json().get("user") == "admin"
