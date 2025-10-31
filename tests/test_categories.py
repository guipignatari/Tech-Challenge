import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from api.v1 import app

client = TestClient(app)

def test_categories_endpoint_ok():
    r = client.get("/api/v1/categories")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    # se houver categorias, todas devem ser strings
    for c in body:
        assert isinstance(c, str)
