# tests/test_ml_endpoints.py
from fastapi.testclient import TestClient
from api.v1 import app

client = TestClient(app)


def test_ml_features_json_ok():
    r = client.get("/api/v1/ml/features", params={"normalized": True, "limit": 5, "format": "json"})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # Se houver linhas, valida chaves mínimas
    if data:
        row = data[0]
        for k in ("x_rating", "x_availability", "x_category_idx", "x_title_len"):
            assert k in row


def test_ml_training_data_csv_ok():
    r = client.get("/api/v1/ml/training-data", params={"normalized": True, "limit": 10, "format": "csv"})
    assert r.status_code == 200
    # content-type do Starlette pode vir como text/csv; charset é opcional
    assert "text/csv" in r.headers.get("content-type", "").lower()
    # Deve conter o cabeçalho com as colunas usadas
    text = r.text.splitlines()
    assert len(text) >= 1
    header = text[0]
    for col in ("x_rating", "x_availability", "x_category_idx", "x_title_len", "price"):
        assert col in header


def test_ml_predictions_mock_ok():
    payload = {
        "normalized": True,
        "items": [
            {"rating": 4, "availability": 12, "category": "Travel", "title": "A Fun Journey"},
            {"rating": 5, "availability": 3, "category": "History", "title": "Ancient Worlds"},
        ],
    }
    r = client.post("/api/v1/ml/predictions", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert "model" in body and "predictions" in body
    preds = body["predictions"]
    assert isinstance(preds, list) and len(preds) == 2
    p0 = preds[0]
    assert "predicted_price" in p0 and isinstance(p0["predicted_price"], (int, float))
    # features retornadas por item
    for k in ("x_rating", "x_availability", "x_category_idx", "x_title_len"):
        assert k in p0["features"]
