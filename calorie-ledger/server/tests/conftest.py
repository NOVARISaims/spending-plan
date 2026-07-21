import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Config  # noqa: E402
from app.main import create_app  # noqa: E402

PASSPHRASE = "test-passphrase-123"


@pytest.fixture()
def app(tmp_path):
    cfg = Config(data_dir=tmp_path / "data", bootstrap_passphrase=PASSPHRASE)
    return create_app(cfg, start_background=False)


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_client(client):
    r = client.post("/api/auth/login", json={"passphrase": PASSPHRASE, "label": "tests"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def sync_op(client, entity, action, payload, op_id=None):
    import uuid
    op = {
        "op_id": op_id or str(uuid.uuid4()),
        "entity": entity,
        "action": action,
        "payload": payload,
    }
    r = client.post("/api/sync/batch", json={"ops": [op]})
    assert r.status_code == 200, r.text
    return r.json()["results"][0]
