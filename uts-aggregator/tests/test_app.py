from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data_test"
    monkeypatch.setenv("DATA_DIR", str(data_dir))

    from src.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def test_publish_unique(client):
    res = client.post("/publish", json=[{
        "topic": "test",
        "event_id": "1",
        "timestamp": "2026-04-25T10:00:00",
        "source": "app",
        "payload": {"msg": "hello"}
    }])
    assert res.status_code == 200

    stats = client.get("/stats").json()
    assert stats["unique_processed"] == 1


def test_publish_duplicate(client):
    client.post("/publish", json=[{
        "topic": "test",
        "event_id": "dup",
        "timestamp": "2026-04-25T10:00:00",
        "source": "app",
        "payload": {"msg": "x"}
    }])

    client.post("/publish", json=[{
        "topic": "test",
        "event_id": "dup",
        "timestamp": "2026-04-25T10:00:00",
        "source": "app",
        "payload": {"msg": "x"}
    }])

    stats = client.get("/stats").json()
    assert stats["duplicate_dropped"] >= 1


def test_get_events(client):
    client.post("/publish", json=[{
        "topic": "t2",
        "event_id": "1",
        "timestamp": "2026-04-25T10:00:00",
        "source": "app",
        "payload": {"msg": "data"}
    }])

    res = client.get("/events?topic=t2")
    data = res.json()

    assert len(data) == 1
    assert isinstance(data[0]["payload"], dict)


def test_validation(client):
    res = client.post("/publish", json=[{
        "event_id": "1"
    }])

    assert res.status_code == 422


def test_stats_consistency(client):
    client.post("/publish", json={
        "topic": "s1",
        "event_id": "e1",
        "timestamp": "2026-04-25T10:00:00",
        "source": "app",
        "payload": {"msg": "ok"}
    })

    res = client.get("/stats").json()

    assert res["received"] >= res["unique_processed"]
    assert "s1" in res["topics"]


def test_topic_scoped_dedup(client):
    payload = {
        "timestamp": "2026-04-25T10:00:00",
        "source": "app",
        "payload": {"msg": "same id different topic"}
    }

    client.post("/publish", json=[
        {"topic": "t1", "event_id": "same-id", **payload},
        {"topic": "t2", "event_id": "same-id", **payload},
    ])

    stats = client.get("/stats").json()
    assert stats["unique_processed"] == 2


def test_dedup_persists_after_restart(tmp_path, monkeypatch):
    data_dir = tmp_path / "persist_data"
    monkeypatch.setenv("DATA_DIR", str(data_dir))

    from src.main import create_app

    event = {
        "topic": "persist",
        "event_id": "keep-1",
        "timestamp": "2026-04-25T10:00:00",
        "source": "app",
        "payload": {"msg": "persist"}
    }

    with TestClient(create_app()) as c1:
        c1.post("/publish", json=[event])
        stats1 = c1.get("/stats").json()
        assert stats1["unique_processed"] == 1

    with TestClient(create_app()) as c2:
        c2.post("/publish", json=[event])
        stats2 = c2.get("/stats").json()
        assert stats2["duplicate_dropped"] == 1